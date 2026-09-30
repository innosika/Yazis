"""Translation endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_session
from app.mt.domains import DOMAINS
from app.schemas.translate import SampleOut, TranslateRequest, TranslateResponse
from app.services import translate as translate_service

router = APIRouter(prefix="/translate", tags=["translation"])
log = logging.getLogger(__name__)

# Which subject area each bundled sample belongs to, so picking one also picks the domain.
SAMPLE_DOMAINS = {
    "cs-neural-machine-translation": ("cs", "Computer science: neural machine translation"),
    "literature-essay-on-narration": ("lit", "Literary essay: the unreliable narrator"),
    "mixed-short-demo": ("cs", "Short demo: four sentences, both subject areas"),
}


@router.post("", response_model=TranslateResponse, summary="Translate English text to Russian")
async def translate(
    request: TranslateRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    if request.domain not in DOMAINS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown subject area '{request.domain}'; expected one of {sorted(DOMAINS)}",
        )
    _, payload = await translate_service.translate(
        session,
        text=request.text,
        domain=request.domain,
        mode=request.mode,
        include_direct=request.include_direct,
        use_memory=request.use_memory,
        save=request.save,
        title=request.title,
    )
    return payload


@router.get("/samples", response_model=list[SampleOut], summary="Bundled sample texts")
async def samples() -> list[dict]:
    out: list[dict] = []
    directory = settings.samples_dir
    if not directory.exists():
        return out
    for path in sorted(directory.glob("*.txt")):
        domain, title = SAMPLE_DOMAINS.get(path.stem, ("general", path.stem))
        text = path.read_text(encoding="utf-8")
        out.append(
            {
                "name": path.stem,
                "title": title,
                "domain": domain,
                "characters": len(text),
                "text": text,
            }
        )
    return out
