"""Алфавитный метод.

Идея: каждый язык использует свой набор символов. Для русского — кириллица (а-я, ё),
для английского — латиница (a-z). Для входного текста считаем:
  • доля букв, принадлежащих алфавиту каждого языка (главный признак);
  • косинусное сходство распределения частот букв текста с эталонным распределением языка,
    построенным по тренировочному корпусу (уточняющий признак: помогает, когда алфавиты
    пересекаются или текст содержит транслит/заимствования).
Итоговая оценка = 0.7·доля + 0.3·сходство. Язык с максимальной оценкой — ответ.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .base import LanguageDetector

ALPHABETS: dict[str, frozenset[str]] = {
    "ru": frozenset("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"),
    "en": frozenset("abcdefghijklmnopqrstuvwxyz"),
}
W_SHARE, W_COS = 0.7, 0.3


def letter_distribution(text: str, alphabet: frozenset[str]) -> dict[str, float]:
    counts = Counter(ch for ch in text if ch in alphabet)
    total = sum(counts.values()) or 1
    return {ch: c / total for ch, c in counts.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class AlphabetDetector(LanguageDetector):
    id = "alphabet"
    title = "Алфавитный"
    metric_name = "оценка принадлежности"
    lower_is_better = False

    def __init__(self) -> None:
        self.reference: dict[str, dict[str, float]] = {}

    def fit(self, corpus: dict[str, str]) -> None:
        for lang, text in corpus.items():
            self.reference[lang] = letter_distribution(text, ALPHABETS[lang])

    def _predict(self, text: str) -> tuple[str, float, dict[str, float], dict[str, Any]]:
        letters = [ch for ch in text if ch.isalpha()]
        total = len(letters) or 1
        shares, cosines, scores = {}, {}, {}
        for lang, alphabet in ALPHABETS.items():
            share = sum(1 for ch in letters if ch in alphabet) / total
            cos = cosine(letter_distribution(text, alphabet), self.reference.get(lang, {}))
            shares[lang], cosines[lang] = round(share, 4), round(cos, 4)
            scores[lang] = round(W_SHARE * share + W_COS * cos, 4)
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        best = ordered[0]
        second = ordered[1][1] if len(ordered) > 1 else 0.0
        confidence = min(1.0, (best[1] - second) * 1.5) if letters else 0.0
        return best[0], confidence, scores, {"shares": shares, "cosine": cosines, "letters": len(letters)}
