"""Cross-validation of the metric core against NIST ``trec_eval`` (via ``pytrec_eval``).

``pytrec_eval`` vendors the actual ``trec_eval`` C sources, so agreement to 1e-9 is
agreement with the reference implementation. Two *deliberate* disagreements are asserted
rather than papered over, because they are conventions ROMIP fixes differently:

* ROMIP excludes topics with no relevant document from every mean; modern ``trec_eval``
  keeps them (scoring 0). The per-topic values agree; the means differ.
* The 11-point curve's recall→document-count conversion. The metric reference expected
  modern ``trec_eval`` to use ``lround`` and ROMIP the historical ceiling. Running the
  vendored ``trec_eval`` settles it: it computes ``(long)(level·R + 0.9)`` in double
  precision — the ceiling, *except* where ``level·R`` lands a hair below an integer (0.7·3
  = 2.0999…) and the truncation drops a document. So the **ROMIP ceiling agrees with
  trec_eval** everywhere but at those floating-point edge levels, and ``lround`` (kept in
  the metric core as ``convention="trec"``) is the one that differs on the appendix's own
  worked example. The tests assert exactly this; the metric core is unchanged.
"""

from __future__ import annotations

import math
import statistics

import pytest

from irs.eval import metrics as m
from irs.eval.trec_format import format_qrels, format_run, to_pytrec_eval

pytrec_eval = pytest.importorskip("pytrec_eval")

TOL = 1e-9


def _fixture() -> tuple[dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments]]:
    """Five topics: the appendix example, three ordinary ones, one with no relevant document."""
    rankings: dict[int, list[tuple[int, float]]] = {}
    judgments: dict[int, m.QueryJudgments] = {}

    # Topic 1 — the appendix's worked example: 20 returned, relevant at ranks 1, 2, 4, 15.
    docs = list(range(101, 121))
    rankings[1] = [(d, 1.0 - i * 0.01) for i, d in enumerate(docs)]
    relevant = {docs[0], docs[1], docs[3], docs[14]}
    judgments[1] = m.QueryJudgments(
        relevant=frozenset(relevant),
        non_relevant=frozenset(set(docs) - relevant),
        gains=dict.fromkeys(relevant, 1.0),
    )

    # Topic 2 — R = 3, two found (ranks 2 and 5), one missed; some unjudged in the run.
    rankings[2] = [(201, 0.9), (202, 0.8), (203, 0.7), (204, 0.6), (205, 0.5), (206, 0.4)]
    judgments[2] = m.QueryJudgments(
        relevant=frozenset({202, 205, 299}),
        non_relevant=frozenset({201, 204}),
        gains={202: 1.0, 205: 1.0, 299: 1.0},
    )

    # Topic 3 — short run of 3, R = 2, both found at the top.
    rankings[3] = [(301, 0.9), (302, 0.8), (303, 0.7)]
    judgments[3] = m.QueryJudgments(
        relevant=frozenset({301, 302}), non_relevant=frozenset({303}), gains={301: 1.0, 302: 1.0}
    )

    # Topic 4 — R = 1 found deep at rank 12.
    rankings[4] = [(400 + i, 1.0 - i * 0.05) for i in range(1, 16)]
    judgments[4] = m.QueryJudgments(
        relevant=frozenset({412}), non_relevant=frozenset({401, 402, 403}), gains={412: 1.0}
    )

    # Topic 5 — judged, but nothing relevant: ROMIP drops it, trec_eval keeps it at 0.
    rankings[5] = [(501, 0.9), (502, 0.8)]
    judgments[5] = m.QueryJudgments(
        relevant=frozenset(), non_relevant=frozenset({501, 502, 503}), gains={}
    )
    return rankings, judgments


def _evaluate(
    rankings: dict[int, list[tuple[int, float]]], judgments: dict[int, m.QueryJudgments]
) -> dict[str, dict[str, float]]:
    qrels, run = to_pytrec_eval(rankings, judgments)
    measures = {
        "map",
        "P_5",
        "P_10",
        "Rprec",
        "recall_100",
        "bpref",
        "ndcg_cut_10",
        "iprec_at_recall_0.00",
        "iprec_at_recall_0.10",
        "iprec_at_recall_0.20",
        "iprec_at_recall_0.30",
        "iprec_at_recall_0.40",
        "iprec_at_recall_0.50",
        "iprec_at_recall_0.60",
        "iprec_at_recall_0.70",
        "iprec_at_recall_0.80",
        "iprec_at_recall_0.90",
        "iprec_at_recall_1.00",
    }
    evaluator = pytrec_eval.RelevanceEvaluator(qrels, measures)
    result: dict[str, dict[str, float]] = evaluator.evaluate(run)
    return result


@pytest.fixture(scope="module")
def reference() -> tuple[
    dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments], dict[str, dict[str, float]]
]:
    rankings, judgments = _fixture()
    return rankings, judgments, _evaluate(rankings, judgments)


def _ranked(rankings: dict[int, list[tuple[int, float]]], qid: int) -> list[int]:
    return [d for d, _ in rankings[qid]]


@pytest.mark.parametrize("qid", [1, 2, 3, 4])
def test_scalar_metrics_agree_per_topic(
    reference: tuple[
        dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments], dict[str, dict[str, float]]
    ],
    qid: int,
) -> None:
    rankings, judgments, ref = reference
    ranked, marks = _ranked(rankings, qid), judgments[qid]
    got = ref[str(qid)]

    assert m.average_precision(ranked, marks) == pytest.approx(got["map"], abs=TOL)
    assert m.precision_at_k(ranked, marks, 5) == pytest.approx(got["P_5"], abs=TOL)
    assert m.precision_at_k(ranked, marks, 10) == pytest.approx(got["P_10"], abs=TOL)
    assert m.r_precision(ranked, marks) == pytest.approx(got["Rprec"], abs=TOL)
    assert m.set_recall(ranked[:100], marks) == pytest.approx(got["recall_100"], abs=TOL)
    assert m.bpref(ranked, marks) == pytest.approx(got["bpref"], abs=TOL)
    # All gains are 1, so ROMIP's 2^g − 1 gain equals trec_eval's linear gain.
    assert m.ndcg(ranked, marks, 10) == pytest.approx(got["ndcg_cut_10"], abs=TOL)


def _trec_eval_count(level: float, r: int) -> int:
    """What ``m_iprec_at_recall.c`` does: ``(long)(level * R + 0.9)`` in doubles."""
    return int(level * r + 0.9)


@pytest.mark.parametrize("qid", [1, 2, 3, 4])
def test_eleven_point_curve_agrees_with_trec_eval_under_the_ceiling_convention(
    reference: tuple[
        dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments], dict[str, dict[str, float]]
    ],
    qid: int,
) -> None:
    """The appendix's ceiling reproduces trec_eval at every level whose count trec_eval
    also rounds up; the only disagreements are trec_eval's own floating-point truncations."""
    rankings, judgments, ref = reference
    marks = judgments[qid]
    precisions, _ = m._interpolated_precisions(_ranked(rankings, qid), marks, convention="romip")

    disagreements: list[float] = []
    for level, value in zip(m.ELEVEN_POINT_LEVELS, precisions, strict=True):
        expected = ref[str(qid)][f"iprec_at_recall_{level:.2f}"]
        ceiling_count = math.ceil(level * marks.r - 1e-12) if level > 0 else 0
        if _trec_eval_count(level, marks.r) == ceiling_count:
            assert (value or 0.0) == pytest.approx(expected, abs=TOL), (qid, level)
        else:
            disagreements.append(level)
            assert (value or 0.0) != pytest.approx(expected, abs=TOL), (qid, level)

    # Topic 2 (R = 3) is the one case in the fixture: 0.7 · 3 = 2.0999… + 0.9 truncates to 2.
    assert disagreements == ([0.7] if qid == 2 else []), (qid, disagreements)


def test_mismatch_1_zero_relevant_topic_is_excluded_by_romip_but_kept_by_trec_eval(
    reference: tuple[
        dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments], dict[str, dict[str, float]]
    ],
) -> None:
    rankings, judgments, ref = reference

    # trec_eval scores topic 5 (no relevant document) as 0 and averages it in.
    assert "5" in ref
    assert ref["5"]["map"] == 0.0
    trec_mean = statistics.fmean(ref[q]["map"] for q in ref)

    # ROMIP: the topic is not part of the evaluation at all.
    romip_topics = [q for q, marks in judgments.items() if marks.has_relevant]
    assert 5 not in romip_topics
    romip_mean = statistics.fmean(
        m.average_precision(_ranked(rankings, q), judgments[q]) for q in romip_topics
    )

    assert romip_mean != pytest.approx(trec_mean, abs=TOL)
    # …and the two agree exactly once trec_eval's mean is taken over the same four topics.
    assert romip_mean == pytest.approx(
        statistics.fmean(ref[str(q)]["map"] for q in romip_topics), abs=TOL
    )


def test_mismatch_2_recall_level_rounding_on_the_appendix_example(
    reference: tuple[
        dict[int, list[tuple[int, float]]], dict[int, m.QueryJudgments], dict[str, dict[str, float]]
    ],
) -> None:
    """R = 4, recall 0.6: ceiling needs 3 documents (→ 0.75), lround needs 2 (→ 1.0).

    The vendored trec_eval reports 0.75 — the ceiling, the same rule as the appendix. The
    ``lround`` variant stays in the metric core only as the documented alternative and is
    asserted here to be the convention that disagrees with the reference implementation.
    """
    rankings, judgments, ref = reference
    ranked, marks = _ranked(rankings, 1), judgments[1]

    romip, _ = m._interpolated_precisions(ranked, marks, convention="romip")
    lround, _ = m._interpolated_precisions(ranked, marks, convention="trec")

    # The appendix's printed values, verbatim: 1.0 ×6, 0.75 ×2, 0.27 ×3.
    expected_romip = [1.0] * 6 + [0.75] * 2 + [4 / 15] * 3
    for value, expected in zip(romip, expected_romip, strict=True):
        assert (value or 0.0) == pytest.approx(expected, abs=1e-9)

    assert ref["1"]["iprec_at_recall_0.60"] == pytest.approx(0.75, abs=TOL)
    assert (romip[6] or 0.0) == pytest.approx(ref["1"]["iprec_at_recall_0.60"], abs=TOL)
    assert (lround[6] or 0.0) == pytest.approx(1.0)
    assert romip[6] != lround[6]


def test_export_round_trip_shapes() -> None:
    rankings, judgments = _fixture()
    run_text = format_run(rankings, run_id="irs-test")
    qrels_text = format_qrels(judgments)
    assert all(len(line.split()) == 6 for line in run_text.strip().splitlines())
    assert all(len(line.split()) == 4 for line in qrels_text.strip().splitlines())
    # Judged non-relevant documents are written explicitly (bpref depends on it).
    assert "2 0 201 0" in qrels_text
