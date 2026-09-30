"""Request and response models of the translation memory."""

from pydantic import BaseModel, Field


class UnitOut(BaseModel):
    id: int
    source_text: str
    target_text: str
    domain_code: str
    origin: str
    hits: int
    created_at: str
    updated_at: str


class UnitPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[UnitOut]


class UnitIn(BaseModel):
    source_text: str = Field(min_length=1)
    target_text: str = Field(min_length=1)
    domain_code: str = "general"
    origin: str = "post-edit"


class MatchRequest(BaseModel):
    text: str = Field(min_length=1)
    domain: str = "general"
    limit: int = Field(default=5, ge=1, le=20)


class MatchOut(BaseModel):
    id: int
    similarity: float
    source_text: str
    target_text: str
    domain_code: str
    origin: str
    exact: bool


class MemoryStats(BaseModel):
    units: int
    post_edited: int
    imported: int
    total_hits: int
    by_domain: dict[str, int]


class ImportRequest(BaseModel):
    units: list[UnitIn] = Field(min_length=1, max_length=5000)
