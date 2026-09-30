"""TREC-format export, for validation against ``trec_eval``/``pytrec_eval``.

Two implementations of a metric agreeing is the only practical evidence that either is
right. ``pytrec_eval`` vendors the actual NIST ``trec_eval`` C sources, so its numbers
*are* ``trec_eval``'s; exporting to the format it consumes lets the whole metric core be
checked against the reference implementation.

Formats:
    run   — ``qid Q0 docid rank score runid``
    qrels — ``qid 0 docid relevance``

One caveat carried into the tests: ``pytrec_eval`` silently ignores queries absent from
the qrels, so ``num_q`` has to be asserted independently rather than inferred from a mean.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from irs.eval.metrics import QueryJudgments


def format_run(rankings: Mapping[int, Iterable[tuple[int, float]]], run_id: str = "irs") -> str:
    """Render a run as TREC six-column text.

    Args:
        rankings: query id → iterable of ``(document_id, score)`` in rank order.
        run_id: identifier recorded in the last column.
    """
    lines: list[str] = []
    for query_id in sorted(rankings):
        for rank, (document_id, score) in enumerate(rankings[query_id], start=1):
            lines.append(f"{query_id} Q0 {document_id} {rank} {score:.6f} {run_id}")
    return "\n".join(lines) + ("\n" if lines else "")


def format_qrels(judgments: Mapping[int, QueryJudgments]) -> str:
    """Render a relevance table as TREC four-column text.

    Graded gains are written rather than the binary flag, so a consumer can compute
    graded measures too. Judged non-relevant documents are written explicitly with 0 —
    omitting them would make ``bpref`` treat them as unjudged and change its value.
    """
    lines: list[str] = []
    for query_id in sorted(judgments):
        marks = judgments[query_id]
        for document_id in sorted(marks.relevant):
            grade = round(marks.gain(document_id)) or 1
            lines.append(f"{query_id} 0 {document_id} {grade}")
        for document_id in sorted(marks.non_relevant):
            lines.append(f"{query_id} 0 {document_id} 0")
    return "\n".join(lines) + ("\n" if lines else "")


def to_pytrec_eval(
    rankings: Mapping[int, Iterable[tuple[int, float]]],
    judgments: Mapping[int, QueryJudgments],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, float]]]:
    """Build the dict pair ``pytrec_eval`` expects.

    Returns ``(qrels, run)`` with string keys, as the library requires.
    """
    qrels: dict[str, dict[str, int]] = {}
    for query_id, marks in judgments.items():
        entry: dict[str, int] = {}
        for document_id in marks.relevant:
            entry[str(document_id)] = round(marks.gain(document_id)) or 1
        for document_id in marks.non_relevant:
            entry[str(document_id)] = 0
        qrels[str(query_id)] = entry

    run: dict[str, dict[str, float]] = {
        str(query_id): {str(document_id): float(score) for document_id, score in ranking}
        for query_id, ranking in rankings.items()
    }
    return qrels, run
