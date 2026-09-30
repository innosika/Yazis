"""Term weighting and vector similarity — the assignment's formulas, implemented directly.

Everything here is a pure function over plain numbers and dictionaries: no database, no
ORM, no I/O. That is deliberate. It makes the formulas unit-testable against values
computed by hand, which is the only way to demonstrate that the vector model is
genuinely implemented rather than delegated to a library.

The formulas, transcribed from the assignment:

**(1.5) Inverse term frequency**

    B_i = log(N / P_i)

**(1.6) Weight of term i in document j** — the assignment specifies this one for
*automatic keyword extraction*:

    A_i^j = Q_i^j · B_i

**Normalized TF-IDF** — the assignment specifies this one for the *search* vectors:

                 N_dk · log(N / N_k)
    w_dk = ────────────────────────────────────
           sqrt( Σ_j ( N_dj · log(N / N_j) )² )

**Query vector** — binary, not weighted:

    w_qj = 1 if word j occurs in query q, else 0

**Similarity** — cosine of the angle between the vectors:

    r(D, Q) = (D, Q) / (‖D‖ · ‖Q‖)

Three properties of this particular scheme are worth stating explicitly, because they
are easy to get wrong and they matter for the report's analysis:

1. **1.6 and w_dk are different weights over the same data.** The numerator of `w_dk`
   *is* `A_i^j`; `w_dk` additionally divides by the document's Euclidean norm. Keyword
   extraction must use the unnormalized value, ranking must use the normalized one. Both
   are derived here from the same stored `N_dk` and `N_k`.

2. **‖D‖ = 1 whenever the document has any term with non-zero IDF**, because `w_dk` is
   already L2-normalized over `j`. Consequently `r(D,Q)` reduces to
   `Σ_{k∈q} w_dk / sqrt(|q|)`. The general cosine is still computed — it is what the
   assignment's ``ScalarProduct`` and ``EuclideanNorm`` methods describe — but the
   identity is asserted in the tests, and a stored norm that drifts from 1 is a
   reliable signal of a stale index.

3. **The logarithm base does not affect ranking.** Changing the base multiplies every
   IDF by a constant, which appears in both the numerator and the denominator of `w_dk`
   and cancels exactly. It *does* rescale the keyword weights from 1.6. The base is
   therefore configurable, and the report notes that only 1.6's absolute values move.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from irs.config import settings

__all__ = [
    "CosineDerivation",
    "TermContribution",
    "TermWeightDerivation",
    "cosine_similarity",
    "derive_cosine",
    "derive_term_weight",
    "euclidean_norm",
    "inverse_frequency",
    "normalized_weights",
    "query_vector",
    "raw_weight",
    "scalar_product",
    "top_keywords",
]


# --------------------------------------------------------------------------------
# Formula 1.5 — inverse term frequency
# --------------------------------------------------------------------------------


def inverse_frequency(
    document_count: int, document_frequency: int, log_base: str | None = None
) -> float:
    """`B_i = log(N / P_i)` — the assignment's formula 1.5.

    Args:
        document_count: `N`, documents in the collection.
        document_frequency: `P_i`, documents containing the term.
        log_base: ``"e"``, ``"2"`` or ``"10"``. Defaults to the configured base.

    Returns:
        The inverse frequency, always ``>= 0``.

    Edge cases, all of which occur in a real collection:

    * `N = 0` (empty collection) or `P_i = 0` (term in the dictionary but in no
      document — only reachable from a stale index) → ``0.0``.
    * `P_i = N` → ``log(1) = 0``. A term present in *every* document distinguishes
      nothing, and the formula says so on its own; no special case is needed.
    * `P_i > N` → clamped to ``0.0``. This cannot happen in consistent data, so it
      indicates the counters were updated without rebuilding, and returning a negative
      weight would silently corrupt every score that touched the term.
    """
    if document_count <= 0 or document_frequency <= 0:
        return 0.0
    if document_frequency >= document_count:
        return 0.0

    divisor = (
        settings.index.log_divisor
        if log_base is None
        else {"e": 1.0, "2": math.log(2.0), "10": math.log(10.0)}[log_base]
    )
    return math.log(document_count / document_frequency) / divisor


# --------------------------------------------------------------------------------
# Formula 1.6 — unnormalized weight, used for keyword extraction
# --------------------------------------------------------------------------------


def raw_weight(term_frequency: int, inverse_freq: float) -> float:
    """`A_i^j = Q_i^j · B_i` — the assignment's formula 1.6.

    This is the weight the assignment mandates for automatic keyword extraction, and it
    is *not* the weight used for ranking. Kept as its own function so the distinction
    is visible at every call site.
    """
    return float(term_frequency) * inverse_freq


def top_keywords(
    term_frequencies: Mapping[str, int],
    inverse_frequencies: Mapping[str, float],
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """The document's keywords, by descending `A_i^j` — the assignment's requirement
    that «выделение ключевых слов документов осуществляется системой автоматически
    в соответствие с формулой 1.6».

    Ties are broken alphabetically so the output is deterministic; without that, two
    keyword lists over the same document could differ between runs purely by dict order.
    """
    limit = settings.index.keywords_per_document if limit is None else limit
    weighted = [
        (lemma, raw_weight(tf, inverse_frequencies.get(lemma, 0.0)))
        for lemma, tf in term_frequencies.items()
    ]
    weighted.sort(key=lambda item: (-item[1], item[0]))
    return [pair for pair in weighted[:limit] if pair[1] > 0.0]


# --------------------------------------------------------------------------------
# Normalized weights — the search vectors
# --------------------------------------------------------------------------------


def normalized_weights(
    term_frequencies: Mapping[str, int],
    inverse_frequencies: Mapping[str, float],
) -> tuple[dict[str, float], float]:
    """Compute `w_dk` for every term of one document.

    Args:
        term_frequencies: `N_dk` per term, i.e. raw occurrence counts.
        inverse_frequencies: `B_k = log(N / N_k)` per term.

    Returns:
        ``(weights, denominator)`` where ``weights`` maps term → `w_dk` and
        ``denominator`` is ``sqrt(Σ_j (N_dj·log(N/N_j))²)`` — the value returned so the
        glass-box explanation can show it without recomputing.

    A document whose every term has zero IDF (each term occurs in every document) gives
    a zero denominator. Rather than divide by zero, all weights are returned as ``0.0``:
    such a document is genuinely indistinguishable from every other under this scheme,
    and a zero vector is the honest representation of that.
    """
    numerators = {
        lemma: float(tf) * inverse_frequencies.get(lemma, 0.0)
        for lemma, tf in term_frequencies.items()
    }
    denominator = math.sqrt(sum(value * value for value in numerators.values()))

    if denominator <= 0.0:
        return dict.fromkeys(numerators, 0.0), 0.0

    return (
        {lemma: value / denominator for lemma, value in numerators.items()},
        denominator,
    )


def query_vector(lemmas: Iterable[str]) -> dict[str, float]:
    """Build `Q = {w_qj}` with `w_qj = 1` for every distinct query word, else 0.

    Binary by specification — the assignment does not weight the query by IDF. Repeating
    a word in the query therefore does not increase its influence, which is a genuine
    limitation of the specified model and is discussed in the report's analysis.
    """
    return dict.fromkeys(lemmas, 1.0)


# --------------------------------------------------------------------------------
# Vector algebra — the assignment's Search class methods
# --------------------------------------------------------------------------------


def scalar_product(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """`(A, B)` — the dot product over the sparse intersection.

    Iterates the smaller operand, since the query vector has a handful of components and
    a document vector has hundreds.
    """
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def euclidean_norm(vector: Mapping[str, float]) -> float:
    """`‖A‖` — the Euclidean norm."""
    return math.sqrt(sum(value * value for value in vector.values()))


def cosine_similarity(
    document: Mapping[str, float],
    query: Mapping[str, float],
    document_norm: float | None = None,
) -> float:
    """`r(D, Q) = (D, Q) / (‖D‖ · ‖Q‖)`.

    Args:
        document: the document vector `D`.
        query: the query vector `Q`.
        document_norm: pre-computed ``‖D‖``. Supplied from the stored column during
            retrieval so the norm is not recomputed for every candidate; recomputed here
            when omitted.

    Returns:
        Cosine similarity in ``[0, 1]`` for non-negative vectors, or ``0.0`` when either
        vector is empty or has zero norm — an unanswerable query and a contentless
        document both correctly score zero rather than raising.
    """
    if not document or not query:
        return 0.0

    norm_d = euclidean_norm(document) if document_norm is None else document_norm
    norm_q = euclidean_norm(query)
    if norm_d <= 0.0 or norm_q <= 0.0:
        return 0.0

    return scalar_product(document, query) / (norm_d * norm_q)


# --------------------------------------------------------------------------------
# Derivations — the intermediate values behind one score
# --------------------------------------------------------------------------------


@dataclass(slots=True)
class TermWeightDerivation:
    """Every intermediate value in one term's weight, for the glass-box explanation."""

    lemma: str
    #: `N_dk` — occurrences in this document.
    term_frequency: int
    #: `N_k` — documents containing the term.
    document_frequency: int
    #: `N` — documents in the collection.
    document_count: int
    #: `B_k = log(N / N_k)` (formula 1.5).
    inverse_frequency: float
    #: `A_k = N_dk · B_k` (formula 1.6) — also the numerator of `w_dk`.
    weight_raw: float
    #: `w_dk` — the normalized weight.
    weight_norm: float
    #: True when the term appears in the query as well as the document.
    in_query: bool = False


@dataclass(slots=True)
class TermContribution:
    """One term's share of the final similarity score."""

    lemma: str
    #: `w_dk`, the document-side component.
    document_weight: float
    #: `w_qk`, the query-side component (1 or 0).
    query_weight: float
    #: `w_dk · w_qk` — this term's addend in the scalar product.
    product: float
    #: Share of the total score, in ``[0, 1]``. The glass box charts this.
    share: float


@dataclass(slots=True)
class CosineDerivation:
    """The full arithmetic behind `r(D, Q)`, reproducible by hand from these fields."""

    score: float
    scalar_product: float
    document_norm: float
    query_norm: float
    #: Terms shared by document and query, by descending contribution.
    contributions: list[TermContribution] = field(default_factory=list)
    #: Query terms absent from this document — they contribute nothing, and showing them
    #: explains *why* a document the user expected to rank higher did not.
    missing_terms: list[str] = field(default_factory=list)


def derive_term_weight(
    lemma: str,
    term_frequency: int,
    document_frequency: int,
    document_count: int,
    denominator: float,
    in_query: bool = False,
    log_base: str | None = None,
) -> TermWeightDerivation:
    """Recompute one term's weight from raw counts, retaining every intermediate."""
    idf = inverse_frequency(document_count, document_frequency, log_base)
    numerator = raw_weight(term_frequency, idf)
    return TermWeightDerivation(
        lemma=lemma,
        term_frequency=term_frequency,
        document_frequency=document_frequency,
        document_count=document_count,
        inverse_frequency=idf,
        weight_raw=numerator,
        weight_norm=numerator / denominator if denominator > 0.0 else 0.0,
        in_query=in_query,
    )


def derive_cosine(
    document: Mapping[str, float],
    query: Mapping[str, float],
    document_norm: float | None = None,
) -> CosineDerivation:
    """Compute `r(D, Q)` while retaining the per-term breakdown.

    Used by the "why did this document rank here?" panel. Kept separate from
    :func:`cosine_similarity` so that the hot retrieval path does not pay for building
    the explanation — only the handful of results the user actually inspects do.
    """
    norm_d = euclidean_norm(document) if document_norm is None else document_norm
    norm_q = euclidean_norm(query)
    dot = scalar_product(document, query)
    score = dot / (norm_d * norm_q) if norm_d > 0.0 and norm_q > 0.0 else 0.0

    contributions: list[TermContribution] = []
    missing: list[str] = []
    for lemma, query_weight in query.items():
        document_weight = document.get(lemma, 0.0)
        if document_weight == 0.0:
            missing.append(lemma)
            continue
        product = document_weight * query_weight
        contributions.append(
            TermContribution(
                lemma=lemma,
                document_weight=document_weight,
                query_weight=query_weight,
                product=product,
                share=product / dot if dot > 0.0 else 0.0,
            )
        )

    contributions.sort(key=lambda c: (-c.product, c.lemma))
    return CosineDerivation(
        score=score,
        scalar_product=dot,
        document_norm=norm_d,
        query_norm=norm_q,
        contributions=contributions,
        missing_terms=sorted(missing),
    )
