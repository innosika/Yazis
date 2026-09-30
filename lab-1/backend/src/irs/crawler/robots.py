"""robots.txt fetching, caching and evaluation.

Compliance is a matter of good behaviour rather than access control, and a crawler
written for coursework has no excuse for ignoring it. Rules are parsed once per host and
cached, because refetching robots.txt before every request would be both slow and
precisely the kind of load the protocol exists to prevent.

Conventions applied, following the protocol's usual reading:

* a 404 or any other unreachable robots.txt **permits** the crawl;
* a 401 or 403 on robots.txt **forbids** it, since the host is signalling that even its
  policy is private;
* a declared ``Crawl-delay`` overrides our own default whenever it is longer — never
  shorter, so a host cannot be talked into accepting more load than we would otherwise
  apply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from protego import Protego
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import RobotsCache
from irs.logging import get_logger

log = get_logger("irs.crawler.robots")

#: How long a parsed robots.txt stays valid.
CACHE_TTL = timedelta(hours=6)


class RobotsPolicy:
    """Per-host robots.txt rules, cached in memory and in the database.

    The in-memory layer keeps a single crawl fast; the database layer means a restarted
    worker does not re-request every host's policy.
    """

    def __init__(self, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or settings.crawler.user_agent
        self._parsers: dict[str, Protego | None] = {}
        self._delays: dict[str, float | None] = {}

    async def allows(self, session: AsyncSession, url: str) -> tuple[bool, str | None]:
        """Whether ``url`` may be fetched.

        Returns:
            ``(allowed, reason)``; ``reason`` is populated only on refusal.
        """
        if not settings.crawler.respect_robots_txt:
            return True, None

        host = _host_of(url)
        if not host:
            return False, "malformed URL"

        parser = await self._parser_for(session, url, host)
        if parser is None:
            # Unreachable robots.txt — conventionally permissive.
            return True, None

        if parser.can_fetch(url, self.user_agent):
            return True, None

        log.debug("robots_disallowed", url=url[:200], user_agent=self.user_agent)
        return False, "disallowed by robots.txt"

    async def delay_for(self, session: AsyncSession, url: str) -> float:
        """Politeness delay for this host, in seconds."""
        host = _host_of(url)
        default = settings.crawler.default_delay_seconds
        if not host:
            return default

        if host not in self._delays:
            await self._parser_for(session, url, host)
        declared = self._delays.get(host)
        # Take the longer of the two: a host may ask for more restraint, never less.
        return max(default, declared) if declared else default

    # ------------------------------------------------------------------ loading ----

    async def _parser_for(self, session: AsyncSession, url: str, host: str) -> Protego | None:
        if host in self._parsers:
            return self._parsers[host]

        cached = await session.get(RobotsCache, host)
        now = datetime.now(UTC).replace(tzinfo=None)

        if cached is not None and cached.expires_at and cached.expires_at > now:
            parser = Protego.parse(cached.body) if cached.body else None
            self._parsers[host] = parser
            self._delays[host] = cached.crawl_delay
            return parser

        body, status = await self._fetch(url, host)
        parser = Protego.parse(body) if body else None

        declared_delay: float | None = None
        sitemaps: list[str] = []
        if parser is not None:
            try:
                raw_delay = parser.crawl_delay(self.user_agent)
                declared_delay = float(raw_delay) if raw_delay is not None else None
            except (TypeError, ValueError):
                declared_delay = None
            try:
                sitemaps = list(parser.sitemaps or [])[:20]
            except Exception:
                sitemaps = []

        await session.execute(
            pg_insert(RobotsCache)
            .values(
                host=host,
                body=body,
                fetched=body is not None,
                http_status=status,
                crawl_delay=declared_delay,
                sitemaps=sitemaps or None,
                expires_at=now + CACHE_TTL,
            )
            .on_conflict_do_update(
                index_elements=["host"],
                set_={
                    "body": body,
                    "fetched": body is not None,
                    "http_status": status,
                    "crawl_delay": declared_delay,
                    "sitemaps": sitemaps or None,
                    "expires_at": now + CACHE_TTL,
                },
            )
        )

        self._parsers[host] = parser
        self._delays[host] = declared_delay
        log.info(
            "robots_fetched",
            host=host,
            status=status,
            has_rules=parser is not None,
            crawl_delay=declared_delay,
        )
        return parser

    async def _fetch(self, url: str, host: str) -> tuple[str | None, int | None]:
        """Fetch a host's robots.txt. Never raises."""
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                response = await client.get(robots_url)
        except httpx.HTTPError as exc:
            log.debug("robots_unreachable", host=host, error=str(exc))
            return None, None

        if response.status_code in (401, 403):
            # The host will not even reveal its policy; treat everything as disallowed.
            log.info("robots_forbidden", host=host, status=response.status_code)
            return "User-agent: *\nDisallow: /", response.status_code

        if response.status_code >= 400:
            return None, response.status_code

        return response.text[:512_000], response.status_code


def _host_of(url: str) -> str | None:
    try:
        netloc = urlsplit(url).netloc.lower()
    except ValueError:
        return None
    return netloc or None
