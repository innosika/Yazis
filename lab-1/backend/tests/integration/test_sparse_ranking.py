"""The real-valued query scorer must reproduce the binary ranker exactly.

:func:`irs.selection.rocchio.rank_sparse_query` is a generalisation of the mandated
ranker's SQL: with all query weights equal to 1 it must give the same scores in the same
order. That pin is what lets `vector_idf` and `vector_prf` be described as «the same
model with one change» rather than as separate implementations.
"""

from __future__ import annotations

import math

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Document, Posting
from irs.selection.base import SearchFilters
from irs.selection.parser import parse_query
from irs.selection.rocchio import (
    binary_query_vector,
    idf_query_vector,
    load_document_vectors,
    rank_sparse_query,
)
from irs.selection.vector import ranker as vector_ranker
from irs.selection.vector_idf import ranker as idf_ranker
from irs.selection.vector_prf import ranker as prf_ranker
from tests.conftest import requires_database

pytestmark = [pytest.mark.integration, requires_database]

QUERY = "vector space model information retrieval"


@pytest.fixture
async def has_index(session: AsyncSession) -> None:
    count = (await session.execute(select(Posting.term_id).limit(1))).first()
    if count is None:
        pytest.skip("index is empty — run `make seed && make index`")


async def test_binary_weights_reproduce_vector_ranker(
    session: AsyncSession, has_index: None
) -> None:
    parsed = await parse_query(session, QUERY)
    assert parsed.is_answerable

    reference = await vector_ranker.rank(session, parsed, SearchFilters(), limit=50)
    sparse = await rank_sparse_query(
        session, binary_query_vector(parsed), SearchFilters(), 50, query_lemmas=parsed.lemmas
    )

    assert [d.document_id for d in sparse.documents] == [d.document_id for d in reference.documents]
    for a, b in zip(sparse.documents, reference.documents, strict=True):
        assert a.score == pytest.approx(b.score, abs=1e-9)
        assert a.matched_lemmas == b.matched_lemmas
    assert sparse.total_candidates == reference.total_candidates


async def test_idf_ranker_matches_python_recomputation(
    session: AsyncSession, has_index: None
) -> None:
    parsed = await parse_query(session, QUERY)
    page = await idf_ranker.rank(session, parsed, SearchFilters(), limit=5)
    assert page.documents

    weights = idf_query_vector(parsed)
    query_norm = math.sqrt(sum(w * w for w in weights.values()))
    vectors = await load_document_vectors(session, [d.document_id for d in page.documents])
    norms = {
        row.id: row.vector_norm
        for row in (
            await session.execute(
                select(Document.id, Document.vector_norm).where(
                    Document.id.in_([d.document_id for d in page.documents])
                )
            )
        ).all()
    }

    for scored in page.documents:
        vector = vectors[scored.document_id]
        dot = sum(vector.get(term, 0.0) * w for term, w in weights.items())
        expected = dot / (norms[scored.document_id] * query_norm)
        assert scored.score == pytest.approx(expected, abs=1e-9)


async def test_prf_ranker_is_deterministic_and_expands(
    session: AsyncSession, has_index: None
) -> None:
    parsed = await parse_query(session, QUERY)
    first = await prf_ranker.rank(session, parsed, SearchFilters(), limit=20)
    second = await prf_ranker.rank(session, parsed, SearchFilters(), limit=20)

    assert first.documents
    assert [d.document_id for d in first.documents] == [d.document_id for d in second.documents]
    detail = first.documents[0].detail
    assert detail["expanded_terms"] >= detail["original_terms"]
    assert detail["feedback_docs"] >= 1
    # Matched lemmas are the user's words only, never expansion terms.
    assert set(first.documents[0].matched_lemmas) <= set(parsed.lemmas)
