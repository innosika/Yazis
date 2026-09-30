"""Okapi BM25 — the probabilistic baseline.

Included so the assignment's vector model is measured against the standard the field
actually uses, rather than only against itself. BM25 refines TF-IDF cosine in two ways
that matter on real documents:

* **Saturating term frequency.** The contribution of a term grows quickly over its first
  few occurrences and then flattens, controlled by `k1`. Raw TF-IDF is linear in the
  count, so a page that repeats a word twenty times outranks one that uses it ten times
  by a factor of two — which does not match how relevance actually behaves.
* **Explicit length normalisation.** Document length is compared against the collection
  average, with `b` controlling how strongly long documents are penalised. The vector
  model normalises by the Euclidean norm instead, which is a different and less tunable
  correction.

Note the IDF is *not* the assignment's formula 1.5. BM25 uses the probabilistic form

    IDF(t) = ln(1 + (N − n(t) + 0.5) / (n(t) + 0.5))

which stays positive for terms occurring in more than half the collection, where
`log(N / n(t))` would go to zero. Using one ranker's IDF in the other would misrepresent
both, so each keeps its own.
"""

from __future__ import annotations

from sqlalchemy import Float, and_, cast, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import Document, Posting, Term
from irs.db.models.enums import RankerKey
from irs.index.builder import get_collection_stat
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, ScoredDocument, SearchFilters
from irs.selection.filters import apply_document_filters

log = get_logger("irs.selection.bm25")


class BM25Ranker:
    """Okapi BM25 over the same inverted index the vector model uses."""

    key = RankerKey.BM25
    label = "BM25"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        if not query.is_answerable:
            return RankedPage()

        stat = await get_collection_stat(session)
        n = stat.document_count
        average_length = stat.average_document_length or 1.0
        if n <= 0:
            return RankedPage()

        k1 = settings.search.bm25_k1
        b = settings.search.bm25_b
        term_ids = list(query.term_ids.values())

        # BM25's probabilistic IDF, computed per term inside the query so the ranker does
        # not depend on the cached column that holds the assignment's formula 1.5.
        idf = func.ln(
            1.0
            + (cast(literal(n), Float) - Term.document_frequency + 0.5)
            / (Term.document_frequency + 0.5)
        )

        # tf · (k1 + 1) / (tf + k1 · (1 − b + b · |d| / avgdl))
        length_norm = k1 * (1.0 - b + b * (cast(Document.token_count, Float) / average_length))
        term_score = idf * (
            (Posting.term_frequency * (k1 + 1.0)) / (Posting.term_frequency + length_norm)
        )

        score = func.sum(term_score).label("score")
        matched_terms = func.count(func.distinct(Posting.term_id))

        statement = (
            select(
                Posting.document_id.label("document_id"),
                score,
                matched_terms.label("matched_terms"),
                func.array_agg(func.distinct(Term.lemma)).label("matched_lemmas"),
            )
            .join(Term, Term.id == Posting.term_id)
            .join(Document, Document.id == Posting.document_id)
            .where(Posting.term_id.in_(term_ids))
            .group_by(Posting.document_id)
        )

        conditions = apply_document_filters(filters)
        if conditions:
            statement = statement.where(and_(*conditions))
        if filters.all_words_together:
            statement = statement.having(matched_terms == len(query.term_ids))

        statement = statement.having(score > 0)

        # The unlimited, filtered form is reused to count the whole candidate set, so the
        # reported figure is what the ranker matched rather than what fitted on the page.
        candidates = statement
        total_candidates = int(
            (
                await session.execute(select(func.count()).select_from(candidates.subquery()))
            ).scalar_one()
        )

        statement = statement.order_by(text("score DESC"), Posting.document_id.asc()).limit(limit)
        rows = (await session.execute(statement)).all()

        results = [
            ScoredDocument(
                document_id=row.document_id,
                score=float(row.score),
                matched_lemmas=[
                    lemma for lemma in query.lemmas if lemma in set(row.matched_lemmas or [])
                ],
                detail={
                    "k1": k1,
                    "b": b,
                    "average_document_length": average_length,
                    "matched_terms": float(row.matched_terms),
                },
            )
            for row in rows
        ]

        log.info(
            "bm25_ranked",
            raw=query.raw[:120],
            query_terms=len(term_ids),
            results=len(results),
            top_score=round(results[0].score, 6) if results else 0.0,
            k1=k1,
            b=b,
            candidates=total_candidates,
        )
        return RankedPage(documents=results, total_candidates=total_candidates)


ranker = BM25Ranker()
