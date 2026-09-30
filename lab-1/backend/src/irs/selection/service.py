"""Search orchestration: parse → rank → present → record.

Sits between the API and the rankers so that every strategy gets identical query
analysis, identical snippet construction and identical logging. That is what makes a
comparison between two rankers a comparison of *ranking* rather than of incidental
differences in their surrounding code.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import Document, SearchLog
from irs.db.models.enums import RankerKey
from irs.index.builder import get_collection_stat
from irs.logging import Stopwatch, get_logger
from irs.selection.base import ParsedQuery, ScoredDocument, SearchFilters
from irs.selection.parser import parse_query
from irs.selection.registry import get_ranker
from irs.selection.snippet import Highlight, build_snippets
from irs.telemetry.metrics import SEARCH_LATENCY, SEARCH_REQUESTS

log = get_logger("irs.selection.service")


@dataclass(slots=True)
class SearchHit:
    """One entry of the result list.

    Carries exactly what the assignment's ``SearchResult`` class specifies —
    ``documentId``, ``title``, ``snippet``, ``rank``, ``date`` — plus the active link and
    the matched query words the requirements call for separately.
    """

    document_id: int
    title: str
    #: The active link to the document.
    url: str
    snippet: str
    #: Similarity score. Named `rank` in the assignment's class diagram.
    rank: float
    date: date | None
    #: Query words present in this document, in the order the user typed them.
    matched_lemmas: list[str] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)
    source_domain: str = ""
    token_count: int = 0
    detail: dict[str, float] = field(default_factory=dict)
    snippet_is_query_biased: bool = False


@dataclass(slots=True)
class SearchResponse:
    """A complete answer, including the diagnostics the interface displays."""

    query: str
    ranker: RankerKey
    hits: list[SearchHit]
    total_candidates: int
    #: The query's search image — shown so the user can see what was actually searched.
    query_lemmas: list[str] = field(default_factory=list)
    unknown_lemmas: list[str] = field(default_factory=list)
    filters_applied: bool = False
    duration_ms: float = 0.0
    stage_timings_ms: dict[str, float] = field(default_factory=dict)
    document_count: int = 0
    term_count: int = 0
    index_version: int = 0


async def search(
    session: AsyncSession,
    raw_query: str,
    ranker_key: RankerKey = RankerKey.VECTOR,
    filters: SearchFilters | None = None,
    limit: int | None = None,
    offset: int = 0,
    record: bool = True,
) -> SearchResponse:
    """Execute one search."""
    filters = filters or SearchFilters()
    limit = min(limit or settings.search.default_limit, settings.search.max_limit)
    watch = Stopwatch()

    stat = await get_collection_stat(session)
    watch.lap("stats")

    parsed = await parse_query(session, raw_query)
    watch.lap("parse")

    ranker = get_ranker(ranker_key)
    # Fetch through the requested offset so paging does not re-run the ranking.
    page = await ranker.rank(
        session, parsed, filters, limit=min(offset + limit, settings.search.candidate_pool)
    )
    watch.lap("rank")

    window = page.documents[offset : offset + limit]
    hits = await _hydrate(session, window, parsed)
    watch.lap("present")

    response = SearchResponse(
        query=raw_query,
        ranker=ranker_key,
        hits=hits,
        total_candidates=page.total_candidates,
        query_lemmas=parsed.lemmas,
        unknown_lemmas=parsed.unknown_lemmas,
        filters_applied=not filters.is_empty,
        duration_ms=watch.total_ms,
        stage_timings_ms=watch.stages,
        document_count=stat.document_count,
        term_count=stat.term_count,
        index_version=stat.index_version,
    )

    SEARCH_LATENCY.labels(ranker=str(ranker_key)).observe(response.duration_ms / 1_000)
    SEARCH_REQUESTS.labels(ranker=str(ranker_key), outcome="hit" if hits else "empty").inc()

    if record:
        await _record(session, response, parsed, filters)

    log.info(
        "search_completed",
        query=raw_query[:120],
        ranker=str(ranker_key),
        lemmas=parsed.lemmas,
        unknown=parsed.unknown_lemmas,
        candidates=page.total_candidates,
        returned=len(hits),
        top_score=round(hits[0].rank, 6) if hits else 0.0,
        duration_ms=response.duration_ms,
        stages_ms=watch.stages,
    )
    return response


async def _hydrate(
    session: AsyncSession, scored: list[ScoredDocument], parsed: ParsedQuery
) -> list[SearchHit]:
    """Attach titles, links, dates and snippets to the ranked ids.

    One query for the whole page rather than one per result — the classic N+1 that would
    otherwise dominate the latency of an otherwise fast ranking.
    """
    if not scored:
        return []

    ids = [item.document_id for item in scored]
    documents = {
        document.id: document
        for document in (
            await session.execute(select(Document).where(Document.id.in_(ids)))
        ).scalars()
    }

    # Results whose document vanished between ranking and hydration are dropped.
    present = [
        (item, documents[item.document_id]) for item in scored if item.document_id in documents
    ]

    # One linguistic pass for the whole page rather than one per result, and off the
    # event loop because it is CPU-bound.
    snippets = await asyncio.to_thread(
        build_snippets,
        [(document.text, document.title) for _, document in present],
        parsed.known_lemmas,
    )

    hits: list[SearchHit] = []
    for (item, document), snippet in zip(present, snippets, strict=True):
        hits.append(
            SearchHit(
                document_id=document.id,
                title=document.title or document.url,
                url=document.url,
                snippet=snippet.text,
                rank=item.score,
                date=document.published_at
                or (document.fetched_at.date() if document.fetched_at else None),
                matched_lemmas=item.matched_lemmas or snippet.matched_lemmas,
                highlights=snippet.highlights,
                source_domain=document.source_domain,
                token_count=document.token_count,
                detail=item.detail,
                snippet_is_query_biased=snippet.query_biased,
            )
        )
    return hits


async def _record(
    session: AsyncSession,
    response: SearchResponse,
    parsed: ParsedQuery,
    filters: SearchFilters,
) -> None:
    """Persist the search for the report's performance section.

    Failure to log must never fail the search, so this is best-effort: the user's result
    matters more than the telemetry about it.
    """
    try:
        session.add(
            SearchLog(
                created_at=datetime.now(UTC).replace(tzinfo=None),
                query_text=response.query[:512],
                query_lemmas=parsed.lemmas[:64],
                ranker=response.ranker,
                all_words_together=filters.all_words_together,
                date_from=(
                    datetime.combine(filters.date_from, datetime.min.time())
                    if filters.date_from
                    else None
                ),
                date_to=(
                    datetime.combine(filters.date_to, datetime.min.time())
                    if filters.date_to
                    else None
                ),
                candidates_considered=response.total_candidates,
                result_count=len(response.hits),
                top_score=response.hits[0].rank if response.hits else None,
                stage_timings_ms=response.stage_timings_ms,
                duration_ms=response.duration_ms,
                index_version=response.index_version,
            )
        )
        await session.flush()
    except Exception as exc:
        log.warning("search_log_failed", error=str(exc))
