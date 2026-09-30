"""Метод N-грамм (Cavnar & Trenkle, «N-Gram-Based Text Categorization», 1994).

1. Каждое слово обрамляется пробелами-маркерами: «_слово_».
2. Из него извлекаются все подстроки длиной 1..N (N = 5).
3. Профиль языка/документа — топ-300 N-грамм по убыванию частоты.
4. Расстояние out-of-place: сумма |ранг в профиле документа − ранг в профиле языка|;
   для N-граммы, отсутствующей в профиле языка, — максимальный штраф (300).
5. Язык = профиль с минимальным расстоянием.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..config import NGRAM_MAX_N, NGRAM_MISSING_PENALTY, NGRAM_PROFILE_SIZE
from .base import LanguageDetector


def extract_ngrams(text: str, max_n: int = NGRAM_MAX_N) -> Counter:
    counts: Counter = Counter()
    for word in text.split():
        padded = f"_{word}_"
        L = len(padded)
        for n in range(1, max_n + 1):
            for i in range(L - n + 1):
                counts[padded[i:i + n]] += 1
    return counts


def build_profile(text: str, size: int = NGRAM_PROFILE_SIZE) -> list[str]:
    """Упорядоченный список N-грамм: индекс = ранг."""
    counts = extract_ngrams(text)
    # сортировка по убыванию частоты, при равенстве — лексикографически (детерминированность)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [g for g, _ in ordered[:size]]


def out_of_place(doc_profile: list[str], lang_rank: dict[str, int],
                 penalty: int = NGRAM_MISSING_PENALTY) -> int:
    dist = 0
    for rank, gram in enumerate(doc_profile):
        lang_pos = lang_rank.get(gram)
        dist += penalty if lang_pos is None else abs(rank - lang_pos)
    return dist


class NGramDetector(LanguageDetector):
    id = "ngram"
    title = "N-грамм"
    metric_name = "расстояние out-of-place"
    lower_is_better = True

    def __init__(self) -> None:
        self.profiles: dict[str, list[str]] = {}
        self.ranks: dict[str, dict[str, int]] = {}

    def fit(self, corpus: dict[str, str]) -> None:
        for lang, text in corpus.items():
            profile = build_profile(text)
            self.profiles[lang] = profile
            self.ranks[lang] = {g: i for i, g in enumerate(profile)}

    def _predict(self, text: str) -> tuple[str, float, dict[str, float], dict[str, Any]]:
        doc_profile = build_profile(text)
        if not doc_profile:
            return "en", 0.0, {l: 0.0 for l in self.ranks}, {"doc_profile": []}
        scores = {lang: float(out_of_place(doc_profile, ranks)) for lang, ranks in self.ranks.items()}
        ordered = sorted(scores.items(), key=lambda kv: kv[1])
        best, second = ordered[0], ordered[1] if len(ordered) > 1 else (None, ordered[0][1])
        max_possible = len(doc_profile) * NGRAM_MISSING_PENALTY
        confidence = (second[1] - best[1]) / max_possible if max_possible else 0.0
        return best[0], min(1.0, confidence * 3), scores, {
            "doc_profile": doc_profile[:20],
            "doc_profile_size": len(doc_profile),
            "matched": {lang: sum(1 for g in doc_profile if g in r) for lang, r in self.ranks.items()},
        }
