"""Sparse query vectors, Rocchio feedback and real-valued query scoring.

The mandated vector model can score with a plain ``SUM(weight_norm)`` because its query
vector is *binary* — every query term weighs 1 (see :mod:`irs.selection.vector`). Three
things in this system need a query whose weights are arbitrary reals instead:

* the ``vector_idf`` ranker (query terms weighted by their inverse frequency `B_i`),
* the ``vector_prf`` ranker (pseudo-relevance feedback expands the query),
* the Relevance Lab's interactive Rocchio loop (the user marks results and the query
  moves: «процедуры поиска и коррекции запросов» from the assignment's theory section).

This module is the kernel they share: a sparse vector type keyed by ``term_id``, the
Rocchio update itself, and one SQL scorer that joins the query weights in as a ``VALUES``
relation so the cosine is still computed by the database over the inverted index.

Rocchio (1971):

    q' = α·q + (β / |D_r|) · Σ_{d ∈ D_r} d − (γ / |D_nr|) · Σ_{d ∈ D_nr} d

Document vectors are the stored, L2-normalised `w_dk` weights, so the feedback centroid
is a direction in the same term space the documents live in. Negative coordinates are
clipped and the vector is truncated to its heaviest terms, both of which are standard
practice and keep the expanded query small enough to score cheaply.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Float, Integer, and_, case, column, func, select, values
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from irs.db.models import Document, Posting, Term
from irs.logging import get_logger
from irs.selection.base import ParsedQuery, RankedPage, ScoredDocument, SearchFilters
from irs.selection.filters import apply_document_filters

log = get_logger("irs.selection.rocchio")

#: A vector in term space: ``term_id → weight``. Absent keys are zero.
SparseVector = dict[int, float]


# ------------------------------------------------------------------ vectors ----


def binary_query_vector(query: ParsedQuery) -> SparseVector:
    """The assignment's `w_qj = 1` query image, keyed by term id."""
    return dict.fromkeys(query.term_ids.values(), 1.0)


def idf_query_vector(query: ParsedQuery) -> SparseVector:
    """Query terms weighted by `B_i = log(N / P_i)` (formula 1.5).

    A term present in every document has `B_i = 0` and drops out — it would contribute
    nothing to any score anyway, since every `w_dk` for it is zero too.
    """
    weights = {
        query.term_ids[lemma]: idf
        for lemma, idf in query.inverse_frequencies.items()
        if lemma in query.term_ids and idf > 0
    }
    return weights


async def load_document_vectors(
    session: AsyncSession, document_ids: Sequence[int]
) -> dict[int, SparseVector]:
    """The stored normalised vectors of the given documents, as sparse dicts."""
    if not document_ids:
        return {}
    rows = (
        await session.execute(
            select(Posting.document_id, Posting.term_id, Posting.weight_norm).where(
                Posting.document_id.in_(list(document_ids))
            )
        )
    ).all()
    vectors: dict[int, SparseVector] = {document_id: {} for document_id in document_ids}
    for document_id, term_id, weight in rows:
        vectors[document_id][term_id] = float(weight)
    return vectors


def norm(vector: Mapping[int, float]) -> float:
    return math.sqrt(sum(weight * weight for weight in vector.values()))


def rocchio(
    query: Mapping[int, float],
    relevant: Sequence[Mapping[int, float]],
    non_relevant: Sequence[Mapping[int, float]],
    alpha: float,
    beta: float,
    gamma: float,
) -> SparseVector:
    """One Rocchio update. Pure; keeps negative coordinates (see :func:`truncate`)."""
    result: SparseVector = {term: alpha * weight for term, weight in query.items()}

    if relevant and beta:
        scale = beta / len(relevant)
        for vector in relevant:
            for term, weight in vector.items():
                result[term] = result.get(term, 0.0) + scale * weight

    if non_relevant and gamma:
        scale = gamma / len(non_relevant)
        for vector in non_relevant:
            for term, weight in vector.items():
                result[term] = result.get(term, 0.0) - scale * weight

    return result


def truncate(
    vector: Mapping[int, float], max_terms: int, drop_negative: bool = True
) -> SparseVector:
    """Keep the ``max_terms`` heaviest coordinates; ties broken by ascending term id.

    Negative weights are dropped by default: a negative query coordinate would *reward*
    documents for lacking a term, which the cosine over non-negative document vectors
    cannot express sensibly, and the standard Rocchio implementations clip them.
    """
    items = [
        (term, weight)
        for term, weight in vector.items()
        if weight != 0.0 and (weight > 0.0 or not drop_negative)
    ]
    items.sort(key=lambda item: (-abs(item[1]), item[0]))
    return dict(items[: max(max_terms, 0)])


@dataclass(slots=True)
class ExpansionSummary:
    """What a feedback round did to the query, for display."""

    added: list[tuple[int, float]] = field(default_factory=list)
    changed: list[tuple[int, float, float]] = field(default_factory=list)
    dropped: list[int] = field(default_factory=list)


def diff(before: Mapping[int, float], after: Mapping[int, float]) -> ExpansionSummary:
    summary = ExpansionSummary()
    for term, weight in sorted(after.items(), key=lambda item: (-item[1], item[0])):
        if term not in before:
            summary.added.append((term, weight))
        elif not math.isclose(before[term], weight, rel_tol=1e-12, abs_tol=1e-12):
            summary.changed.append((term, before[term], weight))
    summary.dropped = sorted(term for term in before if term not in after)
    return summary


# ------------------------------------------------------------------ scoring ----


async def rank_sparse_query(
    session: AsyncSession,
    weights: Mapping[int, float],
    filters: SearchFilters,
    limit: int,
    query_lemmas: Sequence[str] = (),
    extra_detail: Mapping[str, float] | None = None,
) -> RankedPage:
    """Cosine between every document and a real-valued query vector.

    Same structure as the binary ranker's query — one grouped scan of the query terms'
    postings — except that the query weights arrive as a ``VALUES`` relation joined on
    ``term_id``, so the scalar product is ``SUM(weight_norm * weight)``. ``‖Q‖`` is a
    Python constant. Ties are broken by ascending document id, as everywhere.

    ``query_lemmas`` are the *user's* words; only those are reported as matched, because
    the assignment asks for «слова запроса, присутствующие в документе» — expansion
    terms the user never typed are not query words.
    """
    if not weights:
        return RankedPage()

    query_norm = norm(weights)
    if query_norm <= 0:
        return RankedPage()

    q = values(column("term_id", Integer), column("weight", Float), name="q").data(
        [(int(term), float(weight)) for term, weight in sorted(weights.items())]
    )

    dot_product = func.sum(Posting.weight_norm * q.c.weight)
    matched_terms = func.count(func.distinct(Posting.term_id))
    score = case(
        (Document.vector_norm > 0, dot_product / (Document.vector_norm * query_norm)),
        else_=0.0,
    ).label("score")

    statement: Select[Any] = (
        select(
            Posting.document_id.label("document_id"),
            score,
            dot_product.label("dot"),
            matched_terms.label("matched_terms"),
            func.array_agg(func.distinct(Term.lemma)).label("matched_lemmas"),
        )
        .join(q, q.c.term_id == Posting.term_id)
        .join(Term, Term.id == Posting.term_id)
        .join(Document, Document.id == Posting.document_id)
        .group_by(Posting.document_id, Document.vector_norm)
    )

    conditions = apply_document_filters(filters)
    if conditions:
        statement = statement.where(and_(*conditions))
    if filters.all_words_together:
        statement = statement.having(matched_terms == len(weights))

    # Orthogonal documents are not results — same convention as the binary ranker.
    statement = statement.having(dot_product > 0)

    candidates = statement
    statement = statement.order_by(score.desc(), Posting.document_id.asc()).limit(limit)

    count_statement = select(func.count()).select_from(candidates.subquery())
    total_candidates = int((await session.execute(count_statement)).scalar_one())
    rows = (await session.execute(statement)).all()

    wanted = list(query_lemmas)
    detail_base: dict[str, float] = {
        "query_norm": query_norm,
        "query_terms": float(len(weights)),
        "document_norm": 1.0,
    }
    if extra_detail:
        detail_base.update(extra_detail)

    documents = [
        ScoredDocument(
            document_id=row.document_id,
            score=float(row.score),
            matched_lemmas=_order_as_typed(wanted, row.matched_lemmas),
            detail={
                **detail_base,
                "scalar_product": float(row.dot),
                "matched_terms": float(row.matched_terms),
            },
        )
        for row in rows
    ]

    log.info(
        "sparse_query_ranked",
        query_terms=len(weights),
        results=len(documents),
        candidates=total_candidates,
        top_score=round(documents[0].score, 6) if documents else 0.0,
    )
    return RankedPage(documents=documents, total_candidates=total_candidates)


def _order_as_typed(wanted: Sequence[str], matched: Sequence[str] | None) -> list[str]:
    if not matched:
        return []
    found = set(matched)
    if not wanted:
        return sorted(found)
    return [lemma for lemma in wanted if lemma in found]
