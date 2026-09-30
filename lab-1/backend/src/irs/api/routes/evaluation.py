"""The quality-evaluation module's API — the assignment's «подменю» for metrics.

Everything the interface's Evaluation screens show comes from here: the metric registry,
test collections and their topics, the judgment pool with its provenance, the blind
judging endpoint, materialised relevance tables, evaluation runs (executed in the
background), per-topic drill-downs, curves, aligned comparisons, significance tests and
TREC-format exports.

Two rules the endpoints enforce rather than trust the client with:

* ``/pool/next`` is **blind** — it never reveals which ranker retrieved a pair or at what
  rank, and serves pairs in a hash order that has nothing to do with any ranking.
* ``/compare`` aligns runs on the **intersection** of their topics and reports its size.
  Comparing means over different topic sets is the classic invalid comparison.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from irs.api.sse import channel_response
from irs.config import settings
from irs.db.models import (
    Document,
    EvalRun,
    JudgingJob,
    Judgment,
    PoolEntry,
    Qrel,
    QrelSet,
    Query,
    RunCurve,
    RunMetric,
    RunQueryCurve,
    RunResult,
    SignificanceResult,
    TestCollection,
)
from irs.db.models.enums import (
    AssessorKind,
    EvalRunStatus,
    QrelAggregation,
    RankerKey,
    RelevanceGrade,
)
from irs.db.models.evaluation import Assessor
from irs.db.session import get_session
from irs.eval import pooling, qrels, topics
from irs.eval import significance as significance_module
from irs.eval.assessor import LlmAssessor
from irs.eval.caveats import MetricCaveat, metric_caveats
from irs.eval.collection import collection_summary
from irs.eval.judging import (
    PROGRESS_CHANNEL,
    count_pending,
    create_judging_job,
    get_or_create_llm_assessor,
    judged_counts,
)
from irs.eval.registry import CURVE_KEYS, METRICS, PRIMARY_ORDER, MetricSpec
from irs.eval.runner import create_run
from irs.eval.service import PRIMARY_METRIC, compare_stored_runs, load_per_query
from irs.eval.trec_format import format_qrels, format_run
from irs.logging import get_logger
from irs.selection.registry import get_rankers

log = get_logger("irs.api.evaluation")
router = APIRouter(prefix="/eval", tags=["evaluation"])


# ------------------------------------------------------------------ schemas ----


class MetricSpecOut(BaseModel):
    key: str
    label: str
    description: str
    kind: str
    edition: str
    needs_graded: bool = False
    cutoff: int | None = None
    higher_is_better: bool = True
    formula_tex: str | None = None
    label_ru: str | None = None


class MetricRegistryOut(BaseModel):
    metrics: list[MetricSpecOut]
    primary_order: list[str]
    curve_keys: list[str]
    primary_metric: str


class AssessorOut(BaseModel):
    id: int
    name: str
    kind: str
    meta: dict[str, Any] = {}
    judgment_count: int = 0


class CollectionOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    frozen_at: datetime | None = None
    created_at: datetime | None = None
    summary: dict[str, int] = {}
    topics_by_category: dict[str, dict[str, int]] = {}
    grade_counts: dict[str, int] = {}
    assessors: list[AssessorOut] = []
    pool_depth: int = settings.evaluation.pool_depth
    is_known_item: bool = False


class TopicOut(BaseModel):
    id: int
    ext_id: int
    title: str
    description: str | None = None
    narrative: str | None = None
    category: str | None = None
    is_judged: bool
    selected_at: datetime | None = None
    #: Hidden until the collection is frozen — anti-tuning.
    oracle_query: str | None = None
    pool_size: int = 0
    judged_pairs: int = 0


class SelectTopicsIn(BaseModel):
    count: int | None = Field(default=None, ge=1, le=500)
    seed: int | None = None


class SeedTopicsIn(BaseModel):
    replace: bool = False


class PoolBuildIn(BaseModel):
    depth: int | None = Field(default=None, ge=1, le=100)
    random_size: int | None = Field(default=None, ge=0, le=50)
    rankers: list[RankerKey] | None = None
    replace: bool = False


class PoolBuildOut(BaseModel):
    topics: int
    entries: int
    by_source: dict[str, int]
    rankers: list[str]
    oracle_ranker: str
    depth: int
    random_size: int
    duration_ms: float


class PoolStatsOut(BaseModel):
    depth: int
    unique_documents: int
    total_entries: int
    by_source: dict[str, dict[str, float]]
    per_topic: list[dict[str, Any]]


class PoolNextTopicOut(BaseModel):
    id: int
    ext_id: int
    title: str
    description: str | None = None
    narrative: str | None = None


class PoolNextDocumentOut(BaseModel):
    id: int
    title: str
    url: str
    text: str


class PoolNextOut(BaseModel):
    topic: PoolNextTopicOut
    document: PoolNextDocumentOut
    remaining: int
    total: int
    judged_by_you: int
    grades: list[str] = [grade.value for grade in RelevanceGrade]


class AssessorIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class JudgmentIn(BaseModel):
    query_id: int
    document_id: int
    assessor: str = Field(min_length=1, max_length=128)
    grade: RelevanceGrade
    seconds_spent: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=2_000)


class JudgmentOut(BaseModel):
    id: int
    query_id: int
    document_id: int
    assessor_id: int
    assessor: str
    grade: RelevanceGrade
    seconds_spent: float | None = None
    note: str | None = None
    created_at: datetime | None = None


class JudgingStartIn(BaseModel):
    limit: int | None = Field(default=None, ge=1)


class JudgingJobOut(BaseModel):
    id: int
    collection_id: int
    assessor_id: int
    assessor: str | None = None
    status: EvalRunStatus
    task_id: str | None = None
    total_pairs: int
    judged_pairs: int
    failed_pairs: int
    pending_pairs: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    model: str | None = None


class QrelSetIn(BaseModel):
    aggregation: QrelAggregation = QrelAggregation.OR
    threshold: int = Field(default=settings.evaluation.binary_relevance_threshold, ge=0, le=3)


class QrelSetOut(BaseModel):
    id: int
    collection_id: int
    name: str
    aggregation: QrelAggregation
    threshold: int
    query_count: int
    relevant_count: int
    judged_count: int
    excluded_queries: int | None = None
    disagreement_count: int | None = None


class RunStartIn(BaseModel):
    collection_id: int
    aggregation: QrelAggregation = QrelAggregation.OR
    threshold: int | None = Field(default=None, ge=0, le=3)
    rankers: list[RankerKey] | None = None
    top_k: int | None = Field(default=None, ge=1, le=1_000)


class RunOut(BaseModel):
    id: int
    collection_id: int
    qrel_set_id: int
    ranker: str
    label: str | None = None
    top_k: int
    status: EvalRunStatus
    index_version: int
    params_snapshot: dict[str, Any] = {}
    scored_query_count: int = 0
    unjudged_retrieved: int = 0
    duration_ms: float | None = None
    batch_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    aggregation: str | None = None
    threshold: int | None = None


class RunBatchOut(BaseModel):
    batch_id: str
    qrel_set: QrelSetOut
    runs: list[RunOut]


class AggregateMetricOut(BaseModel):
    metric_key: str
    value: float
    query_count: int
    ci_low: float | None = None
    ci_high: float | None = None


class CaveatOut(BaseModel):
    metric_key: str
    kind: str
    note: str


class RunDetailOut(RunOut):
    aggregate: list[AggregateMetricOut] = []
    caveats: list[CaveatOut] = []


class QueryMetricsOut(BaseModel):
    query_id: int
    ext_id: int
    title: str
    category: str | None = None
    metrics: dict[str, float]


class RankedDocumentOut(BaseModel):
    rank: int
    document_id: int
    title: str
    url: str
    score: float
    grade: str | None = None
    gain: float | None = None
    is_relevant: bool | None = None
    is_judged: bool = False


class QueryDrilldownOut(BaseModel):
    query: QueryMetricsOut
    top: list[RankedDocumentOut]
    pr_raw: list[list[float]] = []
    relevant_total: int = 0
    relevant_documents: list[RankedDocumentOut] = []


class CurveOut(BaseModel):
    curve_key: str
    points: list[list[float]]
    support: list[list[float]] | None = None


class CompareRowOut(BaseModel):
    run_id: int
    ranker: str
    label: str
    mean_on_intersection: float
    ci_low: float | None = None
    ci_high: float | None = None
    stored_mean: float | None = None
    stored_query_count: int = 0
    dropped_topics: int = 0
    delta_vs_baseline: float | None = None


class CompareOut(BaseModel):
    metric: str
    topic_count: int
    baseline_run_id: int
    rows: list[CompareRowOut]
    per_topic: list[dict[str, Any]]


class SignificanceOut(BaseModel):
    metric_key: str
    test: str
    label_a: str
    label_b: str
    run_a_id: int | None = None
    run_b_id: int | None = None
    sample_size: int
    mean_a: float
    mean_b: float
    mean_difference: float
    p_value: float
    p_value_corrected: float | None = None
    correction: str | None = None
    statistic: float | None = None
    effect_size: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    ties: int = 0


# ------------------------------------------------------------------ helpers ----


async def _collection_or_404(session: AsyncSession, collection_id: int) -> TestCollection:
    collection = await session.get(TestCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"test collection {collection_id} not found")
    return collection


async def _run_or_404(session: AsyncSession, run_id: int) -> EvalRun:
    run = await session.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return run


def _spec_out(spec: MetricSpec) -> MetricSpecOut:
    return MetricSpecOut(
        key=spec.key,
        label=spec.label,
        description=spec.description,
        kind=str(spec.kind),
        edition=str(spec.edition),
        needs_graded=spec.needs_graded,
        cutoff=spec.cutoff,
        higher_is_better=spec.higher_is_better,
        formula_tex=spec.formula_tex,
        label_ru=spec.label_ru,
    )


async def _assessor_outs(
    session: AsyncSession, collection_id: int | None = None
) -> list[AssessorOut]:
    statement = select(Assessor, func.count(Judgment.id)).outerjoin(
        Judgment, Judgment.assessor_id == Assessor.id
    )
    if collection_id is not None:
        statement = statement.outerjoin(Query, Query.id == Judgment.query_id).where(
            (Query.collection_id == collection_id) | (Query.id.is_(None))
        )
    statement = statement.group_by(Assessor.id).order_by(Assessor.id)
    return [
        AssessorOut(
            id=assessor.id,
            name=assessor.name,
            kind=str(assessor.kind),
            meta=assessor.meta,
            judgment_count=int(n),
        )
        for assessor, n in (await session.execute(statement)).all()
    ]


async def _collection_out(session: AsyncSession, collection: TestCollection) -> CollectionOut:
    summary = await collection_summary(session, collection.id)
    return CollectionOut(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        frozen_at=collection.frozen_at,
        created_at=collection.created_at,
        summary=summary,
        topics_by_category=await topics.topic_counts(session, collection.id),
        grade_counts=await judged_counts(session, collection.id),
        assessors=await _assessor_outs(session, collection.id),
        is_known_item=collection.name.startswith("known-item"),
    )


def _run_out(run: EvalRun, qrel_set: QrelSet | None = None) -> RunOut:
    return RunOut(
        id=run.id,
        collection_id=run.collection_id,
        qrel_set_id=run.qrel_set_id,
        ranker=str(run.ranker),
        label=run.label,
        top_k=run.top_k,
        status=run.status,
        index_version=run.index_version,
        params_snapshot=run.params_snapshot,
        scored_query_count=run.scored_query_count,
        unjudged_retrieved=run.unjudged_retrieved,
        duration_ms=run.duration_ms,
        batch_id=run.batch_id,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        aggregation=str(qrel_set.aggregation) if qrel_set else None,
        threshold=qrel_set.threshold if qrel_set else None,
    )


def _qrel_set_out(qrel_set: QrelSet, stats: qrels.QrelSetStats | None = None) -> QrelSetOut:
    return QrelSetOut(
        id=qrel_set.id,
        collection_id=qrel_set.collection_id,
        name=qrel_set.name,
        aggregation=QrelAggregation(qrel_set.aggregation),
        threshold=qrel_set.threshold,
        query_count=qrel_set.query_count,
        relevant_count=qrel_set.relevant_count,
        judged_count=qrel_set.judged_count,
        excluded_queries=stats.excluded_queries if stats else None,
        disagreement_count=stats.disagreement_count if stats else None,
    )


def _significance_out(
    comparison: significance_module.ComparisonResult,
    run_a: int | None = None,
    run_b: int | None = None,
) -> SignificanceOut:
    return SignificanceOut(
        metric_key=comparison.metric_key,
        test=comparison.test,
        label_a=comparison.label_a,
        label_b=comparison.label_b,
        run_a_id=run_a,
        run_b_id=run_b,
        sample_size=comparison.sample_size,
        mean_a=comparison.mean_a,
        mean_b=comparison.mean_b,
        mean_difference=comparison.mean_difference,
        p_value=comparison.p_value,
        p_value_corrected=comparison.p_value_corrected,
        correction=comparison.correction,
        statistic=comparison.statistic,
        effect_size=comparison.effect_size,
        ci_low=comparison.ci_low,
        ci_high=comparison.ci_high,
        ties=comparison.ties,
    )


async def _judging_job_out(session: AsyncSession, job: JudgingJob) -> JudgingJobOut:
    assessor = await session.get(Assessor, job.assessor_id)
    pending = await count_pending(session, job.collection_id, job.assessor_id)
    return JudgingJobOut(
        id=job.id,
        collection_id=job.collection_id,
        assessor_id=job.assessor_id,
        assessor=assessor.name if assessor else None,
        status=job.status,
        task_id=job.task_id,
        total_pairs=job.total_pairs,
        judged_pairs=job.judged_pairs,
        failed_pairs=job.failed_pairs,
        pending_pairs=pending,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        model=str((assessor.meta or {}).get("model")) if assessor and assessor.meta else None,
    )


# ------------------------------------------------------------------ registry ----


@router.get("/metrics", response_model=MetricRegistryOut, summary="Metric registry")
async def metric_registry() -> MetricRegistryOut:
    return MetricRegistryOut(
        metrics=[_spec_out(spec) for spec in METRICS.values()],
        primary_order=list(PRIMARY_ORDER),
        curve_keys=list(CURVE_KEYS),
        primary_metric=PRIMARY_METRIC,
    )


# --------------------------------------------------------------- collections ----


@router.get("/collections", response_model=list[CollectionOut], summary="Test collections")
async def list_collections(session: AsyncSession = Depends(get_session)) -> list[CollectionOut]:
    rows = (
        (await session.execute(select(TestCollection).order_by(TestCollection.id))).scalars().all()
    )
    return [await _collection_out(session, collection) for collection in rows]


@router.post(
    "/collections/known-item",
    response_model=CollectionOut,
    summary="Build (or rebuild) the automatic known-item collection",
)
async def build_known_item(
    size: int = QueryParam(default=30, ge=5, le=200),
    replace: bool = QueryParam(default=False),
    session: AsyncSession = Depends(get_session),
) -> CollectionOut:
    from irs.eval.collection import build_known_item_collection

    collection, _ = await build_known_item_collection(session, size=size, replace=replace)
    await session.flush()
    return await _collection_out(session, collection)


@router.post(
    "/collections/topical/seed", response_model=CollectionOut, summary="Seed the topical collection"
)
async def seed_topical(
    body: SeedTopicsIn | None = None, session: AsyncSession = Depends(get_session)
) -> CollectionOut:
    import asyncio
    from pathlib import Path

    path = Path("/app/seeds/topics.yaml")
    try:
        file = await asyncio.to_thread(topics.load_topic_file, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"topics file not found at {path}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    collection, _ = await topics.seed_topics(session, file, replace=bool(body and body.replace))
    return await _collection_out(session, collection)


@router.get("/collections/{collection_id}", response_model=CollectionOut)
async def get_collection(
    collection_id: int, session: AsyncSession = Depends(get_session)
) -> CollectionOut:
    return await _collection_out(session, await _collection_or_404(session, collection_id))


@router.get("/collections/{collection_id}/topics", response_model=list[TopicOut])
async def list_topics(
    collection_id: int,
    judged_only: bool = QueryParam(default=False),
    session: AsyncSession = Depends(get_session),
) -> list[TopicOut]:
    collection = await _collection_or_404(session, collection_id)
    statement = select(Query).where(Query.collection_id == collection_id).order_by(Query.ext_id)
    if judged_only:
        statement = statement.where(Query.is_judged)
    rows = (await session.execute(statement)).scalars().all()

    pool_sizes: dict[int, int] = {
        int(query_id): int(count)
        for query_id, count in (
            await session.execute(
                select(PoolEntry.query_id, func.count())
                .join(Query, Query.id == PoolEntry.query_id)
                .where(Query.collection_id == collection_id)
                .group_by(PoolEntry.query_id)
            )
        ).all()
    }
    judged_pairs: dict[int, int] = {
        int(query_id): int(count)
        for query_id, count in (
            await session.execute(
                select(Judgment.query_id, func.count(func.distinct(Judgment.document_id)))
                .join(Query, Query.id == Judgment.query_id)
                .where(Query.collection_id == collection_id)
                .group_by(Judgment.query_id)
            )
        ).all()
    }
    frozen = collection.frozen_at is not None
    return [
        TopicOut(
            id=topic.id,
            ext_id=topic.ext_id,
            title=topic.title,
            description=topic.description,
            narrative=topic.narrative,
            category=topic.category,
            is_judged=topic.is_judged,
            selected_at=topic.selected_at,
            oracle_query=topic.oracle_query if frozen else None,
            pool_size=int(pool_sizes.get(topic.id, 0)),
            judged_pairs=int(judged_pairs.get(topic.id, 0)),
        )
        for topic in rows
    ]


@router.post("/collections/{collection_id}/topics/select", response_model=list[TopicOut])
async def select_topics(
    collection_id: int,
    body: SelectTopicsIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[TopicOut]:
    await _collection_or_404(session, collection_id)
    body = body or SelectTopicsIn()
    try:
        await topics.select_judged(session, collection_id, count=body.count, seed=body.seed)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await list_topics(collection_id, judged_only=True, session=session)


# ---------------------------------------------------------------------- pool ----


@router.post(
    "/collections/{collection_id}/pool", response_model=PoolBuildOut, summary="Build the pool"
)
async def build_pool(
    collection_id: int,
    body: PoolBuildIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> PoolBuildOut:
    await _collection_or_404(session, collection_id)
    body = body or PoolBuildIn()
    try:
        stats = await pooling.build_pool(
            session,
            collection_id,
            depth=body.depth,
            random_size=body.random_size,
            rankers=body.rankers,
            replace=body.replace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PoolBuildOut(
        topics=stats.topics,
        entries=stats.entries,
        by_source=stats.by_source,
        rankers=stats.rankers,
        oracle_ranker=stats.oracle_ranker,
        depth=stats.depth,
        random_size=stats.random_size,
        duration_ms=stats.duration_ms,
    )


@router.get("/collections/{collection_id}/pool/stats", response_model=PoolStatsOut)
async def pool_statistics(
    collection_id: int, session: AsyncSession = Depends(get_session)
) -> PoolStatsOut:
    await _collection_or_404(session, collection_id)
    stats = await pooling.pool_stats(session, collection_id)
    return PoolStatsOut(
        depth=stats.depth,
        unique_documents=stats.unique_documents,
        total_entries=stats.total_entries,
        by_source=stats.by_source,
        per_topic=stats.per_topic,
    )


async def _human_assessor(session: AsyncSession, name: str) -> Assessor:
    assessor = (
        await session.execute(select(Assessor).where(Assessor.name == name))
    ).scalar_one_or_none()
    if assessor is None:
        assessor = Assessor(name=name, kind=AssessorKind.HUMAN)
        session.add(assessor)
        await session.flush()
    return assessor


@router.get(
    "/collections/{collection_id}/pool/next",
    response_model=PoolNextOut,
    responses={204: {"description": "nothing left to judge"}},
    summary="Next blind pair to judge",
)
async def next_pair(
    collection_id: int,
    assessor: str = QueryParam(min_length=1, max_length=128),
    session: AsyncSession = Depends(get_session),
) -> Response | PoolNextOut:
    """One unjudged pair for this assessor: topic and document, nothing else.

    No ranker, rank, score or provenance is exposed, and the order is a hash of the pair
    and the assessor, so it cannot correlate with any system's ranking.
    """
    await _collection_or_404(session, collection_id)
    person = await _human_assessor(session, assessor)

    already = (
        select(Judgment.id)
        .where(
            Judgment.query_id == PoolEntry.query_id,
            Judgment.document_id == PoolEntry.document_id,
            Judgment.assessor_id == person.id,
        )
        .exists()
    )
    base = (
        select(PoolEntry.query_id, PoolEntry.document_id)
        .join(Query, Query.id == PoolEntry.query_id)
        .where(Query.collection_id == collection_id, Query.is_judged)
    )
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    pending_statement = base.where(~already)
    remaining = int(
        (
            await session.execute(select(func.count()).select_from(pending_statement.subquery()))
        ).scalar_one()
    )
    if remaining == 0:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    shuffle_key = func.md5(
        literal(f"{person.id}:")
        + cast(PoolEntry.query_id, String)
        + ":"
        + cast(PoolEntry.document_id, String)
    )
    row = (await session.execute(pending_statement.order_by(shuffle_key).limit(1))).first()
    assert row is not None
    topic = await session.get(Query, int(row[0]))
    document = await session.get(Document, int(row[1]))
    assert topic is not None and document is not None

    return PoolNextOut(
        topic=PoolNextTopicOut(
            id=topic.id,
            ext_id=topic.ext_id,
            title=topic.title,
            description=topic.description,
            narrative=topic.narrative,
        ),
        document=PoolNextDocumentOut(
            id=document.id,
            title=document.title or "(untitled)",
            url=document.url,
            text=(document.text or "")[:8_000],
        ),
        remaining=remaining,
        total=total,
        judged_by_you=total - remaining,
    )


# ----------------------------------------------------------------- assessors ----


@router.get("/assessors", response_model=list[AssessorOut])
async def list_assessors(session: AsyncSession = Depends(get_session)) -> list[AssessorOut]:
    return await _assessor_outs(session)


@router.post("/assessors", response_model=AssessorOut, status_code=status.HTTP_201_CREATED)
async def create_assessor(
    body: AssessorIn, session: AsyncSession = Depends(get_session)
) -> AssessorOut:
    assessor = await _human_assessor(session, body.name.strip())
    return AssessorOut(
        id=assessor.id, name=assessor.name, kind=str(assessor.kind), meta=assessor.meta
    )


# ----------------------------------------------------------------- judgments ----


@router.post("/judgments", response_model=JudgmentOut, summary="Record a judgment")
async def record_judgment(
    body: JudgmentIn, session: AsyncSession = Depends(get_session)
) -> JudgmentOut:
    in_pool = (
        await session.execute(
            select(PoolEntry.id).where(
                PoolEntry.query_id == body.query_id, PoolEntry.document_id == body.document_id
            )
        )
    ).first()
    if in_pool is None:
        raise HTTPException(
            status_code=422, detail="that (topic, document) pair is not in the judgment pool"
        )

    person = await _human_assessor(session, body.assessor.strip())
    statement = pg_insert(Judgment).values(
        query_id=body.query_id,
        document_id=body.document_id,
        assessor_id=person.id,
        grade=str(body.grade),
        seconds_spent=body.seconds_spent,
        note=body.note,
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_judgment_pair_assessor",
            set_={
                "grade": statement.excluded.grade,
                "seconds_spent": statement.excluded.seconds_spent,
                "note": statement.excluded.note,
            },
        )
    )
    judgment = (
        await session.execute(
            select(Judgment).where(
                Judgment.query_id == body.query_id,
                Judgment.document_id == body.document_id,
                Judgment.assessor_id == person.id,
            )
        )
    ).scalar_one()
    return JudgmentOut(
        id=judgment.id,
        query_id=judgment.query_id,
        document_id=judgment.document_id,
        assessor_id=person.id,
        assessor=person.name,
        grade=RelevanceGrade(judgment.grade),
        seconds_spent=judgment.seconds_spent,
        note=judgment.note,
        created_at=judgment.created_at,
    )


@router.get("/collections/{collection_id}/judgments", response_model=list[JudgmentOut])
async def list_judgments(
    collection_id: int,
    query_id: int | None = QueryParam(default=None),
    assessor: str | None = QueryParam(default=None),
    limit: int = QueryParam(default=200, ge=1, le=2_000),
    offset: int = QueryParam(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[JudgmentOut]:
    await _collection_or_404(session, collection_id)
    statement = (
        select(Judgment, Assessor.name)
        .join(Query, Query.id == Judgment.query_id)
        .join(Assessor, Assessor.id == Judgment.assessor_id)
        .where(Query.collection_id == collection_id)
        .order_by(Judgment.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if query_id is not None:
        statement = statement.where(Judgment.query_id == query_id)
    if assessor:
        statement = statement.where(Assessor.name == assessor)
    return [
        JudgmentOut(
            id=j.id,
            query_id=j.query_id,
            document_id=j.document_id,
            assessor_id=j.assessor_id,
            assessor=name,
            grade=RelevanceGrade(j.grade),
            seconds_spent=j.seconds_spent,
            note=j.note,
            created_at=j.created_at,
        )
        for j, name in (await session.execute(statement)).all()
    ]


# ------------------------------------------------------------ LLM judging jobs ----


@router.post(
    "/collections/{collection_id}/judging",
    response_model=JudgingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start the LLM assessor over the pending pool pairs",
)
async def start_judging(
    collection_id: int,
    body: JudgingStartIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> JudgingJobOut:
    await _collection_or_404(session, collection_id)
    running = (
        (
            await session.execute(
                select(JudgingJob).where(
                    JudgingJob.collection_id == collection_id,
                    JudgingJob.status.in_([EvalRunStatus.PENDING, EvalRunStatus.RUNNING]),
                )
            )
        )
        .scalars()
        .first()
    )
    if running is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"judging job {running.id} is already {running.status} for this collection",
        )

    assessor = LlmAssessor()
    assessor_row = await get_or_create_llm_assessor(session, assessor)
    job = await create_judging_job(
        session, collection_id, assessor_row.id, limit=body.limit if body else None
    )
    if job.total_pairs == 0:
        job.status = EvalRunStatus.DONE
        await session.commit()
        return await _judging_job_out(session, job)
    await session.commit()

    from irs.eval.tasks import judge_pool

    try:
        handle = await judge_pool.kiq(job.id)
        job.task_id = handle.task_id
        await session.commit()
    except Exception as exc:
        log.error("judging_enqueue_failed", job_id=job.id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"judging job {job.id} was created but could not be queued: {exc}. "
                "Is the worker running?"
            ),
        ) from exc
    return await _judging_job_out(session, job)


@router.get("/judging/jobs", response_model=list[JudgingJobOut])
async def list_judging_jobs(
    collection_id: int | None = QueryParam(default=None),
    limit: int = QueryParam(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[JudgingJobOut]:
    statement = select(JudgingJob).order_by(JudgingJob.id.desc()).limit(limit)
    if collection_id is not None:
        statement = statement.where(JudgingJob.collection_id == collection_id)
    return [
        await _judging_job_out(session, job) for job in (await session.execute(statement)).scalars()
    ]


@router.get("/judging/jobs/{job_id}", response_model=JudgingJobOut)
async def get_judging_job(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> JudgingJobOut:
    job = await session.get(JudgingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"judging job {job_id} not found")
    return await _judging_job_out(session, job)


@router.get("/judging/assessor", summary="The configured LLM assessor")
async def describe_assessor() -> dict[str, Any]:
    assessor = LlmAssessor()
    try:
        await assessor.healthcheck()
        reachable, problem = True, None
    except Exception as exc:
        reachable, problem = False, str(exc)
    finally:
        await assessor.aclose()
    return {
        "name": assessor.assessor_name,
        "meta": assessor.meta(),
        "reachable": reachable,
        "problem": problem,
    }


# ----------------------------------------------------------------- qrel sets ----


@router.post("/collections/{collection_id}/qrel-sets", response_model=QrelSetOut)
async def materialize_qrels(
    collection_id: int, body: QrelSetIn | None = None, session: AsyncSession = Depends(get_session)
) -> QrelSetOut:
    await _collection_or_404(session, collection_id)
    body = body or QrelSetIn()
    qrel_set, stats = await qrels.materialize(
        session, collection_id, body.aggregation, body.threshold
    )
    return _qrel_set_out(qrel_set, stats)


@router.get("/collections/{collection_id}/qrel-sets", response_model=list[QrelSetOut])
async def list_qrel_sets(
    collection_id: int, session: AsyncSession = Depends(get_session)
) -> list[QrelSetOut]:
    await _collection_or_404(session, collection_id)
    rows = (
        await session.execute(
            select(QrelSet).where(QrelSet.collection_id == collection_id).order_by(QrelSet.id)
        )
    ).scalars()
    return [_qrel_set_out(q) for q in rows]


@router.get("/qrel-sets/{qrel_set_id}/trec", response_class=Response, summary="TREC qrels export")
async def export_qrels(qrel_set_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    if await session.get(QrelSet, qrel_set_id) is None:
        raise HTTPException(status_code=404, detail=f"qrel set {qrel_set_id} not found")
    judgments = await qrels.load_judgments(session, qrel_set_id)
    return Response(content=format_qrels(judgments), media_type="text/plain")


# ---------------------------------------------------------------------- runs ----


@router.post(
    "/runs", response_model=RunBatchOut, status_code=status.HTTP_202_ACCEPTED, summary="Start runs"
)
async def start_runs(body: RunStartIn, session: AsyncSession = Depends(get_session)) -> RunBatchOut:
    """Materialise the relevance table, register one run per ranker, hand them to the worker."""
    await _collection_or_404(session, body.collection_id)
    threshold = (
        settings.evaluation.binary_relevance_threshold if body.threshold is None else body.threshold
    )
    qrel_set, stats = await qrels.materialize(
        session, body.collection_id, body.aggregation, threshold
    )
    if qrel_set.query_count == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "no topic has a relevant document under this relevance table — judge the pool first"
            ),
        )

    keys = list(body.rankers) if body.rankers else sorted(get_rankers(), key=str)
    batch_id = uuid.uuid4().hex[:16]
    runs = [
        await create_run(
            session, body.collection_id, qrel_set.id, key, top_k=body.top_k, batch_id=batch_id
        )
        for key in keys
    ]
    await session.commit()

    from irs.eval.tasks import execute_runs

    try:
        await execute_runs.kiq([run.id for run in runs])
    except Exception as exc:
        log.error("runs_enqueue_failed", batch_id=batch_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"runs were registered but could not be queued: {exc}. Is the worker running?",
        ) from exc

    return RunBatchOut(
        batch_id=batch_id,
        qrel_set=_qrel_set_out(qrel_set, stats),
        runs=[_run_out(r, qrel_set) for r in runs],
    )


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    collection_id: int | None = QueryParam(default=None),
    qrel_set_id: int | None = QueryParam(default=None),
    batch_id: str | None = QueryParam(default=None),
    ranker: RankerKey | None = QueryParam(default=None),
    run_status: EvalRunStatus | None = QueryParam(default=None, alias="status"),
    limit: int = QueryParam(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[RunOut]:
    statement = (
        select(EvalRun, QrelSet)
        .join(QrelSet, QrelSet.id == EvalRun.qrel_set_id)
        .order_by(EvalRun.id.desc())
        .limit(limit)
    )
    if collection_id is not None:
        statement = statement.where(EvalRun.collection_id == collection_id)
    if qrel_set_id is not None:
        statement = statement.where(EvalRun.qrel_set_id == qrel_set_id)
    if batch_id:
        statement = statement.where(EvalRun.batch_id == batch_id)
    if ranker is not None:
        statement = statement.where(EvalRun.ranker == ranker)
    if run_status is not None:
        statement = statement.where(EvalRun.status == run_status)
    return [_run_out(run, qrel_set) for run, qrel_set in (await session.execute(statement)).all()]


async def _caveats_for(session: AsyncSession, run: EvalRun) -> list[MetricCaveat]:
    judgments = await qrels.load_judgments(session, run.qrel_set_id)
    max_assessors = (
        await session.execute(
            select(func.max(Qrel.assessor_count)).where(Qrel.qrel_set_id == run.qrel_set_id)
        )
    ).scalar_one()
    return metric_caveats(judgments, top_k=run.top_k, single_assessor=(max_assessors or 1) <= 1)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)) -> RunDetailOut:
    run = await _run_or_404(session, run_id)
    qrel_set = await session.get(QrelSet, run.qrel_set_id)
    metrics = (
        (await session.execute(select(RunMetric).where(RunMetric.run_id == run_id))).scalars().all()
    )
    base = _run_out(run, qrel_set)
    return RunDetailOut(
        **base.model_dump(),
        aggregate=[
            AggregateMetricOut(
                metric_key=m.metric_key,
                value=m.value,
                query_count=m.query_count,
                ci_low=m.ci_low,
                ci_high=m.ci_high,
            )
            for m in sorted(metrics, key=lambda m: m.metric_key)
        ],
        caveats=[
            CaveatOut(metric_key=c.metric_key, kind=c.kind, note=c.note)
            for c in await _caveats_for(session, run)
        ]
        if run.status == EvalRunStatus.DONE
        else [],
    )


async def _query_metrics(session: AsyncSession, run_id: int) -> list[QueryMetricsOut]:
    per_query = await load_per_query(session, run_id)
    if not per_query:
        return []
    rows = (
        await session.execute(
            select(Query.id, Query.ext_id, Query.title, Query.category).where(
                Query.id.in_(list(per_query))
            )
        )
    ).all()
    out = [
        QueryMetricsOut(
            query_id=qid, ext_id=ext_id, title=title, category=category, metrics=per_query[qid]
        )
        for qid, ext_id, title, category in rows
    ]
    out.sort(key=lambda q: (q.metrics.get(PRIMARY_METRIC, 0.0), q.ext_id))
    return out


@router.get(
    "/runs/{run_id}/queries", response_model=list[QueryMetricsOut], summary="Per-topic metrics"
)
async def run_queries(
    run_id: int, session: AsyncSession = Depends(get_session)
) -> list[QueryMetricsOut]:
    await _run_or_404(session, run_id)
    return await _query_metrics(session, run_id)


@router.get("/runs/{run_id}/queries/{query_id}", response_model=QueryDrilldownOut)
async def run_query_drilldown(
    run_id: int,
    query_id: int,
    top: int = QueryParam(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> QueryDrilldownOut:
    run = await _run_or_404(session, run_id)
    summaries = {q.query_id: q for q in await _query_metrics(session, run_id)}
    if query_id not in summaries:
        raise HTTPException(
            status_code=404, detail=f"topic {query_id} was not scored in run {run_id}"
        )

    qrel_rows = (
        await session.execute(
            select(Qrel.document_id, Qrel.is_relevant, Qrel.gain, Qrel.is_unjudged).where(
                Qrel.qrel_set_id == run.qrel_set_id, Qrel.query_id == query_id
            )
        )
    ).all()
    judged = {int(d): (bool(rel), float(gain), bool(unj)) for d, rel, gain, unj in qrel_rows}

    grade_rows = (
        await session.execute(
            select(Judgment.document_id, Judgment.grade).where(Judgment.query_id == query_id)
        )
    ).all()
    grades: dict[int, str] = {}
    for document_id, grade in grade_rows:
        grades.setdefault(int(document_id), str(grade))

    results = (
        await session.execute(
            select(
                RunResult.rank, RunResult.document_id, RunResult.score, Document.title, Document.url
            )
            .join(Document, Document.id == RunResult.document_id)
            .where(RunResult.run_id == run_id, RunResult.query_id == query_id)
            .order_by(RunResult.rank)
            .limit(top)
        )
    ).all()

    def ranked(
        rank: int, document_id: int, score: float, title: str, url: str
    ) -> RankedDocumentOut:
        mark = judged.get(document_id)
        return RankedDocumentOut(
            rank=rank,
            document_id=document_id,
            title=title,
            url=url,
            score=float(score),
            grade=grades.get(document_id),
            gain=mark[1] if mark else None,
            is_relevant=mark[0] if mark else None,
            is_judged=mark is not None and not mark[2],
        )

    relevant_ids = [d for d, (rel, _, _) in judged.items() if rel]
    relevant_docs = (
        (
            await session.execute(
                select(Document.id, Document.title, Document.url).where(
                    Document.id.in_(relevant_ids)
                )
            )
        ).all()
        if relevant_ids
        else []
    )
    positions = (
        {
            int(d): int(r)
            for r, d in (
                await session.execute(
                    select(RunResult.rank, RunResult.document_id).where(
                        RunResult.run_id == run_id,
                        RunResult.query_id == query_id,
                        RunResult.document_id.in_(relevant_ids),
                    )
                )
            ).all()
        }
        if relevant_ids
        else {}
    )

    curve = (
        await session.execute(
            select(RunQueryCurve.points).where(
                RunQueryCurve.run_id == run_id,
                RunQueryCurve.query_id == query_id,
                RunQueryCurve.curve_key == "pr_raw",
            )
        )
    ).scalar_one_or_none()

    return QueryDrilldownOut(
        query=summaries[query_id],
        top=[ranked(int(r), int(d), float(s), t, u) for r, d, s, t, u in results],
        pr_raw=[[float(x) for x in point] for point in (curve or [])],
        relevant_total=len(relevant_ids),
        relevant_documents=sorted(
            (ranked(positions.get(int(d), 0), int(d), 0.0, t, u) for d, t, u in relevant_docs),
            key=lambda r: (r.rank == 0, r.rank),
        ),
    )


@router.get("/runs/{run_id}/curves", response_model=list[CurveOut])
async def run_curves(run_id: int, session: AsyncSession = Depends(get_session)) -> list[CurveOut]:
    await _run_or_404(session, run_id)
    rows = (
        await session.execute(
            select(RunCurve).where(RunCurve.run_id == run_id).order_by(RunCurve.curve_key)
        )
    ).scalars()
    by_key = {row.curve_key: row for row in rows}
    out: list[CurveOut] = []
    for key, row in by_key.items():
        if key.endswith("_support"):
            continue
        support_row = by_key.get(f"{key}_support")
        out.append(
            CurveOut(
                curve_key=key,
                points=row.points,
                support=support_row.points if support_row else None,
            )
        )
    return out


@router.get("/runs/{run_id}/trec", response_class=Response, summary="TREC run export")
async def export_run(run_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    run = await _run_or_404(session, run_id)
    rows = (
        await session.execute(
            select(RunResult.query_id, RunResult.document_id, RunResult.score)
            .where(RunResult.run_id == run_id)
            .order_by(RunResult.query_id, RunResult.rank)
        )
    ).all()
    rankings: dict[int, list[tuple[int, float]]] = {}
    for query_id, document_id, score in rows:
        rankings.setdefault(int(query_id), []).append((int(document_id), float(score)))
    return Response(
        content=format_run(rankings, run_id=f"{run.ranker}-{run.id}"), media_type="text/plain"
    )


# ------------------------------------------------------------------- compare ----


@router.get("/compare", response_model=CompareOut, summary="Compare runs on their common topics")
async def compare_runs(
    runs: str = QueryParam(description="comma-separated run ids; the first is the baseline"),
    metric: str = QueryParam(default=PRIMARY_METRIC),
    session: AsyncSession = Depends(get_session),
) -> CompareOut:
    try:
        run_ids = [int(part) for part in runs.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="runs must be comma-separated integers"
        ) from exc
    if not run_ids:
        raise HTTPException(status_code=422, detail="at least one run id is required")
    if metric not in METRICS:
        raise HTTPException(status_code=422, detail=f"unknown metric {metric!r}")

    loaded = [await _run_or_404(session, rid) for rid in run_ids]
    if len({run.collection_id for run in loaded}) > 1:
        raise HTTPException(
            status_code=422, detail="runs span different test collections and cannot be compared"
        )

    per_query = {rid: await load_per_query(session, rid) for rid in run_ids}
    shared = set.intersection(*(set(pq) for pq in per_query.values())) if per_query else set()
    topics_sorted = sorted(shared)

    stored = {
        rid: (
            await session.execute(
                select(RunMetric).where(RunMetric.run_id == rid, RunMetric.metric_key == metric)
            )
        ).scalar_one_or_none()
        for rid in run_ids
    }
    seed = settings.evaluation.random_seed
    means: dict[int, float] = {}
    rows: list[CompareRowOut] = []
    for run in loaded:
        values = [per_query[run.id][qid].get(metric, 0.0) for qid in topics_sorted]
        mean = statistics.fmean(values) if values else 0.0
        means[run.id] = mean
        ci = (
            significance_module.bootstrap_interval(values, seed=seed)
            if len(values) > 1
            else (mean, mean)
        )
        row_stored = stored[run.id]
        rows.append(
            CompareRowOut(
                run_id=run.id,
                ranker=str(run.ranker),
                label=f"{run.ranker}#{run.id}",
                mean_on_intersection=mean,
                ci_low=ci[0],
                ci_high=ci[1],
                stored_mean=row_stored.value if row_stored else None,
                stored_query_count=row_stored.query_count if row_stored else 0,
                dropped_topics=len(per_query[run.id]) - len(topics_sorted),
            )
        )
    baseline = run_ids[0]
    for row in rows:
        row.delta_vs_baseline = row.mean_on_intersection - means[baseline]

    titles: dict[int, int] = (
        {
            int(query_id): int(ext_id)
            for query_id, ext_id in (
                await session.execute(
                    select(Query.id, Query.ext_id).where(Query.id.in_(topics_sorted))
                )
            ).all()
        }
        if topics_sorted
        else {}
    )
    per_topic = [
        {
            "query_id": qid,
            "ext_id": titles.get(qid),
            "values": {str(rid): per_query[rid][qid].get(metric, 0.0) for rid in run_ids},
        }
        for qid in topics_sorted
    ]
    return CompareOut(
        metric=metric,
        topic_count=len(topics_sorted),
        baseline_run_id=baseline,
        rows=rows,
        per_topic=per_topic,
    )


# -------------------------------------------------------------- significance ----


@router.get(
    "/significance", response_model=list[SignificanceOut], summary="Pairwise significance (live)"
)
async def significance(
    runs: str = QueryParam(description="comma-separated run ids"),
    metric: str = QueryParam(default=PRIMARY_METRIC),
    test: str = QueryParam(default="permutation", pattern="^(permutation|wilcoxon|ttest_rel)$"),
    session: AsyncSession = Depends(get_session),
) -> list[SignificanceOut]:
    try:
        run_ids = [int(part) for part in runs.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="runs must be comma-separated integers"
        ) from exc
    if len(run_ids) < 2:
        raise HTTPException(status_code=422, detail="at least two run ids are required")
    if metric not in METRICS:
        raise HTTPException(status_code=422, detail=f"unknown metric {metric!r}")
    try:
        results = await compare_stored_runs(session, run_ids, metric_key=metric, test=test)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_significance_out(c, *_ids_from_labels(c.label_a, c.label_b)) for c in results]


def _ids_from_labels(label_a: str, label_b: str) -> tuple[int | None, int | None]:
    def parse(label: str) -> int | None:
        try:
            return int(label.rsplit("#", 1)[1])
        except (IndexError, ValueError):
            return None

    return parse(label_a), parse(label_b)


@router.get(
    "/runs/{run_id}/significance",
    response_model=list[SignificanceOut],
    summary="Stored comparisons",
)
async def stored_significance(
    run_id: int, session: AsyncSession = Depends(get_session)
) -> list[SignificanceOut]:
    await _run_or_404(session, run_id)
    rows = (
        (
            await session.execute(
                select(SignificanceResult).where(
                    (SignificanceResult.run_a_id == run_id)
                    | (SignificanceResult.run_b_id == run_id)
                )
            )
        )
        .scalars()
        .all()
    )
    ids = {r.run_a_id for r in rows} | {r.run_b_id for r in rows}
    labels = (
        {
            rid: f"{ranker}#{rid}"
            for rid, ranker in (
                await session.execute(
                    select(EvalRun.id, EvalRun.ranker).where(EvalRun.id.in_(list(ids)))
                )
            ).all()
        }
        if ids
        else {}
    )
    return [
        SignificanceOut(
            metric_key=r.metric_key,
            test=r.test,
            label_a=labels.get(r.run_a_id, str(r.run_a_id)),
            label_b=labels.get(r.run_b_id, str(r.run_b_id)),
            run_a_id=r.run_a_id,
            run_b_id=r.run_b_id,
            sample_size=r.sample_size,
            mean_a=0.0,
            mean_b=0.0,
            mean_difference=r.mean_difference,
            p_value=r.p_value,
            p_value_corrected=r.p_value_corrected,
            correction=r.correction,
            statistic=r.statistic,
            effect_size=r.effect_size,
            ci_low=r.ci_low,
            ci_high=r.ci_high,
        )
        for r in rows
    ]


# -------------------------------------------------------------------- stream ----


@router.get("/stream", summary="Live judging and run progress (SSE)")
async def stream_progress(request: Request) -> EventSourceResponse:
    return channel_response(request, PROGRESS_CHANNEL)
