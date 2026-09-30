# -*- coding: utf-8 -*-
"""Альтернативный метод ранжирования предложений — TextRank.

Метод из методических указаний учитывает позицию предложения, из-за чего
содержательные предложения из конца документа не попадают в реферат.
Чтобы оценить масштаб этого эффекта, в системе реализован второй,
независимый от позиции алгоритм — TextRank (Mihalcea & Tarau, 2004):

1. Каждое предложение — вершина графа.
2. Рёбра взвешены косинусной близостью tf-idf векторов предложений.
3. По графу запускается алгоритм PageRank; вес вершины тем выше,
   чем больше «голосов» она получает от похожих на неё предложений.

Реализация выполнена на чистом Python без внешних библиотек.
"""
from __future__ import annotations

import math

DAMPING = 0.85
MAX_ITERATIONS = 100
TOLERANCE = 1e-6
SIMILARITY_THRESHOLD = 0.03


def _vectors(scores, term_weights) -> list[dict[str, float]]:
    vectors: list[dict[str, float]] = []
    for sentence in scores:
        vector: dict[str, float] = {}
        for term, tf, weight in sentence.terms:
            vector[term] = tf * weight
        norm = math.sqrt(sum(v * v for v in vector.values()))
        if norm > 0:
            vector = {t: v / norm for t, v in vector.items()}
        vectors.append(vector)
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0.0) for term, value in a.items())


def textrank(scores, term_weights) -> dict[int, float]:
    """Возвращает отображение «индекс предложения -> вес TextRank»."""
    n = len(scores)
    if n == 0:
        return {}
    if n == 1:
        return {scores[0].index: 1.0}

    vectors = _vectors(scores, term_weights)
    # разреженная матрица смежности
    neighbours: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    out_weight = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(vectors[i], vectors[j])
            if sim <= SIMILARITY_THRESHOLD:
                continue
            neighbours[i].append((j, sim))
            neighbours[j].append((i, sim))
            out_weight[i] += sim
            out_weight[j] += sim

    rank = [1.0 / n] * n
    for _ in range(MAX_ITERATIONS):
        updated = [(1.0 - DAMPING) / n] * n
        for i in range(n):
            if out_weight[i] <= 0:
                # висячая вершина распределяет вес равномерно
                share = DAMPING * rank[i] / n
                for k in range(n):
                    updated[k] += share
                continue
            for j, sim in neighbours[i]:
                updated[j] += DAMPING * rank[i] * sim / out_weight[i]
        delta = sum(abs(updated[i] - rank[i]) for i in range(n))
        rank = updated
        if delta < TOLERANCE:
            break

    return {scores[i].index: rank[i] for i in range(n)}


def lead_baseline(scores) -> dict[int, float]:
    """Базовая эвристика Lead-N: чем ближе к началу, тем важнее."""
    n = len(scores)
    return {s.index: float(n - i) for i, s in enumerate(scores)}


def hybrid(scores, term_weights, params) -> dict[int, float]:
    """Комбинация: позиционные функции методички + TextRank.

    Ранг TextRank заменяет «сырую» сумму Score, сохраняя множители
    Posd и Posp; это снижает зависимость от длины предложения.
    """
    tr = textrank(scores, term_weights)
    max_tr = max(tr.values(), default=1.0) or 1.0
    max_score = max((s.score for s in scores), default=1.0) or 1.0
    result: dict[int, float] = {}
    for s in scores:
        content = 0.5 * (s.score / max_score) + 0.5 * (tr.get(s.index, 0.0) / max_tr)
        result[s.index] = (s.posd ** params.alpha) * (s.posp ** params.beta) * content
    return result
