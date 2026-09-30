"""Forwarding a Redis pub/sub channel as a server-sent event stream.

Used by the crawl progress stream and the evaluation progress stream alike: the worker
publishes JSON payloads to a channel, this generator relays them to the browser, and a
heartbeat keeps the connection alive across proxies while nothing happens.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import Request
from sse_starlette.sse import EventSourceResponse

from irs.telemetry.redis_client import get_redis


async def forward_channel(
    request: Request, channel: str, event_name: str = "progress", poll_seconds: float = 15.0
) -> AsyncIterator[dict[str, str]]:
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            if await request.is_disconnected():
                break
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_seconds)
            if message is None:
                yield {"event": "heartbeat", "data": "{}"}
                continue
            try:
                payload = json.loads(message["data"])
            except (TypeError, ValueError):
                continue
            yield {"event": event_name, "data": json.dumps(payload)}
    except asyncio.CancelledError:
        raise
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]


def channel_response(
    request: Request, channel: str, event_name: str = "progress"
) -> EventSourceResponse:
    return EventSourceResponse(forward_channel(request, channel, event_name), ping=15)
