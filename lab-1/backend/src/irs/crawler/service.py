"""Crawl orchestration.

Drives one crawl job from its seed URLs to indexed documents, recording every URL's
outcome in the frontier table so the crawl can be inspected and reported on rather than
only observed while it runs.

The pipeline per URL is: claim → robots check → fetch → extract → deduplicate → store,
with a stage-timing breakdown and a skip reason recorded at whichever step rejects it.
Progress is published to Redis as it happens, so the interface shows a live crawl rather
than a spinner.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.crawler import urls as urlutil
from irs.crawler.dedup import (
    content_hash,
    from_signed_64,
    hamming_distance,
    simhash,
    to_signed_64,
)
from irs.crawler.extract import Extracted, extract
from irs.crawler.fetcher import Fetcher, FetchResult, HostThrottle
from irs.crawler.robots import RobotsPolicy
from irs.db.models import CrawlJob, CrawlTask, Document
from irs.db.models.enums import CrawlStatus, SkipReason, UrlStatus
from irs.db.session import get_sessionmaker
from irs.index.builder import IndexBuilder
from irs.logging import Stopwatch, bind_request_id, get_logger
from irs.telemetry.metrics import CRAWL_PAGES
from irs.telemetry.redis_client import get_redis

log = get_logger("irs.crawler.service")

PROGRESS_CHANNEL = "irs.crawl.progress"


@dataclass(slots=True)
class CrawlOutcome:
    """Summary of a finished crawl."""

    job_id: int
    fetched: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    discovered: int = 0
    bytes_downloaded: int = 0
    skip_breakdown: dict[str, int] | None = None
    duration_ms: float = 0.0


async def create_job(
    session: AsyncSession,
    seed_urls: list[str],
    max_pages: int,
    max_depth: int,
    same_domain_only: bool = True,
) -> CrawlJob:
    """Create a crawl job and enqueue its seeds in the frontier."""
    canonical_seeds: list[str] = []
    for raw in seed_urls:
        canonical = urlutil.canonicalize(raw)
        if canonical is None:
            raise ValueError(f"not a crawlable URL: {raw!r}")
        canonical_seeds.append(canonical)

    if not canonical_seeds:
        raise ValueError("at least one seed URL is required")

    job = CrawlJob(
        seed_urls=canonical_seeds,
        max_pages=min(max_pages, settings.crawler.max_pages_per_job),
        max_depth=min(max_depth, settings.crawler.max_depth),
        same_domain_only=same_domain_only,
        respect_robots_txt=settings.crawler.respect_robots_txt,
        delay_seconds=settings.crawler.default_delay_seconds,
        status=CrawlStatus.PENDING,
    )
    session.add(job)
    await session.flush()

    for url in canonical_seeds:
        session.add(
            CrawlTask(
                job_id=job.id,
                url=url,
                url_canonical=url,
                depth=0,
                priority=0,  # seeds always go first
                status=UrlStatus.PENDING,
            )
        )
    await session.flush()

    log.info(
        "crawl_job_created",
        job_id=job.id,
        seeds=canonical_seeds,
        max_pages=job.max_pages,
        max_depth=job.max_depth,
        same_domain_only=same_domain_only,
    )
    return job


class Crawler:
    """Executes one crawl job."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self.robots = RobotsPolicy()
        self.throttle = HostThrottle()
        self.skip_counts: dict[str, int] = {}
        self._sessionmaker = get_sessionmaker()

    async def run(self) -> CrawlOutcome:
        """Drain the frontier until the page budget or the frontier is exhausted."""
        watch = Stopwatch()
        outcome = CrawlOutcome(job_id=self.job_id)

        async with self._sessionmaker() as session:
            job = await session.get(CrawlJob, self.job_id)
            if job is None:
                raise LookupError(f"crawl job {self.job_id} does not exist")
            job.status = CrawlStatus.RUNNING
            job.started_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            budget = job.max_pages
            max_depth = job.max_depth
            same_domain_only = job.same_domain_only
            seeds = list(job.seed_urls)

        log.info("crawl_started", job_id=self.job_id, budget=budget, max_depth=max_depth)
        await self._publish({"event": "started", "job_id": self.job_id, "budget": budget})

        async with Fetcher(self.throttle) as fetcher:
            # Workers share the frontier and claim rows with SKIP LOCKED, so several can
            # drain it concurrently without ever being handed the same URL.
            workers = [
                asyncio.create_task(
                    self._worker(
                        index=index,
                        fetcher=fetcher,
                        outcome=outcome,
                        budget=budget,
                        max_depth=max_depth,
                        same_domain_only=same_domain_only,
                        seeds=seeds,
                    ),
                    name=f"crawl-{self.job_id}-{index}",
                )
                for index in range(settings.crawler.max_concurrency)
            ]
            await asyncio.gather(*workers, return_exceptions=True)

        outcome.skip_breakdown = dict(self.skip_counts)
        outcome.duration_ms = watch.total_ms

        async with self._sessionmaker() as session:
            job = await session.get(CrawlJob, self.job_id)
            if job is not None:
                job.status = CrawlStatus.DONE
                job.finished_at = datetime.now(UTC).replace(tzinfo=None)
                job.pages_fetched = outcome.fetched
                job.pages_indexed = outcome.indexed
                job.pages_skipped = outcome.skipped
                job.pages_failed = outcome.failed
                job.urls_discovered = outcome.discovered
                job.bytes_downloaded = outcome.bytes_downloaded
                job.skip_breakdown = outcome.skip_breakdown or {}
                await session.commit()

            # Every weight in the collection depends on N, so the reweighting happens
            # once at the end of the job rather than after each page.
            if outcome.indexed:
                async with self._sessionmaker() as index_session:
                    stats = await IndexBuilder(index_session).rebuild(reanalyze=False)
                    await index_session.commit()
                log.info("crawl_index_updated", job_id=self.job_id, **stats.as_dict())

        log.info(
            "crawl_finished",
            job_id=self.job_id,
            fetched=outcome.fetched,
            indexed=outcome.indexed,
            skipped=outcome.skipped,
            failed=outcome.failed,
            discovered=outcome.discovered,
            skip_breakdown=outcome.skip_breakdown,
            duration_ms=round(outcome.duration_ms, 1),
        )
        await self._publish(
            {
                "event": "finished",
                "job_id": self.job_id,
                "indexed": outcome.indexed,
                "skipped": outcome.skipped,
                "failed": outcome.failed,
                "duration_ms": round(outcome.duration_ms, 1),
            }
        )
        return outcome

    # ------------------------------------------------------------------ worker ----

    async def _worker(
        self,
        index: int,
        fetcher: Fetcher,
        outcome: CrawlOutcome,
        budget: int,
        max_depth: int,
        same_domain_only: bool,
        seeds: list[str],
    ) -> None:
        idle_rounds = 0

        while True:
            if outcome.fetched >= budget:
                return

            async with self._sessionmaker() as session:
                task = await self._claim(session)
                if task is None:
                    await session.commit()
                    # The frontier may be momentarily empty while a peer is still
                    # discovering links, so give up only after several empty rounds.
                    idle_rounds += 1
                    if idle_rounds >= 3:
                        return
                    await asyncio.sleep(0.4)
                    continue

                idle_rounds = 0
                with bind_request_id():
                    await self._process(
                        session=session,
                        task=task,
                        fetcher=fetcher,
                        outcome=outcome,
                        budget=budget,
                        max_depth=max_depth,
                        same_domain_only=same_domain_only,
                        seeds=seeds,
                    )
                await session.commit()
                # Progress is committed after the frontier row's own transaction, so a
                # reader never sees counters that include work which was rolled back.
                await self._flush_progress(outcome)

    async def _claim(self, session: AsyncSession) -> CrawlTask | None:
        """Take the next pending URL, locking it against other workers.

        ``FOR UPDATE SKIP LOCKED`` is what makes the frontier safe to share: a row being
        processed by one worker is invisible to the others rather than blocking them.
        """
        row = (
            await session.execute(
                text(
                    """
                    SELECT id FROM crawl_task
                     WHERE job_id = :job_id AND status = 'pending'
                     ORDER BY priority, depth, id
                     LIMIT 1
                     FOR UPDATE SKIP LOCKED
                    """
                ),
                {"job_id": self.job_id},
            )
        ).first()

        if row is None:
            return None

        task = await session.get(CrawlTask, row.id)
        if task is None:
            return None

        task.status = UrlStatus.IN_PROGRESS
        task.claimed_at = datetime.now(UTC).replace(tzinfo=None)
        task.attempts += 1
        await session.flush()
        return task

    async def _process(
        self,
        session: AsyncSession,
        task: CrawlTask,
        fetcher: Fetcher,
        outcome: CrawlOutcome,
        budget: int,
        max_depth: int,
        same_domain_only: bool,
        seeds: list[str],
    ) -> None:
        watch = Stopwatch()
        url = task.url

        # --- robots.txt ---------------------------------------------------------
        allowed, reason = await self.robots.allows(session, url)
        watch.lap("robots")
        if not allowed:
            await self._skip(session, task, outcome, SkipReason.ROBOTS_DISALLOWED, reason)
            return

        delay = await self.robots.delay_for(session, url)

        # --- fetch --------------------------------------------------------------
        host = urlutil.registrable_host(url) or "unknown"
        result = await fetcher.fetch(url, host, delay)
        watch.lap("fetch")

        task.http_status = result.status
        task.content_bytes = result.byte_size
        outcome.bytes_downloaded += result.byte_size

        if not result.ok:
            failed = result.skip_reason in (SkipReason.HTTP_ERROR, SkipReason.TIMEOUT)
            await self._skip(
                session,
                task,
                outcome,
                result.skip_reason or SkipReason.HTTP_ERROR,
                result.error,
                counts_as_failure=failed,
            )
            return

        outcome.fetched += 1

        # --- extract ------------------------------------------------------------
        extracted = extract(result.html or "", result.final_url)
        watch.lap("extract")
        if extracted is None:
            await self._skip(session, task, outcome, SkipReason.TOO_SHORT, "no usable content")
            await self._enqueue_links(
                session,
                task,
                result.html or "",
                result.final_url,
                outcome,
                max_depth,
                same_domain_only,
                seeds,
            )
            return

        task.extracted_chars = extracted.char_count

        # Variant 34 specifies an English collection, so other languages are recorded
        # as skips rather than indexed — a mixed-language dictionary would make the
        # term statistics meaningless.
        if extracted.language and not extracted.language.startswith("en"):
            await self._skip(session, task, outcome, SkipReason.WRONG_LANGUAGE, extracted.language)
            return

        # --- deduplicate --------------------------------------------------------
        # SimHash tokenises and hashes the whole document, so it is CPU-bound for a
        # long page; both digests are computed in one thread hop.
        digest, fingerprint = await asyncio.to_thread(
            lambda text: (content_hash(text), simhash(text)), extracted.text
        )
        duplicate_of = await self._find_duplicate(session, digest, fingerprint)
        watch.lap("dedup")

        if duplicate_of is not None:
            kind = (
                SkipReason.DUPLICATE_CONTENT if duplicate_of[1] == 0 else SkipReason.NEAR_DUPLICATE
            )
            await self._skip(
                session,
                task,
                outcome,
                kind,
                f"document {duplicate_of[0]} (distance {duplicate_of[1]})",
            )
            await self._enqueue_links(
                session,
                task,
                result.html or "",
                result.final_url,
                outcome,
                max_depth,
                same_domain_only,
                seeds,
            )
            return

        # --- store and index ----------------------------------------------------
        stored = await self._store(
            session, task, outcome, result, extracted, digest, fingerprint, watch, budget
        )
        if stored:
            await self._enqueue_links(
                session,
                task,
                result.html or "",
                result.final_url,
                outcome,
                max_depth,
                same_domain_only,
                seeds,
            )

    async def _store(
        self,
        session: AsyncSession,
        task: CrawlTask,
        outcome: CrawlOutcome,
        result: FetchResult,
        extracted: Extracted,
        digest: str,
        fingerprint: int,
        watch: Stopwatch,
        budget: int,
    ) -> bool:
        """Persist an accepted page and add it to the index.

        Returns False when a concurrent worker stored the same URL first.
        """
        document = Document(
            url=result.final_url,
            source_domain=urlutil.registrable_host(result.final_url),
            title=extracted.title,
            text=extracted.text,
            published_at=extracted.published_at,
            fetched_at=datetime.now(UTC).replace(tzinfo=None),
            language=extracted.language or "en",
            author=extracted.author,
            description=extracted.description,
            http_status=result.status,
            byte_size=result.byte_size,
            content_hash=digest,
            simhash=to_signed_64(fingerprint),
        )
        session.add(document)

        try:
            await session.flush()
        except IntegrityError:
            # Another worker stored this URL first.
            await session.rollback()
            await self._skip(
                session, task, outcome, SkipReason.DUPLICATE_URL, "stored concurrently"
            )
            return False

        await IndexBuilder(session).index_document(document)
        watch.lap("index")

        task.status = UrlStatus.INDEXED
        task.document_id = document.id
        task.finished_at = datetime.now(UTC).replace(tzinfo=None)
        task.stage_timings_ms = watch.stages
        outcome.indexed += 1
        CRAWL_PAGES.labels(outcome="indexed").inc()

        log.info(
            "page_indexed",
            job_id=self.job_id,
            url=result.final_url[:200],
            document_id=document.id,
            depth=task.depth,
            title=extracted.title[:80],
            chars=extracted.char_count,
            bytes=result.byte_size,
            stages_ms=watch.stages,
        )
        await self._publish(
            {
                "event": "indexed",
                "job_id": self.job_id,
                "url": result.final_url,
                "title": extracted.title[:120],
                "document_id": document.id,
                "depth": task.depth,
                "chars": extracted.char_count,
                "fetched": outcome.fetched,
                "indexed": outcome.indexed,
                "skipped": outcome.skipped,
                "budget": budget,
            }
        )

        return True

    # ----------------------------------------------------------------- helpers ----

    async def _find_duplicate(
        self, session: AsyncSession, digest: str, fingerprint: int
    ) -> tuple[int, int] | None:
        """Locate an existing document that duplicates this content.

        Returns ``(document_id, hamming_distance)``, with distance 0 for an exact match.

        The near-duplicate scan compares against every stored fingerprint, which is
        linear in `N`. At the scale this collection is built for that is a few thousand
        integer comparisons and not worth optimising; a larger crawl would index the
        fingerprints by band (the standard LSH approach) instead.
        """
        exact = (
            await session.execute(
                select(Document.id).where(Document.content_hash == digest).limit(1)
            )
        ).scalar_one_or_none()
        if exact is not None:
            return exact, 0

        if not fingerprint:
            return None

        threshold = settings.crawler.near_duplicate_distance
        rows = (
            await session.execute(
                select(Document.id, Document.simhash).where(Document.simhash.isnot(None))
            )
        ).all()

        for document_id, stored in rows:
            distance = hamming_distance(fingerprint, from_signed_64(stored))
            if distance <= threshold:
                return document_id, distance
        return None

    async def _enqueue_links(
        self,
        session: AsyncSession,
        task: CrawlTask,
        html: str,
        base_url: str,
        outcome: CrawlOutcome,
        max_depth: int,
        same_domain_only: bool,
        seeds: list[str],
    ) -> None:
        """Add a page's outbound links to the frontier."""
        if task.depth >= max_depth:
            return

        links = urlutil.extract_links(html, base_url)
        if not links:
            return

        if same_domain_only:
            links = [link for link in links if any(urlutil.same_site(link, seed) for seed in seeds)]

        if not links:
            return

        # One statement for the page's links; the unique constraint on
        # (job_id, url_canonical) discards any already in the frontier.
        existing = {
            row[0]
            for row in (
                await session.execute(
                    select(CrawlTask.url_canonical).where(
                        CrawlTask.job_id == self.job_id,
                        CrawlTask.url_canonical.in_(links),
                    )
                )
            ).all()
        }

        added = 0
        for link in links:
            if link in existing:
                continue
            session.add(
                CrawlTask(
                    job_id=self.job_id,
                    url=link,
                    url_canonical=link,
                    depth=task.depth + 1,
                    # Shallower pages are more likely to be substantive, so depth is the
                    # priority: a breadth-first frontier rather than depth-first.
                    priority=100 + task.depth,
                    status=UrlStatus.PENDING,
                    discovered_from=task.id,
                )
            )
            added += 1

        if added:
            outcome.discovered += added
            try:
                await session.flush()
            except IntegrityError:
                # A peer enqueued the same link between the SELECT and the INSERT.
                await session.rollback()

    async def _skip(
        self,
        session: AsyncSession,
        task: CrawlTask,
        outcome: CrawlOutcome,
        reason: SkipReason,
        detail: str | None = None,
        counts_as_failure: bool = False,
    ) -> None:
        task.status = UrlStatus.FAILED if counts_as_failure else UrlStatus.SKIPPED
        task.skip_reason = reason
        task.error = (detail or "")[:500] or None
        task.finished_at = datetime.now(UTC).replace(tzinfo=None)

        key = str(reason)
        self.skip_counts[key] = self.skip_counts.get(key, 0) + 1
        if counts_as_failure:
            outcome.failed += 1
        else:
            outcome.skipped += 1
        CRAWL_PAGES.labels(outcome=key).inc()

        log.info(
            "page_skipped",
            job_id=self.job_id,
            url=task.url[:200],
            reason=key,
            detail=(detail or "")[:160] or None,
            depth=task.depth,
        )
        await self._publish(
            {
                "event": "skipped",
                "job_id": self.job_id,
                "url": task.url,
                "reason": key,
                "detail": (detail or "")[:160] or None,
                "fetched": outcome.fetched,
                "indexed": outcome.indexed,
                "skipped": outcome.skipped,
            }
        )

    async def _flush_progress(self, outcome: CrawlOutcome) -> None:
        """Write the running counters onto the job row.

        Called as pages complete rather than only at the end of the job, so that
        ``GET /crawl/jobs/{id}`` reports a crawl in progress instead of zeros until it
        finishes. Uses its own short-lived session: the worker's session is inside the
        transaction that holds the frontier row lock, and progress must be visible to
        other connections before that transaction commits.
        """
        async with self._sessionmaker() as session:
            await session.execute(
                update(CrawlJob)
                .where(CrawlJob.id == self.job_id)
                .values(
                    pages_fetched=outcome.fetched,
                    pages_indexed=outcome.indexed,
                    pages_skipped=outcome.skipped,
                    pages_failed=outcome.failed,
                    urls_discovered=outcome.discovered,
                    bytes_downloaded=outcome.bytes_downloaded,
                    skip_breakdown=dict(self.skip_counts),
                )
            )
            await session.commit()

    async def _publish(self, payload: dict[str, object]) -> None:
        """Publish crawl progress. Best-effort — telemetry must not break a crawl."""
        try:
            await get_redis().publish(PROGRESS_CHANNEL, json.dumps(payload, default=str))
        except Exception as exc:
            log.debug("crawl_progress_publish_failed", error=str(exc))


# --------------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------------


async def run_crawl(job_id: int) -> CrawlOutcome:
    """Execute an existing crawl job."""
    try:
        return await Crawler(job_id).run()
    except Exception as exc:
        log.exception("crawl_failed", job_id=job_id)
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            job = await session.get(CrawlJob, job_id)
            if job is not None:
                job.status = CrawlStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"[:2_000]
                job.finished_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()
        raise


async def run_crawl_from_cli(
    seed_urls: list[str],
    max_pages: int,
    max_depth: int,
    same_domain_only: bool = True,
) -> int:
    """Create and run a crawl synchronously, for ``python -m irs.cli crawl``."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        job = await create_job(
            session,
            seed_urls=seed_urls,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
        )
        await session.commit()
        job_id = job.id

    outcome = await run_crawl(job_id)

    print(f"\nCrawl {job_id} complete")
    print("-" * 46)
    print(f"  fetched          {outcome.fetched}")
    print(f"  indexed          {outcome.indexed}")
    print(f"  skipped          {outcome.skipped}")
    print(f"  failed           {outcome.failed}")
    print(f"  discovered       {outcome.discovered}")
    print(f"  downloaded       {outcome.bytes_downloaded / 1024:.0f} KiB")
    print(f"  duration         {outcome.duration_ms / 1000:.1f} s")
    if outcome.skip_breakdown:
        print("  skip reasons:")
        for reason, count in sorted(outcome.skip_breakdown.items(), key=lambda item: -item[1]):
            print(f"    {reason:<24} {count}")
    print()
    return 0
