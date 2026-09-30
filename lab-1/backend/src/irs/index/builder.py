"""Index construction: documents → dictionary → inverted index → term weights.

Two implementations of the same arithmetic coexist here on purpose.

:mod:`irs.index.weights` holds the formulas as pure Python, verified against values
computed by hand (``tests/unit/test_weights.py``). It is the reference: readable, and
the thing the report points at to show the vector model was implemented rather than
imported.

This module additionally computes the weights **set-based in SQL** for a full rebuild.
The reason is that every weight depends on `N`: adding one document changes `B_i` for
every term, and therefore `w_dk` for every posting in the collection. Streaming hundreds
of thousands of postings through Python to multiply each by a constant is pointless when
the database can do it in five statements. ``tests/integration/test_index_builder.py``
asserts the SQL path agrees with the Python reference to within floating-point
tolerance, so the optimisation cannot silently diverge from the specification.

Rebuild is therefore the default operation, and it is idempotent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import ARRAY, String, any_, delete, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import CollectionStat, Document, Posting, Term
from irs.logging import Stopwatch, get_logger
from irs.nlp.pipeline import analyzer, compose_document_text

log = get_logger("irs.index")

#: Documents analysed per batch. Bounded so that a large collection does not have every
#: document's token stream resident at once.
ANALYZE_BATCH = 64

#: asyncpg refuses a statement with more than 32767 bound parameters; multi-row inserts
#: are cut so no statement approaches it.
MAX_BIND_PARAMETERS = 30_000


def _chunks(rows: list[dict[str, object]], params_per_row: int) -> list[list[dict[str, object]]]:
    """Split ``rows`` so each chunk binds at most :data:`MAX_BIND_PARAMETERS` values."""
    size = max(1, MAX_BIND_PARAMETERS // params_per_row)
    return [rows[start : start + size] for start in range(0, len(rows), size)]


@dataclass(slots=True)
class IndexStats:
    """Outcome of an index build."""

    document_count: int
    term_count: int
    posting_count: int
    average_document_length: float
    index_version: int
    log_base: str
    duration_ms: float
    embedded_document_count: int = 0

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "document_count": self.document_count,
            "term_count": self.term_count,
            "posting_count": self.posting_count,
            "average_document_length": round(self.average_document_length, 3),
            "index_version": self.index_version,
            "log_base": self.log_base,
            "duration_ms": round(self.duration_ms, 2),
        }


class IndexBuilder:
    """Builds and maintains the inverted index."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ public ----

    async def rebuild(self, reanalyze: bool = True) -> IndexStats:
        """Rebuild the whole index.

        Args:
            reanalyze: when ``False``, existing postings' raw term frequencies are kept
                and only the weights are recomputed. That is the fast path after the
                collection size changes but no document text did — which is what happens
                when documents are deleted.

        The order matters: raw counts must exist before document frequencies can be
        counted, `N` must be known before any IDF, and every `weight_raw` must be final
        before the per-document normalisation denominator is summed.
        """
        watch = Stopwatch()
        log.info("index_rebuild_started", reanalyze=reanalyze)

        if reanalyze:
            analyzed = await self._analyze_all()
            watch.lap("analyze")
            log.info("index_documents_analyzed", documents=analyzed)

        await self._update_document_frequencies()
        watch.lap("document_frequencies")

        document_count = await self._count_documents()
        await self._update_inverse_frequencies(document_count)
        watch.lap("inverse_frequencies")

        await self._update_raw_weights()
        watch.lap("raw_weights")

        await self._update_normalized_weights()
        watch.lap("normalized_weights")

        await self._prune_orphan_terms()
        watch.lap("prune")

        stats = await self._commit_stats(watch.total_ms)
        watch.lap("stats")

        log.info(
            "index_rebuild_finished",
            **stats.as_dict(),
            stages_ms=watch.stages,
        )
        return stats

    async def embed_pending(self, batch_size: int | None = None) -> int:
        """Compute embeddings for documents that do not have one yet.

        Kept separate from the term index for two reasons: embeddings do not depend on
        `N`, so they survive a reweighting untouched, and encoding is by far the slowest
        part of indexing — making it resumable means an interrupted run does not have to
        start over.

        Returns:
            The number of documents embedded.
        """
        if not settings.semantic.enabled:
            log.info("embedding_skipped", reason="semantic ranker disabled")
            return 0

        from irs.nlp.embeddings import embedder

        batch_size = batch_size or settings.semantic.batch_size
        embedded = 0

        while True:
            rows = (
                await self.session.execute(
                    select(Document.id, Document.title, Document.text)
                    .where(Document.embedding.is_(None))
                    .order_by(Document.id)
                    .limit(batch_size)
                )
            ).all()
            if not rows:
                break

            heads = [
                f"{row.title}. {row.text}"[: settings.semantic.max_chars].strip() for row in rows
            ]
            vectors = await embedder.embed(heads)

            for row, vector in zip(rows, vectors, strict=True):
                await self.session.execute(
                    update(Document).where(Document.id == row.id).values(embedding=vector)
                )

            embedded += len(rows)
            await self.session.commit()
            log.info("embedding_batch", embedded=embedded)

        if embedded:
            log.info("embedding_finished", documents=embedded, model=embedder.model_name)
        return embedded

    async def index_document(self, document: Document) -> int:
        """Analyse one document and write its postings, without reweighting.

        Backs the assignment's ``Document.AddDocumentToBase``. The weights it writes are
        correct only for the current `N`; a caller adding documents in bulk should run
        :meth:`rebuild` with ``reanalyze=False`` afterwards. The crawler does exactly
        that at the end of a job rather than after each page.

        Returns:
            The number of distinct index terms written.
        """
        # spaCy is synchronous and CPU-bound. Left on the event loop it blocks every
        # other coroutine in the process — which in the crawl worker means the task
        # queue's Redis connection stops being read, the broker decides the worker is
        # dead, and it is killed mid-crawl. Off-loading to a thread keeps the loop free.
        image = await asyncio.to_thread(analyzer.analyze_document, document.title, document.text)
        await self._write_postings({document.id: image.frequencies()}, {document.id: image})
        return image.distinct_term_count

    # ----------------------------------------------------------------- analysis ----

    async def _analyze_all(self) -> int:
        """Re-analyse every document, replacing all postings.

        Postings are deleted wholesale rather than diffed: a full re-analysis after a
        tokeniser or stop-list change must not leave terms behind that the current
        pipeline would no longer produce.
        """
        await self.session.execute(delete(Posting))

        total = 0
        offset = 0
        while True:
            rows = (
                await self.session.execute(
                    select(Document.id, Document.title, Document.text)
                    .order_by(Document.id)
                    .offset(offset)
                    .limit(ANALYZE_BATCH)
                )
            ).all()
            if not rows:
                break

            ids = [row.id for row in rows]
            texts = [compose_document_text(row.title, row.text) for row in rows]
            # `texts` is passed as an argument rather than captured, so the closure
            # cannot observe a later iteration's value.
            analyzed = await asyncio.to_thread(
                lambda batch: list(analyzer.analyze_many(batch, batch_size=ANALYZE_BATCH)),
                texts,
            )
            images = dict(zip(ids, analyzed, strict=True))

            await self._write_postings(
                {doc_id: image.frequencies() for doc_id, image in images.items()}, images
            )

            total += len(rows)
            offset += ANALYZE_BATCH
            log.debug("index_batch_analyzed", documents=total)

        return total

    async def _write_postings(
        self,
        frequencies_by_document: dict[int, dict[str, int]],
        images: dict[int, object],
    ) -> None:
        """Upsert the dictionary entries, then insert this batch's postings."""
        lemmas: dict[str, str | None] = {}
        for doc_id, frequencies in frequencies_by_document.items():
            image = images[doc_id]
            for lemma in frequencies:
                occurrence = image.terms[lemma]  # type: ignore[attr-defined]
                lemmas.setdefault(lemma, occurrence.pos)

        if not lemmas:
            return

        # The batch's vocabulary in as few statements as asyncpg allows (it caps a single
        # statement at 32767 bound parameters). `ON CONFLICT DO NOTHING` makes this safe
        # to run concurrently from several crawl workers.
        term_rows: list[dict[str, object]] = [
            {"lemma": lemma, "pos": pos} for lemma, pos in lemmas.items()
        ]
        for chunk in _chunks(term_rows, params_per_row=len(Term.__table__.columns)):
            await self.session.execute(
                pg_insert(Term).values(chunk).on_conflict_do_nothing(index_elements=["lemma"]),
            )

        term_ids = {
            row.lemma: row.id
            for row in (
                await self.session.execute(
                    select(Term.id, Term.lemma).where(
                        Term.lemma == any_(literal(list(lemmas), ARRAY(String)))
                    )
                )
            ).all()
        }

        rows: list[dict[str, object]] = []
        for doc_id, frequencies in frequencies_by_document.items():
            image = images[doc_id]
            for lemma, frequency in frequencies.items():
                rows.append(
                    {
                        "term_id": term_ids[lemma],
                        "document_id": doc_id,
                        "term_frequency": frequency,
                        # Weights are filled in by the reweighting pass, which needs `N`.
                        "weight_raw": 0.0,
                        "weight_norm": 0.0,
                        "positions": image.terms[lemma].positions[:512],  # type: ignore[attr-defined]
                    }
                )

        for chunk in _chunks(rows, params_per_row=len(Posting.__table__.columns)):
            # `excluded` refers to the row proposed by this INSERT. With a multi-row
            # VALUES clause a bound parameter would be ambiguous — there is one per row —
            # so the conflict action has to name the proposed row instead.
            statement = pg_insert(Posting).values(chunk)
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=["term_id", "document_id"],
                    set_={
                        "term_frequency": statement.excluded.term_frequency,
                        "positions": statement.excluded.positions,
                    },
                )
            )

        # Per-document length counters, needed by BM25 and shown in the corpus browser.
        for doc_id, frequencies in frequencies_by_document.items():
            image = images[doc_id]
            await self.session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(
                    token_count=image.token_count,  # type: ignore[attr-defined]
                    distinct_term_count=len(frequencies),
                )
            )

    # ------------------------------------------------------------- reweighting ----
    #
    # The five statements below are the set-based equivalent of `irs.index.weights`.
    # Each is a single pass over the postings table.

    async def _update_document_frequencies(self) -> None:
        """`N_k` and the collection frequency, counted straight off the postings."""
        await self.session.execute(
            text(
                """
                UPDATE term AS t
                   SET document_frequency = COALESCE(s.df, 0),
                       collection_frequency = COALESCE(s.cf, 0)
                  FROM (
                        SELECT term_id,
                               COUNT(*)              AS df,
                               SUM(term_frequency)   AS cf
                          FROM posting
                         GROUP BY term_id
                       ) AS s
                 WHERE t.id = s.term_id
                """
            )
        )
        # Terms that lost every posting must not keep a stale frequency.
        await self.session.execute(
            text(
                """
                UPDATE term
                   SET document_frequency = 0, collection_frequency = 0, idf = 0
                 WHERE id NOT IN (SELECT DISTINCT term_id FROM posting)
                """
            )
        )

    async def _update_inverse_frequencies(self, document_count: int) -> None:
        """`B_i = log(N / P_i)` — formula 1.5, applied to the whole dictionary.

        The ``CASE`` reproduces the guards in
        :func:`irs.index.weights.inverse_frequency` exactly: an empty collection, a term
        with no postings, and a term present in every document all yield zero rather
        than a negative weight or a division by zero.
        """
        await self.session.execute(
            text(
                """
                UPDATE term
                   SET idf = CASE
                       WHEN :n <= 0                      THEN 0.0
                       WHEN document_frequency <= 0      THEN 0.0
                       WHEN document_frequency >= :n     THEN 0.0
                       -- CAST(... AS ...) rather than `::`, because SQLAlchemy's text()
                       -- parameter parser cannot disambiguate `:n::type` from a parameter
                       -- named `n:`.
                       ELSE LN(CAST(:n AS double precision) / document_frequency) / :divisor
                   END
                """
            ),
            {"n": document_count, "divisor": settings.index.log_divisor},
        )

    async def _update_raw_weights(self) -> None:
        """`A_i^j = Q_i^j · B_i` — formula 1.6."""
        await self.session.execute(
            text(
                """
                UPDATE posting AS p
                   SET weight_raw = p.term_frequency * t.idf
                  FROM term AS t
                 WHERE t.id = p.term_id
                """
            )
        )

    async def _update_normalized_weights(self) -> None:
        """`w_dk = A_dk / sqrt(Σ_j A_dj²)`, then cache ‖D‖.

        A document whose every term has zero IDF has a zero denominator; the ``CASE``
        yields a zero vector, matching the Python reference rather than raising.
        """
        await self.session.execute(
            text(
                """
                UPDATE posting AS p
                   SET weight_norm = CASE
                           WHEN s.denominator > 0 THEN p.weight_raw / s.denominator
                           ELSE 0.0
                       END
                  FROM (
                        SELECT document_id,
                               SQRT(SUM(weight_raw * weight_raw)) AS denominator
                          FROM posting
                         GROUP BY document_id
                       ) AS s
                 WHERE p.document_id = s.document_id
                """
            )
        )
        await self.session.execute(
            text(
                """
                UPDATE document AS d
                   SET vector_norm = COALESCE(s.norm, 0.0)
                  FROM (
                        SELECT document_id,
                               SQRT(SUM(weight_norm * weight_norm)) AS norm
                          FROM posting
                         GROUP BY document_id
                       ) AS s
                 WHERE d.id = s.document_id
                """
            )
        )
        # Documents that produced no index terms at all.
        await self.session.execute(
            text(
                """
                UPDATE document
                   SET vector_norm = 0.0
                 WHERE id NOT IN (SELECT DISTINCT document_id FROM posting)
                """
            )
        )

    async def _prune_orphan_terms(self) -> None:
        """Drop dictionary entries that no document uses any more.

        Without this, `D` would grow monotonically and the reported dictionary size
        would overstate the collection's actual vocabulary.
        """
        result = await self.session.execute(
            text("DELETE FROM term WHERE id NOT IN (SELECT DISTINCT term_id FROM posting)")
        )
        # `rowcount` is declared on CursorResult, which is what a DML statement returns.
        pruned = cast("CursorResult[Any]", result).rowcount
        if pruned:
            log.debug("index_orphan_terms_pruned", terms=pruned)

    # -------------------------------------------------------------------- stats ----

    async def _count_documents(self) -> int:
        return int(
            (await self.session.execute(select(func.count()).select_from(Document))).scalar_one()
        )

    async def _commit_stats(self, duration_ms: float) -> IndexStats:
        document_count = await self._count_documents()
        term_count = int(
            (await self.session.execute(select(func.count()).select_from(Term))).scalar_one()
        )
        posting_count = int(
            (await self.session.execute(select(func.count()).select_from(Posting))).scalar_one()
        )
        average_length = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.avg(Document.token_count), 0.0))
                )
            ).scalar_one()
        )
        embedded = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(Document).where(Document.embedding.isnot(None))
                )
            ).scalar_one()
        )

        stat = await self.session.get(CollectionStat, 1)
        if stat is None:
            stat = CollectionStat(id=1)
            self.session.add(stat)

        stat.document_count = document_count
        stat.term_count = term_count
        stat.posting_count = posting_count
        stat.average_document_length = average_length
        stat.index_version = (stat.index_version or 0) + 1
        stat.log_base = settings.index.log_base
        stat.built_at = datetime.now(UTC).replace(tzinfo=None)
        stat.build_duration_ms = duration_ms
        stat.embedded_document_count = embedded

        await self.session.flush()

        return IndexStats(
            document_count=document_count,
            term_count=term_count,
            posting_count=posting_count,
            average_document_length=average_length,
            index_version=stat.index_version,
            log_base=stat.log_base,
            duration_ms=duration_ms,
            embedded_document_count=embedded,
        )


async def get_collection_stat(session: AsyncSession) -> CollectionStat:
    """Read the singleton statistics row, creating it if a migration has not seeded it."""
    stat = await session.get(CollectionStat, 1)
    if stat is None:
        stat = CollectionStat(id=1)
        session.add(stat)
        await session.flush()
    return stat
