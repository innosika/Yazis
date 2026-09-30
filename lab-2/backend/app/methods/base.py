"""Общий интерфейс методов распознавания языка."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Detection:
    method: str                 # идентификатор метода
    lang: str                   # предсказанный язык ("ru"/"en")
    confidence: float           # 0..1 — уверенность
    scores: dict[str, float]    # метрика по каждому языку (для N-грамм — расстояние, для НС — вероятность)
    elapsed_ms: float           # время распознавания
    details: dict[str, Any] = field(default_factory=dict)  # пояснения для интерфейса


class LanguageDetector(ABC):
    id: str = "base"
    title: str = "Метод"
    metric_name: str = "метрика"
    lower_is_better: bool = True

    @abstractmethod
    def fit(self, corpus: dict[str, str]) -> None:
        """corpus: {lang: большой нормализованный текст}"""

    @abstractmethod
    def _predict(self, text: str) -> tuple[str, float, dict[str, float], dict[str, Any]]:
        """Возвращает (lang, confidence, scores, details) для нормализованного текста."""

    def predict(self, normalized_text: str) -> Detection:
        t0 = time.perf_counter()
        lang, conf, scores, details = self._predict(normalized_text)
        elapsed = (time.perf_counter() - t0) * 1000
        return Detection(self.id, lang, round(conf, 4), scores, round(elapsed, 3), details)
