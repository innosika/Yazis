"""Hand-authored topics: loading, seeding and the anti-tuning selection.

A topic file holds many more topics than will ever be judged. ROMIP's 2004 web track
issued 24,250 tasks and judged 67, chosen only *after* every participant's runs were
submitted — so no system could have been tuned to the judged topics. The same discipline
is enforced here mechanically: :func:`select_judged` refuses to run until every topic
has pool entries, because building the pool is what freezes the runs.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import PoolEntry, Query, TestCollection
from irs.logging import get_logger

log = get_logger("irs.eval.topics")

CATEGORIES = ("navigational", "topical", "vocabulary-mismatch")


@dataclass(slots=True)
class TopicSeed:
    ext_id: int
    title: str
    description: str
    narrative: str
    oracle_query: str
    category: str


@dataclass(slots=True)
class TopicFile:
    collection: str
    description: str
    topics: list[TopicSeed]


def load_topic_file(path: Path) -> TopicFile:
    """Parse and validate a topics YAML file. Raises ``ValueError`` on any defect."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("topics"), list):
        raise ValueError(f"{path}: expected a mapping with a `topics` list")

    topics: list[TopicSeed] = []
    seen: set[int] = set()
    for index, entry in enumerate(raw["topics"]):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: topic #{index} is not a mapping")
        try:
            topic = TopicSeed(
                ext_id=int(entry["ext_id"]),
                title=str(entry["title"]).strip(),
                description=str(entry.get("description", "")).strip(),
                narrative=str(entry.get("narrative", "")).strip(),
                oracle_query=str(entry["oracle_query"]).strip(),
                category=str(entry["category"]).strip(),
            )
        except KeyError as exc:
            raise ValueError(f"{path}: topic #{index} lacks required field {exc}") from exc
        if topic.ext_id in seen:
            raise ValueError(f"{path}: duplicate ext_id {topic.ext_id}")
        if topic.category not in CATEGORIES:
            raise ValueError(
                f"{path}: topic {topic.ext_id} has category {topic.category!r}; "
                f"expected one of {CATEGORIES}"
            )
        if not topic.title or not topic.oracle_query:
            raise ValueError(f"{path}: topic {topic.ext_id} needs a title and an oracle_query")
        seen.add(topic.ext_id)
        topics.append(topic)

    return TopicFile(
        collection=str(raw.get("collection") or settings.evaluation.topical_collection_name),
        description=str(raw.get("description", "")).strip(),
        topics=topics,
    )


async def seed_topics(
    session: AsyncSession, file: TopicFile, replace: bool = False
) -> tuple[TestCollection, int]:
    """Create the collection if needed and insert its topics (unjudged)."""
    collection = (
        await session.execute(select(TestCollection).where(TestCollection.name == file.collection))
    ).scalar_one_or_none()

    if collection is None:
        collection = TestCollection(name=file.collection, description=file.description or None)
        session.add(collection)
        await session.flush()
    elif replace:
        await session.execute(delete(Query).where(Query.collection_id == collection.id))
        collection.frozen_at = None
        await session.flush()

    existing = {
        ext_id
        for (ext_id,) in (
            await session.execute(select(Query.ext_id).where(Query.collection_id == collection.id))
        ).all()
    }

    inserted = 0
    for topic in file.topics:
        if topic.ext_id in existing:
            continue
        session.add(
            Query(
                collection_id=collection.id,
                ext_id=topic.ext_id,
                title=topic.title,
                description=topic.description or None,
                narrative=topic.narrative or None,
                oracle_query=topic.oracle_query,
                category=topic.category,
                is_judged=False,
            )
        )
        inserted += 1
    await session.flush()

    log.info(
        "topics_seeded",
        collection=collection.name,
        inserted=inserted,
        skipped_existing=len(existing),
    )
    return collection, inserted


def stratified_sample(
    by_category: Mapping[str, Sequence[int]], count: int, rng: random.Random
) -> list[int]:
    """Pick ``count`` ids, proportionally per category, round-robin over the remainder.

    Pure, so the selection rule can be tested. Deterministic for a fixed ``rng`` state.
    """
    total = sum(len(ids) for ids in by_category.values())
    if count >= total:
        return sorted(identifier for ids in by_category.values() for identifier in ids)

    shuffled = {
        category: rng.sample(list(ids), len(ids)) for category, ids in sorted(by_category.items())
    }
    quotas = {
        category: (len(ids) * count) // total for category, ids in sorted(by_category.items())
    }
    chosen: list[int] = []
    for category, quota in quotas.items():
        chosen.extend(shuffled[category][:quota])
        shuffled[category] = shuffled[category][quota:]

    # Remainder round-robin over the categories that still have topics left.
    categories = [c for c in sorted(shuffled) if shuffled[c]]
    while len(chosen) < count and categories:
        for category in list(categories):
            if len(chosen) >= count:
                break
            if shuffled[category]:
                chosen.append(shuffled[category].pop(0))
            if not shuffled[category]:
                categories.remove(category)

    return sorted(chosen)


async def select_judged(
    session: AsyncSession,
    collection_id: int,
    count: int | None = None,
    seed: int | None = None,
) -> list[Query]:
    """Freeze the judged subset. Refuses until the pool (= the frozen runs) exists."""
    count = settings.evaluation.judged_topics if count is None else count

    topics = list(
        (
            await session.execute(
                select(Query).where(Query.collection_id == collection_id).order_by(Query.ext_id)
            )
        ).scalars()
    )
    if not topics:
        raise ValueError("the collection has no topics to select from")

    pooled = {
        query_id
        for (query_id,) in (
            await session.execute(
                select(PoolEntry.query_id)
                .join(Query, Query.id == PoolEntry.query_id)
                .where(Query.collection_id == collection_id)
                .group_by(PoolEntry.query_id)
            )
        ).all()
    }
    missing = [topic.ext_id for topic in topics if topic.id not in pooled]
    if missing:
        raise ValueError(
            "runs are not frozen: build the judgment pool first (topics without pool "
            f"entries: {missing[:10]}{'…' if len(missing) > 10 else ''}). Selecting judged "
            "topics before the runs exist would defeat ROMIP's anti-tuning rule."
        )

    by_category: dict[str, list[int]] = {}
    for topic in topics:
        by_category.setdefault(topic.category or "uncategorised", []).append(topic.id)

    rng = random.Random(settings.evaluation.random_seed if seed is None else seed)
    chosen = set(stratified_sample(by_category, count, rng))

    now = datetime.now(UTC).replace(tzinfo=None)
    selected: list[Query] = []
    for topic in topics:
        topic.is_judged = topic.id in chosen
        topic.selected_at = now if topic.is_judged else None
        if topic.is_judged:
            selected.append(topic)

    collection = await session.get(TestCollection, collection_id)
    if collection is not None:
        collection.frozen_at = now
    await session.flush()

    log.info(
        "judged_topics_selected",
        collection_id=collection_id,
        selected=len(selected),
        of=len(topics),
        by_category={
            category: sum(1 for t in selected if (t.category or "uncategorised") == category)
            for category in sorted(by_category)
        },
    )
    return selected


async def topic_counts(session: AsyncSession, collection_id: int) -> dict[str, dict[str, int]]:
    """``{category: {"total": n, "judged": m}}`` for the interface."""
    rows = (
        await session.execute(
            select(Query.category, Query.is_judged, func.count())
            .where(Query.collection_id == collection_id)
            .group_by(Query.category, Query.is_judged)
        )
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for category, is_judged, number in rows:
        bucket = counts.setdefault(category or "uncategorised", {"total": 0, "judged": 0})
        bucket["total"] += int(number)
        if is_judged:
            bucket["judged"] += int(number)
    return counts
