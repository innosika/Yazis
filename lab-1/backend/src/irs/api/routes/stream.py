"""Server-sent event streams.

The log stream exists so that the assignment's "clear logging" requirement is
demonstrable in the interface: the UI opens this endpoint and renders a live console
carrying records from both the API and the crawl worker.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from irs.logging import get_logger
from irs.telemetry.logstream import subscribe

log = get_logger("irs.api.stream")
router = APIRouter(prefix="/stream", tags=["stream"])

_LEVEL_ORDER = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}


@router.get("/logs", summary="Live log stream (SSE)")
async def stream_logs(
    request: Request,
    min_level: str = Query("info", pattern="^(debug|info|warning|error|critical)$"),
    logger_prefix: str | None = Query(None, description="e.g. 'irs.crawler'"),
    backlog: bool = Query(True, description="Replay recent records on connect"),
) -> EventSourceResponse:
    threshold = _LEVEL_ORDER[min_level]

    async def generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for record in subscribe(replay_backlog=backlog):
                if await request.is_disconnected():
                    break
                event_name = record.get("event", "")
                if event_name == "__heartbeat__":
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                if _LEVEL_ORDER.get(str(record.get("level", "info")), 20) < threshold:
                    continue
                if logger_prefix and not str(record.get("logger", "")).startswith(logger_prefix):
                    continue
                yield {"event": "log", "data": json.dumps(record, default=repr)}
        except asyncio.CancelledError:
            raise

    return EventSourceResponse(generator(), ping=15)
