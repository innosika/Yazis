# -*- coding: utf-8 -*-
"""Построение классического реферата методом sentence extraction.

Вес предложения Si есть произведение трёх функций:

    W(Si) = Posd(Si) * Posp(Si) * Score(Si)

    Posd(Si)  = 1 - BD(Si) / |D|     — положение предложения в документе;
    Posp(Si)  = 1 - BP(Si) / |P|     — положение предложения в абзаце;
    Score(Si) = SUM_t tf(t, Si) * w(t, D)  — содержательная насыщенность.

Генерация реферата — выбор N предложений с наибольшим весом, выводимых
в том порядке, в котором они идут в исходном тексте.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import SummaryParams
from .weights import TermWeight


@dataclass(slots=True)
class SentenceScore:
    """Предложение с рассчитанными составляющими веса."""

    index: int
    text: str
    paragraph: int
    start: int
    end: int
    posd: float
    posp: float
    score: float
    weight: float
    terms: list[tuple[str, int, float]] = field(default_factory=list)

    def as_dict(self, doc_terms: dict[str, TermWeight] | None = None) -> dict:
        top = sorted(self.terms, key=lambda x: -x[1] * x[2])[:6]
        return {
            "index": self.index,
            "text": self.text,
            "paragraph": self.paragraph,
            "start": self.start,
            "end": self.end,
            "posd": round(self.posd, 4),
            "posp": round(self.posp, 4),
            "score": round(self.score, 3),
            "weight": round(self.weight, 4),
            "term_list": sorted({t for t, _, _ in self.terms}),
            "top_terms": [
                {
                    "form": (doc_terms[t].form if doc_terms and t in doc_terms else t),
                    "tf": tf,
                    "w": round(w, 3),
                    "contribution": round(tf * w, 3),
                }
                for t, tf, w in top
            ],
        }


def position_in_document(sentence, doc_length: int) -> float:
    """Posd(Si) = 1 - BD(Si) / |D|."""
    if doc_length <= 0:
        return 1.0
    return max(0.0, 1.0 - sentence.start / doc_length)


def position_in_paragraph(sentence) -> float:
    """Posp(Si) = 1 - BP(Si) / |P|."""
    if sentence.para_len <= 0:
        return 1.0
    return max(0.0, 1.0 - sentence.para_start / sentence.para_len)


def score_sentences(document, term_weights: dict[str, TermWeight],
                    params: SummaryParams) -> list[SentenceScore]:
    """Вычисляет веса всех предложений документа."""
    doc_length = document.length
    result: list[SentenceScore] = []
    for sentence, tokens in zip(document.sentences, document.sentence_tokens):
        tf_local: dict[str, int] = {}
        for token in tokens:
            tf_local[token.term] = tf_local.get(token.term, 0) + 1

        contributions: list[tuple[str, int, float]] = []
        score = 0.0
        for term, tf in tf_local.items():
            tw = term_weights.get(term)
            if tw is None or tw.weight <= 0:
                continue
            score += tf * tw.weight
            contributions.append((term, tf, tw.weight))

        # нормировка Score по длине предложения (исследовательский режим):
        # в формуле методички её нет, из-за чего в реферат попадают самые
        # длинные предложения — сумма по большему числу слов всегда больше
        if params.length_norm == "sqrt" and tokens:
            score /= len(tokens) ** 0.5
        elif params.length_norm == "linear" and tokens:
            score /= len(tokens)

        posd = position_in_document(sentence, doc_length)
        posp = position_in_paragraph(sentence)
        weight = (posd ** params.alpha) * (posp ** params.beta) * score

        result.append(SentenceScore(
            index=sentence.index, text=sentence.text,
            paragraph=sentence.paragraph, start=sentence.start, end=sentence.end,
            posd=posd, posp=posp, score=score, weight=weight,
            terms=contributions,
        ))
    return result


def select_sentences(scores: list[SentenceScore], count: int,
                     *, mmr_lambda: float = 1.0,
                     ranking: dict[int, float] | None = None) -> list[int]:
    """Отбирает индексы предложений реферата.

    При ``mmr_lambda`` < 1 используется процедура MMR (Maximal Marginal
    Relevance): на каждом шаге выбирается предложение, максимизирующее
    lambda * вес - (1 - lambda) * максимальное сходство с уже выбранными,
    что подавляет повторы в реферате.
    """
    if not scores:
        return []
    weights = ranking if ranking is not None else {s.index: s.weight for s in scores}
    order = sorted(scores, key=lambda s: -weights.get(s.index, 0.0))

    if mmr_lambda >= 0.999:
        chosen = [s.index for s in order[:count]]
        return sorted(chosen)

    max_weight = max(weights.values()) or 1.0
    term_sets = {s.index: {t for t, _, _ in s.terms} for s in scores}
    chosen: list[int] = []
    candidates = [s.index for s in order]
    while candidates and len(chosen) < count:
        best, best_value = None, float("-inf")
        for idx in candidates:
            relevance = weights.get(idx, 0.0) / max_weight
            redundancy = 0.0
            for picked in chosen:
                a, b = term_sets[idx], term_sets[picked]
                if a and b:
                    redundancy = max(redundancy, len(a & b) / len(a | b))
            value = mmr_lambda * relevance - (1.0 - mmr_lambda) * redundancy
            if value > best_value:
                best, best_value = idx, value
        chosen.append(best)
        candidates.remove(best)
    return sorted(chosen)


def render_summary(scores: list[SentenceScore], indices: list[int]) -> str:
    """Собирает текст реферата в порядке следования предложений в документе."""
    by_index = {s.index: s for s in scores}
    return " ".join(by_index[i].text for i in sorted(indices) if i in by_index)
