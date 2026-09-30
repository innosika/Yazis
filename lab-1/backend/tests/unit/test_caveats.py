"""Presentation caveats for degenerate metrics (HANDOFF task 1b)."""

from __future__ import annotations

from irs.eval.caveats import MetricCaveat, degenerate_keys, metric_caveats
from irs.eval.metrics import QueryJudgments


def _known_item(n: int) -> dict[int, QueryJudgments]:
    return {
        q: QueryJudgments(relevant=frozenset({q * 100}), gains={q * 100: 3.0}) for q in range(n)
    }


def _topical() -> dict[int, QueryJudgments]:
    return {
        1: QueryJudgments(relevant=frozenset({1, 2, 3}), non_relevant=frozenset({4, 5})),
        2: QueryJudgments(relevant=frozenset({7}), non_relevant=frozenset({8, 9, 10})),
        3: QueryJudgments(relevant=frozenset({11, 12}), non_relevant=frozenset({13})),
    }


def test_known_item_collection_suppresses_recall_bpref_precision_f1() -> None:
    caveats = metric_caveats(_known_item(30), top_k=100)
    assert degenerate_keys(caveats) == {"recall", "bpref", "precision", "f1"}


def test_known_item_precision_note_states_the_ceiling() -> None:
    caveats = metric_caveats(_known_item(5), top_k=100)
    precision = next(c for c in caveats if c.metric_key == "precision")
    assert "0.0100" in precision.note
    assert "top_k = 100" in precision.note


def test_topical_collection_only_annotates() -> None:
    caveats = metric_caveats(_topical(), top_k=100)
    assert degenerate_keys(caveats) == frozenset()
    annotated = {c.metric_key for c in caveats if c.kind == "annotate"}
    assert annotated == {"precision", "recall"}


def test_one_topic_with_r_gt_1_breaks_the_known_item_shape() -> None:
    judgments = _known_item(4)
    judgments[99] = QueryJudgments(relevant=frozenset({1, 2}))
    assert degenerate_keys(metric_caveats(judgments, top_k=100)) == frozenset()


def test_judged_non_relevant_breaks_the_known_item_shape() -> None:
    judgments = _known_item(4)
    judgments[0] = QueryJudgments(relevant=frozenset({0}), non_relevant=frozenset({5}))
    assert degenerate_keys(metric_caveats(judgments, top_k=100)) == frozenset()


def test_single_assessor_adds_a_table_wide_note() -> None:
    caveats = metric_caveats(_topical(), top_k=50, single_assessor=True)
    table_wide = [c for c in caveats if c.metric_key == "*"]
    assert len(table_wide) == 1
    assert table_wide[0].kind == "annotate"
    assert "coincide" in table_wide[0].note


def test_empty_judgments_produce_no_caveats() -> None:
    assert metric_caveats({}, top_k=100) == []


def test_caveat_is_hashable_and_frozen() -> None:
    caveat = MetricCaveat("recall", "degenerate", "x")
    assert hash(caveat)
