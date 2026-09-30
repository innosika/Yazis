"""Translation-memory endpoints. (Additional feature 1.)"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import TmUnit
from app.schemas.memory import (
    ImportRequest,
    MatchOut,
    MatchRequest,
    MemoryStats,
    UnitIn,
    UnitOut,
    UnitPage,
)
from app.services import tm

router = APIRouter(prefix="/memory", tags=["translation memory"])


def _unit_out(unit: TmUnit) -> dict:
    return {
        "id": unit.id,
        "source_text": unit.source_text,
        "target_text": unit.target_text,
        "domain_code": unit.domain_code,
        "origin": unit.origin,
        "hits": unit.hits,
        "created_at": unit.created_at.isoformat() if unit.created_at else "",
        "updated_at": unit.updated_at.isoformat() if unit.updated_at else "",
    }


@router.get("/units", response_model=UnitPage, summary="Browse the memory")
async def units(
    q: str = "",
    domain: str = "",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    total, rows = await tm.page(session, q, domain, page, per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_unit_out(row) for row in rows],
    }


@router.post(
    "/units",
    response_model=UnitOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save a post-edited sentence",
)
async def save_unit(payload: UnitIn, session: AsyncSession = Depends(get_session)) -> dict:
    unit = await tm.remember(
        session,
        source_text=payload.source_text,
        target_text=payload.target_text,
        domain=payload.domain_code,
        origin=payload.origin,
    )
    return _unit_out(unit)


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a unit")
async def delete_unit(unit_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await tm.forget(session, unit_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory unit not found")


@router.post("/search", response_model=list[MatchOut], summary="Fuzzy-match a sentence")
async def search(payload: MatchRequest, session: AsyncSession = Depends(get_session)) -> list[dict]:
    matches = await tm.search(session, payload.text, payload.domain, payload.limit)
    return [
        {
            "id": match.id,
            "similarity": match.similarity,
            "source_text": match.source_text,
            "target_text": match.target_text,
            "domain_code": match.domain_code,
            "origin": match.origin,
            "exact": match.exact,
        }
        for match in matches
    ]


@router.get("/stats", response_model=MemoryStats, summary="Memory size and reuse")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    return await tm.stats(session)


@router.get("/export", response_model=list[UnitOut], summary="Export the whole memory")
async def export_memory(session: AsyncSession = Depends(get_session)) -> list[dict]:
    _, rows = await tm.page(session, page_number=1, per_page=100)
    total, _ = await tm.page(session, page_number=1, per_page=1)
    if total > 100:
        collected: list[TmUnit] = []
        page_number = 1
        while len(collected) < total:
            _, batch = await tm.page(session, page_number=page_number, per_page=100)
            if not batch:
                break
            collected.extend(batch)
            page_number += 1
        rows = collected
    return [_unit_out(row) for row in rows]


@router.post("/import", response_model=MemoryStats, summary="Import memory units")
async def import_memory(
    payload: ImportRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    for unit in payload.units:
        await tm.remember(
            session,
            source_text=unit.source_text,
            target_text=unit.target_text,
            domain=unit.domain_code,
            origin="import",
        )
    return await tm.stats(session)
