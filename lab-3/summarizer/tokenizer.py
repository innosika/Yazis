# -*- coding: utf-8 -*-
"""Токенизация и фильтрация слов документа.

Согласно методическим указаниям при вычислении весов не учитываются:
  * числа;
  * слова, записанные буквами «чужого» алфавита (для русского документа —
    латиница, для английского — кириллица);
  * стоп-слова.
Оставшиеся слова приводятся к основе стеммером и становятся терминами.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .stemmer import stem
from .stopwords import STOPWORDS

# Слово: последовательность букв, возможно с дефисом или апострофом внутри.
# Диакритические знаки (в частности, знак ударения U+0301 в русских текстах
# Wikipedia) считаются частью слова, иначе «иску́сственный» распалось бы на
# два токена.
_LETTER = r"(?:[^\W\d_]|[\u0300-\u036f])"
_TOKEN_RE = re.compile(rf"[^\W\d_]{_LETTER}*(?:[-'’]{_LETTER}+)*", re.UNICODE)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")

MIN_TOKEN_LENGTH = 3


@dataclass(slots=True)
class Token:
    """Одно слово текста: словоформа, основа и позиция."""

    surface: str    # словоформа в исходном виде (как в тексте)
    norm: str       # нормализованная словоформа (нижний регистр)
    term: str       # основа слова (stem) — собственно термин
    start: int      # смещение в обрабатываемой строке
    end: int


def strip_accents(text: str) -> str:
    """Убирает знаки ударения (U+0301 и т.п.), сохраняя букву «ё»."""
    if not any(ord(ch) in (0x0300, 0x0301, 0x0308) for ch in text):
        return text
    decomposed = unicodedata.normalize("NFD", text)
    cleaned = "".join(ch for ch in decomposed if ord(ch) not in (0x0300, 0x0301))
    return unicodedata.normalize("NFC", cleaned)


def is_foreign(word: str, lang: str) -> bool:
    """Слово записано алфавитом, чуждым языку документа."""
    if lang == "ru":
        return bool(_LATIN_RE.search(word)) and not _CYRILLIC_RE.search(word)
    if lang == "en":
        return bool(_CYRILLIC_RE.search(word))
    return False


def tokenize(text: str, lang: str, *, keep_all: bool = False) -> list[Token]:
    """Разбивает текст на значимые токены.

    ``keep_all=True`` отключает фильтрацию (используется для статистики
    «сколько слов отброшено»).
    """
    stop = STOPWORDS.get(lang, frozenset())
    tokens: list[Token] = []
    for match in _TOKEN_RE.finditer(text):
        surface = match.group(0)
        norm = strip_accents(surface).lower().replace("’", "'")
        if not keep_all:
            if len(norm) < MIN_TOKEN_LENGTH:
                continue
            if is_foreign(norm, lang):
                continue
            if norm in stop or norm.replace("ё", "е") in stop:
                continue
        tokens.append(Token(surface=surface, norm=norm,
                            term=stem(norm.replace("ё", "е"), lang),
                            start=match.start(), end=match.end()))
    return tokens


def count_tokens(text: str) -> int:
    """Общее число словоформ в тексте (без какой-либо фильтрации)."""
    return sum(1 for _ in _TOKEN_RE.finditer(text))


_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")


def filter_report(text: str, lang: str) -> dict[str, int]:
    """Показывает, сколько слов и по какой причине отброшено при фильтрации.

    Используется в статистике коллекции: наглядно видно, какую долю текста
    составляют стоп-слова и служебные единицы, не несущие темы документа.
    """
    stop = STOPWORDS.get(lang, frozenset())
    report = {"words": 0, "numbers": len(_NUMBER_RE.findall(text)),
              "short": 0, "foreign": 0, "stopwords": 0, "kept": 0}
    for match in _TOKEN_RE.finditer(text):
        report["words"] += 1
        norm = strip_accents(match.group(0)).lower().replace("’", "'")
        if len(norm) < MIN_TOKEN_LENGTH:
            report["short"] += 1
        elif is_foreign(norm, lang):
            report["foreign"] += 1
        elif norm in stop or norm.replace("ё", "е") in stop:
            report["stopwords"] += 1
        else:
            report["kept"] += 1
    return report
