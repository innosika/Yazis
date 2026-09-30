from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.tts import (
    NormalizeRequest,
    NormalizeResponse,
    SegmentRequest,
    SegmentResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    Unit,
    VoiceInfo,
)
from app.state import state
from app.text.normalize import Context, normalize
from app.text.segment import split_sentences, split_units
from app.tts.voices import ALL_VOICES

router = APIRouter(prefix="/tts", tags=["speech synthesis"])


def _require_ready() -> None:
    if state.status.tts != "ready":
        raise HTTPException(503, "The voice is still loading. Try again in a few seconds.")


@router.get("/voices", response_model=list[VoiceInfo])
def voices() -> list[VoiceInfo]:
    return [
        VoiceInfo(
            id=v.id,
            name=v.name,
            accent=v.accent,
            gender=v.gender,
            grade=v.grade,
            featured=v.featured,
        )
        for v in ALL_VOICES
    ]


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(req: SynthesizeRequest) -> SynthesizeResponse:
    _require_ready()
    try:
        return await state.tts.synthesize(req)  # type: ignore[no-any-return]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/audio/{key}.wav")
def audio(key: str) -> FileResponse:
    if not key.isalnum():
        raise HTTPException(404)
    path = state.tts.cache.wav_path(key)
    if path is None:
        raise HTTPException(404, "audio expired from the cache; synthesize again")
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/normalize", response_model=NormalizeResponse)
def spoken_form(req: NormalizeRequest) -> NormalizeResponse:
    o = req.options
    ctx = Context(
        citations=o.citations,
        urls=o.urls,
        math=o.math,
        acronyms=o.acronyms,
        heading=req.kind == "heading" and o.announce_headings,
        lexicon=state.tts.lexicon if state.tts else {},
    )
    return NormalizeResponse(spoken=[normalize(t, ctx).text for t in req.texts])


@router.post("/segment", response_model=SegmentResponse)
def segment(req: SegmentRequest) -> SegmentResponse:
    """Cut free text into playback units (used by the browser extension)."""
    units: list[Unit] = []
    text = req.text
    for p_index, para in enumerate(_paragraphs(text)):
        a, b = para
        for s in split_sentences(text[a:b]):
            for u in split_units(text, (a + s[0], a + s[1])):
                units.append(Unit(start=u[0], end=u[1], paragraph=p_index))
    return SegmentResponse(units=units)


def _paragraphs(text: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    for m in re.finditer(r"\n\s*\n", text):
        if text[start : m.start()].strip():
            spans.append((start, m.start()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans
