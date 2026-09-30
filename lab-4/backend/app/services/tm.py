"""Translation memory with fuzzy matching. (Additional feature 1.)

A translation memory is the oldest and most useful idea in computer-assisted translation: a
sentence a human has already approved should never be machine-translated again, and a
sentence that is *nearly* the same should be offered as a starting point with an honest
match percentage. That is how Trados and memoQ work, and it is what turns this system from
a one-shot translator into something a person can actually use over several documents.

Matching is trigram similarity from PostgreSQL's `pg_trgm`, over a GIN index on the
normalised source. Trigrams were chosen over edit distance for two reasons: the index makes
the search sublinear in the size of the memory, and `similarity()` already returns the
0..1 figure that CAT tools display as a percentage.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import TmUnit
from app.mt.textnorm import normalise_segment


@dataclass(frozen=True, slots=True)
class Match:
    id: int
    similarity: float
    source_text: str
    target_text: str
    domain_code: str
    origin: str

    @property
    def exact(self) -> bool:
        return self.similarity >= settings.tm_exact_threshold


async def search(
    session: AsyncSession,
    text: str,
    domain: str = "general",
    limit: int | None = None,
) -> list[Match]:
    """Best memory matches for `text`, most similar first.

    Units from the requested domain are preferred over identically-scoring units from
    another one: the same English sentence can have different approved translations in a
    computer-science paper and in a literary essay, which is the whole point of keeping the
    domain on the unit.
    """
    needle = normalise_segment(text)
    if not needle:
        return []

    similarity = func.similarity(TmUnit.source_norm, needle)
    stmt = (
        select(TmUnit, similarity.label("similarity"))
        .where(similarity >= settings.tm_fuzzy_threshold)
        .order_by(
            similarity.desc(),
            (TmUnit.domain_code == domain).desc(),
            TmUnit.hits.desc(),
        )
        .limit(limit or settings.tm_max_candidates)
    )
    rows = (await session.execute(stmt)).all()
    return [
        Match(
            id=unit.id,
            similarity=round(float(score), 4),
            source_text=unit.source_text,
            target_text=unit.target_text,
            domain_code=unit.domain_code,
            origin=unit.origin,
        )
        for unit, score in rows
    ]


async def best_matches(
    session: AsyncSession, sentences: list[str], domain: str
) -> dict[int, Match]:
    """One best match per sentence, keyed by the sentence's position.

    Called once per translation, so it runs the queries concurrently rather than waiting for
    each sentence in turn - a fifty-sentence document would otherwise pay fifty round trips.
    """
    out: dict[int, Match] = {}
    for index, sentence in enumerate(sentences):
        matches = await search(session, sentence, domain, limit=1)
        if matches:
            out[index] = matches[0]
    return out


async def remember(
    session: AsyncSession,
    source_text: str,
    target_text: str,
    domain: str = "general",
    origin: str = "post-edit",
) -> TmUnit:
    """Store or replace a unit. A newer approved translation always wins."""
    normalised = normalise_segment(source_text)
    stmt = (
        insert(TmUnit)
        .values(
            source_text=source_text.strip(),
            source_norm=normalised,
            target_text=target_text.strip(),
            domain_code=domain,
            origin=origin,
        )
        .on_conflict_do_update(
            constraint="uq_tm_unit_source_domain",
            set_={
                "target_text": target_text.strip(),
                "source_text": source_text.strip(),
                "origin": origin,
                "updated_at": func.now(),
            },
        )
        .returning(TmUnit)
    )
    unit = (await session.scalars(stmt)).one()
    await session.commit()
    return unit


async def count_hit(session: AsyncSession, unit_id: int) -> None:
    """Record that a stored unit was actually reused."""
    unit = await session.get(TmUnit, unit_id)
    if unit is not None:
        unit.hits += 1
        await session.commit()


async def forget(session: AsyncSession, unit_id: int) -> bool:
    result = await session.execute(delete(TmUnit).where(TmUnit.id == unit_id))
    await session.commit()
    return bool(result.rowcount)


async def page(
    session: AsyncSession,
    query: str = "",
    domain: str = "",
    page_number: int = 1,
    per_page: int = 25,
) -> tuple[int, list[TmUnit]]:
    conditions = []
    if query:
        needle = f"%{normalise_segment(query)}%"
        conditions.append(TmUnit.source_norm.like(needle))
    if domain:
        conditions.append(TmUnit.domain_code == domain)

    total = await session.scalar(select(func.count()).select_from(TmUnit).where(*conditions))
    rows = (
        await session.scalars(
            select(TmUnit)
            .where(*conditions)
            .order_by(TmUnit.updated_at.desc())
            .offset((page_number - 1) * per_page)
            .limit(per_page)
        )
    ).all()
    return int(total or 0), list(rows)


async def stats(session: AsyncSession) -> dict:
    units = await session.scalar(select(func.count()).select_from(TmUnit)) or 0
    post_edited = (
        await session.scalar(
            select(func.count()).select_from(TmUnit).where(TmUnit.origin == "post-edit")
        )
        or 0
    )
    imported = (
        await session.scalar(
            select(func.count()).select_from(TmUnit).where(TmUnit.origin == "import")
        )
        or 0
    )
    hits = await session.scalar(select(func.coalesce(func.sum(TmUnit.hits), 0))) or 0
    by_domain = dict(
        (
            await session.execute(
                select(TmUnit.domain_code, func.count()).group_by(TmUnit.domain_code)
            )
        ).all()
    )
    return {
        "units": int(units),
        "post_edited": int(post_edited),
        "imported": int(imported),
        "total_hits": int(hits),
        "by_domain": by_domain,
    }
