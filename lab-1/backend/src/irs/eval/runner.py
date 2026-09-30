"""Executing and scoring evaluation runs.

One run = one ranker over one topic set, scored against one relevance table. The run's
result list is **persisted** before any metric is computed, for two reasons: a stored
metric can then be traced back to the exact ranking that produced it, and re-scoring
against a corrected relevance table does not require re-running retrieval.

Averaging is **macro** — each metric is computed per topic and then averaged unweighted
over topics. The assignment's 2004 PDF calls this "микроусреднение", but that edition has
the micro/macro definitions swapped; ROMIP's own 2010 edition corrects the label while
keeping the procedure identical. The report notes the discrepancy with the citation.
"""

from __future__ import annotations

import statistics
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import (
    EvalRun,
    Query,
    RunCurve,
    RunMetric,
    RunQueryCurve,
    RunQueryMetric,
    RunResult,
)
from irs.db.models.enums import EvalRunStatus, RankerKey
from irs.eval import metrics as m
from irs.eval.registry import METRICS, MetricEdition, MetricKind
from irs.index.builder import get_collection_stat
from irs.logging import Stopwatch, get_logger
from irs.selection.base import ScoredDocument, SearchFilters
from irs.selection.parser import parse_query
from irs.selection.registry import get_ranker

log = get_logger("irs.eval.runner")


@dataclass(slots=True)
class RunOutcome:
    run_id: int
    ranker: RankerKey
    scored_queries: int
    aggregate: dict[str, float] = field(default_factory=dict)
    per_query: dict[int, dict[str, float]] = field(default_factory=dict)
    curves: dict[str, list[list[float]]] = field(default_factory=dict)
    unjudged_retrieved: int = 0
    duration_ms: float = 0.0


ProgressHook = Callable[[int, int], Awaitable[None]]


async def create_run(
    session: AsyncSession,
    collection_id: int,
    qrel_set_id: int,
    ranker_key: RankerKey,
    top_k: int | None = None,
    batch_id: str | None = None,
) -> EvalRun:
    """Register a run without executing it — the API's background path."""
    top_k = top_k or settings.evaluation.run_depth
    stat = await get_collection_stat(session)
    run = EvalRun(
        collection_id=collection_id,
        qrel_set_id=qrel_set_id,
        ranker=ranker_key,
        label=str(ranker_key),
        top_k=top_k,
        status=EvalRunStatus.PENDING,
        params_snapshot=_snapshot_params(ranker_key),
        index_version=stat.index_version,
        batch_id=batch_id,
    )
    session.add(run)
    await session.flush()
    return run


async def execute_existing_run(
    session: AsyncSession,
    run: EvalRun,
    judgments: dict[int, m.QueryJudgments],
    on_progress: ProgressHook | None = None,
) -> RunOutcome:
    """Retrieve and score a registered run, marking it RUNNING → DONE/FAILED."""
    watch = Stopwatch()
    ranker_key = RankerKey(run.ranker)
    run.status = EvalRunStatus.RUNNING
    run.started_at = datetime.now(UTC).replace(tzinfo=None)
    run.error = None
    await session.flush()

    try:
        outcome = await _retrieve_and_score(
            session, run, judgments, ranker_key, run.top_k, watch, on_progress
        )
    except Exception as exc:
        run.status = EvalRunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2_000]
        run.finished_at = datetime.now(UTC).replace(tzinfo=None)
        await session.flush()
        log.exception("run_failed", run_id=run.id, ranker=str(ranker_key))
        raise

    run.status = EvalRunStatus.DONE
    run.finished_at = datetime.now(UTC).replace(tzinfo=None)
    run.duration_ms = watch.total_ms
    run.scored_query_count = outcome.scored_queries
    run.unjudged_retrieved = outcome.unjudged_retrieved
    await session.flush()

    log.info(
        "run_completed",
        run_id=run.id,
        ranker=str(ranker_key),
        num_q=outcome.scored_queries,
        map=round(outcome.aggregate.get("ap", 0.0), 4),
        p_10=round(outcome.aggregate.get("p_10", 0.0), 4),
        unjudged_retrieved=outcome.unjudged_retrieved,
        duration_ms=round(watch.total_ms, 1),
    )
    return outcome


async def execute_run(
    session: AsyncSession,
    collection_id: int,
    qrel_set_id: int,
    ranker_key: RankerKey,
    judgments: dict[int, m.QueryJudgments],
    top_k: int | None = None,
) -> RunOutcome:
    """Retrieve for every judged topic, then score the run (register + execute)."""
    run = await create_run(session, collection_id, qrel_set_id, ranker_key, top_k)
    return await execute_existing_run(session, run, judgments)


async def _retrieve_and_score(
    session: AsyncSession,
    run: EvalRun,
    judgments: dict[int, m.QueryJudgments],
    ranker_key: RankerKey,
    top_k: int,
    watch: Stopwatch,
    on_progress: ProgressHook | None = None,
) -> RunOutcome:
    ranker = get_ranker(ranker_key)

    topics = (
        await session.execute(
            select(Query.id, Query.title).where(Query.id.in_(list(judgments))).order_by(Query.id)
        )
    ).all()

    per_query: dict[int, dict[str, float]] = {}
    per_query_curves: dict[int, dict[str, list[list[float]]]] = {}
    runs_for_curve: list[tuple[list[int], m.QueryJudgments]] = []
    unjudged_total = 0

    # Sorted by topic id so repeated runs accumulate floats in the same order and are
    # bit-identical — otherwise a "regression test" flickers in the last digits.
    for topic_id, title in topics:
        marks = judgments[topic_id]
        parsed = await parse_query(session, title)
        page = await ranker.rank(session, parsed, SearchFilters(), limit=top_k)

        ranked = [document.document_id for document in page.documents]
        _assert_unique(ranked, run.id, topic_id)

        await _store_results(session, run.id, topic_id, page.documents)

        judged = marks.judged
        unjudged_here = sum(1 for document_id in ranked if document_id not in judged)
        unjudged_total += unjudged_here

        per_query[topic_id] = _score_one(ranked, marks, unjudged_here)
        per_query_curves[topic_id] = {
            "pr_raw": [list(point) for point in m.pr_curve(ranked, marks).points]
        }
        runs_for_curve.append((ranked, marks))
        if on_progress is not None:
            await on_progress(len(per_query), len(topics))

    watch.lap("retrieve")

    aggregate = _macro_average(per_query)
    curves = _build_curves(runs_for_curve)
    watch.lap("score")

    await _store_metrics(session, run.id, per_query, aggregate, curves, per_query_curves)
    watch.lap("persist")

    return RunOutcome(
        run_id=run.id,
        ranker=ranker_key,
        scored_queries=len(per_query),
        aggregate=aggregate,
        per_query=per_query,
        curves=curves,
        unjudged_retrieved=unjudged_total,
        duration_ms=watch.total_ms,
    )


def _assert_unique(ranked: list[int], run_id: int, query_id: int) -> None:
    """A ranking must not repeat a document.

    Metrics are not defensive about duplicates — average precision would exceed its
    range — so the invariant is enforced here, where a violation names the ranker that
    caused it instead of surfacing as an impossible score.
    """
    if len(set(ranked)) != len(ranked):
        duplicates = [d for d in set(ranked) if ranked.count(d) > 1]
        raise ValueError(f"run {run_id} query {query_id}: ranking repeats documents {duplicates}")


def _score_one(
    ranked: list[int], marks: m.QueryJudgments, unjudged_retrieved: int
) -> dict[str, float]:
    """Every scalar metric for one topic."""
    precision = m.set_precision(ranked, marks)
    recall = m.set_recall(ranked, marks)

    scores: dict[str, float] = {
        "precision": precision,
        "recall": recall,
        "f1": m.f_measure(precision, recall),
        "ap": m.average_precision(ranked, marks),
        "rprec": m.r_precision(ranked, marks),
        "bpref": m.bpref(ranked, marks),
        "mrr": m.reciprocal_rank(ranked, marks),
        "err": m.err(ranked, marks),
        "pfound": m.pfound(ranked, marks),
        # diagnostics
        "num_ret": float(len(ranked)),
        "num_rel_ret": float(sum(1 for d in ranked if marks.is_relevant(d))),
        "num_unjudged_ret": float(unjudged_retrieved),
        "num_rel": float(marks.r),
    }

    for k in settings.evaluation.cutoffs:
        scores[f"p_{k}"] = m.precision_at_k(ranked, marks, k)
    for k in (5, 10):
        scores[f"ndcg_{k}"] = m.ndcg(ranked, marks, k)

    return scores


def _macro_average(per_query: dict[int, dict[str, float]]) -> dict[str, float]:
    """Mean of each metric over topics — macro-averaging.

    Diagnostic counters are summed rather than averaged: "45 unjudged documents were
    retrieved" is the useful figure, not "1.5 per topic".
    """
    if not per_query:
        return {}

    summed = {"num_ret", "num_rel_ret", "num_unjudged_ret"}
    keys = sorted({key for scores in per_query.values() for key in scores})
    # Iterated in sorted topic order for reproducible floating-point accumulation.
    ordered = [per_query[topic_id] for topic_id in sorted(per_query)]

    aggregate: dict[str, float] = {}
    for key in keys:
        values = [scores.get(key, 0.0) for scores in ordered]
        aggregate[key] = sum(values) if key in summed else statistics.fmean(values)
    return aggregate


def _build_curves(
    runs: list[tuple[list[int], m.QueryJudgments]],
) -> dict[str, list[list[float]]]:
    """The aggregate curves the interface plots."""
    levels = list(m.ELEVEN_POINT_LEVELS)

    trec = m.interpolated_precision_11pt(runs)
    nonzeroing, support = m.interpolated_precision_11pt_nonzeroing(runs)

    curves: dict[str, list[list[float]]] = {
        "iprec11": [[level, value] for level, value in zip(levels, trec, strict=True)],
        "iprec11_nz": [[level, value] for level, value in zip(levels, nonzeroing, strict=True)],
        # Support is carried as a curve of its own so the chart can annotate how many
        # topics contributed at each recall level.
        "iprec11_nz_support": [
            [level, float(count)] for level, count in zip(levels, support, strict=True)
        ],
    }

    # P@k as a function of k, which is where rankers separate on early precision.
    cutoffs = sorted({1, 3, 5, 10, 15, 20, 30, *settings.evaluation.cutoffs})
    p_at_k: list[list[float]] = []
    for k in cutoffs:
        values = [m.precision_at_k(ranked, marks, k) for ranked, marks in runs]
        if values:
            p_at_k.append([float(k), statistics.fmean(values)])
    curves["p_at_k"] = p_at_k

    return curves


async def _store_results(
    session: AsyncSession,
    run_id: int,
    query_id: int,
    documents: list[ScoredDocument],
) -> None:
    """Persist the ranking itself — the «прогон»."""
    if not documents:
        return
    session.add_all(
        [
            RunResult(
                run_id=run_id,
                query_id=query_id,
                rank=position,
                document_id=document.document_id,
                score=document.score,
            )
            for position, document in enumerate(documents, start=1)
        ]
    )
    await session.flush()


async def _store_metrics(
    session: AsyncSession,
    run_id: int,
    per_query: dict[int, dict[str, float]],
    aggregate: dict[str, float],
    curves: dict[str, list[list[float]]],
    per_query_curves: dict[int, dict[str, list[list[float]]]],
) -> None:
    await session.execute(delete(RunQueryMetric).where(RunQueryMetric.run_id == run_id))
    await session.execute(delete(RunMetric).where(RunMetric.run_id == run_id))
    await session.execute(delete(RunCurve).where(RunCurve.run_id == run_id))
    await session.execute(delete(RunQueryCurve).where(RunQueryCurve.run_id == run_id))

    session.add_all(
        [
            RunQueryMetric(run_id=run_id, query_id=query_id, metric_key=key, value=value)
            for query_id, scores in sorted(per_query.items())
            for key, value in sorted(scores.items())
        ]
    )

    # `query_count` is stored per metric, not per run: ROMIP's zero-relevant exclusion
    # can drop a different topic set for different metrics, and a mean is only
    # interpretable next to the count it was taken over.
    session.add_all(
        [
            RunMetric(
                run_id=run_id,
                metric_key=key,
                value=value,
                query_count=len(per_query),
                averaging="macro",
            )
            for key, value in sorted(aggregate.items())
        ]
    )

    session.add_all(
        [
            RunCurve(
                run_id=run_id,
                curve_key=key,
                points=points,
                support=None,
            )
            for key, points in sorted(curves.items())
        ]
    )

    session.add_all(
        [
            RunQueryCurve(run_id=run_id, query_id=query_id, curve_key=key, points=points)
            for query_id, per_key in sorted(per_query_curves.items())
            for key, points in sorted(per_key.items())
        ]
    )

    await session.flush()


def _snapshot_params(ranker_key: RankerKey) -> dict[str, object]:
    """Record the configuration a run was produced under.

    A metric without its parameters is not reproducible: nobody remembers weeks later
    which BM25 `b` produced which MAP.
    """
    common: dict[str, object] = {
        "log_base": settings.index.log_base,
        "run_depth": settings.evaluation.run_depth,
        "keep_pos_tags": list(settings.index.keep_pos_tags),
        "min_token_length": settings.index.min_token_length,
    }
    if ranker_key is RankerKey.BM25:
        common |= {"k1": settings.search.bm25_k1, "b": settings.search.bm25_b}
    if ranker_key is RankerKey.HYBRID:
        common |= {"rrf_k": settings.search.rrf_k}
    if ranker_key is RankerKey.VECTOR_PRF:
        common |= {
            "prf_feedback_docs": settings.search.prf_feedback_docs,
            "prf_expansion_terms": settings.search.prf_expansion_terms,
            "rocchio_alpha": settings.search.rocchio_alpha,
            "rocchio_beta": settings.search.rocchio_beta,
        }
    if ranker_key is RankerKey.SEMANTIC:
        common |= {
            "model": settings.semantic.model_name,
            "dimensions": settings.semantic.dimensions,
            "max_chars": settings.semantic.max_chars,
        }
    return common


def reportable_metric_keys() -> list[str]:
    """Scalar quality metrics, excluding diagnostics — what the tables show."""
    return [
        key
        for key, spec in METRICS.items()
        if spec.kind is MetricKind.SCALAR and spec.edition is not MetricEdition.DIAGNOSTIC
    ]
