"""Golden tests for the assignment's term-weighting formulas.

The expected values here were derived by hand from the formulas, independently of the
implementation. Several are given as exact closed forms rather than decimals, because
the corpus was constructed so that the IDF factors cancel — which both pins the
arithmetic precisely and demonstrates the logarithm-base invariance discussed in
``irs.index.weights``.
"""

from __future__ import annotations

import math

import pytest

from irs.index.weights import (
    cosine_similarity,
    derive_cosine,
    derive_term_weight,
    euclidean_norm,
    inverse_frequency,
    normalized_weights,
    query_vector,
    raw_weight,
    scalar_product,
    top_keywords,
)

N = 3  # documents in the hand-worked collection


# --------------------------------------------------------------------------------
# Formula 1.5 — B_i = log(N / P_i)
# --------------------------------------------------------------------------------


class TestInverseFrequency:
    def test_matches_hand_computation(self) -> None:
        # A term in 2 of 3 documents: ln(3/2).
        assert inverse_frequency(3, 2) == pytest.approx(0.4054651081081644, abs=1e-15)
        # A term in 1 of 3 documents: ln(3).
        assert inverse_frequency(3, 1) == pytest.approx(1.0986122886681098, abs=1e-15)

    def test_term_in_every_document_has_zero_weight(self) -> None:
        """`P_i = N` gives log(1) = 0 — such a term distinguishes nothing.

        This falls out of the formula itself; it is asserted because a naive
        implementation that special-cased division would break it.
        """
        assert inverse_frequency(100, 100) == 0.0

    def test_rarer_terms_weigh_more(self) -> None:
        weights = [inverse_frequency(1_000, df) for df in (1, 10, 100, 500)]
        assert weights == sorted(weights, reverse=True)

    @pytest.mark.parametrize(
        ("document_count", "document_frequency"),
        [
            (0, 5),  # empty collection
            (10, 0),  # term in the dictionary but in no document (stale index)
            (10, 11),  # more documents than exist (inconsistent counters)
        ],
    )
    def test_degenerate_inputs_return_zero_not_an_exception(
        self, document_count: int, document_frequency: int
    ) -> None:
        """Never raise and never return a negative weight.

        A negative IDF would silently corrupt every score touching the term, which is far
        harder to notice than a zero.
        """
        assert inverse_frequency(document_count, document_frequency) == 0.0

    def test_log_base_rescales_by_a_constant(self) -> None:
        natural = inverse_frequency(1_000, 7, log_base="e")
        base_two = inverse_frequency(1_000, 7, log_base="2")
        base_ten = inverse_frequency(1_000, 7, log_base="10")
        assert base_two == pytest.approx(natural / math.log(2), rel=1e-12)
        assert base_ten == pytest.approx(natural / math.log(10), rel=1e-12)


# --------------------------------------------------------------------------------
# Formula 1.6 — A_i^j = Q_i^j · B_i, used for keyword extraction
# --------------------------------------------------------------------------------


class TestRawWeight:
    def test_matches_hand_computation(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        d1 = hand_corpus["d1"]

        # A(vector, d1) = 3 · ln(3/2)
        assert raw_weight(d1["vector"], idf["vector"]) == pytest.approx(
            1.2163953243244932, abs=1e-15
        )
        assert raw_weight(d1["model"], idf["model"]) == pytest.approx(0.8109302162163288, abs=1e-15)
        assert raw_weight(d1["search"], idf["search"]) == pytest.approx(
            0.4054651081081644, abs=1e-15
        )

    def test_keyword_extraction_ranks_rare_terms_above_frequent_ones(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """d3 holds `engine` 4× (rare) and `model` once (common).

        `engine` must lead — this is the behaviour formula 1.6 exists to produce.
        """
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        keywords = top_keywords(hand_corpus["d3"], idf)

        assert [lemma for lemma, _ in keywords] == ["engine", "model"]
        assert keywords[0][1] == pytest.approx(4 * math.log(3), abs=1e-15)

    def test_zero_weight_terms_are_excluded_from_keywords(self) -> None:
        """A term present in every document has weight 0 and is not a keyword."""
        keywords = top_keywords({"ubiquitous": 50, "rare": 1}, {"ubiquitous": 0.0, "rare": 2.5})
        assert [lemma for lemma, _ in keywords] == ["rare"]

    def test_ties_break_alphabetically_for_determinism(self) -> None:
        idf = {"beta": 1.0, "alpha": 1.0, "gamma": 1.0}
        keywords = top_keywords({"beta": 2, "alpha": 2, "gamma": 2}, idf)
        assert [lemma for lemma, _ in keywords] == ["alpha", "beta", "gamma"]

    def test_limit_is_respected(self) -> None:
        frequencies = {f"t{i}": i + 1 for i in range(50)}
        idf = dict.fromkeys(frequencies, 1.0)
        assert len(top_keywords(frequencies, idf, limit=5)) == 5


# --------------------------------------------------------------------------------
# Normalized weights w_dk — the search vectors
# --------------------------------------------------------------------------------


class TestNormalizedWeights:
    def test_d1_matches_exact_closed_form(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """d1's three terms share one IDF, so it cancels and w_dk = N_dk / sqrt(14).

        With frequencies 3, 2, 1 the denominator is `c·sqrt(3² + 2² + 1²) = c·sqrt(14)`
        and every numerator carries the same `c`, so the weights are exactly
        3/sqrt(14), 2/sqrt(14) and 1/sqrt(14) — no logarithm survives.
        """
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        weights, denominator = normalized_weights(hand_corpus["d1"], idf)

        root14 = math.sqrt(14)
        assert weights["vector"] == pytest.approx(3 / root14, abs=1e-15)
        assert weights["model"] == pytest.approx(2 / root14, abs=1e-15)
        assert weights["search"] == pytest.approx(1 / root14, abs=1e-15)
        assert denominator == pytest.approx(math.log(1.5) * root14, abs=1e-15)

    def test_d2_matches_exact_closed_form(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        weights, _ = normalized_weights(hand_corpus["d2"], idf)

        root5 = math.sqrt(5)
        assert weights["search"] == pytest.approx(2 / root5, abs=1e-15)
        assert weights["vector"] == pytest.approx(1 / root5, abs=1e-15)

    def test_d3_general_case_with_mixed_idf(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """d3 mixes IDFs, so nothing cancels and the decimals must match."""
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        weights, denominator = normalized_weights(hand_corpus["d3"], idf)

        assert denominator == pytest.approx(4.413115149969971, abs=1e-12)
        assert weights["engine"] == pytest.approx(0.995770335768905, abs=1e-12)
        assert weights["model"] == pytest.approx(0.09187730080211556, abs=1e-12)

    def test_document_norm_is_unity(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """‖D‖ = 1 by construction — w_dk is already L2-normalized over j.

        The property the retrieval path relies on when it uses the stored norm, and the
        invariant that detects a stale index if it ever drifts.
        """
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        for terms in hand_corpus.values():
            weights, _ = normalized_weights(terms, idf)
            assert euclidean_norm(weights) == pytest.approx(1.0, abs=1e-12)

    def test_weights_are_invariant_to_the_logarithm_base(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """Changing the base rescales every IDF by a constant, which cancels.

        This is why the report can state that the configured base affects only the
        absolute keyword weights from formula 1.6, never the ranking.
        """
        for terms in hand_corpus.values():
            per_base = [
                normalized_weights(
                    terms,
                    {
                        t: inverse_frequency(N, df, log_base=base)
                        for t, df in hand_document_frequencies.items()
                    },
                )[0]
                for base in ("e", "2", "10")
            ]
            reference = per_base[0]
            for other in per_base[1:]:
                assert other.keys() == reference.keys()
                for lemma in reference:
                    assert other[lemma] == pytest.approx(reference[lemma], rel=1e-12)

    def test_all_zero_idf_yields_a_zero_vector_not_a_division_by_zero(self) -> None:
        """Every term occurring in every document gives a zero denominator.

        A zero vector is the honest representation: the document really is
        indistinguishable from every other under this weighting.
        """
        weights, denominator = normalized_weights({"the": 10, "of": 5}, {"the": 0.0, "of": 0.0})
        assert denominator == 0.0
        assert set(weights.values()) == {0.0}

    def test_unknown_terms_are_treated_as_zero_idf(self) -> None:
        weights, _ = normalized_weights({"known": 1, "absent": 5}, {"known": 1.0})
        assert weights["absent"] == 0.0
        assert weights["known"] == pytest.approx(1.0, abs=1e-12)

    def test_empty_document(self) -> None:
        weights, denominator = normalized_weights({}, {})
        assert weights == {}
        assert denominator == 0.0


# --------------------------------------------------------------------------------
# Query vector — binary by specification
# --------------------------------------------------------------------------------


class TestQueryVector:
    def test_components_are_binary(self) -> None:
        assert query_vector(["vector", "search"]) == {"vector": 1.0, "search": 1.0}

    def test_repetition_does_not_increase_weight(self) -> None:
        """`w_qj` is 1 or 0, so repeating a query word has no effect.

        A real limitation of the specified model, recorded here so the behaviour is
        deliberate rather than accidental.
        """
        assert query_vector(["vector", "vector", "vector"]) == {"vector": 1.0}

    def test_norm_is_the_root_of_the_distinct_term_count(self) -> None:
        assert euclidean_norm(query_vector(["a", "b", "c", "d"])) == pytest.approx(2.0)


# --------------------------------------------------------------------------------
# Similarity — r(D, Q) = (D, Q) / (‖D‖ · ‖Q‖)
# --------------------------------------------------------------------------------


class TestCosineSimilarity:
    @pytest.fixture
    def vectors(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> dict[str, dict[str, float]]:
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        return {name: normalized_weights(terms, idf)[0] for name, terms in hand_corpus.items()}

    def test_matches_exact_closed_form(self, vectors: dict[str, dict[str, float]]) -> None:
        """For query "vector search": d1 scores 4/sqrt(28), d2 scores 3/sqrt(10)."""
        query = query_vector(["vector", "search"])

        assert cosine_similarity(vectors["d1"], query) == pytest.approx(
            4 / math.sqrt(28), abs=1e-15
        )
        assert cosine_similarity(vectors["d2"], query) == pytest.approx(
            3 / math.sqrt(10), abs=1e-15
        )

    def test_ranks_the_more_focused_document_higher(
        self, vectors: dict[str, dict[str, float]]
    ) -> None:
        """d2 outranks d1 although d1 contains `vector` three times.

        d2 is shorter and entirely about the query's terms, so a larger share of its
        vector points along the query. This is the length normalisation doing its job,
        and it is the behaviour that distinguishes the vector model from raw term counts.
        """
        query = query_vector(["vector", "search"])
        assert cosine_similarity(vectors["d2"], query) > cosine_similarity(vectors["d1"], query)

    def test_disjoint_document_scores_zero(self, vectors: dict[str, dict[str, float]]) -> None:
        query = query_vector(["vector", "search"])
        assert cosine_similarity(vectors["d3"], query) == 0.0

    def test_reduces_to_the_sum_of_weights_over_root_query_length(
        self, vectors: dict[str, dict[str, float]]
    ) -> None:
        """Because ‖D‖ = 1 and ‖Q‖ = sqrt(|q|), r(D,Q) = Σ w_dk / sqrt(|q|).

        Verifying the identity confirms the general implementation agrees with the
        simplification, and documents why the stored norm is safe to reuse.
        """
        terms = ["vector", "search"]
        query = query_vector(terms)
        for vector in vectors.values():
            expected = sum(vector.get(t, 0.0) for t in terms) / math.sqrt(len(terms))
            assert cosine_similarity(vector, query) == pytest.approx(expected, abs=1e-15)

    def test_identical_vectors_score_one(self) -> None:
        vector = {"a": 0.6, "b": 0.8}
        assert cosine_similarity(vector, vector) == pytest.approx(1.0, abs=1e-12)

    def test_precomputed_norm_matches_recomputed_norm(
        self, vectors: dict[str, dict[str, float]]
    ) -> None:
        query = query_vector(["vector", "search"])
        for vector in vectors.values():
            assert cosine_similarity(
                vector, query, document_norm=euclidean_norm(vector)
            ) == pytest.approx(cosine_similarity(vector, query), abs=1e-15)

    @pytest.mark.parametrize(
        ("document", "query"),
        [
            ({}, {"a": 1.0}),  # empty document
            ({"a": 1.0}, {}),  # query with no known terms
            ({"a": 0.0}, {"a": 1.0}),  # zero-norm document
        ],
    )
    def test_degenerate_inputs_score_zero(
        self, document: dict[str, float], query: dict[str, float]
    ) -> None:
        assert cosine_similarity(document, query) == 0.0


class TestVectorAlgebra:
    def test_scalar_product_is_symmetric(self) -> None:
        a = {"x": 1.5, "y": -2.0, "z": 3.0}
        b = {"y": 4.0, "z": 0.5, "w": 9.0}
        assert scalar_product(a, b) == pytest.approx(scalar_product(b, a))

    def test_scalar_product_uses_only_shared_terms(self) -> None:
        # 1.5·0 + (-2)·4 + 3·0.5 = -6.5
        a = {"x": 1.5, "y": -2.0, "z": 3.0}
        b = {"y": 4.0, "z": 0.5, "w": 9.0}
        assert scalar_product(a, b) == pytest.approx(-6.5)

    def test_disjoint_vectors_have_zero_product(self) -> None:
        assert scalar_product({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_euclidean_norm(self) -> None:
        assert euclidean_norm({"a": 3.0, "b": 4.0}) == pytest.approx(5.0)
        assert euclidean_norm({}) == 0.0


# --------------------------------------------------------------------------------
# Derivations — the glass-box explanation
# --------------------------------------------------------------------------------


class TestDerivations:
    def test_term_weight_derivation_reproduces_every_intermediate(self) -> None:
        derivation = derive_term_weight(
            lemma="vector",
            term_frequency=3,
            document_frequency=2,
            document_count=3,
            denominator=math.log(1.5) * math.sqrt(14),
            in_query=True,
        )

        assert derivation.inverse_frequency == pytest.approx(math.log(1.5), abs=1e-15)
        assert derivation.weight_raw == pytest.approx(3 * math.log(1.5), abs=1e-15)
        assert derivation.weight_norm == pytest.approx(3 / math.sqrt(14), abs=1e-15)
        assert derivation.in_query is True

    def test_zero_denominator_gives_zero_weight(self) -> None:
        derivation = derive_term_weight("t", 1, 1, 10, denominator=0.0)
        assert derivation.weight_norm == 0.0

    def test_cosine_derivation_agrees_with_the_plain_score(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        vector, _ = normalized_weights(hand_corpus["d1"], idf)
        query = query_vector(["vector", "search"])

        derivation = derive_cosine(vector, query)
        assert derivation.score == pytest.approx(cosine_similarity(vector, query), abs=1e-15)

    def test_contributions_sum_to_the_scalar_product(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """The per-term breakdown must account for the whole score, not approximate it."""
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        vector, _ = normalized_weights(hand_corpus["d1"], idf)
        derivation = derive_cosine(vector, query_vector(["vector", "search", "model"]))

        assert sum(c.product for c in derivation.contributions) == pytest.approx(
            derivation.scalar_product, abs=1e-15
        )
        assert sum(c.share for c in derivation.contributions) == pytest.approx(1.0, abs=1e-12)

    def test_contributions_are_ordered_by_descending_influence(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        vector, _ = normalized_weights(hand_corpus["d1"], idf)
        derivation = derive_cosine(vector, query_vector(["search", "vector", "model"]))

        assert [c.lemma for c in derivation.contributions] == ["vector", "model", "search"]

    def test_missing_query_terms_are_reported(
        self, hand_corpus: dict[str, dict[str, int]], hand_document_frequencies: dict[str, int]
    ) -> None:
        """Query words absent from the document explain a lower-than-expected rank."""
        idf = {t: inverse_frequency(N, df) for t, df in hand_document_frequencies.items()}
        vector, _ = normalized_weights(hand_corpus["d2"], idf)
        derivation = derive_cosine(vector, query_vector(["vector", "engine", "absent"]))

        assert derivation.missing_terms == ["absent", "engine"]
        assert [c.lemma for c in derivation.contributions] == ["vector"]
