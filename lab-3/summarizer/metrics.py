# -*- coding: utf-8 -*-
"""Метрики оценки качества реферата.

Используются стандартные в автоматическом реферировании меры семейства
ROUGE (Recall-Oriented Understudy for Gisting Evaluation), вычисляемые по
основам слов, а также прикладные показатели: степень сжатия, покрытие
ключевых слов и согласованность разных методов.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class PRF:
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict:
        return {"precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4)}


def _prf(overlap: int, candidate: int, reference: int) -> PRF:
    precision = overlap / candidate if candidate else 0.0
    recall = overlap / reference if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(precision, recall, f1)


def rouge_n(candidate: list[str], reference: list[str], n: int = 1) -> PRF:
    """ROUGE-N: пересечение n-грамм реферата и эталона."""
    def ngrams(seq: list[str]) -> dict[tuple[str, ...], int]:
        result: dict[tuple[str, ...], int] = {}
        for i in range(len(seq) - n + 1):
            key = tuple(seq[i:i + n])
            result[key] = result.get(key, 0) + 1
        return result

    cand, ref = ngrams(candidate), ngrams(reference)
    overlap = sum(min(count, ref.get(gram, 0)) for gram, count in cand.items())
    return _prf(overlap, sum(cand.values()), sum(ref.values()))


def rouge_l(candidate: list[str], reference: list[str]) -> PRF:
    """ROUGE-L: наибольшая общая подпоследовательность (LCS)."""
    if not candidate or not reference:
        return PRF(0.0, 0.0, 0.0)
    previous = [0] * (len(reference) + 1)
    for c in candidate:
        current = [0]
        for j, r in enumerate(reference, start=1):
            current.append(previous[j - 1] + 1 if c == r else max(previous[j], current[j - 1]))
        previous = current
    return _prf(previous[-1], len(candidate), len(reference))


def selection_agreement(a: list[int], b: list[int]) -> float:
    """Коэффициент Жаккара между наборами выбранных предложений."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def keyword_coverage(summary_terms: set[str], keywords: list[str]) -> float:
    """Доля ключевых слов документа, представленных в классическом реферате."""
    if not keywords:
        return 0.0
    return sum(1 for k in keywords if k in summary_terms) / len(keywords)


def compression(summary_chars: int, document_chars: int) -> float:
    """Степень сжатия: доля символов исходного текста, попавшая в реферат."""
    return summary_chars / document_chars if document_chars else 0.0


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Косинусная близость двух взвешенных векторов терминов."""
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(value * b.get(term, 0.0) for term, value in a.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
