from __future__ import annotations

from pydantic import BaseModel, Field


class DetectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200_000, description="Текст или HTML для распознавания")
    is_html: bool = Field(False, description="Если true — текст трактуется как HTML и очищается от тегов")
