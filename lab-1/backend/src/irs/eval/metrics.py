"""IR quality metrics — the pure computational core.

Implements the metrics of **Приложение А. «Официальные метрики РОМИП'2004»** (Агеев,
Кураленок), the document the assignment cites, plus the graded metrics ROMIP added in
its 2009 and 2010 editions. The full specification, with sources and every convention
this module commits to, is in ``docs/romip-2004-metrics-reference.md``.

**This module is deliberately free of any I/O, ORM or configuration.** Every function
takes a ranked list of document ids and a :class:`QueryJudgments`, and returns a number
or a curve. That is what makes it testable against values published in the ROMIP
appendix itself and against ``pytrec_eval`` — a metric implementation entangled with a
database cannot be verified against anything.

The conventions below are chosen deliberately; each is a documented trap where
implementations commonly disagree.

**`R` always comes from the judgments, never from the run.** Every one of the following
is a special case of that single rule, and getting any of them wrong inflates scores:

* ``average_precision`` divides by `R`, so relevant documents that were never retrieved
  contribute 0 to the numerator while still counting in the denominator.
* ``precision_at_k`` divides by `k` even when fewer than `k` documents were returned. The
  appendix states this directly, and ``trec_eval``'s ``m_P.c`` does the same. Dividing by
  ``min(k, len(ranked))`` is wrong.
* ``r_precision`` scans ``min(len(ranked), R)`` positions but divides by `R`.
* the 11-point curve averages a **0** at recall levels a query never reaches, rather than
  dropping the query from that level's average.

**Queries with no relevant documents are excluded** by the caller, per ROMIP's explicit
rule («запросы, для которых нет релевантных документов, не рассматриваются при
вычислении метрик»). Note that *modern* ``trec_eval`` does not do this, so a deliberate
discrepancy against ``pytrec_eval`` is expected on such queries — see the reference.

**Unjudged retrieved documents count as non-relevant** for every metric except
``bpref``, which skips them. ROMIP 2004 has no ``bpref``, so this is forced there; the
runner therefore also reports how many retrieved documents were unjudged, because a high
figure means the pool does not cover that ranker.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

__all__ = [
    "ELEVEN_POINT_LEVELS",
    "MAX_GRADE",
    "PRBreakdown",
    "QueryJudgments",
    "average_precision",
    "bpref",
    "bpref_romip",
    "dcg",
    "err",
    "f_measure",
    "interpolated_precision_11pt",
    "interpolated_precision_11pt_nonzeroing",
    "ndcg",
    "pfound",
    "pr_curve",
    "precision_at_k",
    "r_precision",
    "reciprocal_rank",
    "set_precision",
    "set_recall",
]

#: The eleven standard recall levels of the TREC method.
ELEVEN_POINT_LEVELS: tuple[float, ...] = tuple(round(i / 10, 1) for i in range(11))

#: Top of ROMIP's five-point scale (`VITAL`), used by ERR and PFound.
MAX_GRADE = 3


@dataclass(slots=True)
class QueryJudgments:
    """The relevance facts for one query.

    Separating "judged non-relevant" from "not judged at all" is the whole point of this
    type: the two are identical for precision and recall but not for ``bpref``, which
    skips unjudged documents rather than penalising a ranker for surfacing them.
    """

    #: Documents judged relevant (grade at or above the threshold).
    relevant: frozenset[int] = frozenset()
    #: Documents explicitly judged non-relevant. Excludes anything never judged.
    non_relevant: frozenset[int] = frozenset()
    #: Graded gain per judged document, for nDCG, ERR and PFound.
    gains: Mapping[int, float] = field(default_factory=dict)

    @property
    def r(self) -> int:
        """`R` — the number of relevant documents *in the judgments*."""
        return len(self.relevant)

    @property
    def n(self) -> int:
        """`N` — the number of judged non-relevant documents."""
        return len(self.non_relevant)

    @property
    def judged(self) -> frozenset[int]:
        return self.relevant | self.non_relevant

    @property
    def has_relevant(self) -> bool:
        """False for queries ROMIP excludes from every metric."""
        return bool(self.relevant)

    def is_relevant(self, document_id: int) -> bool:
        return document_id in self.relevant

    def gain(self, document_id: int) -> float:
        """Graded gain; 0 for an unjudged or non-relevant document."""
        return float(self.gains.get(document_id, 0.0))


# --------------------------------------------------------------------------------
# Set measures — the appendix's `точность` and `полнота`
# --------------------------------------------------------------------------------


def set_precision(ranked: Sequence[int], judgments: QueryJudgments) -> float:
    """`p = a / (a + b)` over the **whole** submitted list.

    This is the appendix's `точность`, a *set* measure, not `P@k`. Its value therefore
    depends on how many documents the run returns, so the run length must be published
    alongside it — a system returning 10 documents and one returning 1000 are not
    comparable on this number.

    An empty result list has undefined precision; 0.0 is returned, matching
    ``trec_eval``'s ``set_P``.
    """
    if not ranked:
        return 0.0
    hits = sum(1 for document_id in ranked if judgments.is_relevant(document_id))
    return hits / len(ranked)


def set_recall(ranked: Sequence[int], judgments: QueryJudgments) -> float:
    """`r = a / (a + c)` over the whole submitted list.

    Undefined when the query has no relevant documents; such queries are excluded by the
    caller, and 0.0 is returned as a defensive default.
    """
    if judgments.r == 0:
        return 0.0
    hits = sum(1 for document_id in ranked if judgments.is_relevant(document_id))
    return hits / judgments.r


def f_measure(precision: float, recall: float, beta: float = 1.0) -> float:
    """The appendix's F-measure, `F = 2 / (1/p + 1/r)` for β = 1.

    Guards the harmonic mean at zero: the appendix itself lists `F = 0` when either
    component is 0 as a property of the measure, so this is the specified behaviour
    rather than a convenience.
    """
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    beta_squared = beta * beta
    return (1 + beta_squared) * precision * recall / (beta_squared * precision + recall)


# --------------------------------------------------------------------------------
# Rank-based measures
# --------------------------------------------------------------------------------


def precision_at_k(ranked: Sequence[int], judgments: QueryJudgments, k: int) -> float:
    """`P@k` — precision among the top `k`.

    **The denominator is always `k`.** If the run returned fewer than `k` documents the
    missing positions count as non-relevant, which the appendix states explicitly:
    «Если система выдала менее n документов, то точность на уровне n документов будет
    заведомо не выше точности системы». Confirmed identical in ``trec_eval``'s ``m_P.c``.
    """
    if k <= 0:
        return 0.0
    hits = sum(1 for document_id in ranked[:k] if judgments.is_relevant(document_id))
    return hits / k


def r_precision(ranked: Sequence[int], judgments: QueryJudgments) -> float:
    """`R-Precision` = `P@R`, where `R` is the number of relevant documents in the qrels.

    Scans ``min(len(ranked), R)`` positions but divides by `R`, exactly as
    ``trec_eval``'s ``m_Rprec.c`` does — so a run shorter than `R` is penalised as if its
    missing positions were non-relevant. Dividing by the number of positions actually
    examined is the common error and inflates short runs.

    Exists because `P@k` is incomparable across queries with different `R`: the appendix's
    own example notes that a perfect system scores `P@100 = 0.2` when `R = 20` and `0.3`
    when `R = 30`.
    """
    r = judgments.r
    if r == 0:
        return 0.0
    examined = min(len(ranked), r)
    hits = sum(1 for document_id in ranked[:examined] if judgments.is_relevant(document_id))
    return hits / r


def average_precision(ranked: Sequence[int], judgments: QueryJudgments) -> float:
    """`AveragePrec` — the mean of the precisions observed at each relevant document.

    The appendix's formulation, followed literally because it makes the denominator
    unambiguous: for a query with `k` relevant documents, the `i`-th relevant document
    contributes `P@pos(i)` if it was retrieved and **0 if it was not**; the sum is divided
    by `k`. Equivalently `AP = (1/R) · Σ_{i: rel(d_i)} P@i`, which is what ``m_map.c``
    computes.

    Properties the appendix states, all asserted in the tests: `AP ≤ recall`, with
    equality when every relevant document is at the very top; `AP ≈ precision · recall`
    for uniformly spread relevant documents; and documents ranked below the last relevant
    one do not affect `AP` («отсекается "хвост"»).
    """
    if judgments.r == 0:
        return 0.0

    hits = 0
    total = 0.0
    for position, document_id in enumerate(ranked, start=1):
        if judgments.is_relevant(document_id):
            hits += 1
            total += hits / position

    # Divided by R from the judgments, not by `hits`. Unretrieved relevant documents
    # contribute nothing to the numerator but still count here.
    return total / judgments.r


def reciprocal_rank(
    ranked: Sequence[int], judgments: QueryJudgments, ruler: Sequence[float] | None = None
) -> float:
    """`1 / rank` of the first relevant document, or 0 if none was retrieved.

    ROMIP 2010 defines this via a *ruler* rather than fixing `1/x`: it used `1/pos` for
    document search, while TREC's question-answering track used
    ``{1.0, 0.5, 0.33, 0.2, 0.1}`` and then 0. The default here is `1/pos`; passing a
    ruler reproduces the alternative.
    """
    for position, document_id in enumerate(ranked, start=1):
        if judgments.is_relevant(document_id):
            if ruler is None:
                return 1.0 / position
            return ruler[position - 1] if position <= len(ruler) else 0.0
    return 0.0


# --------------------------------------------------------------------------------
# Precision–recall curves
# --------------------------------------------------------------------------------


@dataclass(slots=True)
class PRBreakdown:
    """A query's raw precision/recall trajectory, before interpolation."""

    #: `(recall, precision)` at each rank where a relevant document was retrieved.
    points: list[tuple[float, float]] = field(default_factory=list)
    #: The highest recall the run achieved.
    max_recall: float = 0.0


def pr_curve(ranked: Sequence[int], judgments: QueryJudgments) -> PRBreakdown:
    """The un-interpolated precision/recall points of one run.

    Plotted beside the interpolated curve, this is what makes the effect of interpolation
    visible: the raw curve is a sawtooth, and the standard graph is its upper envelope.
    """
    if judgments.r == 0:
        return PRBreakdown()

    points: list[tuple[float, float]] = []
    hits = 0
    for position, document_id in enumerate(ranked, start=1):
        if judgments.is_relevant(document_id):
            hits += 1
            points.append((hits / judgments.r, hits / position))

    return PRBreakdown(points=points, max_recall=points[-1][0] if points else 0.0)


def _recall_to_count(level: float, r: int, convention: str) -> int:
    """Number of relevant documents corresponding to a recall level.

    ``"romip"`` (default) takes the ceiling, per the appendix's definition and worked
    example. ``"trec"`` rounds, matching current ``trec_eval``, for cross-validation.
    """
    exact = level * r
    if convention == "trec":
        return round(exact)
    # Ceiling, with a tolerance so that an exact level such as 0.5 · 4 = 2.0 does not
    # become 3 through binary floating-point representation error.
    return math.ceil(exact - 1e-9)


def _interpolated_precisions(
    ranked: Sequence[int], judgments: QueryJudgments, convention: str = "romip"
) -> tuple[list[float | None], float]:
    """Interpolated precision at each of the eleven recall levels for one query.

    Returns ``(precisions, max_recall)`` where an entry is ``None`` at a recall level the
    query never reached. The caller decides what an unreached level means — the TREC
    method scores it 0, the non-zeroing reconstruction omits it — which is the single
    substantive difference between the appendix's two official curve metrics.

    Interpolated precision at level `r` is `max{ precision(n) : recall(n) ≥ r }`. It is
    computed by sweeping the ranking **in reverse** with a running maximum, as
    ``trec_eval`` does; a forward pass with a look-ahead maximum is `O(n²)` and easy to
    get subtly wrong.

    Recall levels are converted to relevant-document counts by **ceiling**, which is
    what the appendix's own definition requires and what its worked example produces.
    The definition places `pos(r_i, q_j)` at the *shortest prefix at which recall `r_i`
    is reached*, i.e. the first rank where `hits / R ≥ r_i`, i.e. `hits ≥ ⌈r_i · R⌉`.

    This matters, and it is not a detail. Current ``trec_eval`` uses ``lround`` here
    (older versions used ``int(level · R + 0.9)``, effectively a ceiling), and with the
    appendix's own example — 20 documents, 4 relevant at ranks 1, 2, 4, 15 — the two
    conventions give *different curves*:

        ceiling: 1.0 ×6, 0.75, 0.75, 0.267 ×3   ← the appendix's published values
        round:   1.0 ×7, 0.75, 0.75, 0.267 ×2

    Since the assignment cites the 2004 appendix, ceiling is the default; pass
    ``convention="trec"`` to reproduce modern ``trec_eval`` for cross-validation. Both
    are pinned by tests, and the discrepancy is noted in the report.
    """
    r = judgments.r
    if r == 0:
        return [None] * len(ELEVEN_POINT_LEVELS), 0.0

    # Precision at every rank, and the recall reached by that rank.
    hits = 0
    precision_at_rank: list[float] = []
    hits_at_rank: list[int] = []
    for position, document_id in enumerate(ranked, start=1):
        if judgments.is_relevant(document_id):
            hits += 1
        precision_at_rank.append(hits / position)
        hits_at_rank.append(hits)

    max_recall = (hits / r) if r else 0.0

    # Reverse sweep: best_from[i] is the maximum precision at rank i or later.
    best_from = [0.0] * (len(precision_at_rank) + 1)
    for index in range(len(precision_at_rank) - 1, -1, -1):
        best_from[index] = max(precision_at_rank[index], best_from[index + 1])

    precisions: list[float | None] = []
    for level in ELEVEN_POINT_LEVELS:
        needed = _recall_to_count(level, r, convention)
        if needed == 0:
            # Recall 0 is reached before any document is examined, so interpolated
            # precision there is the maximum precision anywhere in the ranking.
            precisions.append(best_from[0] if precision_at_rank else 0.0)
            continue
        if needed > hits:
            precisions.append(None)  # this recall level was never reached
            continue
        # First rank at which `needed` relevant documents have been seen.
        first = next(index for index, seen in enumerate(hits_at_rank) if seen >= needed)
        precisions.append(best_from[first])

    return precisions, max_recall


def interpolated_precision_11pt(
    runs: Sequence[tuple[Sequence[int], QueryJudgments]],
    convention: str = "romip",
) -> list[float]:
    """The 11-point interpolated precision/recall graph, **TREC method**.

    ROMIP 2004 official metric #7, and the one metric in that list which is inherently a
    curve rather than a scalar — presumably why the assignment asks for graphs.

    A query that never reaches recall level `r` contributes **0** at that level, and that
    zero *is* included in the average. This is the trap: averaging over only the queries
    that reached each level produces a flattering, non-standard curve. Confirmed against
    ``trec_eval``'s ``m_iprec_at_recall.c``, where unreached cutoffs keep their
    zero-initialised value.
    """
    if not runs:
        return [0.0] * len(ELEVEN_POINT_LEVELS)

    totals = [0.0] * len(ELEVEN_POINT_LEVELS)
    for ranked, judgments in runs:
        precisions, _ = _interpolated_precisions(ranked, judgments, convention)
        for index, value in enumerate(precisions):
            totals[index] += value if value is not None else 0.0

    return [total / len(runs) for total in totals]


def interpolated_precision_11pt_nonzeroing(
    runs: Sequence[tuple[Sequence[int], QueryJudgments]],
    convention: str = "romip",
) -> tuple[list[float], list[int]]:
    """The 11-point graph averaged only over queries that reached each recall level.

    ROMIP lists a second, "RIRES-modified" 11-point metric as official in every edition
    (2009 and 2010 rename it "ROMIP") but **never defines it anywhere** — section 4 of the
    appendix defines only the TREC variant and then goes straight to the bibliography.

    This is therefore an explicitly-documented *reconstruction*, chosen because it is the
    most natural modification and because plotting it against the TREC curve demonstrates
    what the zeroing convention actually does — the deepest idea in the appendix. It must
    be presented as a reconstruction, not as ROMIP's metric.

    Returns ``(precisions, support)`` where ``support[i]`` is how many queries reached
    level `i`. The support has to be published: at high recall levels the denominator can
    fall to a handful of queries, and a mean over three queries is not comparable with a
    mean over thirty.
    """
    levels = len(ELEVEN_POINT_LEVELS)
    if not runs:
        return [0.0] * levels, [0] * levels

    totals = [0.0] * levels
    support = [0] * levels
    for ranked, judgments in runs:
        precisions, _ = _interpolated_precisions(ranked, judgments, convention)
        for index, value in enumerate(precisions):
            if value is not None:
                totals[index] += value
                support[index] += 1

    return [
        (totals[index] / support[index]) if support[index] else 0.0 for index in range(levels)
    ], support


# --------------------------------------------------------------------------------
# Graded measures — ROMIP 2009/2010 additions, not part of the 2004 official set
# --------------------------------------------------------------------------------


def dcg(ranked: Sequence[int], judgments: QueryJudgments, k: int) -> float:
    """Discounted cumulative gain over the top `k`.

    Two conventions are fixed here deliberately, because implementations differ:

    * **Gain is `2^grade − 1`**, following ROMIP 2010. ``trec_eval``'s ``ndcg`` uses the
      *linear* relevance level instead (``m_ndcg.c``'s ``get_gain``), which produces
      materially different numbers on a 0–3 scale. Cross-checks against ``pytrec_eval``
      must pass explicit gains or expect a mismatch.
    * **The discount is `log2(1 + rank)` with rank 1-based**, so the first position is
      undiscounted. ROMIP's printed formula reads `log2(2 + p)` with `p` starting at 1,
      which would discount rank 1 by `1/log2(3) ≈ 0.63`; that is almost certainly a
      0-versus-1 indexing slip, and the standard form is used instead.
    """
    total = 0.0
    for position, document_id in enumerate(ranked[:k], start=1):
        grade = judgments.gain(document_id)
        if grade > 0:
            total += (2.0**grade - 1.0) / math.log2(1 + position)
    return total


def ndcg(ranked: Sequence[int], judgments: QueryJudgments, k: int) -> float:
    """Normalised DCG — `DCG@k` divided by the DCG of the ideal ranking.

    The ideal ranking is built from the judgments, so a run that omits a highly-graded
    document is penalised for it. Returns 0 when no judged document carries any gain.
    """
    actual = dcg(ranked, judgments, k)
    if actual == 0.0:
        return 0.0

    ideal_order = sorted(judgments.gains.values(), reverse=True)[:k]
    ideal = sum(
        (2.0**grade - 1.0) / math.log2(1 + position)
        for position, grade in enumerate(ideal_order, start=1)
        if grade > 0
    )
    return actual / ideal if ideal > 0 else 0.0


def bpref(ranked: Sequence[int], judgments: QueryJudgments) -> float:
    """Binary preference — robust to incomplete judgments.

    Unjudged documents are **skipped** rather than counted as non-relevant, which makes
    this the right measure when a ranker surfaces documents outside the judgment pool.
    That is exactly the situation a small pooled collection creates for whichever ranker
    contributed least to the pool.

    This implements ``trec_eval``'s formula, not the one printed in ROMIP 2010:

        bpref = (1/R) · Σ_r ( 1 − min(NonRelBefore(r), R) / min(N, R) )

    ROMIP writes the denominator as `R`; ``m_bpref.c`` uses ``min(N, R)`` and caps the
    numerator at `R`. The two agree only when `N ≥ R`, and `N < R` is entirely possible in
    a small collection with a generous relevance threshold. ``trec_eval``'s own README
    records that bpref changed incompatibly at version 8.0, so this is the least portable
    measure here — :func:`bpref_romip` provides the literal ROMIP form for comparison.
    """
    r = judgments.r
    if r == 0:
        return 0.0

    denominator = min(judgments.n, r)
    if denominator == 0:
        # No judged non-relevant documents: nothing can rank before a relevant one, so
        # every retrieved relevant document scores a full 1.
        retrieved_relevant = sum(1 for d in ranked if judgments.is_relevant(d))
        return retrieved_relevant / r

    total = 0.0
    non_relevant_seen = 0
    for document_id in ranked:
        if judgments.is_relevant(document_id):
            total += 1.0 - min(non_relevant_seen, r) / denominator
        elif document_id in judgments.non_relevant and non_relevant_seen < denominator:
            # Only *judged* non-relevant documents count; unjudged ones are skipped, and
            # the running total is capped, matching trec_eval's `min(nonrel, R)`.
            non_relevant_seen += 1

    return total / r


def bpref_romip(ranked: Sequence[int], judgments: QueryJudgments, offset: int = 0) -> float:
    """ROMIP 2010's literal bpref, `(1/R) · Σ_r (1 − NonRelBefore(r) / (offset + R))`.

    ``offset = 10`` gives ROMIP's ``bpref-10``. Modern ``trec_eval`` offers only ``bpref``
    and ``gm_bpref`` — the older ``bpref_top*nonrel`` variants were removed — so
    ``bpref-10`` has **no reference implementation** and cannot be cross-validated. It is
    reported with that caveat rather than presented as verified.
    """
    r = judgments.r
    if r == 0:
        return 0.0

    denominator = offset + r
    total = 0.0
    non_relevant_seen = 0
    for document_id in ranked:
        if judgments.is_relevant(document_id):
            total += 1.0 - min(non_relevant_seen, denominator) / denominator
        elif document_id in judgments.non_relevant:
            non_relevant_seen += 1

    return total / r


def err(ranked: Sequence[int], judgments: QueryJudgments, k: int | None = None) -> float:
    """Expected reciprocal rank (Chapelle et al., CIKM'09; ROMIP 2010).

        ERR = Σ_r (1/r) · R_r · Π_{i<r} (1 − R_i),    R_i = (2^grade_i − 1) / 2^max_grade

    A cascade model: a document's contribution is discounted by the probability that the
    user was still looking when they reached it. The appendix's own intuition is that a
    relevant document at position 10 barely matters if nine relevant ones precede it, but
    matters a great deal if nine non-relevant ones do.
    """
    window = ranked[:k] if k else ranked
    max_gain = 2.0**MAX_GRADE

    total = 0.0
    unsatisfied = 1.0
    for position, document_id in enumerate(window, start=1):
        grade = judgments.gain(document_id)
        probability = (2.0**grade - 1.0) / max_gain if grade > 0 else 0.0
        total += unsatisfied * probability / position
        unsatisfied *= 1.0 - probability
        if unsatisfied <= 0.0:
            break
    return total


def pfound(
    ranked: Sequence[int],
    judgments: QueryJudgments,
    k: int | None = None,
    break_probability: float = 0.15,
) -> float:
    """PFound (Гулин et al., РОМИП'2009; defined in ROMIP 2010).

        pFound   = Σ_r pLook(r) · pRel(r)
        pLook(r) = pLook(r−1) · (1 − pRel(r−1)) · (1 − pBreak),   pLook(1) = 1
        pRel(r)  = 0.5 · 2^(grade(r) − 3)  for grade > 0, else 0

    Like ERR a cascade model, but with an explicit per-position abandonment probability
    (`pBreak = 0.15`) as well as satisfaction.
    """
    window = ranked[:k] if k else ranked

    total = 0.0
    p_look = 1.0
    previous_relevance = 0.0
    for position, document_id in enumerate(window, start=1):
        if position > 1:
            p_look = p_look * (1.0 - previous_relevance) * (1.0 - break_probability)

        grade = judgments.gain(document_id)
        p_rel = 0.5 * 2.0 ** (grade - MAX_GRADE) if grade > 0 else 0.0

        total += p_look * p_rel
        previous_relevance = p_rel

        if p_look <= 1e-12:
            break
    return total
