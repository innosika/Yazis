"""Golden tests for the IR quality metrics.

Three independent kinds of check, because they catch different classes of error:

1. **The ROMIP appendix's own worked example** — 20 documents, 4 relevant at ranks
   1, 2, 4, 15, with the published interpolated curve. This catches *convention* errors
   (the recall-to-count conversion, the interpolation direction) that agreement with
   another implementation would not, because both could share the same wrong convention.
2. **The four properties the appendix states for average precision**, asserted directly.
3. **Hand-computed values** for the rank-based measures, including every documented trap:
   short runs, unretrieved relevant documents, and empty result lists.
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import ClassVar

import pytest

from irs.eval.metrics import (
    ELEVEN_POINT_LEVELS,
    QueryJudgments,
    average_precision,
    bpref,
    bpref_romip,
    dcg,
    err,
    f_measure,
    interpolated_precision_11pt,
    interpolated_precision_11pt_nonzeroing,
    ndcg,
    pfound,
    pr_curve,
    precision_at_k,
    r_precision,
    reciprocal_rank,
    set_precision,
    set_recall,
)


def judgments(
    relevant: set[int],
    non_relevant: set[int] = frozenset(),
    **gains: float,
) -> QueryJudgments:
    """Build judgments, defaulting every relevant document to the top grade."""
    graded = {int(k.lstrip("d")): v for k, v in gains.items()}
    if not graded:
        graded = dict.fromkeys(relevant, 3.0)
    return QueryJudgments(
        relevant=frozenset(relevant),
        non_relevant=frozenset(non_relevant),
        gains=graded,
    )


# ================================================================================
# The appendix's worked example
# ================================================================================


class TestRomipWorkedExample:
    """«Пример» from section 4 of Приложение А.

    A collection of 20 documents of which 4 are relevant; the system returns all 20 with
    the relevant ones at ranks 1, 2, 4 and 15. The appendix publishes the resulting
    11-point interpolated curve, which is reproduced here exactly.
    """

    RANKED: ClassVar[list[int]] = list(range(1, 21))
    RELEVANT: ClassVar[set[int]] = {1, 2, 4, 15}

    #: Published values: 1.0 for recall 0.0–0.5, 0.75 at 0.6 and 0.7, 4/15 at 0.8–1.0.
    EXPECTED: ClassVar[list[float]] = [
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        0.75,
        0.75,
        4 / 15,
        4 / 15,
        4 / 15,
    ]

    @pytest.fixture
    def example(self) -> QueryJudgments:
        return judgments(self.RELEVANT, non_relevant=set(self.RANKED) - self.RELEVANT)

    def test_interpolated_curve_matches_the_published_values(self, example: QueryJudgments) -> None:
        """The single most important test in the suite.

        The recall-to-count conversion is a documented point of disagreement between
        implementations: the appendix's definition and example require a **ceiling**,
        while current ``trec_eval`` rounds. Rounding produces a visibly different curve
        (1.0 at recall 0.6 instead of 0.75), so this test is what pins the convention to
        the document the assignment actually cites.
        """
        curve = interpolated_precision_11pt([(self.RANKED, example)])

        assert len(curve) == 11
        for level, got, want in zip(ELEVEN_POINT_LEVELS, curve, self.EXPECTED, strict=True):
            assert got == pytest.approx(want, abs=1e-9), (
                f"recall {level}: got {got:.6f}, appendix says {want:.6f}"
            )

    def test_trec_convention_differs_and_is_reproducible(self, example: QueryJudgments) -> None:
        """The alternative convention is available for cross-validation.

        Asserted to *differ* so that a future change silently unifying the two cannot
        pass unnoticed — the discrepancy is a real property of the two specifications.
        """
        trec = interpolated_precision_11pt([(self.RANKED, example)], convention="trec")
        romip = interpolated_precision_11pt([(self.RANKED, example)])

        assert trec != romip
        # Under rounding, recall 0.6 needs round(2.4) = 2 relevant documents, reached at
        # rank 2 where precision is still 1.0.
        assert trec[6] == pytest.approx(1.0, abs=1e-9)
        assert romip[6] == pytest.approx(0.75, abs=1e-9)

    def test_curve_is_non_increasing(self, example: QueryJudgments) -> None:
        """Interpolated precision can never rise with recall, by construction."""
        curve = interpolated_precision_11pt([(self.RANKED, example)])
        assert all(a >= b - 1e-12 for a, b in pairwise(curve))

    def test_derived_scalars_for_the_example(self, example: QueryJudgments) -> None:
        # P@5: relevant at ranks 1, 2, 4 → 3/5.
        assert precision_at_k(self.RANKED, example, 5) == pytest.approx(0.6)
        # P@10: still 3 (the fourth is at rank 15) → 3/10.
        assert precision_at_k(self.RANKED, example, 10) == pytest.approx(0.3)
        # R-Precision: R = 4, so P@4 = 3/4.
        assert r_precision(self.RANKED, example) == pytest.approx(0.75)
        # AP = (1/1 + 2/2 + 3/4 + 4/15) / 4.
        assert average_precision(self.RANKED, example) == pytest.approx(
            (1 / 1 + 2 / 2 + 3 / 4 + 4 / 15) / 4, abs=1e-12
        )
        assert set_recall(self.RANKED, example) == pytest.approx(1.0)
        assert set_precision(self.RANKED, example) == pytest.approx(4 / 20)


# ================================================================================
# Average precision — the appendix's stated properties
# ================================================================================


class TestAveragePrecisionProperties:
    """The four properties section 3.3 of the appendix asserts for AveragePrec."""

    def test_never_exceeds_recall(self) -> None:
        cases = [
            ([1, 2, 3, 4, 5], {1, 3}),
            ([1, 2, 3, 4, 5], {4, 5}),
            ([5, 4, 3, 2, 1], {1, 2, 3}),
            ([1, 2, 3], {1, 2, 3, 9, 10}),  # some relevant never retrieved
        ]
        for ranked, relevant in cases:
            marks = judgments(relevant)
            assert average_precision(ranked, marks) <= set_recall(ranked, marks) + 1e-12

    def test_equals_recall_when_all_relevant_are_at_the_top(self) -> None:
        """With every relevant document leading the ranking, every P@i is 1."""
        marks = judgments({1, 2, 3})
        ranked = [1, 2, 3, 4, 5, 6]
        assert average_precision(ranked, marks) == pytest.approx(1.0)
        assert set_recall(ranked, marks) == pytest.approx(1.0)

        # And with only some retrieved, AP equals recall exactly.
        marks = judgments({1, 2, 3, 4})
        assert average_precision([1, 2, 9, 8], marks) == pytest.approx(0.5)
        assert set_recall([1, 2, 9, 8], marks) == pytest.approx(0.5)

    def test_tail_after_the_last_relevant_document_is_irrelevant(self) -> None:
        """«отсекается "хвост"» — appending non-relevant documents cannot change AP."""
        marks = judgments({1, 3})
        base = average_precision([1, 2, 3], marks)
        for padding in (1, 5, 50):
            assert average_precision([1, 2, 3, *range(100, 100 + padding)], marks) == (
                pytest.approx(base, abs=1e-12)
            )

    def test_denominator_is_r_from_the_judgments(self) -> None:
        """Unretrieved relevant documents must still count in the denominator.

        The single most common MAP bug is dividing by the number of relevant documents
        *found*, which turns a run that missed three quarters of them into a perfect one.
        """
        marks = judgments({1, 2, 3, 4})
        # Only document 1 retrieved, at rank 1: AP = (1/1) / 4 = 0.25, not 1.0.
        assert average_precision([1, 9, 8, 7], marks) == pytest.approx(0.25)

    def test_zero_when_nothing_relevant_is_retrieved(self) -> None:
        assert average_precision([7, 8, 9], judgments({1, 2})) == 0.0

    def test_ranking_earlier_is_always_better(self) -> None:
        """Padding ids are kept disjoint from the relevant id.

        A ranking that repeats a document is malformed and can push AP above 1; the
        runner rejects such runs (see :class:`TestMalformedRuns`) rather than the metric
        silently de-duplicating and hiding a ranker bug.
        """
        marks = judgments({5})
        scores = [
            average_precision([*range(100, 100 + padding), 5], marks) for padding in (0, 1, 4, 9)
        ]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] == pytest.approx(1.0)
        assert scores[-1] == pytest.approx(0.1)


# ================================================================================
# The documented traps
# ================================================================================


class TestPrecisionAtK:
    def test_denominator_is_k_even_for_a_short_run(self) -> None:
        """«Если система выдала менее n документов...» — the denominator stays `k`.

        Confirmed identical in ``trec_eval``'s ``m_P.c``. Using
        ``min(k, len(ranked))`` would score this run 1.0 instead of 0.2.
        """
        marks = judgments({1})
        assert precision_at_k([1], marks, 5) == pytest.approx(0.2)
        assert precision_at_k([1], marks, 10) == pytest.approx(0.1)

    def test_empty_run(self) -> None:
        assert precision_at_k([], judgments({1}), 10) == 0.0

    def test_zero_cutoff_is_not_a_division_error(self) -> None:
        assert precision_at_k([1, 2], judgments({1}), 0) == 0.0

    def test_unjudged_documents_count_as_non_relevant(self) -> None:
        """The ROMIP 2004 convention, since that edition has no bpref."""
        marks = judgments({1}, non_relevant={2})
        # Document 99 was never judged; it still occupies a position.
        assert precision_at_k([1, 99, 2], marks, 3) == pytest.approx(1 / 3)


class TestRPrecision:
    def test_divides_by_r_not_by_positions_examined(self) -> None:
        """`R = 5` but only 2 documents retrieved, both relevant.

        ``trec_eval``'s ``m_Rprec.c`` scans ``min(n, R)`` positions and divides by `R`,
        giving 2/5. Dividing by the 2 positions examined would give a perfect 1.0.
        """
        marks = judgments({1, 2, 3, 4, 5})
        assert r_precision([1, 2], marks) == pytest.approx(0.4)

    def test_equals_precision_and_recall_at_that_point(self) -> None:
        marks = judgments({1, 2, 3, 4})
        ranked = [1, 9, 2, 8, 3, 7, 4]
        # At rank R = 4: 2 of 4 relevant retrieved → both precision and recall are 0.5.
        assert r_precision(ranked, marks) == pytest.approx(0.5)
        assert precision_at_k(ranked, marks, 4) == pytest.approx(0.5)

    def test_no_relevant_documents(self) -> None:
        assert r_precision([1, 2], judgments(set())) == 0.0


class TestElevenPointZeroing:
    def test_unreached_levels_contribute_zero_to_the_mean(self) -> None:
        """The TREC method's zeroing rule, and the most common 11-point bug.

        Two queries: one perfect, one that retrieves nothing relevant. At every recall
        level the average must be halved, not left at the good query's value.
        """
        good = ([1, 2], judgments({1, 2}))
        bad = ([7, 8], judgments({5, 6}))

        curve = interpolated_precision_11pt([good, bad])
        assert curve[0] == pytest.approx(0.5)
        assert curve[10] == pytest.approx(0.5)

    def test_nonzeroing_variant_averages_only_over_reached_levels(self) -> None:
        """The reconstruction of ROMIP's undefined metric #8.

        One query retrieves both relevant documents, the other only one of two. At recall
        0.5 both contribute; at recall 1.0 only the complete run does, so the partial
        query is omitted from that level's mean instead of dragging it to zero.
        """
        complete = ([1, 2], judgments({1, 2}))
        partial = ([3, 9], judgments({3, 4}))  # finds 3, never finds 4

        curve, support = interpolated_precision_11pt_nonzeroing([complete, partial])

        # Recall 0.5 needs 1 relevant document; both runs reach it.
        assert support[5] == 2
        # Recall 1.0 needs both; only the complete run reaches it, and scores 1.0 there.
        assert support[10] == 1
        assert curve[10] == pytest.approx(1.0)

        # The TREC variant instead averages a zero in for the partial run.
        zeroing = interpolated_precision_11pt([complete, partial])
        assert zeroing[10] == pytest.approx(0.5)
        assert curve[10] > zeroing[10]

    def test_recall_zero_is_reached_even_when_nothing_relevant_is_retrieved(self) -> None:
        """Recall 0 is reached by the empty prefix, so it is never an "unreached" level.

        A run that retrieves nothing relevant therefore contributes an interpolated
        precision of 0 at level 0 — it is counted, not skipped. Worth pinning because it
        is the one level where the zeroing and non-zeroing variants agree.
        """
        good = ([1, 2], judgments({1, 2}))
        bad = ([7, 8], judgments({5, 6}))

        curve, support = interpolated_precision_11pt_nonzeroing([good, bad])
        assert support[0] == 2
        assert curve[0] == pytest.approx(0.5)
        # Beyond level 0 the failing run reaches nothing.
        assert support[10] == 1

    def test_support_falls_at_high_recall(self) -> None:
        """Why support must be published alongside the non-zeroing curve."""
        full = ([1, 2, 3, 4], judgments({1, 2, 3, 4}))
        partial = ([1, 9, 9, 9], judgments({1, 2, 3, 4}))

        _, support = interpolated_precision_11pt_nonzeroing([full, partial])
        assert support[0] == 2
        assert support[10] == 1  # only the complete run reaches recall 1.0

    def test_empty_input(self) -> None:
        assert interpolated_precision_11pt([]) == [0.0] * 11


class TestRawPrCurve:
    def test_points_are_recorded_at_each_relevant_document(self) -> None:
        marks = judgments({1, 3})
        breakdown = pr_curve([1, 2, 3, 4], marks)
        assert breakdown.points == [
            pytest.approx((0.5, 1.0)),
            pytest.approx((1.0, 2 / 3)),
        ]
        assert breakdown.max_recall == pytest.approx(1.0)

    def test_sawtooth_shape_is_preserved(self) -> None:
        """Precision may fall between relevant documents — that is the point of showing
        the raw curve next to the interpolated one."""
        marks = judgments({1, 5})
        points = pr_curve([1, 2, 3, 4, 5], marks).points
        assert points[0][1] > points[1][1]


# ================================================================================
# Set measures
# ================================================================================


class TestSetMeasures:
    def test_precision_and_recall(self) -> None:
        marks = judgments({1, 2, 3})
        ranked = [1, 2, 9]
        assert set_precision(ranked, marks) == pytest.approx(2 / 3)
        assert set_recall(ranked, marks) == pytest.approx(2 / 3)

    def test_precision_depends_on_run_length(self) -> None:
        """Why `top_k` must be published beside these numbers."""
        marks = judgments({1})
        assert set_precision([1], marks) == pytest.approx(1.0)
        assert set_precision([1, 2, 3, 4, 5], marks) == pytest.approx(0.2)

    def test_empty_run(self) -> None:
        assert set_precision([], judgments({1})) == 0.0
        assert set_recall([], judgments({1})) == 0.0

    @pytest.mark.parametrize(
        ("precision", "recall", "expected"),
        [
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 0.0),  # the appendix: F = 0 when either component is 0
            (1.0, 0.0, 0.0),
            (0.5, 0.5, 0.5),  # F = p = r when p = r
            (0.2, 0.8, 2 * 0.2 * 0.8 / 1.0),
        ],
    )
    def test_f_measure(self, precision: float, recall: float, expected: float) -> None:
        assert f_measure(precision, recall) == pytest.approx(expected)

    def test_f_lies_between_the_minimum_and_the_arithmetic_mean(self) -> None:
        """A property the appendix states: min(p,r) ≤ F ≤ (p+r)/2."""
        for precision, recall in ((0.2, 0.9), (0.7, 0.3), (0.5, 0.51)):
            value = f_measure(precision, recall)
            assert min(precision, recall) <= value + 1e-12
            assert value <= (precision + recall) / 2 + 1e-12


# ================================================================================
# Graded measures (ROMIP 2009/2010 additions)
# ================================================================================


class TestGradedMeasures:
    def test_dcg_uses_exponential_gain_and_log2_of_one_plus_rank(self) -> None:
        """ROMIP's `2^g − 1` gain with the standard `log2(1 + rank)` discount.

        Rank 1 is undiscounted, so a single top-graded document at rank 1 scores exactly
        `2^3 − 1 = 7`.
        """
        marks = QueryJudgments(relevant=frozenset({1}), gains={1: 3.0})
        assert dcg([1], marks, 10) == pytest.approx(7.0)
        # At rank 2 the discount is log2(3).
        assert dcg([9, 1], marks, 10) == pytest.approx(7.0 / math.log2(3))

    def test_ndcg_is_one_for_the_ideal_ranking(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1, 2, 3}), gains={1: 3.0, 2: 2.0, 3: 1.0})
        assert ndcg([1, 2, 3], marks, 10) == pytest.approx(1.0)

    def test_ndcg_rewards_putting_higher_grades_first(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1, 2}), gains={1: 3.0, 2: 1.0})
        assert ndcg([1, 2], marks, 10) > ndcg([2, 1], marks, 10)

    def test_ndcg_is_bounded(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1, 2}), gains={1: 3.0, 2: 2.0})
        for ranked in ([1, 2], [2, 1], [9, 1, 2], [1, 9, 2]):
            assert 0.0 <= ndcg(ranked, marks, 10) <= 1.0 + 1e-12

    def test_ndcg_zero_when_nothing_graded_is_retrieved(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1}), gains={1: 3.0})
        assert ndcg([7, 8], marks, 10) == 0.0

    def test_err_is_bounded_and_prefers_early_relevance(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1}), gains={1: 3.0})
        early = err([1, 2, 3], marks)
        late = err([2, 3, 1], marks)
        assert 0.0 < early <= 1.0
        assert early > late

    def test_pfound_is_bounded_and_prefers_early_relevance(self) -> None:
        marks = QueryJudgments(relevant=frozenset({1}), gains={1: 3.0})
        early = pfound([1, 2, 3], marks)
        late = pfound([2, 3, 1], marks)
        assert 0.0 < early <= 1.0
        assert early > late

    def test_pfound_first_position_is_undiscounted(self) -> None:
        """`pLook(1) = 1`, so a top-grade document at rank 1 contributes `pRel` in full."""
        marks = QueryJudgments(relevant=frozenset({1}), gains={1: 3.0})
        assert pfound([1], marks) == pytest.approx(0.5)


class TestBpref:
    def test_perfect_ranking_scores_one(self) -> None:
        marks = judgments({1, 2}, non_relevant={3, 4})
        assert bpref([1, 2, 3, 4], marks) == pytest.approx(1.0)

    def test_non_relevant_documents_ranked_first_reduce_the_score(self) -> None:
        marks = judgments({1, 2}, non_relevant={3, 4})
        assert bpref([3, 4, 1, 2], marks) < bpref([1, 2, 3, 4], marks)

    def test_unjudged_documents_are_skipped_not_penalised(self) -> None:
        """The property bpref exists for, and the reason it is reported alongside the
        2004 metrics when pool coverage is poor."""
        marks = judgments({1, 2}, non_relevant={3})
        with_unjudged = bpref([99, 98, 1, 2], marks)  # 99, 98 never judged
        without = bpref([1, 2], marks)
        assert with_unjudged == pytest.approx(without)

    def test_romip_variant_uses_a_different_denominator(self) -> None:
        """ROMIP prints `/R`; trec_eval uses `/min(N, R)`. They differ when `N < R`.

        Asserted to differ so the divergence is a recorded fact rather than a surprise.
        """
        marks = judgments({1, 2, 3, 4}, non_relevant={5})  # N = 1 < R = 4
        assert bpref([5, 1, 2, 3, 4], marks) != pytest.approx(bpref_romip([5, 1, 2, 3, 4], marks))

    def test_bpref_10_offsets_the_denominator(self) -> None:
        marks = judgments({1, 2}, non_relevant={3, 4})
        assert bpref_romip([3, 1, 2], marks, offset=10) > bpref_romip([3, 1, 2], marks)

    def test_no_relevant_documents(self) -> None:
        assert bpref([1, 2], judgments(set())) == 0.0


class TestReciprocalRank:
    @pytest.mark.parametrize(
        ("ranked", "expected"), [([1], 1.0), ([9, 1], 0.5), ([9, 8, 1], 1 / 3), ([9, 8], 0.0)]
    )
    def test_default_ruler(self, ranked: list[int], expected: float) -> None:
        assert reciprocal_rank(ranked, judgments({1})) == pytest.approx(expected)

    def test_custom_ruler(self) -> None:
        """ROMIP 2010 defines RR via a ruler, not necessarily `1/x`."""
        ruler = [1.0, 0.5, 0.33, 0.2, 0.1]
        assert reciprocal_rank([9, 8, 1], judgments({1}), ruler=ruler) == pytest.approx(0.33)
        # Beyond the ruler's length the score is 0.
        assert reciprocal_rank([*range(9, 20), 1], judgments({1}), ruler=ruler) == 0.0


class TestMalformedRuns:
    """A ranking must not repeat a document.

    Metrics are deliberately not defensive about this: de-duplicating inside
    :func:`average_precision` would let a ranker that emits the same document twice score
    normally, hiding the bug. Instead the property is documented here and enforced by the
    evaluation runner before any metric is computed.
    """

    def test_duplicates_would_inflate_average_precision(self) -> None:
        marks = judgments({5})
        honest = average_precision([1, 2, 3, 4, 5], marks)
        duplicated = average_precision([1, 2, 3, 4, 5, 6, 7, 8, 9, 5], marks)

        assert honest == pytest.approx(0.2)
        # Counted twice, so the score exceeds what a single hit can earn — which is why
        # the runner validates uniqueness rather than the metric tolerating it.
        assert duplicated > honest
