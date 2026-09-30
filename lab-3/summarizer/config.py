# -*- coding: utf-8 -*-
"""Параметры системы автоматического реферирования."""
from __future__ import annotations

import os
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_DIR = os.path.join(ROOT, "data", "collection")
EXPORT_DIR = os.path.join(ROOT, "data", "output")

#: рекомендуемый методичкой размер классического реферата
DEFAULT_SUMMARY_SENTENCES = 10
#: размер реферата в виде списка ключевых слов
DEFAULT_KEYWORDS = 15


@dataclass(slots=True)
class SummaryParams:
    """Настройки построения реферата.

    ``alpha``/``beta`` — показатели степени у позиционных функций Posd и Posp.
    Значение 1.0 соответствует формуле методических указаний;
    значение 0.0 полностью отключает влияние позиции (исследовательский режим,
    позволяющий увидеть позиционный перекос базовой формулы).
    """

    sentences: int = DEFAULT_SUMMARY_SENTENCES
    keywords: int = DEFAULT_KEYWORDS
    alpha: float = 1.0                 # степень Posd
    beta: float = 1.0                  # степень Posp
    method: str = "tfidf"              # tfidf | textrank | lead | hybrid
    conflate_stems: bool = True        # склейка близких основ (улучшение)
    mmr_lambda: float = 1.0            # 1.0 — без подавления повторов
    length_norm: str = "none"          # none | sqrt | linear — нормировка Score

    def clamp(self) -> "SummaryParams":
        self.sentences = max(1, min(50, int(self.sentences)))
        self.keywords = max(1, min(60, int(self.keywords)))
        self.alpha = max(0.0, min(4.0, float(self.alpha)))
        self.beta = max(0.0, min(4.0, float(self.beta)))
        self.mmr_lambda = max(0.1, min(1.0, float(self.mmr_lambda)))
        if self.method not in ("tfidf", "textrank", "lead", "hybrid"):
            self.method = "tfidf"
        if self.length_norm not in ("none", "sqrt", "linear"):
            self.length_norm = "none"
        return self
