from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.settings import ReadingSettings


class VoiceSpec(BaseModel):
    id: str = "af_heart"
    blend: str | None = None
    mix: float = Field(0.3, ge=0.0, le=1.0)


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    kind: Literal["text", "heading"] = "text"
    voice: VoiceSpec = VoiceSpec()
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-4.0, le=4.0)
    options: ReadingSettings = ReadingSettings()
    priority: Literal["now", "prefetch", "background"] = "now"


class Word(BaseModel):
    text: str
    start: float
    end: float
    src_start: int
    src_end: int


class SynthesizeResponse(BaseModel):
    id: str
    audio_url: str
    duration: float
    spoken: str
    words: list[Word]
    cached: bool
    compute_ms: float


class NormalizeRequest(BaseModel):
    texts: list[str] = Field(..., max_length=500)
    kind: Literal["text", "heading"] = "text"
    options: ReadingSettings = ReadingSettings()


class NormalizeResponse(BaseModel):
    spoken: list[str]


class SegmentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200_000)


class Unit(BaseModel):
    start: int
    end: int
    paragraph: int


class SegmentResponse(BaseModel):
    units: list[Unit]


class VoiceInfo(BaseModel):
    id: str
    name: str
    accent: str
    gender: str
    grade: str
    featured: bool
