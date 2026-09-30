from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.asr.base import ASRError
from app.state import state

router = APIRouter(prefix="/voice", tags=["speech recognition"])
MAX_AUDIO = 10 * 1024 * 1024


@router.get("/status")
def status() -> dict[str, Any]:
    asr = state.asr.status() if state.asr else {}
    return {**asr, "local_status": state.status.asr_local, "llm": state.llm is not None}


@router.post("/recognize")
async def recognize(
    audio: UploadFile = File(...),
    language: Literal["en", "ru", "de", "fr"] = Form("en"),
    mode: Literal["command", "dictation"] = Form("command"),
    engine: Literal["auto", "cloud", "local"] = Form("auto"),
    playing: bool = Form(False),
    played_text: str = Form(""),
    document_id: str | None = Form(None),
    llm_fallback: bool = Form(True),
) -> dict[str, Any]:
    data = await audio.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "Utterance too long")
    if len(data) < 1000:
        raise HTTPException(422, "The recording is empty")
    try:
        return await state.commands.recognize(  # type: ignore[no-any-return]
            data,
            lang=language,
            mode=mode,
            engine=engine,
            playing=playing,
            played_text=played_text[:4000],
            document_id=document_id or None,
            allow_llm=llm_fallback,
        )
    except ASRError as exc:
        raise HTTPException(503, str(exc)) from exc
