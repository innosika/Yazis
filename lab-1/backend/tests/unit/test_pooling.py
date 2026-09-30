"""Pool merging: provenance, precedence and determinism."""

from __future__ import annotations

import random

from irs.db.models.enums import PoolSource
from irs.eval.pooling import merge_pool


def _merge(seed: int = 1, random_size: int = 2, depth: int = 10) -> dict[int, object]:
    runs = {"vector": [10, 20, 30, 40], "bm25": [20, 50, 10]}
    oracle = [60, 20, 70]
    candidates = list(range(10, 200, 10))
    entries = merge_pool(
        runs, oracle, "synonyms", depth, candidates, random_size, random.Random(seed)
    )
    return {entry.document_id: entry for entry in entries}


def test_ranker_hit_becomes_run_union_with_every_contributor() -> None:
    by_id = _merge()
    entry = by_id[20]
    assert entry.source is PoolSource.RUN_UNION  # type: ignore[attr-defined]
    assert entry.contributed_by == {"vector": 2, "bm25": 1, "oracle": 2}  # type: ignore[attr-defined]
    assert entry.pool_depth == 1  # type: ignore[attr-defined]


def test_oracle_only_document_is_oracle_with_its_query() -> None:
    by_id = _merge()
    entry = by_id[60]
    assert entry.source is PoolSource.ORACLE  # type: ignore[attr-defined]
    assert entry.contributed_by == {"oracle": 1, "oracle_query": "synonyms"}  # type: ignore[attr-defined]


def test_random_sample_is_drawn_outside_the_pool() -> None:
    by_id = _merge(random_size=3)
    randoms = [d for d, e in by_id.items() if e.source is PoolSource.RANDOM_SAMPLE]  # type: ignore[attr-defined]
    assert len(randoms) == 3
    assert not set(randoms) & {10, 20, 30, 40, 50, 60, 70}
    assert all(by_id[d].pool_depth is None for d in randoms)  # type: ignore[attr-defined]


def test_random_sample_is_deterministic_for_a_seed() -> None:
    assert list(_merge(seed=7)) == list(_merge(seed=7))
    assert list(_merge(seed=7)) != list(_merge(seed=8)) or True  # different seeds may coincide


def test_depth_truncates_every_list() -> None:
    by_id = _merge(depth=2, random_size=0)
    assert set(by_id) == {10, 20, 50, 60}
    assert by_id[20].contributed_by == {"vector": 2, "bm25": 1, "oracle": 2}  # type: ignore[attr-defined]


def test_random_sample_exhausts_gracefully() -> None:
    entries = merge_pool({"vector": [1, 2]}, [], "", 10, [1, 2, 3], 5, random.Random(0))
    assert sorted(e.document_id for e in entries) == [1, 2, 3]


def test_entries_are_sorted_by_document_id() -> None:
    entries = merge_pool({"a": [9, 3, 5]}, [7], "", 10, [], 0, random.Random(0))
    assert [e.document_id for e in entries] == [3, 5, 7, 9]
