"""Polite, bounded HTTP fetching.

Three properties matter more than speed here:

* **Politeness** — per-host concurrency and a minimum interval between requests to the
  same host, so a crawl of one site does not behave like a denial of service.
* **Boundedness** — a size ceiling enforced *while streaming*, so a multi-gigabyte
  response cannot exhaust memory before the content-length check would have caught it.
* **Never raising** — a crawl visits arbitrary hosts, so every failure mode (DNS, TLS,
  timeout, malformed encoding) is an expected outcome that becomes a recorded skip.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

import httpx

from irs.config import settings
from irs.db.models.enums import SkipReason
from irs.logging import get_logger
from irs.telemetry.metrics import CRAWL_FETCH_LATENCY

log = get_logger("irs.crawler.fetch")


@dataclass(slots=True)
class FetchResult:
    """Outcome of one HTTP request."""

    url: str
    #: URL after redirects — what the document is actually stored under.
    final_url: str
    status: int | None = None
    html: str | None = None
    content_type: str | None = None
    byte_size: int = 0
    duration_ms: float = 0.0
    skip_reason: SkipReason | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.html is not None and self.skip_reason is None


class HostThrottle:
    """Enforces a minimum interval and a concurrency cap per host.

    Politeness is per host rather than global: fetching ten pages from ten different
    sites at once is courteous, fetching ten pages from one site at once is not.
    """

    def __init__(self, per_host_concurrency: int = 2) -> None:
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._per_host_concurrency = per_host_concurrency

    def _semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._semaphores:
            self._semaphores[host] = asyncio.Semaphore(self._per_host_concurrency)
        return self._semaphores[host]

    async def acquire(self, host: str, delay: float) -> None:
        await self._semaphore(host).acquire()
        async with self._locks[host]:
            elapsed = time.monotonic() - self._last_request.get(host, 0.0)
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._last_request[host] = time.monotonic()

    def release(self, host: str) -> None:
        self._semaphore(host).release()


class Fetcher:
    """Async HTTP client for crawling.

    HTTP/2 is enabled because it multiplexes several requests to the same host over one
    connection, which reduces the handshake cost of a crawl that revisits a host
    repeatedly — the normal shape of a same-domain crawl.
    """

    def __init__(self, throttle: HostThrottle | None = None) -> None:
        self.throttle = throttle or HostThrottle()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Fetcher:
        self._client = httpx.AsyncClient(
            http2=True,
            follow_redirects=True,
            max_redirects=5,
            timeout=httpx.Timeout(settings.crawler.request_timeout_seconds),
            limits=httpx.Limits(
                max_connections=settings.crawler.max_concurrency * 2,
                max_keepalive_connections=settings.crawler.max_concurrency,
            ),
            headers={
                "User-Agent": settings.crawler.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en",
                # Identify the crawl as automated, so operators can see what we are.
                "From": "coursework-crawler",
            },
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch(self, url: str, host: str, delay: float) -> FetchResult:
        """Fetch one URL. Never raises; failures come back as a skip reason."""
        if self._client is None:
            raise RuntimeError("Fetcher must be used as an async context manager")

        started = time.perf_counter()
        await self.throttle.acquire(host, delay)

        try:
            return await self._fetch_inner(url, started)
        except httpx.TimeoutException as exc:
            return self._failure(url, started, SkipReason.TIMEOUT, str(exc))
        except httpx.HTTPError as exc:
            return self._failure(url, started, SkipReason.HTTP_ERROR, str(exc))
        except UnicodeDecodeError as exc:
            return self._failure(url, started, SkipReason.EXTRACTION_FAILED, str(exc))
        except Exception as exc:
            return self._failure(
                url, started, SkipReason.HTTP_ERROR, f"{type(exc).__name__}: {exc}"
            )
        finally:
            self.throttle.release(host)
            CRAWL_FETCH_LATENCY.observe(time.perf_counter() - started)

    async def _fetch_inner(self, url: str, started: float) -> FetchResult:
        assert self._client is not None

        # Streamed so the size ceiling is enforced as bytes arrive, rather than trusting
        # a Content-Length header that may be absent or wrong.
        async with self._client.stream("GET", url) as response:
            final_url = str(response.url)
            content_type = (
                (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            )

            if response.status_code >= 400:
                await response.aclose()
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    status=response.status_code,
                    content_type=content_type,
                    duration_ms=(time.perf_counter() - started) * 1_000,
                    skip_reason=SkipReason.HTTP_ERROR,
                    error=f"HTTP {response.status_code}",
                )

            if content_type and content_type not in settings.crawler.allowed_content_types:
                await response.aclose()
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    status=response.status_code,
                    content_type=content_type,
                    duration_ms=(time.perf_counter() - started) * 1_000,
                    skip_reason=SkipReason.WRONG_CONTENT_TYPE,
                )

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes(chunk_size=65_536):
                total += len(chunk)
                if total > settings.crawler.max_content_bytes:
                    await response.aclose()
                    return FetchResult(
                        url=url,
                        final_url=final_url,
                        status=response.status_code,
                        content_type=content_type,
                        byte_size=total,
                        duration_ms=(time.perf_counter() - started) * 1_000,
                        skip_reason=SkipReason.TOO_LARGE,
                    )
                chunks.append(chunk)

            body = b"".join(chunks)
            # httpx resolves the charset from headers and, failing that, sniffs it.
            encoding = response.encoding or "utf-8"
            try:
                html = body.decode(encoding, errors="replace")
            except LookupError:
                html = body.decode("utf-8", errors="replace")

        duration_ms = (time.perf_counter() - started) * 1_000
        log.debug(
            "fetched",
            url=url[:200],
            status=response.status_code,
            bytes=total,
            duration_ms=round(duration_ms, 1),
        )
        return FetchResult(
            url=url,
            final_url=final_url,
            status=response.status_code,
            html=html,
            content_type=content_type,
            byte_size=total,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _failure(url: str, started: float, reason: SkipReason, error: str) -> FetchResult:
        duration_ms = (time.perf_counter() - started) * 1_000
        log.debug("fetch_failed", url=url[:200], reason=str(reason), error=error[:200])
        return FetchResult(
            url=url,
            final_url=url,
            duration_ms=duration_ms,
            skip_reason=reason,
            error=error[:500],
        )
