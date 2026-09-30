"""TaskIQ broker.

The crawler runs out-of-process: a crawl of several hundred URLs must survive an API
restart and must not occupy a request worker. TaskIQ is used rather than arq (which is
in maintenance-only mode) because it is async-first, typed, and integrates with
FastAPI's dependency system so tasks can reuse the same session factory as the API.
"""

from __future__ import annotations

from taskiq import InMemoryBroker
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from irs.config import settings
from irs.logging import configure_logging, get_logger

log = get_logger("irs.queue")

QUEUE_NAME = "irs.tasks"

#: Connection settings required for blocking reads to survive.
#:
#: redis-py 8 applies a five-second read timeout when ``socket_timeout`` is left unset,
#: which aborts the broker's blocking stream read and takes the worker process down with
#: it. Passing ``None`` *explicitly* restores unbounded blocking — the value is not the
#: same as the default. Verified directly against this Redis: unset raises after 5 s,
#: explicit ``None`` blocks indefinitely.
#: ``socket_timeout=None`` is the load-bearing entry; the others are hygiene.
#: Detecting a silently dropped connection is what keepalive is for.
_SOCKET_TIMEOUT: float | None = None
_SOCKET_CONNECT_TIMEOUT = 10


def _build_broker() -> RedisStreamBroker | InMemoryBroker:
    # Tests run tasks inline so they need neither Redis nor a worker process.
    if settings.environment == "test":
        return InMemoryBroker()

    result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
        redis_url=str(settings.redis_dsn),
        # Crawl results are progress summaries, not durable data — they live in Postgres.
        result_ex_time=3_600,
        socket_timeout=_SOCKET_TIMEOUT,
        socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT,
        socket_keepalive=True,
    )

    # Redis Streams with a consumer group, rather than the simpler list-based broker,
    # for two reasons.
    #
    # Correctness: a stream entry is acknowledged only after the task completes, so a
    # crawl that dies mid-job is redelivered rather than lost. A list-based broker pops
    # the task off before running it, which loses the job on a worker crash — poor
    # behaviour for work that takes minutes.
    #
    # Robustness: `XREAD ... BLOCK` polls with an explicit interval and reissues, so the
    # listener does not depend on a socket blocking indefinitely. redis-py 8 applies a
    # read timeout that makes an unbounded `BRPOP` raise and take the worker down with
    # it, which is exactly the failure the list broker exhibited here.
    return RedisStreamBroker(
        url=str(settings.redis_dsn),
        queue_name=QUEUE_NAME,
        consumer_group_name="irs-workers",
        # Re-poll every two seconds; the cost is negligible and the listener stays alive.
        xread_block=2_000,
        # Reclaim entries a dead consumer never acknowledged, after ten minutes.
        idle_timeout=600_000,
        max_connection_pool_size=settings.crawler.max_concurrency + 2,
        socket_timeout=_SOCKET_TIMEOUT,
        socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT,
        socket_keepalive=True,
    ).with_result_backend(result_backend)


broker = _build_broker()


@broker.on_event("worker_startup" if not isinstance(broker, InMemoryBroker) else "startup")  # type: ignore[arg-type]
async def _on_worker_startup(_: object = None) -> None:
    configure_logging()
    log.info("worker_startup", queue=QUEUE_NAME, concurrency=settings.crawler.max_concurrency)
