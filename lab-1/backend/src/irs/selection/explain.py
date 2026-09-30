"""Glass-box score explanation — "why did this document rank here?".

Rebuilds the complete arithmetic behind one document's similarity score, from the raw
counts upward, using the reference formulas in :mod:`irs.index.weights`.

It deliberately **recomputes** every weight from `N_dk`, `N_k` and `N` rather than
reading the stored `weight_norm` column, for two reasons. It makes the panel a live
derivation the reader can follow with a calculator, and it makes any disagreement with
the stored value visible instead of hidden — the response carries both numbers, so a
stale index shows up in the interface rather than silently skewing results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import Document, Posting, Term
from irs.index.builder import get_collection_stat
from irs.index.weights import (
    TermWeightDerivation,
    derive_cosine,
    euclidean_norm,
    inverse_frequency,
    normalized_weights,
    query_vector,
    raw_weight,
    top_keywords,
)
from irs.logging import get_logger
from irs.selection.base import ParsedQuery

log = get_logger("irs.selection.explain")


@dataclass(slots=True)
class ScoreStep:
    """One addend of the scalar product, with the running total after it."""

    lemma: str
    document_weight: float
    query_weight: float
    product: float
    running_sum: float
    share: float


@dataclass(slots=True)
class ScoreExplanation:
    """Everything needed to reproduce one score by hand."""

    document_id: int
    title: str
    url: str

    #: `N` — the collection size every inverse frequency depends on.
    document_count: int
    #: `D` — dictionary cardinality, for context on the vector's dimensionality.
    term_count: int
    log_base: str

    #: Per query term: the raw counts and both weights.
    query_terms: list[TermWeightDerivation] = field(default_factory=list)
    #: Query terms this document does not contain — the reason it is not higher.
    missing_terms: list[str] = field(default_factory=list)
    #: Query terms absent from the dictionary entirely.
    unknown_terms: list[str] = field(default_factory=list)

    #: The scalar product, accumulated one term at a time.
    steps: list[ScoreStep] = field(default_factory=list)
    scalar_product: float = 0.0
    document_norm: float = 0.0
    query_norm: float = 0.0
    score: float = 0.0

    #: The normalisation denominator `sqrt(Σ_j A_dj²)` for this document.
    normalization_denominator: float = 0.0
    #: The stored score, for comparison with the recomputed one.
    stored_document_norm: float = 0.0
    #: True when recomputation matches the stored weights — false means a stale index.
    consistent_with_index: bool = True

    #: The document's own keywords by formula 1.6, for context.
    document_keywords: list[tuple[str, float]] = field(default_factory=list)
    #: Total distinct index terms in this document (the vector's non-zero count).
    distinct_term_count: int = 0
    token_count: int = 0


async def explain_score(
    session: AsyncSession, document_id: int, query: ParsedQuery
) -> ScoreExplanation | None:
    """Derive the full similarity computation for one document and query."""
    document = await session.get(Document, document_id)
    if document is None:
        return None

    stat = await get_collection_stat(session)
    n = stat.document_count

    # Every posting of this document, so both the normalisation denominator and the
    # keyword list can be computed — the denominator sums over *all* the document's
    # terms, not only the query's.
    rows = (
        await session.execute(
            select(
                Term.lemma,
                Term.document_frequency,
                Posting.term_frequency,
                Posting.weight_norm,
            )
            .join(Posting, Posting.term_id == Term.id)
            .where(Posting.document_id == document_id)
        )
    ).all()

    frequencies = {row.lemma: row.term_frequency for row in rows}
    document_frequencies = {row.lemma: row.document_frequency for row in rows}
    stored_weights = {row.lemma: row.weight_norm for row in rows}

    inverse_frequencies = {
        lemma: inverse_frequency(n, df) for lemma, df in document_frequencies.items()
    }
    recomputed, denominator = normalized_weights(frequencies, inverse_frequencies)

    # Does the recomputation agree with what the index stored?
    consistent = all(
        abs(recomputed.get(lemma, 0.0) - stored) < 1e-9 for lemma, stored in stored_weights.items()
    )
    if not consistent:
        log.warning(
            "explanation_disagrees_with_index",
            document_id=document_id,
            hint="the index is stale; rebuild it",
        )

    known = query.known_lemmas
    vector = query_vector(known)
    derivation = derive_cosine(recomputed, vector, document_norm=euclidean_norm(recomputed))

    # Per-term derivations, in the order the user typed the query.
    query_terms = [
        TermWeightDerivation(
            lemma=lemma,
            term_frequency=frequencies.get(lemma, 0),
            # For a query term this document does not contain, `N_k` still comes from
            # the dictionary — showing it is what explains the zero contribution.
            document_frequency=document_frequencies.get(
                lemma, query.document_frequencies.get(lemma, 0)
            ),
            document_count=n,
            inverse_frequency=inverse_frequencies.get(
                lemma, query.inverse_frequencies.get(lemma, 0.0)
            ),
            weight_raw=raw_weight(
                frequencies.get(lemma, 0),
                inverse_frequencies.get(lemma, query.inverse_frequencies.get(lemma, 0.0)),
            ),
            weight_norm=recomputed.get(lemma, 0.0),
            in_query=True,
        )
        for lemma in known
    ]

    # The scalar product, accumulated so the reader can follow the addition.
    steps: list[ScoreStep] = []
    running = 0.0
    for contribution in derivation.contributions:
        running += contribution.product
        steps.append(
            ScoreStep(
                lemma=contribution.lemma,
                document_weight=contribution.document_weight,
                query_weight=contribution.query_weight,
                product=contribution.product,
                running_sum=running,
                share=contribution.share,
            )
        )

    explanation = ScoreExplanation(
        document_id=document_id,
        title=document.title,
        url=document.url,
        document_count=n,
        term_count=stat.term_count,
        log_base=stat.log_base or settings.index.log_base,
        query_terms=query_terms,
        missing_terms=derivation.missing_terms,
        unknown_terms=list(query.unknown_lemmas),
        steps=steps,
        scalar_product=derivation.scalar_product,
        document_norm=derivation.document_norm,
        query_norm=derivation.query_norm,
        score=derivation.score,
        normalization_denominator=denominator,
        stored_document_norm=document.vector_norm,
        consistent_with_index=consistent,
        document_keywords=top_keywords(frequencies, inverse_frequencies),
        distinct_term_count=len(frequencies),
        token_count=document.token_count,
    )

    log.info(
        "score_explained",
        document_id=document_id,
        score=round(derivation.score, 6),
        contributing_terms=len(steps),
        missing_terms=len(derivation.missing_terms),
        consistent=consistent,
    )
    return explanation
