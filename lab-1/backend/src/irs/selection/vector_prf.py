"""Vector model with Rocchio pseudo-relevance feedback — improvement proposal №2.

The «AI element» of variant 34 is the document-selection module, and the classic way a
vector-space selector learns from its own output is Rocchio feedback. With no user in the
loop the top-`k` documents of the initial run are *assumed* relevant (pseudo-relevance
feedback), their centroid is added to the query, and the expanded query is scored again:

    q' = α·q + (β / k) · Σ_{d ∈ top-k} d          (γ = 0: nothing is assumed non-relevant)

The effect being tested is vocabulary expansion: documents about the topic that use none
of the user's exact words can still be reached through the words the top documents
share. The known risk is *query drift* when the initial top-`k` is wrong — which is
precisely what the evaluation's per-topic table makes visible.

The same kernel powers the interactive Relevance Lab, where a person marks the documents
instead and γ is non-zero.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, SearchFilters
from irs.selection.rocchio import (
    binary_query_vector,
    load_document_vectors,
    rank_sparse_query,
    rocchio,
    truncate,
)

log = get_logger("irs.selection.vector_prf")


class VectorPrfRanker:
    """Binary query → top-k of the vector model → Rocchio expansion → rescore."""

    key = RankerKey.VECTOR_PRF
    label = "Vector model + Rocchio PRF"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        if not query.is_answerable:
            return RankedPage()

        from irs.selection.vector import ranker as vector_ranker

        feedback_docs = settings.search.prf_feedback_docs
        initial = await vector_ranker.rank(session, query, filters, feedback_docs)
        if not initial.documents:
            return RankedPage()

        pseudo_relevant = await load_document_vectors(
            session, [document.document_id for document in initial.documents]
        )
        original = binary_query_vector(query)
        expanded = rocchio(
            original,
            relevant=list(pseudo_relevant.values()),
            non_relevant=[],
            alpha=settings.search.rocchio_alpha,
            beta=settings.search.rocchio_beta,
            gamma=0.0,
        )
        expanded = truncate(expanded, settings.search.prf_expansion_terms)

        log.info(
            "vector_prf_expanded",
            raw=query.raw[:120],
            feedback_docs=len(pseudo_relevant),
            original_terms=len(original),
            expanded_terms=len(expanded),
        )

        return await rank_sparse_query(
            session,
            expanded,
            filters,
            limit,
            query_lemmas=query.lemmas,
            extra_detail={
                "feedback_docs": float(len(pseudo_relevant)),
                "expanded_terms": float(len(expanded)),
                "original_terms": float(len(original)),
            },
        )


ranker = VectorPrfRanker()
