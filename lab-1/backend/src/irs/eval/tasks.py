"""Background evaluation tasks: LLM judging, run batches, LSA builds.

Same shape as :mod:`irs.crawler.tasks`: the API commits a row, enqueues the id, returns
202; the worker does the work and publishes progress to Redis for the SSE stream.

One hazard is specific to judging. The broker reclaims a stream entry that has stayed
unacknowledged for ``idle_timeout`` (ten minutes, see :mod:`irs.queue`), and a judging
pass over a thousand pairs on a CPU model runs for hours — so the same task *will* be
delivered a second time while the first is still working. The task therefore takes a
Redis lock keyed by job and refreshes it as it goes; a redelivery finds the lock held and
returns at once. Judgment inserts are idempotent besides, so even a lost lock cannot
double-count.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from irs.db.session import dispose_engine
from irs.logging import bind_request_id, get_logger
from irs.queue import broker
from irs.telemetry.redis_client import get_redis

log = get_logger("irs.eval.tasks")

LOCK_TTL_SECONDS = 180


class JobLock:
    """``SET NX EX`` lock with a background heartbeat."""

    def __init__(self, key: str, ttl: int = LOCK_TTL_SECONDS) -> None:
        self.key = key
        self.ttl = ttl
        self._heartbeat: asyncio.Task[None] | None = None

    async def acquire(self) -> bool:
        acquired = await get_redis().set(self.key, "1", nx=True, ex=self.ttl)
        if acquired:
            self._heartbeat = asyncio.create_task(self._refresh())
        return bool(acquired)

    async def _refresh(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.ttl / 3)
                await get_redis().expire(self.key, self.ttl)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("job_lock_refresh_failed", key=self.key, error=str(exc))

    async def release(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._heartbeat
        try:
            await get_redis().delete(self.key)
        except Exception as exc:
            log.debug("job_lock_release_failed", key=self.key, error=str(exc))


async def _locked(key: str, work: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    lock = JobLock(key)
    if not await lock.acquire():
        log.info("task_duplicate_delivery_ignored", lock=key)
        return {"status": "already_running", "lock": key}
    try:
        return await work()
    finally:
        await lock.release()
        await dispose_engine()


@broker.task(task_name="eval.judge_pool")
async def judge_pool(job_id: int) -> dict[str, Any]:
    """Let the LLM assessor work through one judging job."""
    from irs.eval.judging import run_judging_job

    async def work() -> dict[str, Any]:
        with bind_request_id() as request_id:
            log.info("judging_task_received", job_id=job_id, request_id=request_id)
            outcome = await run_judging_job(job_id)
        return {
            "job_id": outcome.job_id,
            "judged": outcome.judged,
            "failed": outcome.failed,
            "duration_ms": round(outcome.duration_ms, 1),
        }

    return await _locked(f"irs.eval.judging.lock:{job_id}", work)


@broker.task(task_name="eval.execute_runs")
async def execute_runs(run_ids: list[int]) -> dict[str, Any]:
    """Execute a batch of pending evaluation runs, then compare them."""
    from irs.eval.service import execute_pending_runs

    async def work() -> dict[str, Any]:
        with bind_request_id() as request_id:
            log.info("runs_task_received", run_ids=run_ids, request_id=request_id)
            return await execute_pending_runs(run_ids)

    key = "irs.eval.runs.lock:" + ",".join(str(r) for r in sorted(run_ids))
    return await _locked(key, work)


@broker.task(task_name="eval.build_lsa")
async def build_lsa(components: int | None = None) -> dict[str, Any]:
    """Rebuild the latent-semantic projection for the Relevance Lab."""
    from irs.db.session import get_sessionmaker
    from irs.index.matrix import build_lsa as build

    async def work() -> dict[str, Any]:
        async with get_sessionmaker()() as session:
            stats = await build(session, components)
            await session.commit()
        return stats.as_dict()

    return await _locked("irs.eval.lsa.lock", work)
