"""Crawl control and live progress."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from irs.api.sse import channel_response
from irs.config import settings
from irs.crawler import urls as urlutil
from irs.crawler.service import PROGRESS_CHANNEL, create_job
from irs.db.models import CrawlJob, CrawlTask
from irs.db.models.enums import CrawlStatus, UrlStatus
from irs.db.session import get_session
from irs.logging import get_logger

log = get_logger("irs.api.crawl")
router = APIRouter(prefix="/crawl", tags=["crawl"])


class CrawlRequest(BaseModel):
    """Configuration for a new crawl."""

    seed_urls: list[str] = Field(min_length=1, max_length=20)
    max_pages: int = Field(default=50, ge=1, le=settings.crawler.max_pages_per_job)
    max_depth: int = Field(default=2, ge=0, le=settings.crawler.max_depth)
    #: Off-domain crawling is opt-in: an unrestricted crawl from a single seed will
    #: happily wander the entire web.
    same_domain_only: bool = True

    @field_validator("seed_urls")
    @classmethod
    def _crawlable(cls, value: list[str]) -> list[str]:
        for url in value:
            if urlutil.canonicalize(url) is None:
                raise ValueError(f"not a crawlable http(s) URL: {url!r}")
        return value


class CrawlJobOut(BaseModel):
    id: int
    status: CrawlStatus
    seed_urls: list[str]
    max_pages: int
    max_depth: int
    same_domain_only: bool
    respect_robots_txt: bool

    pages_fetched: int = 0
    pages_indexed: int = 0
    pages_skipped: int = 0
    pages_failed: int = 0
    urls_discovered: int = 0
    bytes_downloaded: int = 0
    skip_breakdown: dict[str, Any] = {}

    #: Pending frontier size — how much work is left.
    pending_urls: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    task_id: str | None = None


class CrawlTaskOut(BaseModel):
    id: int
    url: str
    depth: int
    status: UrlStatus
    skip_reason: str | None = None
    http_status: int | None = None
    error: str | None = None
    document_id: int | None = None
    extracted_chars: int | None = None
    content_bytes: int | None = None
    stage_timings_ms: dict[str, Any] | None = None


@router.post("/jobs", response_model=CrawlJobOut, status_code=status.HTTP_202_ACCEPTED)
async def start_crawl(
    request: CrawlRequest, session: AsyncSession = Depends(get_session)
) -> CrawlJobOut:
    """Create a crawl job and hand it to the worker.

    Returns immediately with the job. Progress is available from
    ``GET /crawl/jobs/{id}`` or, live, from ``GET /crawl/stream``.
    """
    try:
        job = await create_job(
            session,
            seed_urls=request.seed_urls,
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            same_domain_only=request.same_domain_only,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await session.commit()

    # Enqueue only after the job row is committed, so the worker cannot start before the
    # row it needs is visible.
    from irs.crawler.tasks import run_crawl_job

    try:
        handle = await run_crawl_job.kiq(job.id)
        job.task_id = handle.task_id
        await session.commit()
    except Exception as exc:
        # The queue being unavailable is worth reporting clearly: the job exists but
        # nothing will pick it up.
        log.error("crawl_enqueue_failed", job_id=job.id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"crawl job {job.id} was created but could not be queued: {exc}. "
                "Is the worker container running?"
            ),
        ) from exc

    return await _describe(session, job)


@router.get("/jobs", response_model=list[CrawlJobOut])
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CrawlJobOut]:
    jobs = (
        (await session.execute(select(CrawlJob).order_by(desc(CrawlJob.id)).limit(limit)))
        .scalars()
        .all()
    )
    return [await _describe(session, job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=CrawlJobOut)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> CrawlJobOut:
    job = await session.get(CrawlJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"crawl job {job_id} not found")
    return await _describe(session, job)


@router.get("/jobs/{job_id}/urls", response_model=list[CrawlTaskOut])
async def list_urls(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    url_status: UrlStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[CrawlTaskOut]:
    """The frontier, so the crawl's decisions can be inspected URL by URL.

    This is what makes the crawl auditable: every URL carries why it was skipped, what
    the host answered, and how long each stage took.
    """
    statement = (
        select(CrawlTask)
        .where(CrawlTask.job_id == job_id)
        .order_by(CrawlTask.id)
        .offset(offset)
        .limit(limit)
    )
    if url_status is not None:
        statement = statement.where(CrawlTask.status == url_status)

    tasks = (await session.execute(statement)).scalars().all()
    return [
        CrawlTaskOut(
            id=task.id,
            url=task.url,
            depth=task.depth,
            status=task.status,
            skip_reason=task.skip_reason,
            http_status=task.http_status,
            error=task.error,
            document_id=task.document_id,
            extracted_chars=task.extracted_chars,
            content_bytes=task.content_bytes,
            stage_timings_ms=task.stage_timings_ms,
        )
        for task in tasks
    ]


@router.get("/stream", summary="Live crawl progress (SSE)")
async def stream_progress(request: Request) -> EventSourceResponse:
    """Stream crawl events as they happen.

    The worker publishes to a Redis channel and this forwards it, so progress is visible
    in the interface as pages are fetched rather than only after the job completes.
    """
    return channel_response(request, PROGRESS_CHANNEL)


async def _describe(session: AsyncSession, job: CrawlJob) -> CrawlJobOut:
    pending = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CrawlTask)
                .where(CrawlTask.job_id == job.id, CrawlTask.status == UrlStatus.PENDING)
            )
        ).scalar_one()
    )
    return CrawlJobOut(
        id=job.id,
        status=job.status,
        seed_urls=list(job.seed_urls),
        max_pages=job.max_pages,
        max_depth=job.max_depth,
        same_domain_only=job.same_domain_only,
        respect_robots_txt=job.respect_robots_txt,
        pages_fetched=job.pages_fetched,
        pages_indexed=job.pages_indexed,
        pages_skipped=job.pages_skipped,
        pages_failed=job.pages_failed,
        urls_discovered=job.urls_discovered,
        bytes_downloaded=job.bytes_downloaded,
        skip_breakdown=job.skip_breakdown or {},
        pending_urls=pending,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
        task_id=job.task_id,
    )
