"""Vector model with an IDF-weighted query — improvement proposal №1.

Identical to the mandated model in every respect but one: the assignment fixes the
query vector as *binary* (`w_qj = 1` if word `j` is in the query), so a rare, highly
informative query word and a near-ubiquitous one pull on the ranking equally. Here
`w_qj = B_j = log(N / N_j)` instead — the same inverse frequency the documents already
use — so the query's own words are weighted by how much they discriminate.

This is not a different retrieval model. It isolates one variable so the evaluation can
answer one question: how much of the gap between the vector model and BM25 is the binary
query alone. The analysis section of the report reads the answer off the arena table.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, SearchFilters
from irs.selection.rocchio import idf_query_vector, rank_sparse_query

log = get_logger("irs.selection.vector_idf")


class VectorIdfRanker:
    """TF-IDF cosine with `w_qj = B_j` instead of `w_qj = 1`."""

    key = RankerKey.VECTOR_IDF
    label = "Vector model (IDF-weighted query)"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        if not query.is_answerable:
            return RankedPage()

        weights = idf_query_vector(query)
        if not weights:
            # Every query term occurs in every document: no term can separate anything.
            log.info("vector_idf_all_terms_uninformative", raw=query.raw[:120])
            return RankedPage()

        return await rank_sparse_query(session, weights, filters, limit, query_lemmas=query.lemmas)


ranker = VectorIdfRanker()
