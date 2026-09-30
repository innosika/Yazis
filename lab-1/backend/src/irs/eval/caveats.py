"""Per-collection caveats on what a metric value can mean.

A metric can be arithmetically correct and still misleading. On the known-item collection
every topic has exactly one relevant document and no judged non-relevant ones, so recall
and bpref collapse to "was the document found" and print ``1.0000`` — which reads as a
perfect score. Set precision divides by the run length, so a 100-document run shows
``0.0100`` next to a short run's ``0.4697`` and invites a comparison down a column that
means nothing.

These rules decide, from the *judgments alone*, which cells to suppress (``n/a`` with a
footnote) and which to annotate. They are pure so they can be tested without a database,
and they deliberately never touch :mod:`irs.eval.metrics`: the arithmetic is right, it is
the presentation that needs care.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from irs.eval.metrics import QueryJudgments

CaveatKind = Literal["degenerate", "annotate"]


@dataclass(frozen=True, slots=True)
class MetricCaveat:
    #: Metric the caveat applies to, or ``"*"`` for the whole table.
    metric_key: str
    kind: CaveatKind
    note: str


def metric_caveats(
    judgments: Mapping[int, QueryJudgments],
    top_k: int,
    single_assessor: bool = False,
) -> list[MetricCaveat]:
    """Caveats for a table computed over ``judgments`` with runs of depth ``top_k``."""
    caveats: list[MetricCaveat] = []
    if not judgments:
        return caveats

    marks = list(judgments.values())
    known_item_shaped = all(m.r == 1 for m in marks) and all(m.n == 0 for m in marks)

    if known_item_shaped:
        found = (
            "every topic has exactly one relevant document (R = 1) and no judged "
            "non-relevant ones, so the value collapses to «was it found» — it equals "
            "the fraction of topics whose target was retrieved and says nothing about "
            "ranking quality"
        )
        caveats.append(MetricCaveat("recall", "degenerate", f"recall: {found}"))
        caveats.append(MetricCaveat("bpref", "degenerate", f"bpref: {found}"))
        caveats.append(
            MetricCaveat(
                "precision",
                "degenerate",
                "precision (set): with R = 1 it cannot exceed 1/top_k "
                f"(= {1 / top_k:.4f} for top_k = {top_k}); it measures run length, "
                "not quality",
            )
        )
        caveats.append(
            MetricCaveat(
                "f1",
                "degenerate",
                "F₁: harmonic mean of two degenerate values (see precision and recall)",
            )
        )
    else:
        caveats.append(
            MetricCaveat(
                "precision",
                "annotate",
                "precision and recall are set measures over the whole returned list "
                f"(top_k = {top_k}); their values move with the run length",
            )
        )
        caveats.append(
            MetricCaveat(
                "recall",
                "annotate",
                "recall is *pooled* recall: the denominator counts only judged relevant documents",
            )
        )

    if single_assessor:
        caveats.append(
            MetricCaveat(
                "*",
                "annotate",
                "every pair carries one assessment, so the «or» and «and» relevance "
                "tables coincide and inter-assessor agreement is not measured",
            )
        )
    return caveats


def degenerate_keys(caveats: list[MetricCaveat]) -> frozenset[str]:
    return frozenset(c.metric_key for c in caveats if c.kind == "degenerate")
