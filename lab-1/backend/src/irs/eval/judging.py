"""Judging jobs: an assessor working through a collection's pool, resumably.

The unit of work is one (topic, document) pair; the unit of *progress* is the
:class:`~irs.db.models.evaluation.JudgingJob` row, updated after every pair and mirrored
onto a Redis channel for the interface. Pairs are inserted with ``ON CONFLICT DO
NOTHING`` against the ``(query, document, assessor)`` constraint, so a job that is
interrupted — or delivered twice by the queue — never double-counts and can simply be
started again: :func:`pending_pairs` returns whatever this assessor has not judged yet.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import Document, JudgingJob, Judgment, PoolEntry, Query
from irs.db.models.enums import AssessorKind, EvalRunStatus
from irs.db.models.evaluation import Assessor
from irs.db.session import get_sessionmaker
from irs.eval.assessor import AssessorError, DocumentView, LlmAssessor, TopicView, select_passage
from irs.logging import Stopwatch, get_logger
from irs.nlp.pipeline import analyzer
from irs.telemetry.redis_client import get_redis

log = get_logger("irs.eval.judging")

#: Progress channel shared by judging jobs and evaluation runs. Payloads carry ``kind``.
PROGRESS_CHANNEL = "irs.eval.progress"

ProgressHook = Callable[[dict[str, Any]], Awaitable[None]]


async def get_or_create_llm_assessor(session: AsyncSession, assessor: LlmAssessor) -> Assessor:
    row = (
        await session.execute(select(Assessor).where(Assessor.name == assessor.assessor_name))
    ).scalar_one_or_none()
    if row is None:
        row = Assessor(
            name=assessor.assessor_name,
            kind=AssessorKind.LLM,
            meta=assessor.meta(),
            note=(
                "Language-model assessor. Sees the topic (title, description, narrative) and "
                "the document only — never a ranker, rank or score. Verdicts are on ROMIP's "
                "five-point scale; each carries the model's one-sentence reason."
            ),
        )
        session.add(row)
        await session.flush()
    elif row.meta != assessor.meta():
        row.meta = assessor.meta()
        await session.flush()
    return row


async def pending_pairs(
    session: AsyncSession, collection_id: int, assessor_id: int, limit: int | None = None
) -> list[tuple[int, int]]:
    """Pool pairs of *judged* topics this assessor has not graded yet, in stable order."""
    already = exists().where(
        Judgment.query_id == PoolEntry.query_id,
        Judgment.document_id == PoolEntry.document_id,
        Judgment.assessor_id == assessor_id,
    )
    statement = (
        select(PoolEntry.query_id, PoolEntry.document_id)
        .join(Query, Query.id == PoolEntry.query_id)
        .where(Query.collection_id == collection_id, Query.is_judged, ~already)
        .order_by(PoolEntry.query_id, PoolEntry.document_id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return [(int(q), int(d)) for q, d in (await session.execute(statement)).all()]


async def count_pending(session: AsyncSession, collection_id: int, assessor_id: int) -> int:
    return len(await pending_pairs(session, collection_id, assessor_id))


async def create_judging_job(
    session: AsyncSession, collection_id: int, assessor_id: int, limit: int | None = None
) -> JudgingJob:
    total = await count_pending(session, collection_id, assessor_id)
    if limit is not None:
        total = min(total, limit)
    job = JudgingJob(
        collection_id=collection_id,
        assessor_id=assessor_id,
        status=EvalRunStatus.PENDING,
        total_pairs=total,
    )
    session.add(job)
    await session.flush()
    return job


@dataclass(slots=True)
class JudgingOutcome:
    job_id: int
    judged: int = 0
    failed: int = 0
    skipped_existing: int = 0
    duration_ms: float = 0.0
    grades: dict[str, int] = field(default_factory=dict)


async def run_judging_job(
    job_id: int,
    assessor: LlmAssessor | None = None,
    limit: int | None = None,
    on_progress: ProgressHook | None = None,
) -> JudgingOutcome:
    """Work through the job's pending pairs. Owns its sessions, like the crawler."""
    assessor = assessor or LlmAssessor()
    publish = on_progress or _publish
    watch = Stopwatch()
    sessionmaker = get_sessionmaker()
    outcome = JudgingOutcome(job_id=job_id)

    async with sessionmaker() as session:
        job = await session.get(JudgingJob, job_id)
        if job is None:
            raise LookupError(f"judging job {job_id} does not exist")
        collection_id, assessor_id = job.collection_id, job.assessor_id
        if job.status not in (EvalRunStatus.PENDING, EvalRunStatus.RUNNING):
            # Redelivered after the job was stopped or finished: nothing to do.
            log.info("judging_job_not_active", job_id=job_id, status=str(job.status))
            return outcome

        try:
            await assessor.healthcheck()
        except AssessorError as exc:
            job.status = EvalRunStatus.FAILED
            job.error = str(exc)[:2_000]
            job.finished_at = _now()
            await session.commit()
            await publish(
                {"kind": "judging", "event": "failed", "job_id": job_id, "error": str(exc)}
            )
            raise

        assessor_row = await session.get(Assessor, assessor_id)
        if assessor_row is not None and assessor_row.kind == AssessorKind.LLM:
            assessor_row.meta = assessor.meta()

        pairs = await pending_pairs(session, collection_id, assessor_id, limit)
        job.status = EvalRunStatus.RUNNING
        job.started_at = job.started_at or _now()
        job.total_pairs = job.judged_pairs + job.failed_pairs + len(pairs)
        await session.commit()

    await publish({"kind": "judging", "event": "started", "job_id": job_id, "total": len(pairs)})
    log.info("judging_started", job_id=job_id, pairs=len(pairs), assessor=assessor.assessor_name)

    for query_id, document_id in pairs:
        async with sessionmaker() as session:
            await _judge_pair(
                session, job_id, assessor, assessor_id, query_id, document_id, outcome
            )
            await session.commit()

            job = await session.get(JudgingJob, job_id)
            if job is not None:
                await publish(
                    {
                        "kind": "judging",
                        "event": "judged",
                        "job_id": job_id,
                        "query_id": query_id,
                        "document_id": document_id,
                        "judged": job.judged_pairs,
                        "failed": job.failed_pairs,
                        "total": job.total_pairs,
                        "elapsed_ms": round(watch.total_ms, 1),
                    }
                )

    async with sessionmaker() as session:
        job = await session.get(JudgingJob, job_id)
        if job is not None:
            job.status = EvalRunStatus.DONE
            job.finished_at = _now()
            await session.commit()

    outcome.duration_ms = watch.total_ms
    await publish(
        {
            "kind": "judging",
            "event": "finished",
            "job_id": job_id,
            "judged": outcome.judged,
            "failed": outcome.failed,
            "duration_ms": round(outcome.duration_ms, 1),
        }
    )
    await assessor.aclose()
    log.info(
        "judging_finished",
        job_id=job_id,
        judged=outcome.judged,
        failed=outcome.failed,
        grades=outcome.grades,
        duration_ms=round(outcome.duration_ms, 1),
    )
    return outcome


async def _judge_pair(
    session: AsyncSession,
    job_id: int,
    assessor: LlmAssessor,
    assessor_id: int,
    query_id: int,
    document_id: int,
    outcome: JudgingOutcome,
) -> None:
    topic = await session.get(Query, query_id)
    document = await session.get(Document, document_id)
    job = await session.get(JudgingJob, job_id)
    if topic is None or document is None or job is None:
        return

    views = await build_views(topic, document, assessor.config.max_document_chars)
    try:
        verdict = await assessor.judge(*views)
    except AssessorError as exc:
        outcome.failed += 1
        job.failed_pairs += 1
        log.warning(
            "judgment_failed",
            job_id=job_id,
            query_id=query_id,
            document_id=document_id,
            error=str(exc),
        )
        return

    inserted = cast(
        CursorResult[Any],
        await session.execute(
            pg_insert(Judgment)
            .values(
                query_id=query_id,
                document_id=document_id,
                assessor_id=assessor_id,
                grade=str(verdict.grade),
                seconds_spent=round(verdict.seconds, 3),
                note=verdict.reason[:2_000] or None,
            )
            .on_conflict_do_nothing(constraint="uq_judgment_pair_assessor")
        ),
    )
    if inserted.rowcount:
        outcome.judged += 1
        job.judged_pairs += 1
        outcome.grades[str(verdict.grade)] = outcome.grades.get(str(verdict.grade), 0) + 1
    else:
        outcome.skipped_existing += 1

    log.info(
        "judged",
        job_id=job_id,
        query_id=query_id,
        document_id=document_id,
        grade=str(verdict.grade),
        seconds=round(verdict.seconds, 2),
        attempts=verdict.attempts,
    )


async def build_views(
    topic: Query, document: Document, budget: int
) -> tuple[TopicView, DocumentView]:
    """What the assessor sees: the topic and a bounded passage of the document."""
    import asyncio

    image = await asyncio.to_thread(analyzer.analyze_query, topic.title)
    passage = await select_passage(
        document.text or "", document.title or "", image.ordered_lemmas, budget
    )
    return (
        TopicView(title=topic.title, description=topic.description, narrative=topic.narrative),
        DocumentView(title=document.title or "(untitled)", url=document.url, passage=passage),
    )


async def _publish(payload: dict[str, Any]) -> None:
    """Best-effort progress publication; telemetry must never break judging."""
    try:
        await get_redis().publish(PROGRESS_CHANNEL, json.dumps(payload, default=str))
    except Exception as exc:
        log.debug("judging_progress_publish_failed", error=str(exc))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def judged_counts(session: AsyncSession, collection_id: int) -> dict[str, int]:
    """Grade distribution over a collection, for the interface."""
    rows = (
        await session.execute(
            select(Judgment.grade, func.count())
            .join(Query, Query.id == Judgment.query_id)
            .where(Query.collection_id == collection_id)
            .group_by(Judgment.grade)
        )
    ).all()
    return {str(grade): int(number) for grade, number in rows}


def default_assessor_settings_summary() -> dict[str, Any]:
    return {
        "model": settings.assessor.model,
        "base_url": settings.assessor.base_url,
        "prompt_version": settings.assessor.prompt_version,
    }
