"""The vector search model — the ranker variant 34 mandates.

Scores documents by the cosine of the angle between the document vector and the query
vector, using the normalized TF-IDF weights `w_dk` written by the index builder.

The retrieval is a single aggregate query, and the reason it can be is worth stating
because it is a direct consequence of the specified formulas rather than a shortcut:

* The query vector is **binary** (`w_qj ∈ {0, 1}`), so the scalar product
  `(D, Q) = Σ_j w_dj·w_qj` reduces to `Σ_{k ∈ q} w_dk` — a plain sum of the stored
  weights of the query's terms. No per-candidate vector needs to be materialised.
* `‖D‖` is cached on the document row, and equals 1 by construction.
* `‖Q‖ = sqrt(|q|)`, a constant for the whole query.

So the cosine is `SUM(weight_norm) / (vector_norm · sqrt(|q|))`, computed by the database
over exactly the postings of the query's terms — which is the inverted-index scan the
structure exists to support. :mod:`irs.index.weights` remains the readable reference for
the same arithmetic, and the explanation path in :mod:`irs.selection.explain` uses it
directly when a user asks why a document ranked where it did.
"""

from __future__ import annotations

import math

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Document, Posting, Term
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, ScoredDocument, SearchFilters
from irs.selection.filters import apply_document_filters

log = get_logger("irs.selection.vector")


class VectorRanker:
    """TF-IDF weights with cosine similarity — the assignment's «векторная» strategy."""

    key = RankerKey.VECTOR
    label = "Vector model (TF-IDF · cosine)"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        if not query.is_answerable:
            log.info(
                "vector_query_unanswerable",
                raw=query.raw[:120],
                unknown=query.unknown_lemmas,
            )
            return RankedPage()

        term_ids = list(query.term_ids.values())

        # ‖Q‖ counts the query's *dictionary* terms. A word absent from the dictionary
        # spans no dimension of the term space, so it cannot contribute to the norm —
        # which is the faithful reading of `w_qj = 1 if word j is in the query`, where j
        # ranges over the dictionary. (It would in any case only rescale every score for
        # this query by one constant, leaving the ranking unchanged.)
        query_norm = math.sqrt(len(term_ids))

        dot_product = func.sum(Posting.weight_norm)
        matched_terms = func.count(func.distinct(Posting.term_id))
        score = case(
            (
                Document.vector_norm > 0,
                dot_product / (Document.vector_norm * query_norm),
            ),
            else_=0.0,
        ).label("score")

        statement = (
            select(
                Posting.document_id.label("document_id"),
                score,
                dot_product.label("dot"),
                matched_terms.label("matched_terms"),
                func.array_agg(func.distinct(Term.lemma)).label("matched_lemmas"),
            )
            .join(Term, Term.id == Posting.term_id)
            .join(Document, Document.id == Posting.document_id)
            .where(Posting.term_id.in_(term_ids))
            .group_by(Posting.document_id, Document.vector_norm)
        )

        statement = self._apply_filters(statement, query, filters)

        # Documents whose similarity is exactly zero are orthogonal to the query — they
        # match only terms carrying no information (`B_i = 0`, i.e. present in every
        # document). Returning them as "results" would misrepresent the model, so they
        # are excluded rather than ranked last.
        statement = statement.having(dot_product > 0)

        # Ties are broken by ascending document id. TF-IDF cosine produces exact ties
        # routinely, and an unstable order there would make evaluation metrics differ
        # between two runs of an unchanged system.
        # The unlimited form is reused to count the full candidate set.
        candidates = statement
        statement = statement.order_by(score.desc(), Posting.document_id.asc()).limit(limit)

        # Counted over the same grouped-and-filtered set, so the figure reflects what
        # the ranker actually matched rather than what fitted on the page.
        total_candidates = int(
            (
                await session.execute(select(func.count()).select_from(candidates.subquery()))
            ).scalar_one()
        )

        rows = (await session.execute(statement)).all()

        results = [
            ScoredDocument(
                document_id=row.document_id,
                score=float(row.score),
                matched_lemmas=self._order_as_typed(query, row.matched_lemmas),
                detail={
                    "scalar_product": float(row.dot),
                    "document_norm": 1.0,
                    "query_norm": query_norm,
                    "matched_terms": float(row.matched_terms),
                    "query_terms": float(len(term_ids)),
                },
            )
            for row in rows
        ]

        log.info(
            "vector_ranked",
            raw=query.raw[:120],
            query_terms=len(term_ids),
            results=len(results),
            top_score=round(results[0].score, 6) if results else 0.0,
            all_words_together=filters.all_words_together,
            candidates=total_candidates,
        )
        return RankedPage(documents=results, total_candidates=total_candidates)

    # ------------------------------------------------------------------ helpers ----

    def _apply_filters(self, statement, query: ParsedQuery, filters: SearchFilters):  # type: ignore[no-untyped-def]
        """Apply the assignment's ``Search`` class filters.

        Document-level predicates come from :mod:`irs.selection.filters` so that every
        ranker filters identically; only the conjunctive term condition is specific to
        this ranker's grouping.
        """
        conditions = apply_document_filters(filters)
        if conditions:
            statement = statement.where(and_(*conditions))

        if filters.all_words_together:
            # `allWordsTogether`: every dictionary term of the query must be present.
            # Compared against the number of *known* query terms, since an unknown term
            # can never be present and would make the condition unsatisfiable.
            statement = statement.having(
                func.count(func.distinct(Posting.term_id)) == len(query.term_ids)
            )

        return statement

    @staticmethod
    def _order_as_typed(query: ParsedQuery, matched: list[str] | None) -> list[str]:
        """Order the matched terms as the user typed them, not as the database returned.

        The result list shows «слова запроса присутствующие в документе», so reading them
        back in the user's own word order makes the list immediately recognisable.
        """
        if not matched:
            return []
        found = set(matched)
        return [lemma for lemma in query.lemmas if lemma in found]


ranker = VectorRanker()
