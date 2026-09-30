"""Materialising binary relevance tables from graded judgments.

ROMIP collects assessments on a five-point scale from two or more assessors, then derives
*two* official binary tables from them at a relevance threshold:

* **слабые требования (`or`)** — relevant if *at least one* assessor's grade meets the
  threshold; "cannot be judged" only when *every* assessor says so.
* **сильные требования (`and`)** — non-relevant if *at least one* assessor's grade falls
  below the threshold.

The official 2004 threshold is `RELEVANT_MINUS` (grade ≥ 1), which is deliberately
generous. Both tables are produced because ROMIP reports that the ranking of systems was
not always stable between them («при использовании слабых требований совпадают только
первые два») — so a comparison that holds under only one aggregation is not a result, and
the report shows both.

Each row also carries a graded ``gain`` (the mean grade), because nDCG, ERR and pFound
need it, and a ``has_disagreement`` flag, which is what makes inter-assessor agreement
reportable.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import GRADE_VALUES, Judgment, Qrel, QrelSet, Query
from irs.db.models.enums import QrelAggregation, RelevanceGrade
from irs.eval.metrics import QueryJudgments
from irs.logging import get_logger

log = get_logger("irs.eval.qrels")


@dataclass(slots=True)
class QrelSetStats:
    query_count: int
    relevant_count: int
    judged_count: int
    disagreement_count: int
    #: Topics dropped because no document was judged relevant — ROMIP excludes these
    #: from every metric, so the figure has to be reported.
    excluded_queries: int


async def materialize(
    session: AsyncSession,
    collection_id: int,
    aggregation: QrelAggregation = QrelAggregation.OR,
    threshold: int = 1,
) -> tuple[QrelSet, QrelSetStats]:
    """Build (or rebuild) one binary relevance table for a collection."""
    qrel_set = (
        await session.execute(
            select(QrelSet).where(
                QrelSet.collection_id == collection_id,
                QrelSet.aggregation == aggregation,
                QrelSet.threshold == threshold,
            )
        )
    ).scalar_one_or_none()

    if qrel_set is None:
        qrel_set = QrelSet(
            collection_id=collection_id,
            name=f"{aggregation}_threshold-{threshold}",
            aggregation=aggregation,
            threshold=threshold,
        )
        session.add(qrel_set)
        await session.flush()
    else:
        # Rebuilt from scratch: judgments may have been added or corrected since.
        await session.execute(delete(Qrel).where(Qrel.qrel_set_id == qrel_set.id))

    rows = (
        await session.execute(
            select(
                Judgment.query_id,
                Judgment.document_id,
                Judgment.grade,
            )
            .join(Query, Query.id == Judgment.query_id)
            .where(Query.collection_id == collection_id)
        )
    ).all()

    # (query, document) → the grades every assessor gave it.
    grouped: dict[tuple[int, int], list[RelevanceGrade]] = {}
    for query_id, document_id, grade in rows:
        grouped.setdefault((query_id, document_id), []).append(RelevanceGrade(grade))

    relevant_by_query: dict[int, int] = {}
    judged_count = 0
    relevant_count = 0
    disagreement_count = 0

    for (query_id, document_id), grades in grouped.items():
        values = [GRADE_VALUES[grade] for grade in grades]
        all_unjudgeable = all(grade is RelevanceGrade.CANTBEJUDGED for grade in grades)

        if aggregation is QrelAggregation.OR:
            # Relevant if any assessor reached the threshold.
            is_relevant = any(value >= threshold for value in values)
        else:
            # Non-relevant if any assessor fell short of it.
            is_relevant = all(value >= threshold for value in values)

        if all_unjudgeable:
            is_relevant = False

        disagreement = len(set(values)) > 1
        if disagreement:
            disagreement_count += 1

        session.add(
            Qrel(
                qrel_set_id=qrel_set.id,
                query_id=query_id,
                document_id=document_id,
                is_relevant=is_relevant,
                # Mean grade: with one assessor this is just their grade, and with
                # several it is the graded consensus nDCG and ERR consume.
                gain=sum(values) / len(values),
                is_unjudged=all_unjudgeable,
                assessor_count=len(grades),
                has_disagreement=disagreement,
            )
        )
        judged_count += 1
        if is_relevant:
            relevant_count += 1
            relevant_by_query[query_id] = relevant_by_query.get(query_id, 0) + 1

    total_queries = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Query)
                .where(Query.collection_id == collection_id, Query.is_judged)
            )
        ).scalar_one()
    )

    stats = QrelSetStats(
        query_count=len(relevant_by_query),
        relevant_count=relevant_count,
        judged_count=judged_count,
        disagreement_count=disagreement_count,
        excluded_queries=max(0, total_queries - len(relevant_by_query)),
    )

    qrel_set.query_count = stats.query_count
    qrel_set.relevant_count = stats.relevant_count
    qrel_set.judged_count = stats.judged_count
    await session.flush()

    log.info(
        "qrels_materialized",
        qrel_set_id=qrel_set.id,
        aggregation=str(aggregation),
        threshold=threshold,
        num_q=stats.query_count,
        relevant=stats.relevant_count,
        judged=stats.judged_count,
        excluded_queries=stats.excluded_queries,
        disagreements=stats.disagreement_count,
    )
    return qrel_set, stats


async def load_judgments(session: AsyncSession, qrel_set_id: int) -> dict[int, QueryJudgments]:
    """Load a relevance table into the metric core's in-memory form.

    Only topics with at least one relevant document are returned: ROMIP excludes the rest
    from every metric, and returning them would let a caller compute a mean over a
    different topic set than `num_q` claims.
    """
    rows = (
        await session.execute(
            select(
                Qrel.query_id,
                Qrel.document_id,
                Qrel.is_relevant,
                Qrel.gain,
                Qrel.is_unjudged,
            ).where(Qrel.qrel_set_id == qrel_set_id)
        )
    ).all()

    relevant: dict[int, set[int]] = {}
    non_relevant: dict[int, set[int]] = {}
    gains: dict[int, dict[int, float]] = {}

    for query_id, document_id, is_relevant, gain, is_unjudged in rows:
        gains.setdefault(query_id, {})[document_id] = float(gain)
        if is_relevant:
            relevant.setdefault(query_id, set()).add(document_id)
        elif not is_unjudged:
            # "Cannot be judged" is neither relevant nor judged-non-relevant: bpref must
            # skip it rather than count it against the run.
            non_relevant.setdefault(query_id, set()).add(document_id)

    return {
        query_id: QueryJudgments(
            relevant=frozenset(documents),
            non_relevant=frozenset(non_relevant.get(query_id, set())),
            gains=gains.get(query_id, {}),
        )
        for query_id, documents in relevant.items()
        if documents
    }


async def agreement(session: AsyncSession, collection_id: int) -> dict[str, float | int]:
    """Inter-assessor agreement over pairs judged by more than one human.

    Reported because ROMIP reports it — its own web classification track averaged 29%,
    so a modest figure here is defensible and citable rather than embarrassing. Only
    human assessors count: the synthetic known-item assessor's verdicts follow from the
    construction, and an LLM's are not an independent human opinion. If a collection
    was judged by an LLM alone the figure is therefore *not measured*, and the report
    must say so rather than quote a number.
    """
    from irs.db.models.enums import AssessorKind
    from irs.db.models.evaluation import Assessor

    statement = (
        select(Judgment.query_id, Judgment.document_id, Judgment.grade)
        .join(Query, Query.id == Judgment.query_id)
        .join(Assessor, Assessor.id == Judgment.assessor_id)
        .where(Query.collection_id == collection_id, Assessor.kind == AssessorKind.HUMAN)
    )

    grouped: dict[tuple[int, int], list[int]] = {}
    for query_id, document_id, grade in (await session.execute(statement)).all():
        grouped.setdefault((query_id, document_id), []).append(GRADE_VALUES[RelevanceGrade(grade)])

    multi = {pair: values for pair, values in grouped.items() if len(values) > 1}
    if not multi:
        return {"double_judged_pairs": 0, "exact_agreement": 0.0, "binary_agreement": 0.0}

    exact = sum(1 for values in multi.values() if len(set(values)) == 1)
    binary = sum(1 for values in multi.values() if len({value >= 1 for value in values}) == 1)

    return {
        "double_judged_pairs": len(multi),
        "exact_agreement": exact / len(multi),
        "binary_agreement": binary / len(multi),
    }
