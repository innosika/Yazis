"""Evaluation orchestration.

Ties the pieces together: build or load a test collection, materialise both official
relevance tables, run every available ranker, score each run, and compare them pairwise
with significance testing.

Everything it produces is persisted, so the report and the interface read stored results
rather than recomputing — which is what makes a reported number traceable to the run,
the index version and the parameters that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import EvalRun, Qrel, RunQueryMetric, SignificanceResult, TestCollection
from irs.db.models.enums import EvalRunStatus, QrelAggregation, RankerKey
from irs.db.session import get_sessionmaker
from irs.eval import collection as collection_module
from irs.eval import qrels as qrels_module
from irs.eval import significance as significance_module
from irs.eval.caveats import MetricCaveat, degenerate_keys, metric_caveats
from irs.eval.runner import RunOutcome, execute_existing_run, execute_run
from irs.logging import Stopwatch, get_logger
from irs.selection.registry import get_rankers

log = get_logger("irs.eval.service")

#: The metric significance is tested on. Average precision is the appendix's own choice
#: of primary measure, citing Buckley & Voorhees for its stability.
PRIMARY_METRIC = "ap"


@dataclass(slots=True)
class EvaluationReport:
    collection_id: int
    collection_name: str
    qrel_set_id: int
    aggregation: str
    threshold: int
    num_queries: int
    runs: dict[str, RunOutcome] = field(default_factory=dict)
    comparisons: list[significance_module.ComparisonResult] = field(default_factory=list)
    agreement: dict[str, float | int] = field(default_factory=dict)
    #: Presentation caveats: which metrics are degenerate on this collection and why.
    caveats: list[MetricCaveat] = field(default_factory=list)
    top_k: int = 0
    duration_ms: float = 0.0


async def evaluate_collection(
    session: AsyncSession,
    collection_id: int,
    aggregation: QrelAggregation = QrelAggregation.OR,
    threshold: int | None = None,
    rankers: list[RankerKey] | None = None,
) -> EvaluationReport:
    """Run and score every ranker over one collection and one relevance table."""
    watch = Stopwatch()
    threshold = settings.evaluation.binary_relevance_threshold if threshold is None else threshold

    collection = await session.get(TestCollection, collection_id)
    if collection is None:
        raise LookupError(f"test collection {collection_id} does not exist")

    qrel_set, stats = await qrels_module.materialize(
        session, collection_id, aggregation=aggregation, threshold=threshold
    )
    judgments = await qrels_module.load_judgments(session, qrel_set.id)

    if not judgments:
        raise ValueError(
            f"collection {collection.name!r} has no topic with a relevant document; "
            "nothing can be evaluated"
        )

    available = list(rankers) if rankers else list(get_rankers())
    log.info(
        "evaluation_started",
        collection=collection.name,
        aggregation=str(aggregation),
        threshold=threshold,
        num_q=len(judgments),
        rankers=[str(key) for key in available],
    )

    outcomes: dict[str, RunOutcome] = {}
    for ranker_key in available:
        outcome = await execute_run(
            session,
            collection_id=collection_id,
            qrel_set_id=qrel_set.id,
            ranker_key=ranker_key,
            judgments=judgments,
        )
        outcomes[str(ranker_key)] = outcome
        await session.commit()

    comparisons = await _compare_runs(session, outcomes)
    await session.commit()

    top_k = settings.evaluation.run_depth
    max_assessors = (
        await session.execute(
            select(func.max(Qrel.assessor_count)).where(Qrel.qrel_set_id == qrel_set.id)
        )
    ).scalar_one()
    caveats = metric_caveats(judgments, top_k=top_k, single_assessor=(max_assessors or 1) <= 1)

    report = EvaluationReport(
        collection_id=collection_id,
        collection_name=collection.name,
        qrel_set_id=qrel_set.id,
        aggregation=str(aggregation),
        threshold=threshold,
        num_queries=len(judgments),
        runs=outcomes,
        comparisons=comparisons,
        agreement=await qrels_module.agreement(session, collection_id),
        caveats=caveats,
        top_k=top_k,
        duration_ms=watch.total_ms,
    )

    log.info(
        "evaluation_finished",
        collection=collection.name,
        num_q=len(judgments),
        excluded_queries=stats.excluded_queries,
        runs=len(outcomes),
        comparisons=len(comparisons),
        duration_ms=round(watch.total_ms, 1),
    )
    return report


async def _compare_runs(
    session: AsyncSession, outcomes: dict[str, RunOutcome]
) -> list[significance_module.ComparisonResult]:
    """Pairwise significance tests between every pair of runs.

    The vector model is the baseline — it is the strategy the assignment mandates — so
    it appears first in each pair and a positive mean difference means the vector model
    won. Holm–Bonferroni then corrects across the whole family of comparisons.
    """
    keys = sorted(outcomes, key=lambda key: (key != str(RankerKey.VECTOR), key))
    results: list[significance_module.ComparisonResult] = []
    pairs: list[tuple[str, str]] = []

    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            comparison = significance_module.compare(
                outcomes[left].per_query,
                outcomes[right].per_query,
                PRIMARY_METRIC,
                test="permutation",
                label_a=left,
                label_b=right,
            )
            results.append(comparison)
            pairs.append((left, right))

    significance_module.holm_bonferroni(results)

    for (left, right), comparison in zip(pairs, results, strict=True):
        session.add(
            SignificanceResult(
                run_a_id=outcomes[left].run_id,
                run_b_id=outcomes[right].run_id,
                metric_key=comparison.metric_key,
                test=comparison.test,
                statistic=comparison.statistic,
                p_value=comparison.p_value,
                p_value_corrected=comparison.p_value_corrected,
                correction=comparison.correction,
                mean_difference=comparison.mean_difference,
                effect_size=comparison.effect_size,
                ci_low=comparison.ci_low,
                ci_high=comparison.ci_high,
                sample_size=comparison.sample_size,
            )
        )
        log.info(
            "comparison",
            a=left,
            b=right,
            metric=comparison.metric_key,
            mean_a=round(comparison.mean_a, 4),
            mean_b=round(comparison.mean_b, 4),
            difference=round(comparison.mean_difference, 4),
            p=round(comparison.p_value, 4),
            p_corrected=round(comparison.p_value_corrected or 1.0, 4),
            effect_size=(
                round(comparison.effect_size, 3) if comparison.effect_size is not None else None
            ),
            n=comparison.sample_size,
            ties=comparison.ties,
        )

    await session.flush()
    return results


async def run_full_evaluation(collection: str | None = None) -> int:
    """CLI entry point: build the automatic collection if needed, then evaluate.

    Both official relevance tables are produced — `or` (слабые требования) and `and`
    (сильные требования) — because ROMIP reports that the ranking of systems is not
    always stable between them, so a result that holds under only one is not a result.
    """
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        if not await collection_module.has_postings(session):
            print(
                "the index is empty — run `make seed && make index` first",
                flush=True,
            )
            return 2

        if collection:
            target = (
                await session.execute(
                    select(TestCollection).where(TestCollection.name == collection)
                )
            ).scalar_one_or_none()
            if target is None:
                print(f"no test collection named {collection!r}", flush=True)
                return 2
            collection_id = target.id
        else:
            built, topics = await collection_module.build_known_item_collection(session, size=30)
            await session.commit()
            collection_id = built.id
            print(
                f"\nTest collection: {built.name}\n  topics: {len(topics)}\n",
                flush=True,
            )

        reports: list[EvaluationReport] = []
        for aggregation in (QrelAggregation.OR, QrelAggregation.AND):
            report = await evaluate_collection(session, collection_id, aggregation=aggregation)
            await session.commit()
            reports.append(report)
            _print_report(report)

        _print_stability(reports)

    return 0


def _print_report(report: EvaluationReport) -> None:
    """Aggregate table for one relevance table, then significance and agreement.

    Metrics that are degenerate on this collection print as ``n/a`` with a numbered
    footnote instead of a value: a ``1.0000`` that means «the one relevant document was
    somewhere in the top 100» must not sit in a column that reads as a perfect score.
    """
    _print_aggregate_table(report)
    _print_caveats(report)

    print()
    for name, outcome in sorted(report.runs.items()):
        print(
            f"  {name:<12} unjudged retrieved: {outcome.unjudged_retrieved:<6} "
            f"({outcome.duration_ms / 1000:.1f}s)"
        )

    _print_comparisons(report)
    _print_agreement(report)
    print()


def _print_aggregate_table(report: EvaluationReport) -> None:
    from irs.eval.registry import METRICS, PRIMARY_ORDER

    suppressed = degenerate_keys(report.caveats)
    footnote_index = _footnote_index(report)
    keys = [key for key in PRIMARY_ORDER if key in METRICS]

    def header_label(key: str) -> str:
        label = METRICS[key].label.split(" (")[0]
        if key in footnote_index:
            return f"{label[:8]}{_superscript(footnote_index[key])}"
        return label[:9]

    header = f"{'ranker':<12}" + "".join(f"{header_label(k):>10}" for k in keys)

    print(
        f"\n{report.aggregation}_threshold-{report.threshold}   "
        f"num_q={report.num_queries}   top_k={report.top_k}"
    )
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    for name, outcome in sorted(
        report.runs.items(), key=lambda item: -item[1].aggregate.get("ap", 0.0)
    ):
        cells = [
            _format_cell(key, outcome.aggregate.get(key), suppressed, footnote_index)
            for key in keys
        ]
        print(f"{name:<12}" + "".join(f"{cell:>10}" for cell in cells))


def _format_cell(
    key: str, value: float | None, suppressed: frozenset[str], footnote_index: dict[str, int]
) -> str:
    if key in suppressed:
        return f"n/a{_superscript(footnote_index[key])}"
    if value is None:
        return "—"
    return f"{value:.4f}"


def _footnote_index(report: EvaluationReport) -> dict[str, int]:
    footnotes = [c for c in report.caveats if c.kind == "degenerate"]
    return {c.metric_key: i + 1 for i, c in enumerate(footnotes)}


def _print_caveats(report: EvaluationReport) -> None:
    footnotes = [c for c in report.caveats if c.kind == "degenerate"]
    if footnotes:
        print()
        for index, caveat in enumerate(footnotes, start=1):
            print(f"  {_superscript(index)} {caveat.note}")
    for caveat in report.caveats:
        if caveat.kind == "annotate":
            print(f"  · {caveat.note}")


def _print_comparisons(report: EvaluationReport) -> None:
    if not report.comparisons:
        return
    print(f"\n  Significance on {PRIMARY_METRIC} (permutation, Holm–Bonferroni):")
    for comparison in report.comparisons:
        corrected = comparison.p_value_corrected or 1.0
        marker = "**" if corrected < 0.01 else "*" if corrected < 0.05 else "  "
        effect = "—" if comparison.effect_size is None else f"{comparison.effect_size:+.2f}"
        pair = f"{comparison.label_a} vs {comparison.label_b}"
        print(
            f"    {marker} {pair:<26} Δ={comparison.mean_difference:+.4f}  "
            f"p={comparison.p_value:.4f}  p_corr={corrected:.4f}  "
            f"d_z={effect}  n={comparison.sample_size}  ties={comparison.ties}"
        )


def _print_agreement(report: EvaluationReport) -> None:
    if report.agreement.get("double_judged_pairs"):
        print(
            f"\n  Assessor agreement: exact "
            f"{report.agreement['exact_agreement']:.1%}, binary "
            f"{report.agreement['binary_agreement']:.1%} over "
            f"{report.agreement['double_judged_pairs']} double-judged pairs"
        )
    else:
        print("\n  Assessor agreement: not measured (no pair judged by two humans)")


_SUPERSCRIPTS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _superscript(number: int) -> str:
    return str(number).translate(_SUPERSCRIPTS)


def _print_stability(reports: list[EvaluationReport]) -> None:
    """Whether the ranker ordering survives changing the aggregation.

    ROMIP found it sometimes did not, so this check is exactly the analysis the source
    document models.
    """
    if len(reports) < 2:
        return

    orderings = {
        report.aggregation: [
            name
            for name, _ in sorted(
                report.runs.items(), key=lambda item: -item[1].aggregate.get("ap", 0.0)
            )
        ]
        for report in reports
    }

    print("Ranker ordering by MAP under each relevance table:")
    for aggregation, order in orderings.items():
        print(f"  {aggregation:<5} {' > '.join(order)}")

    distinct = {tuple(order) for order in orderings.values()}
    if len(distinct) == 1:
        print("  → stable across both official aggregations\n")
    else:
        print(
            "  → NOT stable: the ordering depends on the aggregation, so any claim of "
            "superiority must name which table it holds under\n"
        )


# --------------------------------------------------------------------------------
# background execution (API path) and comparisons over stored runs
# --------------------------------------------------------------------------------


async def execute_pending_runs(run_ids: list[int]) -> dict[str, object]:
    """Execute registered runs one by one (worker path), then compare the batch.

    Owns its sessions like the crawler task does. Progress is published per topic so
    the interface can show «bm25: 17/25 topics» while the batch is running.
    """
    import json

    from irs.eval.judging import PROGRESS_CHANNEL
    from irs.telemetry.redis_client import get_redis

    async def publish(payload: dict[str, object]) -> None:
        try:
            await get_redis().publish(PROGRESS_CHANNEL, json.dumps(payload, default=str))
        except Exception as exc:
            log.debug("run_progress_publish_failed", error=str(exc))

    sessionmaker = get_sessionmaker()
    outcomes: dict[str, RunOutcome] = {}
    failed: list[int] = []

    for run_id in run_ids:
        async with sessionmaker() as session:
            run = await session.get(EvalRun, run_id)
            if run is None or run.status not in (EvalRunStatus.PENDING, EvalRunStatus.FAILED):
                continue
            judgments = await qrels_module.load_judgments(session, run.qrel_set_id)

            async def on_progress(done: int, total: int, *, current: EvalRun = run) -> None:
                await publish(
                    {
                        "kind": "runs",
                        "event": "topic_scored",
                        "run_id": current.id,
                        "ranker": str(current.ranker),
                        "batch_id": current.batch_id,
                        "done": done,
                        "total": total,
                    }
                )

            try:
                outcome = await execute_existing_run(session, run, judgments, on_progress)
            except Exception:
                await session.commit()
                failed.append(run_id)
                await publish(
                    {
                        "kind": "runs",
                        "event": "run_failed",
                        "run_id": run_id,
                        "batch_id": run.batch_id,
                    }
                )
                continue
            await session.commit()
            outcomes[str(run.ranker)] = outcome
            await publish(
                {
                    "kind": "runs",
                    "event": "run_finished",
                    "run_id": run_id,
                    "ranker": str(run.ranker),
                    "batch_id": run.batch_id,
                    "map": round(outcome.aggregate.get("ap", 0.0), 4),
                    "p_10": round(outcome.aggregate.get("p_10", 0.0), 4),
                }
            )

    comparisons = 0
    if len(outcomes) >= 2:
        async with sessionmaker() as session:
            comparisons = len(await _compare_runs(session, outcomes))
            await session.commit()

    await publish(
        {
            "kind": "runs",
            "event": "batch_finished",
            "run_ids": run_ids,
            "completed": [o.run_id for o in outcomes.values()],
            "failed": failed,
            "comparisons": comparisons,
        }
    )
    return {
        "completed": [o.run_id for o in outcomes.values()],
        "failed": failed,
        "comparisons": comparisons,
    }


async def load_per_query(session: AsyncSession, run_id: int) -> dict[int, dict[str, float]]:
    """A stored run's per-topic metrics, in the shape the significance module expects."""
    rows = (
        await session.execute(
            select(RunQueryMetric.query_id, RunQueryMetric.metric_key, RunQueryMetric.value).where(
                RunQueryMetric.run_id == run_id
            )
        )
    ).all()
    per_query: dict[int, dict[str, float]] = {}
    for query_id, key, value in rows:
        per_query.setdefault(int(query_id), {})[str(key)] = float(value)
    return per_query


async def compare_stored_runs(
    session: AsyncSession,
    run_ids: list[int],
    metric_key: str = PRIMARY_METRIC,
    test: str = "permutation",
) -> list[significance_module.ComparisonResult]:
    """Pairwise significance between stored runs, aligned on their common topics.

    Every pair is compared on the *intersection* of the topics both runs scored. Means
    over different topic sets are not comparable, which is why the result carries the
    sample size and the interface prints it beside every p-value.
    """
    runs: dict[int, EvalRun] = {}
    for run_id in run_ids:
        run = await session.get(EvalRun, run_id)
        if run is None:
            raise LookupError(f"run {run_id} does not exist")
        runs[run_id] = run

    per_query = {run_id: await load_per_query(session, run_id) for run_id in run_ids}
    ordered = sorted(run_ids, key=lambda rid: (str(runs[rid].ranker) != str(RankerKey.VECTOR), rid))

    results: list[significance_module.ComparisonResult] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            results.append(
                significance_module.compare(
                    per_query[left],
                    per_query[right],
                    metric_key,
                    test=test,
                    label_a=f"{runs[left].ranker}#{left}",
                    label_b=f"{runs[right].ranker}#{right}",
                )
            )
    significance_module.holm_bonferroni(results)
    return results
