"""Pydantic request and response models.

Kept separate from the domain dataclasses so the wire format can be documented and
validated independently of the internal representation. Field names are snake_case; the
frontend's Zod schemas mirror them exactly.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from irs.config import settings
from irs.db.models.enums import RankerKey


class HighlightOut(BaseModel):
    """A character range in the snippet to mark."""

    start: int
    end: int
    lemma: str


class SearchRequest(BaseModel):
    """A search, with the controls the assignment's ``Search`` class specifies."""

    query: str = Field(min_length=1, max_length=512)
    ranker: RankerKey = RankerKey.VECTOR
    limit: int = Field(default=settings.search.default_limit, ge=1, le=settings.search.max_limit)
    offset: int = Field(default=0, ge=0, le=10_000)

    #: `allWordsTogether` — require every query term to be present.
    all_words_together: bool = False
    #: `dateStartString` / `dateEndString` — inclusive publication-date bounds.
    date_from: date | None = None
    date_to: date | None = None
    source_domain: str | None = Field(default=None, max_length=255)

    @field_validator("query")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped

    @field_validator("date_to")
    @classmethod
    def _ordered(cls, value: date | None, info: Any) -> date | None:
        start = info.data.get("date_from")
        if value and start and value < start:
            raise ValueError("date_to must not precede date_from")
        return value


class SearchHitOut(BaseModel):
    """One result — the assignment's ``SearchResult``, plus presentation detail."""

    document_id: int
    title: str
    #: The active link the requirements ask each result to carry.
    url: str
    snippet: str
    #: Similarity score (`rank` in the assignment's class diagram).
    rank: float
    date: date | None
    #: The words of the query present in this document.
    matched_lemmas: list[str] = []
    highlights: list[HighlightOut] = []
    source_domain: str = ""
    token_count: int = 0
    #: Ranker-specific intermediates — the scalar product, both norms, and so on.
    detail: dict[str, float] = {}
    snippet_is_query_biased: bool = False


class SearchResponseOut(BaseModel):
    query: str
    ranker: RankerKey
    hits: list[SearchHitOut]
    total_candidates: int
    #: The query's search image, so the user can see what was actually searched for.
    query_lemmas: list[str] = []
    #: Query words that appear nowhere in the collection.
    unknown_lemmas: list[str] = []
    filters_applied: bool = False
    duration_ms: float = 0.0
    stage_timings_ms: dict[str, float] = {}
    document_count: int = 0
    term_count: int = 0
    index_version: int = 0


class RankerOut(BaseModel):
    key: RankerKey
    label: str
    description: str
    is_required_model: bool = False
    available: bool = True
    unavailable_reason: str | None = None


# ------------------------------------------------------------------ explanation ----


class TermWeightOut(BaseModel):
    """One query term's full weight derivation."""

    lemma: str
    #: `N_dk` — occurrences in this document.
    term_frequency: int
    #: `N_k` — documents containing the term.
    document_frequency: int
    #: `N` — collection size.
    document_count: int
    #: `B_k = log(N / N_k)` (formula 1.5).
    inverse_frequency: float
    #: `A_k = N_dk · B_k` (formula 1.6).
    weight_raw: float
    #: `w_dk` — the normalized weight.
    weight_norm: float
    in_query: bool = False


class ScoreStepOut(BaseModel):
    """One addend of the scalar product, with the running total."""

    lemma: str
    document_weight: float
    query_weight: float
    product: float
    running_sum: float
    share: float


class ScoreExplanationOut(BaseModel):
    """The complete arithmetic behind one score, reproducible by hand."""

    document_id: int
    title: str
    url: str

    document_count: int
    term_count: int
    log_base: str

    query_terms: list[TermWeightOut] = []
    missing_terms: list[str] = []
    unknown_terms: list[str] = []

    steps: list[ScoreStepOut] = []
    scalar_product: float = 0.0
    document_norm: float = 0.0
    query_norm: float = 0.0
    score: float = 0.0

    normalization_denominator: float = 0.0
    stored_document_norm: float = 0.0
    #: False when the recomputation disagrees with the stored weights — a stale index.
    consistent_with_index: bool = True

    document_keywords: list[tuple[str, float]] = []
    distinct_term_count: int = 0
    token_count: int = 0


# ---------------------------------------------------------------------- corpus ----


class DocumentSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    title: str
    source_domain: str
    published_at: date | None = None
    fetched_at: datetime | None = None
    language: str | None = None
    token_count: int = 0
    distinct_term_count: int = 0
    vector_norm: float = 0.0
    has_embedding: bool = False


class KeywordOut(BaseModel):
    """A document keyword, weighted by formula 1.6."""

    lemma: str
    #: `N_dk`.
    term_frequency: int
    #: `N_k`.
    document_frequency: int
    #: `B_i`.
    inverse_frequency: float
    #: `A_i^j = Q_i^j · B_i` — the weight the assignment specifies for keywords.
    weight_raw: float
    #: `w_dk` — the ranking weight, shown alongside for contrast.
    weight_norm: float


class DocumentDetailOut(DocumentSummaryOut):
    text: str
    description: str | None = None
    author: str | None = None
    http_status: int | None = None
    byte_size: int | None = None
    #: Automatically extracted keywords, per formula 1.6.
    keywords: list[KeywordOut] = []


class CollectionStatsOut(BaseModel):
    """Collection-wide constants — the vector model's `N` and `D`."""

    document_count: int
    term_count: int
    posting_count: int
    average_document_length: float
    index_version: int
    log_base: str
    built_at: datetime | None = None
    build_duration_ms: float | None = None
    embedded_document_count: int = 0
    #: True when live counts differ from the indexed ones, i.e. a rebuild is due.
    is_stale: bool = False
