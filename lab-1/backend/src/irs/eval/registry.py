"""Metric registry.

One declarative table describing every metric: its label, whether it is a scalar or a
curve, whether it needs graded judgments, and — importantly for this assignment — which
ROMIP edition defines it. The API serves this and the interface renders its tables and
charts from it, so adding a metric is a single entry here rather than a change in three
places.

The ``edition`` field is not decoration. The assignment cites the **2004** appendix,
whose official search-track list is exactly eight metrics. `bpref`, `nDCG`, `ERR`,
`PFound` and `MRR` were added in 2009 and 2010. Presenting them as though they were part
of the cited specification would misrepresent it, so the interface groups them
separately and the report labels them as extensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from irs.config import settings


class MetricKind(StrEnum):
    SCALAR = "scalar"
    CURVE = "curve"


class MetricEdition(StrEnum):
    """Which ROMIP document defines the metric."""

    #: Official ROMIP'2004 search-track metric — what the assignment cites.
    OFFICIAL_2004 = "official_2004"
    #: Added in the 2009 or 2010 edition.
    EXTENSION = "extension"
    #: Our own reconstruction of a metric ROMIP lists but never defines.
    RECONSTRUCTION = "reconstruction"
    #: Diagnostic counter rather than a quality measure.
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: str
    label: str
    description: str
    kind: MetricKind = MetricKind.SCALAR
    edition: MetricEdition = MetricEdition.OFFICIAL_2004
    #: True when the metric reads graded gains rather than the binary table.
    needs_graded: bool = False
    cutoff: int | None = None
    higher_is_better: bool = True
    #: Rendered by the interface with KaTeX.
    formula_tex: str | None = None
    #: Russian label, matching the appendix's own terminology.
    label_ru: str | None = None


def _build() -> dict[str, MetricSpec]:
    specs: list[MetricSpec] = [
        # ---------------- official ROMIP'2004 search-track metrics ----------------
        MetricSpec(
            key="precision",
            label="Precision (set)",
            label_ru="точность",
            description=(
                "Fraction of the whole returned list that is relevant. A set measure, "
                "not P@k — its value moves with the run length, which is why top_k is "
                "reported beside it."
            ),
            formula_tex=r"p = \frac{a}{a+b}",
        ),
        MetricSpec(
            key="recall",
            label="Recall (set)",
            label_ru="полнота",
            description=(
                "Fraction of the relevant documents that were retrieved. Pooled recall: "
                "the denominator counts only judged relevant documents."
            ),
            formula_tex=r"r = \frac{a}{a+c}",
        ),
        MetricSpec(
            key="f1",
            label="F₁",
            label_ru="F-мера",
            description="Harmonic mean of precision and recall.",
            formula_tex=r"F = \frac{2}{\frac{1}{p}+\frac{1}{r}}",
        ),
        MetricSpec(
            key="ap",
            label="Average precision",
            label_ru="средняя точность",
            description=(
                "Mean of the precisions observed at each relevant document, divided by "
                "the number of relevant documents in the judgments. Averaged over "
                "queries this is MAP, the primary metric — the appendix cites Buckley & "
                "Voorhees for its stability against assessor disagreement."
            ),
            formula_tex=r"AP = \frac{1}{R}\sum_{i:\,\mathrm{rel}(d_i)} P@i",
        ),
        MetricSpec(
            key="p_5",
            label="P@5",
            label_ru="точность на уровне 5 документов",
            description="Precision among the top 5. Denominator is always 5.",
            cutoff=5,
            formula_tex=r"P@k = \frac{|\{i \le k : \mathrm{rel}(d_i)\}|}{k}",
        ),
        MetricSpec(
            key="p_10",
            label="P@10",
            label_ru="точность на уровне 10 документов",
            description="Precision among the top 10 — what a user sees on one page.",
            cutoff=10,
            formula_tex=r"P@k = \frac{|\{i \le k : \mathrm{rel}(d_i)\}|}{k}",
        ),
        MetricSpec(
            key="rprec",
            label="R-Precision",
            label_ru="R-точность",
            description=(
                "Precision at rank R, where R is the number of relevant documents. "
                "Comparable across queries with different R, which P@k is not."
            ),
            formula_tex=r"\mathrm{Rprec} = P@R",
        ),
        MetricSpec(
            key="iprec11",
            label="11-point interpolated PR (TREC)",
            label_ru="11-точечный график полноты/точности (TREC)",
            description=(
                "Interpolated precision at eleven standard recall levels. A query that "
                "never reaches a level contributes zero to that level's average."
            ),
            kind=MetricKind.CURVE,
            formula_tex=r"p(r_i) = \max_{n \ge \mathrm{pos}(r_i)} \mathrm{precision}(n)",
        ),
        # ---------------------------- reconstruction ----------------------------
        MetricSpec(
            key="iprec11_nz",
            label="11-point interpolated PR (non-zeroing)",
            label_ru="11-точечный график, модифицированный вариант",
            description=(
                "ROMIP lists a second, 'RIRES-modified' 11-point curve as official but "
                "never defines it in any edition. This is a documented reconstruction: "
                "identical to the TREC method except that unreached recall levels are "
                "omitted rather than scored zero. Plotted against the TREC curve it "
                "shows exactly what the zeroing convention does."
            ),
            kind=MetricKind.CURVE,
            edition=MetricEdition.RECONSTRUCTION,
        ),
        # ------------------- ROMIP 2009/2010 additions -------------------
        MetricSpec(
            key="bpref",
            label="bpref",
            description=(
                "Binary preference. Skips unjudged documents instead of counting them "
                "against the run, so it is the robust measure when the judgment pool "
                "does not cover a ranker. Uses trec_eval's min(N, R) denominator."
            ),
            edition=MetricEdition.EXTENSION,
        ),
        MetricSpec(
            key="mrr",
            label="MRR",
            description="Reciprocal rank of the first relevant document.",
            edition=MetricEdition.EXTENSION,
        ),
        MetricSpec(
            key="ndcg_5",
            label="nDCG@5",
            description="Normalised discounted cumulative gain with ROMIP's 2^g − 1 gain.",
            cutoff=5,
            needs_graded=True,
            edition=MetricEdition.EXTENSION,
            formula_tex=r"\mathrm{DCG@}n = \sum_{p=1}^{n}\frac{2^{g(p)}-1}{\log_2(1+p)}",
        ),
        MetricSpec(
            key="ndcg_10",
            label="nDCG@10",
            description="Normalised DCG over the top 10.",
            cutoff=10,
            needs_graded=True,
            edition=MetricEdition.EXTENSION,
            formula_tex=r"\mathrm{nDCG@}n = \frac{\mathrm{DCG@}n}{Z}",
        ),
        MetricSpec(
            key="err",
            label="ERR",
            description=(
                "Expected reciprocal rank — a cascade model where a document's value is "
                "discounted by the chance the user was still looking."
            ),
            needs_graded=True,
            edition=MetricEdition.EXTENSION,
        ),
        MetricSpec(
            key="pfound",
            label="pFound",
            description="Yandex/ROMIP cascade metric with an explicit abandonment term.",
            needs_graded=True,
            edition=MetricEdition.EXTENSION,
        ),
        # ------------------------------ diagnostics ------------------------------
        MetricSpec(
            key="num_ret",
            label="Retrieved",
            description="Documents returned for this query.",
            edition=MetricEdition.DIAGNOSTIC,
            higher_is_better=False,
        ),
        MetricSpec(
            key="num_rel_ret",
            label="Relevant retrieved",
            description="Relevant documents found.",
            edition=MetricEdition.DIAGNOSTIC,
        ),
        MetricSpec(
            key="num_unjudged_ret",
            label="Unjudged retrieved",
            description=(
                "Returned documents carrying no judgment. A high value means the pool "
                "does not cover this ranker, and that its scores are pessimistic."
            ),
            edition=MetricEdition.DIAGNOSTIC,
            higher_is_better=False,
        ),
        MetricSpec(
            key="num_rel",
            label="R",
            description="Relevant documents in the judgments for this query.",
            edition=MetricEdition.DIAGNOSTIC,
        ),
    ]

    # Additional P@k / nDCG@k entries for whatever cutoffs are configured.
    for k in settings.evaluation.cutoffs:
        if f"p_{k}" not in {spec.key for spec in specs}:
            specs.append(
                MetricSpec(
                    key=f"p_{k}",
                    label=f"P@{k}",
                    description=f"Precision among the top {k}.",
                    cutoff=k,
                )
            )

    return {spec.key: spec for spec in specs}


METRICS: dict[str, MetricSpec] = _build()

#: Reported in the aggregate table, in this order.
PRIMARY_ORDER: tuple[str, ...] = (
    "ap",
    "p_5",
    "p_10",
    "rprec",
    "recall",
    "precision",
    "f1",
    "bpref",
    "ndcg_5",
    "ndcg_10",
    "mrr",
    "err",
    "pfound",
)

#: Curves the runner stores per run.
CURVE_KEYS: tuple[str, ...] = ("iprec11", "iprec11_nz", "pr_raw", "p_at_k")


def official_2004() -> list[MetricSpec]:
    """The eight metrics the cited document actually specifies."""
    return [spec for spec in METRICS.values() if spec.edition is MetricEdition.OFFICIAL_2004]


def scalar_keys() -> list[str]:
    return [
        key
        for key, spec in METRICS.items()
        if spec.kind is MetricKind.SCALAR and spec.edition is not MetricEdition.DIAGNOSTIC
    ]
