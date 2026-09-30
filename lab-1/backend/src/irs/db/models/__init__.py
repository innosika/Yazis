"""SQLAlchemy models.

Every model is re-exported here, and ``alembic/env.py`` imports this package so that
``Base.metadata`` is complete before autogenerate compares it against the database.
"""

from __future__ import annotations

from irs.db.base import Base, TimestampMixin
from irs.db.models.corpus import (
    CollectionStat,
    Document,
    LsaModel,
    LsaProjection,
    Posting,
    Term,
)
from irs.db.models.crawl import CrawlJob, CrawlTask, RobotsCache
from irs.db.models.enums import (
    GRADE_VALUES,
    AssessorKind,
    CrawlStatus,
    EvalRunStatus,
    PoolSource,
    QrelAggregation,
    RankerKey,
    RelevanceGrade,
    SignificanceTest,
    SkipReason,
    UrlStatus,
)
from irs.db.models.evaluation import (
    Assessor,
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
    RunQueryMetric,
    RunResult,
    SignificanceResult,
    TestCollection,
)
from irs.db.models.telemetry import FeedbackSession, SearchLog

__all__ = [
    "GRADE_VALUES",
    "Assessor",
    "AssessorKind",
    "Base",
    "CollectionStat",
    "CrawlJob",
    "CrawlStatus",
    "CrawlTask",
    "Document",
    "EvalRun",
    "EvalRunStatus",
    "FeedbackSession",
    "JudgingJob",
    "Judgment",
    "LsaModel",
    "LsaProjection",
    "PoolEntry",
    "PoolSource",
    "Posting",
    "Qrel",
    "QrelAggregation",
    "QrelSet",
    "Query",
    "RankerKey",
    "RelevanceGrade",
    "RobotsCache",
    "RunCurve",
    "RunMetric",
    "RunQueryCurve",
    "RunQueryMetric",
    "RunResult",
    "SearchLog",
    "SignificanceResult",
    "SignificanceTest",
    "SkipReason",
    "Term",
    "TestCollection",
    "TimestampMixin",
    "UrlStatus",
]
