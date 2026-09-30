"""The quality-evaluation module's schema.

Follows ROMIP's own methodology (see ``docs/romip-2004-metrics-reference.md``). The
structural decision that everything else depends on: **raw graded judgments and scored
binary qrels are different tables.**

ROMIP collects assessments on a five-point scale from two or more assessors, then
derives *two* official binary qrel sets from them — `or` (слабые требования) and `and`
(сильные требования) — at a relevance threshold. Storing only the binary outcome would
make it impossible to produce the second set, to compute graded metrics such as nDCG,
or to report inter-assessor agreement. So :class:`Judgment` holds what a human actually
said, and :class:`Qrel` holds a materialised, reproducible view of it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from irs.db.base import Base, TimestampMixin
from irs.db.models.enums import (
    AssessorKind,
    EvalRunStatus,
    PoolSource,
    QrelAggregation,
    RankerKey,
    RelevanceGrade,
)

if TYPE_CHECKING:
    from irs.db.models.corpus import Document


class TestCollection(Base, TimestampMixin):
    """A named set of topics and judgments.

    Versioned rather than mutated so that a metric computed last week remains
    reproducible after the collection grows.
    """

    __tablename__ = "test_collection"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Recorded when the judged subset was frozen — see :attr:`Query.selected_at`.
    frozen_at: Mapped[datetime | None] = mapped_column()

    queries: Mapped[list[Query]] = relationship(
        back_populates="collection", cascade="all, delete-orphan", passive_deletes=True
    )


class Query(Base, TimestampMixin):
    """One topic, in TREC/ROMIP shape.

    ``title`` is what gets executed; ``description`` and ``narrative`` are what the
    assessor reads. ROMIP gave assessors an «расширенное описание» precisely because a
    bare keyword query underdetermines what counts as relevant — recording it is what
    makes a judgment defensible after the fact.
    """

    __tablename__ = "query"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("test_collection.id", ondelete="CASCADE"), nullable=False
    )
    #: Stable external number used when exporting to TREC format.
    ext_id: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    narrative: Mapped[str | None] = mapped_column(Text)
    #: Free-form tag such as `navigational` / `topical` / `vocabulary-mismatch`. The
    #: report breaks the metrics down by this, because a collection with no
    #: vocabulary-mismatch topics cannot show any benefit from the semantic ranker.
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    #: A hand-built synonym/keyword query for the *oracle* pool run: its purpose is to
    #: surface relevant documents that no ranker retrieved for the topic's own wording,
    #: so that pooled recall is not merely recall over what our systems found.
    oracle_query: Mapped[str | None] = mapped_column(Text)

    #: ROMIP's anti-tuning device: many more topics are authored than are judged, and
    #: the judged subset is chosen only *after* every run has been frozen (2004 issued
    #: 24,250 tasks and judged 67). A system cannot be tuned to topics whose identity
    #: was unknown while it was being tuned.
    is_judged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    selected_at: Mapped[datetime | None] = mapped_column()

    collection: Mapped[TestCollection] = relationship(back_populates="queries")
    judgments: Mapped[list[Judgment]] = relationship(
        back_populates="query", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("collection_id", "ext_id", name="uq_query_collection_ext"),)

    def __repr__(self) -> str:
        return f"<Query {self.ext_id} {self.title[:40]!r}>"


class Assessor(Base, TimestampMixin):
    """Whoever produced a judgment.

    Modelled even for a two-person lab, because ROMIP requires at least two independent
    assessments per pair and because inter-assessor agreement cannot be reported without
    knowing who said what. ROMIP's own agreement was 29% on average, so a modest figure
    here is defensible and citable rather than embarrassing.
    """

    __tablename__ = "assessor"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[AssessorKind] = mapped_column(
        String(16), nullable=False, default=AssessorKind.HUMAN
    )
    #: For an LLM assessor: model name and digest, prompt version, temperature, passage
    #: budget — everything needed to state in the report exactly what judged the pool.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PoolEntry(Base, TimestampMixin):
    """A query-document pair selected for judging, with its provenance.

    The provenance is the point. A pool built only from our own rankers' output biases
    recall upward in a way that is invisible in the final numbers, so each entry records
    which runs contributed it and whether it came from the oracle run or the random
    sample instead — the two sources that make the pool's completeness measurable.
    """

    __tablename__ = "pool_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )

    source: Mapped[PoolSource] = mapped_column(
        String(16), nullable=False, default=PoolSource.RUN_UNION
    )
    #: Depth at which this document entered the pool (its best rank across runs).
    pool_depth: Mapped[int | None] = mapped_column(SmallInteger)
    #: Ranker keys that surfaced this document, and at what rank.
    contributed_by: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("query_id", "document_id", name="uq_pool_entry_query_document"),
        Index("ix_pool_entry_query_source", "query_id", "source"),
    )


class Judgment(Base, TimestampMixin):
    """One assessor's graded opinion on one query-document pair.

    The unique constraint on ``(query_id, document_id, assessor_id)`` is what allows
    several assessors to judge the same pair — which the OR/AND aggregation requires.
    """

    __tablename__ = "judgment"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    assessor_id: Mapped[int] = mapped_column(
        ForeignKey("assessor.id", ondelete="CASCADE"), nullable=False
    )

    #: ROMIP's five-point scale. Stored as the enum, not as an integer: mapping a grade
    #: to a number is a *scoring* decision (and differs between metrics), not a fact
    #: about what the assessor said.
    grade: Mapped[RelevanceGrade] = mapped_column(String(16), nullable=False)
    #: Time spent, used to sanity-check judging quality in the report.
    seconds_spent: Mapped[float | None] = mapped_column(Float)
    #: The assessor's stated reason (an LLM's one-sentence justification, or a human's
    #: remark), so any single verdict can be audited afterwards.
    note: Mapped[str | None] = mapped_column(Text)

    query: Mapped[Query] = relationship(back_populates="judgments")
    document: Mapped[Document] = relationship(back_populates="judgments")

    __table_args__ = (
        UniqueConstraint(
            "query_id", "document_id", "assessor_id", name="uq_judgment_pair_assessor"
        ),
        Index("ix_judgment_query_document", "query_id", "document_id"),
    )

    def __repr__(self) -> str:
        return f"<Judgment q={self.query_id} d={self.document_id} {self.grade}>"


class QrelSet(Base, TimestampMixin):
    """A materialised binary relevance table derived from the raw judgments.

    ROMIP publishes two official sets per threshold, and reports that the ranking of
    systems was not always stable between them, so both are produced and the report
    shows the comparison under each.
    """

    __tablename__ = "qrel_set"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("test_collection.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    aggregation: Mapped[QrelAggregation] = mapped_column(String(4), nullable=False)
    #: Numeric grade at or above which a document counts as relevant. ROMIP's official
    #: 2004 threshold is 1 (`релевантный−`), which is deliberately generous.
    threshold: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    #: Number of topics that retain at least one relevant document. Queries with none
    #: are excluded from every metric per ROMIP's rule, so this — not the topic count —
    #: is the `num_q` that must be published beside the results.
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    judged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    qrels: Mapped[list[Qrel]] = relationship(
        back_populates="qrel_set", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "aggregation",
            "threshold",
            name="uq_qrel_set_collection_aggregation_threshold",
        ),
        CheckConstraint("threshold BETWEEN 0 AND 3", name="threshold_in_range"),
    )

    def __repr__(self) -> str:
        return f"<QrelSet {self.aggregation}@{self.threshold} num_q={self.query_count}>"


class Qrel(Base):
    """One materialised binary/graded relevance fact."""

    __tablename__ = "qrel"

    qrel_set_id: Mapped[int] = mapped_column(
        ForeignKey("qrel_set.id", ondelete="CASCADE"), primary_key=True
    )
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), primary_key=True
    )

    is_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Mean numeric grade across assessors — the gain used by nDCG, ERR and PFound.
    gain: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: True when every assessor answered `CANTBEJUDGED`. Distinct from non-relevant:
    #: bpref skips these rather than counting them against the run.
    is_unjudged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: How many assessors contributed, and whether they disagreed.
    assessor_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    has_disagreement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    qrel_set: Mapped[QrelSet] = relationship(back_populates="qrels")
    document: Mapped[Document] = relationship(back_populates="qrels")

    __table_args__ = (
        # `R` per query is read constantly; a partial index makes it a cheap count.
        Index(
            "ix_qrel_relevant",
            "qrel_set_id",
            "query_id",
            postgresql_where=("is_relevant"),
        ),
    )


class EvalRun(Base, TimestampMixin):
    """One ranker scored over one qrel set.

    ``params_snapshot`` and ``index_version`` are recorded because a metric without the
    configuration that produced it is not reproducible — six weeks later nobody
    remembers which BM25 `b` gave which MAP.
    """

    __tablename__ = "eval_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("test_collection.id", ondelete="CASCADE"), nullable=False
    )
    qrel_set_id: Mapped[int] = mapped_column(
        ForeignKey("qrel_set.id", ondelete="CASCADE"), nullable=False
    )

    ranker: Mapped[RankerKey] = mapped_column(String(16), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    #: Results retrieved per topic. Reported next to the set-based `precision` and
    #: `recall`, whose values move with it.
    top_k: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)

    status: Mapped[EvalRunStatus] = mapped_column(
        String(16), nullable=False, default=EvalRunStatus.PENDING
    )
    params_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    #: Runs started together by one request share a batch id (the queue task id), so
    #: the interface can group "the rankers I just launched" without guessing by time.
    batch_id: Mapped[str | None] = mapped_column(String(64), index=True)

    #: Topics actually scored, after ROMIP's zero-relevant exclusion.
    scored_query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Retrieved documents carrying no judgment. High values mean the pool does not
    #: cover this ranker, which is exactly when bpref must be quoted alongside.
    unjudged_retrieved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    duration_ms: Mapped[float | None] = mapped_column(Float)

    results: Mapped[list[RunResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    query_metrics: Mapped[list[RunQueryMetric]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    metrics: Mapped[list[RunMetric]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    curves: Mapped[list[RunCurve]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<EvalRun {self.id} {self.ranker} {self.status}>"


class RunResult(Base):
    """One retrieved document at one rank — the «прогон» itself.

    Persisted rather than recomputed, so that a stored metric cannot silently drift when
    the indexer or a ranker is changed afterwards.
    """

    __tablename__ = "run_result"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True
    )
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), primary_key=True
    )
    #: 1-based, as in TREC run format.
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="results")

    __table_args__ = (Index("ix_run_result_run_query", "run_id", "query_id"),)


class RunQueryMetric(Base):
    """A scalar metric for one topic of one run.

    The workhorse table: it drives the per-query diagnostic view, the per-query charts,
    and the paired significance tests, which need per-topic vectors rather than
    aggregates.
    """

    __tablename__ = "run_query_metric"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True
    )
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), primary_key=True
    )
    metric_key: Mapped[str] = mapped_column(String(32), primary_key=True)

    value: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="query_metrics")

    __table_args__ = (Index("ix_run_query_metric_key", "run_id", "metric_key"),)


class RunMetric(Base):
    """An aggregated metric for one run.

    ``query_count`` is stored per row, not per run, because ROMIP's zero-relevant
    exclusion can drop a different set of topics for different metrics, and comparing
    two averages taken over different topic sets is the classic invalid comparison.
    """

    __tablename__ = "run_metric"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True
    )
    metric_key: Mapped[str] = mapped_column(String(32), primary_key=True)

    value: Mapped[float] = mapped_column(Float, nullable=False)
    #: `num_q` — always published beside the value.
    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: "macro" (per topic, then mean) for the search track. Note the lab's 2004 PDF
    #: labels this procedure "micro"; it has the two definitions swapped, and ROMIP's
    #: own 2010 edition corrects the label while keeping the procedure identical.
    averaging: Mapped[str] = mapped_column(String(8), nullable=False, default="macro")
    #: Bootstrap percentile confidence interval, feeding the chart error bars.
    ci_low: Mapped[float | None] = mapped_column(Float)
    ci_high: Mapped[float | None] = mapped_column(Float)

    run: Mapped[EvalRun] = relationship(back_populates="metrics")


class RunCurve(Base):
    """An aggregated curve — the 11-point interpolated PR graph and its variants."""

    __tablename__ = "run_curve"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True
    )
    curve_key: Mapped[str] = mapped_column(String(32), primary_key=True)

    #: ``[[x, y], …]``.
    points: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False)
    #: Topics contributing at each x. Needed by the non-zeroing 11-point reconstruction,
    #: where the denominator varies by recall level.
    support: Mapped[list[int] | None] = mapped_column(JSONB)

    run: Mapped[EvalRun] = relationship(back_populates="curves")


class RunQueryCurve(Base):
    """A per-topic curve, for drilling into a single query's PR behaviour."""

    __tablename__ = "run_query_curve"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), primary_key=True
    )
    query_id: Mapped[int] = mapped_column(
        ForeignKey("query.id", ondelete="CASCADE"), primary_key=True
    )
    curve_key: Mapped[str] = mapped_column(String(32), primary_key=True)

    points: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False)


class SignificanceResult(Base, TimestampMixin):
    """A paired statistical comparison of two runs on one metric.

    Both raw and corrected p-values are stored: five rankers make ten pairs, so the
    family-wise error rate has to be controlled, but the uncorrected value is what a
    reader comparing against published numbers will expect to see.
    """

    __tablename__ = "significance_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_a_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False
    )
    run_b_id: Mapped[int] = mapped_column(
        ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(32), nullable=False)
    test: Mapped[str] = mapped_column(String(16), nullable=False)

    statistic: Mapped[float | None] = mapped_column(Float)
    p_value: Mapped[float] = mapped_column(Float, nullable=False)
    p_value_corrected: Mapped[float | None] = mapped_column(Float)
    correction: Mapped[str | None] = mapped_column(String(16))

    mean_difference: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Cohen's d_z — reported because a p-value alone says nothing about magnitude.
    effect_size: Mapped[float | None] = mapped_column(Float)
    ci_low: Mapped[float | None] = mapped_column(Float)
    ci_high: Mapped[float | None] = mapped_column(Float)
    #: Topics in the *intersection* of the two runs. Never compare across different sets.
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("run_a_id", "run_b_id", "metric_key", "test", name="uq_significance_pair"),
        CheckConstraint("run_a_id <> run_b_id", name="significance_distinct_runs"),
    )


class JudgingJob(Base, TimestampMixin):
    """One background pass of an assessor over a collection's unjudged pool pairs.

    Mirrors :class:`~irs.db.models.crawl.CrawlJob`: the row is the source of truth for
    progress, the queue only carries the id. A pass that stops halfway is resumed by
    starting another job — pairs already judged by the same assessor are skipped.
    """

    __tablename__ = "judging_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("test_collection.id", ondelete="CASCADE"), nullable=False
    )
    assessor_id: Mapped[int] = mapped_column(
        ForeignKey("assessor.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[EvalRunStatus] = mapped_column(
        String(16), nullable=False, default=EvalRunStatus.PENDING, index=True
    )
    task_id: Mapped[str | None] = mapped_column(String(64))

    total_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    judged_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    def __repr__(self) -> str:
        return f"<JudgingJob {self.id} {self.status} {self.judged_pairs}/{self.total_pairs}>"
