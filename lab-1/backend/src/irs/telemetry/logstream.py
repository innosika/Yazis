"""Publishes log records to Redis and re-serves them as an SSE stream.

The API and the crawl worker are separate processes, so a log console that only showed
one of them would be misleading. Redis pub/sub is the fan-in point: every process
publishes to a single channel, and the API's SSE endpoint subscribes and forwards to the
browser. A client that connects mid-crawl is first sent the local ring buffer, so the
console is never blank.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

from irs.config import settings
from irs.logging import get_logger, log_tap
from irs.telemetry.redis_client import get_redis

log = get_logger("irs.telemetry.logstream")


class LogStreamPublisher:
    """Drains the in-process log tap onto the Redis channel."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not settings.log_stream_enabled or self._task is not None:
            return
        log_tap.bind_loop(asyncio.get_running_loop())
        self._task = asyncio.create_task(self._run(), name="log-stream-publisher")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        redis = get_redis()
        channel = settings.log_stream_channel
        while True:
            record = await log_tap.drain()
            try:
                await redis.publish(channel, json.dumps(record, default=repr))
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never let a logging failure escalate. Redis being briefly unavailable
                # must not take down a crawl, so the record is simply lost.
                await asyncio.sleep(0.5)


publisher = LogStreamPublisher()


async def subscribe(replay_backlog: bool = True) -> AsyncIterator[dict[str, Any]]:
    """Yield log records as they are published. Terminates when the consumer stops."""
    if replay_backlog:
        for record in log_tap.snapshot():
            yield record

    pubsub = get_redis().pubsub()
    await pubsub.subscribe(settings.log_stream_channel)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if message is None:
                # Idle tick. Keeps the SSE connection warm through proxies.
                yield {"event": "__heartbeat__", "level": "debug", "fields": {}}
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                continue
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(settings.log_stream_channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]
