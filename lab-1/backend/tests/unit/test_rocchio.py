"""Rocchio feedback and sparse-vector helpers, verified by hand."""

from __future__ import annotations

import math

import pytest

from irs.selection.base import ParsedQuery
from irs.selection.rocchio import (
    binary_query_vector,
    diff,
    idf_query_vector,
    norm,
    rocchio,
    truncate,
)


def test_rocchio_hand_computed() -> None:
    query = {1: 1.0}
    relevant = [{1: 0.6, 2: 0.8}, {2: 1.0}]
    non_relevant = [{3: 1.0}]

    result = rocchio(query, relevant, non_relevant, alpha=1.0, beta=0.75, gamma=0.15)

    # term 1: 1·1 + 0.75/2·0.6 = 1.225 ; term 2: 0.75/2·(0.8+1.0) = 0.675 ; term 3: −0.15
    assert result == pytest.approx({1: 1.225, 2: 0.675, 3: -0.15})


def test_rocchio_identity_when_only_alpha() -> None:
    query = {1: 1.0, 5: 2.0}
    assert rocchio(query, [{1: 0.3}], [{5: 0.9}], 1.0, 0.0, 0.0) == query


def test_rocchio_empty_feedback_sets_do_not_divide_by_zero() -> None:
    assert rocchio({1: 1.0}, [], [], 1.0, 0.75, 0.15) == {1: 1.0}


def test_rocchio_alpha_scales_original() -> None:
    assert rocchio({1: 1.0, 2: 1.0}, [], [], 0.5, 0.75, 0.15) == {1: 0.5, 2: 0.5}


def test_truncate_drops_negatives_and_zero_and_keeps_heaviest() -> None:
    vector = {1: 0.2, 2: -0.5, 3: 0.9, 4: 0.0, 5: 0.9, 6: 0.4}
    assert truncate(vector, max_terms=3) == {3: 0.9, 5: 0.9, 6: 0.4}


def test_truncate_ties_by_ascending_term_id() -> None:
    vector = {9: 0.5, 2: 0.5, 7: 0.5}
    assert list(truncate(vector, max_terms=2)) == [2, 7]


def test_truncate_can_keep_negatives() -> None:
    vector = {1: 0.1, 2: -0.9}
    assert truncate(vector, max_terms=5, drop_negative=False) == {2: -0.9, 1: 0.1}


def test_norm() -> None:
    assert norm({1: 3.0, 2: 4.0}) == pytest.approx(5.0)
    assert norm({}) == 0.0


def test_diff_reports_added_changed_dropped() -> None:
    before = {1: 1.0, 2: 1.0, 3: 0.5}
    after = {1: 1.0, 2: 1.4, 4: 0.3}
    summary = diff(before, after)
    assert summary.added == [(4, 0.3)]
    assert summary.changed == [(2, 1.0, 1.4)]
    assert summary.dropped == [3]


def _parsed() -> ParsedQuery:
    return ParsedQuery(
        raw="vector space model everywhere",
        lemmas=["vector", "space", "model", "everywhere"],
        term_ids={"vector": 10, "space": 11, "model": 12, "everywhere": 13},
        inverse_frequencies={
            "vector": math.log(4),
            "space": math.log(2),
            "model": math.log(8),
            "everywhere": 0.0,
        },
        document_frequencies={"vector": 2, "space": 4, "model": 1, "everywhere": 8},
    )


def test_binary_query_vector_is_all_ones() -> None:
    assert binary_query_vector(_parsed()) == {10: 1.0, 11: 1.0, 12: 1.0, 13: 1.0}


def test_idf_query_vector_uses_b_i_and_drops_uninformative_terms() -> None:
    weights = idf_query_vector(_parsed())
    assert weights == pytest.approx({10: math.log(4), 11: math.log(2), 12: math.log(8)})
    assert 13 not in weights  # B_i = 0: present in every document
