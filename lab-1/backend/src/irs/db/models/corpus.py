"""The document collection, the dictionary and the inverted index.

This is the storage behind the assignment's vector model. The design principle that
governs every column here: **store the raw counts, derive the weights.** The assignment
needs two different weightings of the same term-document pair — the unnormalized
`A_i^j = Q_i^j · B_i` of formula 1.6 for keyword extraction, and the L2-normalized
`w_dk` for the search vectors — so the raw `N_dk` and `N_k` are the source of truth and
both weights are recomputed from them whenever `N` changes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from irs.config import settings
from irs.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from irs.db.models.evaluation import Judgment, Qrel


class Document(Base, TimestampMixin):
    """One retrievable document.

    Mirrors the assignment's ``Document`` class (title, text, date, time, documentID)
    and adds what a real web crawl requires: provenance, deduplication fingerprints and
    the cached vector norm.
    """

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Canonical absolute URL. This is the "active link" the results list must expose.
    url: Mapped[str] = mapped_column(String(2_048), unique=True, nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(1_024), nullable=False, default="")
    #: Boilerplate-free main text, as extracted by trafilatura.
    text: Mapped[str] = mapped_column(Text, nullable=False)

    #: The document's own publication date, when the page declares one. The assignment's
    #: ``SearchResult.date`` and the ``dateStart``/``dateEnd`` search filters read this,
    #: falling back to ``fetched_at`` when a page carries no date.
    published_at: Mapped[date | None] = mapped_column(Date, index=True)
    fetched_at: Mapped[datetime | None] = mapped_column(index=True)

    language: Mapped[str | None] = mapped_column(String(8), index=True)
    author: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    #: Length in index terms — the `|d|` that BM25's length normalisation needs.
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Distinct index terms, i.e. the number of non-zero components of this document's
    #: vector. Reported in the corpus browser as the vector's sparsity.
    distinct_term_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Exact-duplicate detection: SHA-256 of the normalised extracted text.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Near-duplicate detection: 64-bit SimHash. Two documents within a small Hamming
    #: distance are the same page under a different URL, which a web crawl produces
    #: constantly (print views, tracking parameters, mirrors).
    simhash: Mapped[int | None] = mapped_column(BigInteger, index=True)

    #: Euclidean norm ‖D‖ of the normalized weight vector. Cached because the cosine
    #: denominator needs it on every scored candidate.
    #:
    #: Note this is ~1.0 by construction: `w_dk` is already L2-normalized over the
    #: document's terms, so ‖D‖ = 1 whenever the document has at least one term with
    #: non-zero IDF. It is stored anyway because the assignment's ``EuclideanNorm``
    #: method is part of the specified design, and because a stored value that drifts
    #: from 1.0 is an immediate signal that the index is stale.
    vector_norm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    #: Dense embedding for the semantic ranker. Null when embeddings are disabled or
    #: the document has not been encoded yet.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.semantic.dimensions))

    #: PostgreSQL's own full-text vector, maintained by the database. Used only by the
    #: `fts` baseline ranker — the assignment's vector model deliberately does not
    #: depend on it, so that the TF-IDF implementation is demonstrably our own.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(text, ''))",
            persisted=True,
        ),
    )

    postings: Mapped[list[Posting]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    projection: Mapped[LsaProjection | None] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    judgments: Mapped[list[Judgment]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    qrels: Mapped[list[Qrel]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # GIN over the database's own text vector — used only by the `fts` baseline.
        Index("ix_document_tsv", "tsv", postgresql_using="gin"),
        # Approximate nearest-neighbour index for the semantic ranker. `vector_cosine_ops`
        # matches the cosine distance the ranker orders by; an L2 index would answer a
        # different question. HNSW rather than IVFFlat because it needs no training pass
        # and stays accurate on a collection that grows as the crawler runs.
        Index(
            "ix_document_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.url[:60]!r}>"


class Term(Base):
    """A dictionary entry — one lemma.

    The dictionary is the assignment's ordered term set of cardinality ``D``; a
    document vector has one component per row here.
    """

    __tablename__ = "term"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Lemma, lowercased. Lemmatised rather than stemmed so that the "keywords of this
    #: document" view shows real words.
    lemma: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: Coarse part of speech from spaCy, kept for the corpus browser's facets and to
    #: document which classes of word were retained as index terms.
    pos: Mapped[str | None] = mapped_column(String(16), index=True)

    #: `P_i` / `N_k` — the number of documents containing this term. Formula 1.5's
    #: denominator.
    document_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Total occurrences across the whole collection. Not used by the vector model;
    #: kept for the vocabulary statistics in the report (Zipf plot, coverage).
    collection_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: `B_i = log(N / P_i)` — formula 1.5, cached at index-build time. Recomputed
    #: whenever `N` changes, since every value depends on the collection size.
    idf: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    postings: Mapped[list[Posting]] = relationship(
        back_populates="term", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("document_frequency >= 0", name="df_non_negative"),
        Index("ix_term_document_frequency", "document_frequency"),
    )

    def __repr__(self) -> str:
        return f"<Term {self.lemma!r} df={self.document_frequency}>"


class Posting(Base):
    """One non-zero cell of the term-document matrix `L` (the assignment's matrix 1.7).

    The primary key is ``(term_id, document_id)`` in that order, so a lookup by term —
    the inverted-index scan that drives retrieval — is a primary-key range scan.
    """

    __tablename__ = "posting"

    term_id: Mapped[int] = mapped_column(
        ForeignKey("term.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), primary_key=True
    )

    #: `N_dk` / `Q_i^j` — the raw occurrence count. The source of truth: both weights
    #: below are derived from this and never edited independently.
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)

    #: `A_i^j = Q_i^j · B_i` — formula 1.6, unnormalized. This is the weight the
    #: assignment specifies for *automatic keyword extraction*, and it is deliberately
    #: kept separate from the ranking weight below.
    weight_raw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    #: `w_dk` — the L2-normalized TF-IDF used for the *search* vectors:
    #:     w_dk = N_dk·log(N/N_k) / sqrt( Σ_j (N_dj·log(N/N_j))² )
    weight_norm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    #: Token offsets of every occurrence. Powers query-biased snippet selection and
    #: proximity-aware ranking; costs roughly one integer per occurrence.
    positions: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    term: Mapped[Term] = relationship(back_populates="postings")
    document: Mapped[Document] = relationship(back_populates="postings")

    __table_args__ = (
        # Reverse lookup: "every term of this document", needed to build a document
        # vector for Rocchio feedback and for the keyword view.
        Index("ix_posting_document_id", "document_id"),
        # Partial index over the terms that actually carry information, so candidate
        # generation skips postings whose IDF is zero.
        Index(
            "ix_posting_term_weight",
            "term_id",
            "weight_norm",
            postgresql_where=("weight_norm > 0"),
        ),
        CheckConstraint("term_frequency > 0", name="tf_positive"),
    )

    def __repr__(self) -> str:
        return f"<Posting t={self.term_id} d={self.document_id} tf={self.term_frequency}>"


class CollectionStat(Base):
    """Single-row table holding the collection-wide constants.

    `N` lives here rather than being counted on demand, because every IDF depends on it
    and a mid-query change would make one result set internally inconsistent.
    """

    __tablename__ = "collection_stat"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Every counter carries a *server* default, not just a Python one. The row is
    # seeded by a raw SQL statement in the initial migration and updated by targeted
    # UPDATEs during an index rebuild, neither of which passes through the ORM — so the
    # defaults have to live in the database for a partial insert to succeed.

    #: `N` — documents in the collection.
    document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: `D` — cardinality of the dictionary.
    term_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    posting_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    #: Mean document length in index terms — BM25's `avgdl`.
    average_document_length: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )

    #: Bumped on every index rebuild. Stamped onto evaluation runs so a stored metric can
    #: always be traced to the index that produced it.
    index_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: The logarithm base actually used for this build, recorded for reproducibility.
    log_base: Mapped[str] = mapped_column(
        String(4), nullable=False, default="e", server_default="e"
    )
    built_at: Mapped[datetime | None] = mapped_column()
    build_duration_ms: Mapped[float | None] = mapped_column(Float)
    embedded_document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (CheckConstraint("id = 1", name="collection_stat_is_singleton"),)

    def __repr__(self) -> str:
        return f"<CollectionStat N={self.document_count} D={self.term_count}>"


class LsaProjection(Base):
    """Cached 3D coordinates of a document in latent-semantic space.

    Produced by a truncated SVD of the TF-IDF matrix and consumed by the Relevance Lab's
    vector-space view. Cached because the decomposition is collection-wide work that
    must not run per request.
    """

    __tablename__ = "lsa_projection"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), primary_key=True
    )
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)

    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    z: Mapped[float] = mapped_column(Float, nullable=False)

    document: Mapped[Document] = relationship(back_populates="projection")

    __table_args__ = (Index("ix_lsa_projection_index_version", "index_version"),)


class LsaModel(Base):
    """The SVD basis itself, so a query vector can be projected into the same space.

    Without the stored right singular vectors a query could only be placed by
    re-running the decomposition, which would move every document as well.
    """

    __tablename__ = "lsa_model"

    index_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    components: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Term ids forming the reduced vocabulary the decomposition was run over.
    term_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    #: Row-major `components × len(term_ids)` matrix Vᵀ.
    basis: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    singular_values: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    #: Share of total variance retained — quoted in the Relevance Lab so the viewer
    #: knows how much of the true geometry the 3D picture actually shows.
    explained_variance_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    built_at: Mapped[datetime | None] = mapped_column()

    # `index_version` is the primary key, so it is already unique — no further
    # constraint is needed. There is at most one basis per index build by construction.
