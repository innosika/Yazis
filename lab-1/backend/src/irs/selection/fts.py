"""PostgreSQL full-text search — an independent reference point.

This ranker shares none of our indexing code: it uses the database's own `tsvector`
column, its English text-search configuration (stemming and stop words), and `ts_rank`
for scoring. That independence is the point. If our hand-built index and weighting were
subtly wrong, a comparison against BM25 would not reveal it — both are computed from the
same postings table. `ts_rank` is computed from a completely separate structure, so
agreement between them is real evidence and disagreement is a real signal.

`websearch_to_tsquery` is used rather than `plainto_tsquery` because it tolerates the
punctuation people actually type (quoted phrases, `or`, leading `-`) instead of failing
on it.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Document
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, ScoredDocument, SearchFilters
from irs.selection.filters import apply_document_filters

log = get_logger("irs.selection.fts")

#: ts_rank normalisation flags. 1 divides by 1 + log(document length) and 32 by
#: rank + 1, together giving a length-corrected score bounded in (0, 1) — comparable in
#: shape to a cosine, which makes the arena's charts legible on one axis.
_NORMALIZATION = 1 | 32


class FullTextRanker:
    """`tsvector` matching with `ts_rank` scoring."""

    key = RankerKey.FTS
    label = "PostgreSQL full-text"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        raw = (query.raw or "").strip()
        if not raw:
            return RankedPage()

        # The database does its own stemming and stop-word removal, so it receives the
        # user's original text rather than our lemmas — feeding it our search image would
        # stem already-lemmatised tokens and measure a hybrid of the two pipelines.
        tsquery = (
            func.websearch_to_tsquery("english", raw)
            if not filters.all_words_together
            else func.plainto_tsquery("english", raw)
        )

        score = func.ts_rank(Document.tsv, tsquery, _NORMALIZATION).label("score")

        statement = select(Document.id.label("document_id"), score).where(
            Document.tsv.op("@@")(tsquery)
        )

        conditions = apply_document_filters(filters)
        if conditions:
            statement = statement.where(and_(*conditions))

        candidates = statement
        statement = statement.order_by(score.desc(), Document.id.asc()).limit(limit)

        total_candidates = int(
            (
                await session.execute(select(func.count()).select_from(candidates.subquery()))
            ).scalar_one()
        )
        rows = (await session.execute(statement)).all()

        # The matched-term list still comes from our own dictionary, so that every ranker
        # reports "words of your query present in this document" the same way.
        results = [
            ScoredDocument(
                document_id=row.document_id,
                score=float(row.score),
                matched_lemmas=[],
                detail={"ts_rank": float(row.score)},
            )
            for row in rows
        ]

        if results:
            await self._attach_matches(session, query, results)

        log.info(
            "fts_ranked",
            raw=raw[:120],
            results=len(results),
            top_score=round(results[0].score, 6) if results else 0.0,
            conjunctive=filters.all_words_together,
            candidates=total_candidates,
        )
        return RankedPage(documents=results, total_candidates=total_candidates)

    async def _attach_matches(
        self, session: AsyncSession, query: ParsedQuery, results: list[ScoredDocument]
    ) -> None:
        """Fill in which query lemmas each returned document contains."""
        from irs.db.models import Posting, Term

        if not query.term_ids:
            return

        rows = (
            await session.execute(
                select(Posting.document_id, Term.lemma)
                .join(Term, Term.id == Posting.term_id)
                .where(
                    Posting.document_id.in_([r.document_id for r in results]),
                    Posting.term_id.in_(list(query.term_ids.values())),
                )
            )
        ).all()

        by_document: dict[int, set[str]] = {}
        for document_id, lemma in rows:
            by_document.setdefault(document_id, set()).add(lemma)

        for result in results:
            found = by_document.get(result.document_id, set())
            result.matched_lemmas = [lemma for lemma in query.lemmas if lemma in found]


ranker = FullTextRanker()
