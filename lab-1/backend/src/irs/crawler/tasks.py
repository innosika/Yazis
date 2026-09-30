"""Background crawl tasks.

Crawling runs out-of-process: a crawl of several hundred pages takes minutes, must
survive an API restart, and must not occupy a request worker. The API creates the job
row, enqueues this task and returns immediately; the worker drains the frontier and
publishes progress to Redis, which the interface streams over SSE.
"""

from __future__ import annotations

from typing import Any

from irs.db.session import dispose_engine
from irs.logging import bind_request_id, get_logger
from irs.nlp.pipeline import analyzer
from irs.queue import broker

log = get_logger("irs.crawler.tasks")


@broker.task(task_name="crawler.ping")
async def ping() -> dict[str, str]:
    """Liveness task, used by the smoke check to prove the queue round-trips."""
    log.info("queue_ping")
    return {"status": "ok"}


@broker.task(task_name="crawler.warm")
async def warm_models() -> dict[str, Any]:
    """Load the linguistic model before the first crawl needs it.

    The model takes a second or two to load. Doing it on worker startup rather than
    inside the first page's processing keeps the crawl's own stage timings honest.
    """
    analyzer.warm()
    return {"status": "warm", "pipeline": list(analyzer.nlp.pipe_names)}


@broker.task(task_name="crawler.run_job")
async def run_crawl_job(job_id: int) -> dict[str, Any]:
    """Execute one crawl job."""
    from irs.crawler.service import run_crawl

    with bind_request_id() as request_id:
        log.info("crawl_task_received", job_id=job_id, request_id=request_id)
        try:
            outcome = await run_crawl(job_id)
        finally:
            # The worker process may sit idle for a long time between jobs; releasing
            # the pool avoids holding connections open across that gap.
            await dispose_engine()

    return {
        "job_id": outcome.job_id,
        "fetched": outcome.fetched,
        "indexed": outcome.indexed,
        "skipped": outcome.skipped,
        "failed": outcome.failed,
        "discovered": outcome.discovered,
        "duration_ms": round(outcome.duration_ms, 1),
        "skip_breakdown": outcome.skip_breakdown or {},
    }
