"""Topic file validation and the anti-tuning selection rule."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from irs.eval.topics import load_topic_file, stratified_sample

VALID = """
collection: demo
description: d
topics:
  - ext_id: 1
    category: topical
    title: "a b"
    oracle_query: "x"
    description: "d"
    narrative: "n"
  - {ext_id: 2, category: navigational, title: "c", oracle_query: "y"}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_file_loads(tmp_path: Path) -> None:
    file = load_topic_file(_write(tmp_path, VALID))
    assert file.collection == "demo"
    assert [t.ext_id for t in file.topics] == [1, 2]
    assert file.topics[1].description == ""


@pytest.mark.parametrize(
    "broken",
    [
        VALID.replace("ext_id: 2", "ext_id: 1"),  # duplicate id
        VALID.replace("category: navigational", "category: weird"),  # unknown category
        VALID.replace(', oracle_query: "y"', ""),  # missing oracle
        VALID.replace('title: "c"', 'title: ""'),  # empty title
        "topics: notalist",
    ],
)
def test_defects_are_rejected(tmp_path: Path, broken: str) -> None:
    with pytest.raises(ValueError):
        load_topic_file(_write(tmp_path, broken))


def test_the_shipped_topics_file_is_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "seeds" / "topics.yaml"
    file = load_topic_file(path)
    assert len(file.topics) >= 40
    categories = {t.category for t in file.topics}
    assert categories == {"navigational", "topical", "vocabulary-mismatch"}
    assert all(t.narrative for t in file.topics), "every topic needs a narrative for the assessor"


def test_stratified_sample_is_proportional_and_deterministic() -> None:
    by_category = {
        "a": list(range(100, 112)),
        "b": list(range(200, 224)),
        "c": list(range(300, 310)),
    }
    first = stratified_sample(by_category, 25, random.Random(3))
    second = stratified_sample(by_category, 25, random.Random(3))
    assert first == second
    assert len(first) == 25
    counts = {category: sum(1 for x in first if x in ids) for category, ids in by_category.items()}
    # 46 topics → 25: proportional quotas 6 / 13 / 5 plus one round-robin remainder.
    assert counts["a"] >= 6 and counts["b"] >= 13 and counts["c"] >= 5


def test_stratified_sample_returns_everything_when_count_is_large() -> None:
    by_category = {"a": [1, 2], "b": [3]}
    assert stratified_sample(by_category, 10, random.Random(0)) == [1, 2, 3]
