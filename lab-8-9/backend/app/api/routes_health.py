from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from app.config import settings
from app.state import state

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response) -> dict[str, Any]:
    s = state.status
    body: dict[str, Any] = {
        "status": "ready" if s.tts == "ready" else s.tts,
        "tts": s.tts,
        "asr_local": s.asr_local,
        "groq": "configured" if settings.has_groq else "missing",
        **s.detail,
    }
    if s.tts != "ready":
        response.status_code = 503
    return body
