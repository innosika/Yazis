"""Shared Redis connection pool."""

from __future__ import annotations

from redis.asyncio import Redis

from irs.config import settings
from irs.logging import get_logger

log = get_logger("irs.redis")

_client: Redis | None = None


def get_redis() -> Redis:
    """Process-wide Redis client. Decodes to ``str`` — we only ever store JSON text."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            str(settings.redis_dsn),
            decode_responses=True,
            socket_keepalive=True,
            # Explicitly unbounded: pub/sub `get_message` blocks, and redis-py 8 applies
            # a five-second read timeout when this is left unset. See irs.queue.
            socket_timeout=None,
            socket_connect_timeout=10,
            health_check_interval=30,
        )
    return _client


async def ping() -> bool:
    return bool(await get_redis().ping())


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        log.info("redis_closed")
    _client = None
