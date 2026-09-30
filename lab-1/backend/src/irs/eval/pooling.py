"""Judgment pooling with provenance.

Judging every (topic, document) pair is impossible even for 208 documents, so ROMIP —
like TREC — judges a *pool*: the union of the top-`k` of every participating run. This
module builds that pool and records, for every pair, **why it is there**:

* ``run_union`` — some ranker returned it in its top-`k` (which rankers, at which rank);
* ``oracle`` — only the topic's hand-built synonym query found it. These are the
  documents our own systems missed for the topic's wording; without them pooled recall
  is recall over what we happened to retrieve;
* ``random_sample`` — drawn at random from outside the pool. If ~0% of these turn out
  relevant, that is empirical evidence the pool is near-complete rather than a hope.

Building the pool is also the moment the runs are *frozen*: the judged subset of topics
may only be chosen afterwards (see :mod:`irs.eval.topics`).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import GRADE_VALUES, Document, Judgment, PoolEntry, Query
from irs.db.models.enums import PoolSource, RankerKey, RelevanceGrade
from irs.logging import Stopwatch, get_logger
from irs.selection.base import SearchFilters
from irs.selection.parser import parse_query
from irs.selection.registry import get_ranker, get_rankers

log = get_logger("irs.eval.pooling")


@dataclass(slots=True)
class PoolCandidate:
    document_id: int
    source: PoolSource
    pool_depth: int | None
    contributed_by: dict[str, Any]


def merge_pool(
    run_lists: Mapping[str, Sequence[int]],
    oracle: Sequence[int],
    oracle_query: str,
    depth: int,
    random_candidates: Sequence[int],
    random_size: int,
    rng: random.Random,
) -> list[PoolCandidate]:
    """Combine one topic's run lists, oracle list and random sample. Pure.

    Precedence: a document any ranker returned within ``depth`` is ``run_union`` (its
    oracle rank, if any, is still recorded); a document only the oracle found is
    ``oracle``; the random sample is drawn from ``random_candidates`` minus everything
    already pooled.
    """
    entries: dict[int, PoolCandidate] = {}

    for ranker in sorted(run_lists):
        for rank, document_id in enumerate(run_lists[ranker][:depth], start=1):
            entry = entries.get(document_id)
            if entry is None:
                entry = PoolCandidate(document_id, PoolSource.RUN_UNION, rank, {})
                entries[document_id] = entry
            entry.contributed_by[ranker] = rank
            entry.pool_depth = min(entry.pool_depth or rank, rank)

    for rank, document_id in enumerate(oracle[:depth], start=1):
        entry = entries.get(document_id)
        if entry is None:
            entries[document_id] = PoolCandidate(
                document_id,
                PoolSource.ORACLE,
                rank,
                {"oracle": rank, "oracle_query": oracle_query},
            )
        else:
            entry.contributed_by["oracle"] = rank

    outside = sorted(set(random_candidates) - set(entries))
    for document_id in rng.sample(outside, min(random_size, len(outside))):
        entries[document_id] = PoolCandidate(
            document_id,
            PoolSource.RANDOM_SAMPLE,
            None,
            {"origin": "random_sample"},
        )

    return sorted(entries.values(), key=lambda e: e.document_id)


@dataclass(slots=True)
class PoolBuildStats:
    topics: int = 0
    entries: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    rankers: list[str] = field(default_factory=list)
    oracle_ranker: str = ""
    depth: int = 0
    random_size: int = 0
    duration_ms: float = 0.0


async def build_pool(
    session: AsyncSession,
    collection_id: int,
    depth: int | None = None,
    random_size: int | None = None,
    rankers: Sequence[RankerKey] | None = None,
    replace: bool = False,
) -> PoolBuildStats:
    """Run every ranker over every topic of the collection and upsert the pool."""
    depth = settings.evaluation.pool_depth if depth is None else depth
    random_size = settings.evaluation.pool_random_sample if random_size is None else random_size
    watch = Stopwatch()

    available = get_rankers()
    keys = list(rankers) if rankers else sorted(available, key=str)
    oracle_key = RankerKey(settings.evaluation.oracle_ranker)
    oracle_ranker = get_ranker(oracle_key)

    topics = list(
        (
            await session.execute(
                select(Query).where(Query.collection_id == collection_id).order_by(Query.ext_id)
            )
        ).scalars()
    )
    if not topics:
        raise ValueError("the collection has no topics; seed them first")

    all_documents = [
        int(document_id)
        for (document_id,) in (
            await session.execute(select(Document.id).order_by(Document.id))
        ).all()
    ]

    if replace:
        await session.execute(
            delete(PoolEntry).where(PoolEntry.query_id.in_([topic.id for topic in topics]))
        )

    stats = PoolBuildStats(
        rankers=[str(k) for k in keys],
        oracle_ranker=str(oracle_key),
        depth=depth,
        random_size=random_size,
    )

    for topic in topics:
        parsed = await parse_query(session, topic.title)
        run_lists: dict[str, list[int]] = {}
        for key in keys:
            page = await available[key].rank(session, parsed, SearchFilters(), depth)
            run_lists[str(key)] = [d.document_id for d in page.documents]

        oracle_ids: list[int] = []
        if topic.oracle_query:
            oracle_parsed = await parse_query(session, topic.oracle_query)
            oracle_page = await oracle_ranker.rank(session, oracle_parsed, SearchFilters(), depth)
            oracle_ids = [d.document_id for d in oracle_page.documents]

        rng = random.Random(f"{settings.evaluation.random_seed}:{topic.ext_id}")
        candidates = merge_pool(
            run_lists,
            oracle_ids,
            topic.oracle_query or "",
            depth,
            all_documents,
            random_size,
            rng,
        )
        await _upsert(session, topic.id, candidates)

        stats.topics += 1
        stats.entries += len(candidates)
        for candidate in candidates:
            stats.by_source[str(candidate.source)] = (
                stats.by_source.get(str(candidate.source), 0) + 1
            )

    await session.flush()
    stats.duration_ms = watch.total_ms
    log.info(
        "pool_built",
        collection_id=collection_id,
        topics=stats.topics,
        entries=stats.entries,
        by_source=stats.by_source,
        depth=depth,
        random_size=random_size,
        duration_ms=round(stats.duration_ms, 1),
    )
    return stats


async def _upsert(session: AsyncSession, query_id: int, candidates: list[PoolCandidate]) -> None:
    if not candidates:
        return
    statement = pg_insert(PoolEntry).values(
        [
            {
                "query_id": query_id,
                "document_id": c.document_id,
                "source": str(c.source),
                "pool_depth": c.pool_depth,
                "contributed_by": c.contributed_by,
            }
            for c in candidates
        ]
    )
    # An existing entry keeps its provenance and gains the new one; the source only
    # becomes *more* system-attributed, never less (run_union beats oracle beats random).
    existing_rank = _source_precedence(PoolEntry.source)
    proposed_rank = _source_precedence(statement.excluded.source)
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_pool_entry_query_document",
            set_={
                "contributed_by": PoolEntry.contributed_by.op("||")(
                    statement.excluded.contributed_by
                ),
                "pool_depth": func.least(PoolEntry.pool_depth, statement.excluded.pool_depth),
                "source": case(
                    (proposed_rank > existing_rank, statement.excluded.source),
                    else_=PoolEntry.source,
                ),
            },
        )
    )


def _source_precedence(column: Any) -> Any:
    return case(
        {
            str(PoolSource.RUN_UNION): 3,
            str(PoolSource.ORACLE): 2,
            str(PoolSource.MANUAL_SEED): 1,
            str(PoolSource.RANDOM_SAMPLE): 0,
        },
        value=column,
        else_=0,
    )


@dataclass(slots=True)
class PoolStats:
    depth: int
    unique_documents: int = 0
    total_entries: int = 0
    by_source: dict[str, dict[str, float]] = field(default_factory=dict)
    per_topic: list[dict[str, Any]] = field(default_factory=list)


async def pool_stats(session: AsyncSession, collection_id: int) -> PoolStats:
    """Coverage of the pool and how relevant each provenance class turned out."""
    threshold = settings.evaluation.binary_relevance_threshold

    entries = (
        await session.execute(
            select(
                PoolEntry.query_id,
                PoolEntry.document_id,
                PoolEntry.source,
                PoolEntry.contributed_by,
                Query.ext_id,
                Query.title,
                Query.category,
                Query.is_judged,
            )
            .join(Query, Query.id == PoolEntry.query_id)
            .where(Query.collection_id == collection_id)
            .order_by(Query.ext_id, PoolEntry.document_id)
        )
    ).all()

    grades = (
        await session.execute(
            select(Judgment.query_id, Judgment.document_id, Judgment.grade)
            .join(Query, Query.id == Judgment.query_id)
            .where(Query.collection_id == collection_id)
        )
    ).all()
    best_grade: dict[tuple[int, int], int] = {}
    for query_id, document_id, grade in grades:
        value = GRADE_VALUES[RelevanceGrade(grade)]
        key = (query_id, document_id)
        best_grade[key] = max(best_grade.get(key, 0), value)

    stats = PoolStats(depth=settings.evaluation.pool_depth)
    by_source: dict[str, dict[str, float]] = {}
    per_topic: dict[int, dict[str, Any]] = {}
    documents: set[int] = set()

    for (
        query_id,
        document_id,
        source,
        contributed_by,
        ext_id,
        title,
        category,
        is_judged,
    ) in entries:
        documents.add(document_id)
        stats.total_entries += 1
        bucket = by_source.setdefault(
            str(source), {"entries": 0, "judged": 0, "relevant": 0, "relevant_rate": 0.0}
        )
        bucket["entries"] += 1
        judged_grade = best_grade.get((query_id, document_id))
        if judged_grade is not None:
            bucket["judged"] += 1
            if judged_grade >= threshold:
                bucket["relevant"] += 1

        topic = per_topic.setdefault(
            query_id,
            {
                "query_id": query_id,
                "ext_id": ext_id,
                "title": title,
                "category": category,
                "is_judged": is_judged,
                "total": 0,
                "judged": 0,
                "relevant": 0,
                "by_source": {},
                "by_ranker": {},
            },
        )
        topic["total"] += 1
        topic["by_source"][str(source)] = topic["by_source"].get(str(source), 0) + 1
        for ranker in contributed_by:
            if ranker in {"oracle_query", "origin"}:
                continue
            topic["by_ranker"][ranker] = topic["by_ranker"].get(ranker, 0) + 1
        if judged_grade is not None:
            topic["judged"] += 1
            if judged_grade >= threshold:
                topic["relevant"] += 1

    for bucket in by_source.values():
        if bucket["judged"]:
            bucket["relevant_rate"] = bucket["relevant"] / bucket["judged"]

    stats.unique_documents = len(documents)
    stats.by_source = by_source
    stats.per_topic = [
        per_topic[key] for key in sorted(per_topic, key=lambda k: per_topic[k]["ext_id"])
    ]
    return stats
