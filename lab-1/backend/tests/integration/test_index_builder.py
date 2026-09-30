"""The SQL reweighting must agree with the Python reference implementation.

:mod:`irs.index.weights` is the specification, verified against hand-computed values in
``tests/unit/test_weights.py``. :mod:`irs.index.builder` recomputes the same quantities
set-based in SQL because every weight depends on `N`, so adding one document invalidates
every posting in the collection and streaming them through Python would be wasteful.

Having two implementations is only safe if they are pinned to each other, which is what
this module does. It is the test that lets the report claim the optimisation is faithful
to the specified formulas rather than merely similar to them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import CollectionStat, Document, Posting, Term
from irs.index.builder import IndexBuilder
from irs.index.weights import (
    cosine_similarity,
    euclidean_norm,
    inverse_frequency,
    normalized_weights,
    query_vector,
    raw_weight,
)
from tests.conftest import requires_database

pytestmark = [pytest.mark.integration, requires_database]

#: Both paths use IEEE-754 doubles but accumulate in a different order — Postgres sums
#: per group, Python sums per dict — so exact equality is not a reasonable requirement.
#: Agreement to ~1e-12 is far tighter than any ranking decision depends on.
TOLERANCE = 1e-12


@pytest.fixture
async def indexed(session: AsyncSession) -> dict[str, object]:
    """Rebuild the index, then read everything needed to recompute it independently."""
    await IndexBuilder(session).rebuild()
    await session.flush()

    stat = await session.get(CollectionStat, 1)
    assert stat is not None
    terms = {term.id: term for term in (await session.execute(select(Term))).scalars()}
    postings = list((await session.execute(select(Posting))).scalars())
    documents = {doc.id: doc for doc in (await session.execute(select(Document))).scalars()}

    by_document: dict[int, list[Posting]] = {}
    for posting in postings:
        by_document.setdefault(posting.document_id, []).append(posting)

    return {
        "N": stat.document_count,
        "terms": terms,
        "postings": postings,
        "documents": documents,
        "by_document": by_document,
    }


class TestSqlMatchesPythonReference:
    def test_collection_is_not_empty(self, indexed: dict[str, object]) -> None:
        """Guard: the agreement assertions below are vacuous on an empty collection."""
        assert indexed["N"], "no documents indexed — seed the corpus first"
        assert indexed["postings"], "no postings produced"

    def test_inverse_frequencies_agree(self, indexed: dict[str, object]) -> None:
        """`B_i = log(N / P_i)` — formula 1.5."""
        n = indexed["N"]
        for term in indexed["terms"].values():  # type: ignore[attr-defined]
            expected = inverse_frequency(n, term.document_frequency)
            assert term.idf == pytest.approx(expected, abs=TOLERANCE), (
                f"term {term.lemma!r}: sql={term.idf} python={expected}"
            )

    def test_raw_weights_agree(self, indexed: dict[str, object]) -> None:
        """`A_i^j = Q_i^j · B_i` — formula 1.6, the keyword-extraction weight."""
        terms = indexed["terms"]
        for posting in indexed["postings"]:  # type: ignore[attr-defined]
            term = terms[posting.term_id]  # type: ignore[index]
            expected = raw_weight(posting.term_frequency, term.idf)
            assert posting.weight_raw == pytest.approx(expected, abs=TOLERANCE)

    def test_normalized_weights_agree(self, indexed: dict[str, object]) -> None:
        """`w_dk` — the search-vector weight, recomputed per document from raw counts."""
        n = indexed["N"]
        terms = indexed["terms"]

        for document_id, postings in indexed["by_document"].items():  # type: ignore[attr-defined]
            frequencies = {terms[p.term_id].lemma: p.term_frequency for p in postings}  # type: ignore[index]
            inverse_frequencies = {
                terms[p.term_id].lemma: inverse_frequency(  # type: ignore[index]
                    n,
                    terms[p.term_id].document_frequency,  # type: ignore[index]
                )
                for p in postings
            }
            expected, _denominator = normalized_weights(frequencies, inverse_frequencies)

            for posting in postings:
                lemma = terms[posting.term_id].lemma  # type: ignore[index]
                assert posting.weight_norm == pytest.approx(expected[lemma], abs=TOLERANCE), (
                    f"document {document_id} term {lemma!r}"
                )

    def test_cached_document_norms_agree(self, indexed: dict[str, object]) -> None:
        """The stored ‖D‖ must match the norm of the stored weight vector."""
        documents = indexed["documents"]
        terms = indexed["terms"]

        for document_id, postings in indexed["by_document"].items():  # type: ignore[attr-defined]
            vector = {terms[p.term_id].lemma: p.weight_norm for p in postings}  # type: ignore[index]
            document = documents[document_id]  # type: ignore[index]
            assert document.vector_norm == pytest.approx(euclidean_norm(vector), abs=TOLERANCE)


class TestIndexInvariants:
    def test_document_norms_are_unity(self, indexed: dict[str, object]) -> None:
        """‖D‖ = 1 for every document carrying at least one informative term.

        The property the retrieval path relies on when it reuses the cached norm. A
        stored value that has drifted from 1 means the index is stale, so this doubles as
        a staleness check over the real collection rather than a synthetic one.
        """
        for document in indexed["documents"].values():  # type: ignore[attr-defined]
            if document.distinct_term_count == 0:
                assert document.vector_norm == 0.0
            else:
                assert document.vector_norm == pytest.approx(1.0, abs=1e-9), (
                    f"document {document.id} has ‖D‖={document.vector_norm}"
                )

    def test_document_frequency_matches_posting_count(self, indexed: dict[str, object]) -> None:
        """`P_i` must equal the length of the term's postings list."""
        counted: dict[int, int] = {}
        for posting in indexed["postings"]:  # type: ignore[attr-defined]
            counted[posting.term_id] = counted.get(posting.term_id, 0) + 1

        for term_id, term in indexed["terms"].items():  # type: ignore[attr-defined]
            assert term.document_frequency == counted.get(term_id, 0), (
                f"term {term.lemma!r}: stored df={term.document_frequency} "
                f"actual postings={counted.get(term_id, 0)}"
            )

    def test_no_orphan_terms(self, indexed: dict[str, object]) -> None:
        """Every dictionary entry is used by at least one document, so `D` is honest."""
        used = {posting.term_id for posting in indexed["postings"]}  # type: ignore[attr-defined]
        orphans = set(indexed["terms"]) - used  # type: ignore[arg-type]
        assert not orphans, f"{len(orphans)} dictionary entries have no postings"

    def test_terms_in_every_document_have_zero_weight(self, indexed: dict[str, object]) -> None:
        """A term present in all N documents distinguishes nothing and must weigh zero."""
        n = indexed["N"]
        ubiquitous = [
            term
            for term in indexed["terms"].values()
            if term.document_frequency >= n  # type: ignore[attr-defined]
        ]
        for term in ubiquitous:
            assert term.idf == 0.0, f"{term.lemma!r} is in every document but has idf>0"

    async def test_rebuild_is_idempotent(
        self, session: AsyncSession, indexed: dict[str, object]
    ) -> None:
        """Rebuilding twice must not change any weight.

        Catches accumulation bugs — a counter incremented rather than assigned, or
        postings appended rather than replaced.
        """
        terms = indexed["terms"]
        before = {
            (terms[p.term_id].lemma, p.document_id): (  # type: ignore[index]
                p.term_frequency,
                round(p.weight_raw, 12),
                round(p.weight_norm, 12),
            )
            for p in indexed["postings"]  # type: ignore[attr-defined]
        }

        await IndexBuilder(session).rebuild()
        await session.flush()

        fresh_terms = {t.id: t for t in (await session.execute(select(Term))).scalars()}
        after = {
            (fresh_terms[p.term_id].lemma, p.document_id): (
                p.term_frequency,
                round(p.weight_raw, 12),
                round(p.weight_norm, 12),
            )
            for p in (await session.execute(select(Posting))).scalars()
        }

        assert after == before


class TestRetrievalSanity:
    async def test_query_ranks_the_topically_matching_document_first(
        self, indexed: dict[str, object]
    ) -> None:
        """An end-to-end sanity check over the real stored weights.

        The development corpus contains one document titled "The Vector Space Model", so
        the query "vector space model" must rank it top. This asserts the weights are not
        merely self-consistent but actually retrieve sensibly.
        """
        terms = indexed["terms"]
        documents = indexed["documents"]
        query = query_vector(["vector", "space", "model"])

        scored = []
        for document_id, postings in indexed["by_document"].items():  # type: ignore[attr-defined]
            vector = {terms[p.term_id].lemma: p.weight_norm for p in postings}  # type: ignore[index]
            document = documents[document_id]  # type: ignore[index]
            scored.append((cosine_similarity(vector, query, document.vector_norm), document.title))

        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        assert scored[0][0] > 0.0, "nothing matched a query the corpus should answer"
        assert "vector space model" in scored[0][1].lower(), f"unexpected top result: {scored[:3]}"
