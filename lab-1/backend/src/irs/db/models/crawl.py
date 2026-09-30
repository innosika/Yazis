"""Crawl jobs and the URL frontier.

Variant 34 scopes the system to «Сеть Интернет», so the collection is acquired by
crawling rather than read off disk. The frontier is a table rather than an in-memory
queue so a crawl survives a worker restart and so the report can show exactly which
URLs were rejected and why.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
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
from irs.db.models.enums import CrawlStatus, SkipReason, UrlStatus


class CrawlJob(Base, TimestampMixin):
    """One crawl invocation and its configuration."""

    __tablename__ = "crawl_job"

    id: Mapped[int] = mapped_column(primary_key=True)

    seed_urls: Mapped[list[str]] = mapped_column(ARRAY(String(2_048)), nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    max_depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Restrict the crawl to the seeds' own hosts. On by default: an unrestricted crawl
    #: from a Wikipedia seed will happily wander the entire web.
    same_domain_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    respect_robots_txt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    delay_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    status: Mapped[CrawlStatus] = mapped_column(
        String(16), nullable=False, default=CrawlStatus.PENDING, index=True
    )
    #: TaskIQ task id, so the API can read the worker's progress for this job.
    task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    #: Outcome counters, kept denormalised so the crawl monitor is a single cheap read.
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Breakdown by :class:`SkipReason`, for the report's crawl-yield table.
    skip_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    tasks: Mapped[list[CrawlTask]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("max_pages > 0", name="max_pages_positive"),
        CheckConstraint("max_depth >= 0", name="max_depth_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<CrawlJob {self.id} {self.status} indexed={self.pages_indexed}>"


class CrawlTask(Base):
    """One URL in the frontier.

    Rows are claimed with ``SELECT … FOR UPDATE SKIP LOCKED`` so several concurrent
    fetchers can drain the frontier without handing the same URL to two of them.
    """

    __tablename__ = "crawl_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_job.id", ondelete="CASCADE"), nullable=False
    )

    url: Mapped[str] = mapped_column(String(2_048), nullable=False)
    #: Normalised form (lowercased host, sorted query, no fragment or tracking params).
    #: Deduplication is done on this, not on the raw URL.
    url_canonical: Mapped[str] = mapped_column(String(2_048), nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    #: Lower sorts first. Seeds get 0; shallower discoveries outrank deeper ones.
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)

    status: Mapped[UrlStatus] = mapped_column(String(16), nullable=False, default=UrlStatus.PENDING)
    skip_reason: Mapped[SkipReason | None] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    discovered_from: Mapped[int | None] = mapped_column(
        ForeignKey("crawl_task.id", ondelete="SET NULL")
    )
    document_id: Mapped[int | None] = mapped_column(ForeignKey("document.id", ondelete="SET NULL"))

    #: Per-stage timings (fetch / extract / lemmatise / index) in milliseconds. The
    #: report's performance section aggregates these rather than quoting one run.
    stage_timings_ms: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    content_bytes: Mapped[int | None] = mapped_column(Integer)
    extracted_chars: Mapped[int | None] = mapped_column(Integer)

    claimed_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    job: Mapped[CrawlJob] = relationship(back_populates="tasks")

    __table_args__ = (
        # One visit per URL per job.
        UniqueConstraint("job_id", "url_canonical", name="uq_crawl_task_job_url"),
        # The frontier claim query: pending rows of one job, best priority first.
        Index(
            "ix_crawl_task_claim",
            "job_id",
            "priority",
            "depth",
            "id",
            postgresql_where=("status = 'pending'"),
        ),
        Index("ix_crawl_task_job_status", "job_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<CrawlTask {self.id} d={self.depth} {self.status} {self.url[:50]!r}>"


class RobotsCache(Base, TimestampMixin):
    """Cached robots.txt per host.

    Refetching robots.txt for every URL would be both slow and impolite, so each host's
    directives are parsed once and reused for the whole crawl.
    """

    __tablename__ = "robots_cache"

    host: Mapped[str] = mapped_column(String(255), primary_key=True)
    body: Mapped[str | None] = mapped_column(Text)
    #: True when robots.txt was fetched successfully. On a fetch failure we record the
    #: attempt and fall back to allowing the crawl, which is the conventional reading
    #: of an unreachable robots.txt.
    fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    #: Crawl-delay directive, when the host declares one. Overrides our own default
    #: whenever it is larger.
    crawl_delay: Mapped[float | None] = mapped_column(Float)
    sitemaps: Mapped[list[str] | None] = mapped_column(ARRAY(String(2_048)))
    expires_at: Mapped[datetime | None] = mapped_column(index=True)

    def __repr__(self) -> str:
        return f"<RobotsCache {self.host} fetched={self.fetched}>"
