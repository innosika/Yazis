"""Database schema.

The dictionary is a three-level structure - entry -> sense -> translation - because
that is the shape the assignment's «словарь» actually has: one English headword can
belong to several parts of speech, each part of speech carries several senses, and each
sense offers several Russian equivalents. Flattening it would make word-sense
disambiguation impossible and would lose the grammatical information the report needs.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DictEntry(Base):
    """One English headword with one part of speech."""

    __tablename__ = "dict_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    headword: Mapped[str] = mapped_column(String(200))
    # Case-folded, stripped of the apostrophes and stress marks the source uses, so
    # lookup by a spaCy lemma is a plain equality test.
    headword_norm: Mapped[str] = mapped_column(String(200), index=True)
    # FreeDict's own tag: n, v, adj, adv, pn, preposition, ... Mapped to Universal POS
    # in app.mt.lexicon rather than at load time, so re-tagging never needs a re-seed.
    pos: Mapped[str | None] = mapped_column(String(32))
    ipa: Mapped[str | None] = mapped_column(String(200))
    # Number of whitespace-separated words: 1 for ordinary words, >1 for multiword
    # units such as "machine learning", which are matched longest-first.
    word_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source: Mapped[str] = mapped_column(String(32), default="freedict")
    is_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    senses: Mapped[list["DictSense"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="DictSense.idx",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("headword_norm", "pos", name="uq_dict_entry_headword_pos"),
        Index("ix_dict_entry_lookup", "headword_norm", "pos"),
        Index("ix_dict_entry_words", "word_count"),
    )


class DictSense(Base):
    """One meaning of an entry: an English gloss plus its Russian equivalents."""

    __tablename__ = "dict_sense"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("dict_entry.id", ondelete="CASCADE"), index=True
    )
    # Dictionary order. Doubles as the frequency prior in the disambiguator: lexicographers
    # list the most common sense first, so idx 0 gets the highest prior.
    idx: Mapped[int] = mapped_column(Integer)
    gloss: Mapped[str] = mapped_column(Text, default="")
    # Topical and register labels parsed out of the gloss's leading parenthesis:
    # ("computing", "Internet") for a computer-science sense, ("archaic",) for a dead one.
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Precomputed per-domain affinity, {"cs": 0.9, "lit": 0.0}, filled at seed time so the
    # hot path never re-scores static data.
    domain_scores: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)

    entry: Mapped[DictEntry] = relationship(back_populates="senses")
    translations: Mapped[list["DictTranslation"]] = relationship(
        back_populates="sense",
        cascade="all, delete-orphan",
        order_by="DictTranslation.idx",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("entry_id", "idx", name="uq_dict_sense_entry_idx"),
        Index("ix_dict_sense_labels", "labels", postgresql_using="gin"),
    )


class DictTranslation(Base):
    """One Russian equivalent of a sense."""

    __tablename__ = "dict_translation"

    id: Mapped[int] = mapped_column(primary_key=True)
    sense_id: Mapped[int] = mapped_column(
        ForeignKey("dict_sense.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)
    # The source marks stress ("се́ть"). Kept for display; pymorphy3 is fed form_plain,
    # because a combining acute makes every dictionary lookup miss.
    form_accented: Mapped[str] = mapped_column(String(200))
    form_plain: Mapped[str] = mapped_column(String(200))
    is_user: Mapped[bool] = mapped_column(Boolean, default=False)

    sense: Mapped[DictSense] = relationship(back_populates="translations")

    __table_args__ = (UniqueConstraint("sense_id", "idx", name="uq_dict_translation_sense_idx"),)


class SenseOverride(Base):
    """A sense the user locked for a domain. Beats every disambiguation signal."""

    __tablename__ = "sense_override"

    id: Mapped[int] = mapped_column(primary_key=True)
    headword_norm: Mapped[str] = mapped_column(String(200))
    pos: Mapped[str] = mapped_column(String(16))
    domain_code: Mapped[str] = mapped_column(String(16))
    sense_id: Mapped[int] = mapped_column(ForeignKey("dict_sense.id", ondelete="CASCADE"))
    # Which translation of that sense to prefer; NULL means "the sense's first".
    translation_id: Mapped[int | None] = mapped_column(
        ForeignKey("dict_translation.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "headword_norm", "pos", "domain_code", name="uq_sense_override_word_pos_domain"
        ),
    )


class TmUnit(Base):
    """A translation-memory unit: one source sentence and its approved translation."""

    __tablename__ = "tm_unit"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_text: Mapped[str] = mapped_column(Text)
    # Case-folded, punctuation-stripped, whitespace-collapsed. Trigram-indexed, and the
    # only column the fuzzy matcher compares against.
    source_norm: Mapped[str] = mapped_column(Text)
    target_text: Mapped[str] = mapped_column(Text)
    domain_code: Mapped[str] = mapped_column(String(16), default="general")
    # "post-edit" when a human corrected it, "import" when it came from a TMX-style file.
    origin: Mapped[str] = mapped_column(String(16), default="post-edit")
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source_norm", "domain_code", name="uq_tm_unit_source_domain"),
        Index(
            "ix_tm_unit_source_norm_trgm",
            "source_norm",
            postgresql_using="gin",
            postgresql_ops={"source_norm": "gin_trgm_ops"},
        ),
    )


class OovTerm(Base):
    """A word the dictionary could not translate, queued for replenishment."""

    __tablename__ = "oov_term"

    id: Mapped[int] = mapped_column(primary_key=True)
    lemma: Mapped[str] = mapped_column(String(200))
    pos: Mapped[str] = mapped_column(String(16))
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    # pending -> the queue; accepted -> an entry was created; dismissed -> user said no.
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # The automatic proposal: {"source": "wiktionary", "confidence": 0.8, "forms": [...]}
    suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("lemma", "pos", name="uq_oov_term_lemma_pos"),
        Index("ix_oov_term_rank", "status", "occurrences"),
    )


class Document(Base):
    """A translation run, kept so results can be reopened, exported and printed."""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    source_text: Mapped[str] = mapped_column(Text)
    domain_code: Mapped[str] = mapped_column(String(16), default="general")
    mode: Mapped[str] = mapped_column(String(16), default="transfer")
    # {"words": 412, "translated": 389, "coverage": 0.944, ...}
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_document_created", "created_at"),)
