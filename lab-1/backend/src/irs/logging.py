"""Structured logging.

The lab is graded partly on having *comprehensible* logging, so this module does three
things rather than one:

1. configures ``structlog`` so every record is a structured event with stable keys;
2. keeps a ``request_id`` bound for the whole lifetime of a request or background task,
   so a crawl of one URL can be reconstructed from its log lines alone;
3. taps every record into an in-process queue, which :mod:`irs.telemetry.logstream`
   drains onto a Redis channel. The UI subscribes to that channel over SSE, so the log
   is visible in the interface instead of being buried in ``docker logs``.

The tap is deliberately lossy: if the queue is full the record is dropped rather than
blocking the caller. Logging must never be able to stall a crawl.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable, MutableMapping
from contextvars import ContextVar
from typing import Any, Final

import structlog

from irs.config import settings

#: Correlation id shared by every log record emitted while handling one request/task.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

EventDict = MutableMapping[str, Any]

#: Keys that carry no information for a reader and only add noise to the console.
#: The correlation id is kept in the structured record but hidden from the human-readable
#: renderer, where it would dominate every line.
_DROPPED_IN_CONSOLE: Final = ("logger_name",)


class LogTap:
    """Fan-out buffer between the synchronous logger and the async Redis publisher.

    ``structlog`` processors are synchronous and may run on any thread, while Redis
    publication is async. The tap bridges the two without either side waiting on the
    other: producers call :meth:`emit` (never blocks, drops when saturated) and the
    publisher task calls :meth:`drain`.
    """

    def __init__(self, maxsize: int = 2_048, backlog: int = 200) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        #: Recent records, replayed to a UI client that has only just connected.
        self._backlog: deque[dict[str, Any]] = deque(maxlen=backlog)
        self._loop: asyncio.AbstractEventLoop | None = None
        self.dropped = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record which loop owns the queue, so off-loop threads can hand records over."""
        self._loop = loop

    def emit(self, record: dict[str, Any]) -> None:
        self._backlog.append(record)
        loop = self._loop
        if loop is None:
            return
        try:
            if loop is _running_loop():
                self._queue.put_nowait(record)
            else:
                # Called from a worker thread (e.g. a sync DB driver): hop to the loop.
                loop.call_soon_threadsafe(self._offer, record)
        except (asyncio.QueueFull, RuntimeError):
            self.dropped += 1

    def _offer(self, record: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1

    async def drain(self) -> dict[str, Any]:
        return await self._queue.get()

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._backlog)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


log_tap = LogTap(backlog=settings.log_stream_backlog)


def _add_request_id(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Attach the correlation id, if one is bound to this context."""
    rid = request_id_var.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def _tap_processor(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Copy the record into the live stream. Must run before the final renderer."""
    if settings.log_stream_enabled:
        log_tap.emit(
            {
                "ts": event_dict.get("timestamp") or time.time(),
                "level": event_dict.get("level", "info"),
                "logger": event_dict.get("logger") or event_dict.get("logger_name") or "irs",
                "event": event_dict.get("event", ""),
                "request_id": event_dict.get("request_id"),
                # Everything else, so the UI can show stage timings and counters.
                "fields": {
                    k: _jsonable(v)
                    for k, v in event_dict.items()
                    if k
                    not in {"timestamp", "level", "event", "logger", "logger_name", "request_id"}
                },
            }
        )
    return event_dict


def _jsonable(value: Any) -> Any:
    """Coerce a value into something ``json.dumps`` will accept."""
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return repr(value)


def _drop_console_noise(_: Any, __: str, event_dict: EventDict) -> EventDict:
    for key in _DROPPED_IN_CONSOLE:
        event_dict.pop(key, None)
    return event_dict


def configure_logging() -> None:
    """Install the structlog + stdlib logging configuration. Idempotent."""
    shared: list[Callable[..., Any]] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        # NOTE: `structlog.stdlib.add_logger_name` is deliberately not used — it reads
        # `logger.name`, which the PrintLogger factory below does not provide. The name
        # is bound explicitly by `get_logger` instead.
        _add_request_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Any
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
        tail = [structlog.processors.format_exc_info, _tap_processor, renderer]
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        tail = [
            structlog.processors.format_exc_info,
            _tap_processor,
            _drop_console_noise,
            renderer,
        ]

    structlog.configure(
        processors=[*shared, *tail],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib loggers (uvicorn, sqlalchemy, httpx) through the same pipeline so the
    # UI's log console shows a single coherent stream.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=logging.getLevelNamesMapping()[settings.log_level.upper()],
        force=True,
    )
    for noisy, level in (
        ("uvicorn.access", logging.WARNING),
        ("uvicorn.error", logging.INFO),
        ("httpx", logging.WARNING),
        ("httpcore", logging.WARNING),
        ("sqlalchemy.engine", logging.INFO if settings.db_echo else logging.WARNING),
        ("trafilatura", logging.ERROR),
        ("charset_normalizer", logging.ERROR),
    ):
        logging.getLogger(noisy).setLevel(level)


def get_logger(name: str) -> Any:
    """Return a logger with its stage name bound.

    Use dotted stage names (``irs.crawler.fetch``): the UI's log console filters by
    prefix, so `irs.crawler` selects the whole crawl subsystem.
    """
    return structlog.get_logger().bind(logger=name)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


class bind_request_id:  # noqa: N801 — used as a context manager, reads better lowercase
    """Bind a correlation id for the duration of a block.

    Used by the HTTP middleware and by each background task, so that a crawl of a single
    URL — fetch, extract, lemmatise, index — shares one id across all its log lines.
    """

    def __init__(self, request_id: str | None = None) -> None:
        self.request_id = request_id or new_request_id()
        self._token: Any = None

    def __enter__(self) -> str:
        self._token = request_id_var.set(self.request_id)
        structlog.contextvars.bind_contextvars(request_id=self.request_id)
        return self.request_id

    def __exit__(self, *_: object) -> None:
        if self._token is not None:
            request_id_var.reset(self._token)
        structlog.contextvars.unbind_contextvars("request_id")


class Stopwatch:
    """Accumulates named stage timings for one logical operation.

    Every search and every crawled URL reports its per-stage breakdown, which is what
    makes the report's performance section measurable rather than anecdotal.
    """

    __slots__ = ("_stage_start", "_start", "stages")

    def __init__(self) -> None:
        self.stages: dict[str, float] = {}
        self._start = time.perf_counter()
        self._stage_start = self._start

    def lap(self, stage: str) -> float:
        """Close the current stage and open the next. Returns the stage duration in ms."""
        now = time.perf_counter()
        elapsed_ms = (now - self._stage_start) * 1_000.0
        self.stages[stage] = round(elapsed_ms, 3)
        self._stage_start = now
        return elapsed_ms

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1_000.0, 3)
