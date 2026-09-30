"""Liveness and readiness.

`/live` answers as soon as the process is up. `/ready` answers only once spaCy and
pymorphy3 are loaded and the dictionary has rows - which is what Compose waits on, so
nothing downstream ever talks to a half-built system.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import state
from app.db.base import get_session
from app.db.models import DictEntry

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Process is running")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/ready", summary="Resources loaded and dictionary populated")
async def ready(
    response: Response, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    entries = await session.scalar(select(func.count()).select_from(DictEntry)) or 0
    resources_loaded = state.is_ready()
    ok = resources_loaded and entries > 0
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ok else "starting",
        "resources_loaded": resources_loaded,
        "dictionary_entries": entries,
    }
