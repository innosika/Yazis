"""Шаг 1. Предварительная обработка входного текста.

Одна и та же функция normalize() применяется и к тренировочному корпусу,
и к анализируемым документам — это принципиально для сопоставимости профилей.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Оставляем только буквы (любых алфавитов) и пробелы. Цифры, пунктуация, символы — шум для всех трёх методов.
_KEEP = re.compile(r"[^\w\s]|[\d_]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def html_to_text(raw: str | bytes) -> str:
    """Извлекает видимый текст из HTML: убирает теги, скрипты и стили."""
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "head"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return _SPACES.sub(" ", text).strip()


def normalize(text: str) -> str:
    """Нижний регистр, только буквы и одиночные пробелы."""
    text = text.lower()
    text = _KEEP.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def words(text: str) -> list[str]:
    return normalize(text).split()
