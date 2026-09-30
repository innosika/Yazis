"""Operational records: search log and relevance-feedback sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from irs.db.base import Base, TimestampMixin
from irs.db.models.enums import RankerKey


class SearchLog(Base):
    """One executed search.

    Recorded so the report's testing section can quote measured latency distributions
    over real queries instead of a single hand-timed example, and so the Help page can
    show which queries the collection actually answers well.
    """

    __tablename__ = "search_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(index=True)

    query_text: Mapped[str] = mapped_column(String(512), nullable=False)
    #: The query's search image — the lemmas it reduced to. Kept because the gap between
    #: what a user typed and what was searched is the single most useful debugging clue.
    query_lemmas: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))
    ranker: Mapped[RankerKey] = mapped_column(String(16), nullable=False, index=True)

    all_words_together: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date_from: Mapped[datetime | None] = mapped_column()
    date_to: Mapped[datetime | None] = mapped_column()

    #: Documents pulled from the inverted index before scoring, versus returned. The
    #: ratio is what makes the candidate-generation cost visible.
    candidates_considered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_score: Mapped[float | None] = mapped_column(Float)

    #: Per-stage breakdown in milliseconds: parse, lemmatise, candidates, score, snippet.
    stage_timings_ms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_search_log_ranker_created", "ranker", "created_at"),)


class FeedbackSession(Base, TimestampMixin):
    """A Rocchio relevance-feedback conversation.

    The assignment's theory section names «процедуры поиска и коррекции запросов» —
    query-correction procedures — without implementing them. Each round is appended to
    :attr:`iterations` so the Relevance Lab can replay the query vector's trajectory
    through the term space rather than only showing its final position.
    """

    __tablename__ = "feedback_session"

    id: Mapped[int] = mapped_column(primary_key=True)

    original_query: Mapped[str] = mapped_column(String(512), nullable=False)
    ranker: Mapped[RankerKey] = mapped_column(String(16), nullable=False, default=RankerKey.VECTOR)
    query_id: Mapped[int | None] = mapped_column(ForeignKey("query.id", ondelete="SET NULL"))

    alpha: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    beta: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    gamma: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)

    iteration_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    #: One entry per round: marked ids, the resulting sparse query vector, its 3D
    #: projection, the expansion terms added, and the ranking that followed.
    iterations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<FeedbackSession {self.id} n={self.iteration_count}>"
