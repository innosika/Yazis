# -*- coding: utf-8 -*-
"""Сегментация документа: абзацы, предложения, их позиции в символах.

Структуры данных модуля — фундамент для расчёта позиционных функций
Posd и Posp, которым нужны точные смещения предложения в документе
и в абзаце (в символах).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
#                            структуры данных
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Sentence:
    """Предложение документа вместе с его координатами."""

    index: int            # порядковый номер в документе (с нуля)
    text: str             # текст предложения
    start: int            # смещение первого символа в документе, BD(Si)
    end: int              # смещение конца предложения в документе
    paragraph: int        # номер абзаца
    para_start: int       # смещение первого символа в абзаце, BP(Si)
    para_len: int         # длина абзаца |P|

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(slots=True)
class Paragraph:
    """Абзац документа."""

    index: int
    text: str
    start: int
    end: int
    sentences: list[int] = field(default_factory=list)

    @property
    def length(self) -> int:
        return self.end - self.start


# --------------------------------------------------------------------------
#                        разбиение на абзацы
# --------------------------------------------------------------------------

_PARA_SPLIT_DOUBLE = re.compile(r"\n[ \t]*\n+")
_PARA_SPLIT_SINGLE = re.compile(r"\n+")


def split_paragraphs(text: str) -> list[Paragraph]:
    """Разбивает текст на абзацы, сохраняя их смещения в документе."""
    pattern = _PARA_SPLIT_DOUBLE if _PARA_SPLIT_DOUBLE.search(text) else _PARA_SPLIT_SINGLE
    paragraphs: list[Paragraph] = []
    pos = 0
    for chunk in pattern.split(text):
        start = text.find(chunk, pos) if chunk else pos
        if not chunk.strip():
            pos = start + len(chunk)
            continue
        # выравнивание границ по непробельным символам
        lead = len(chunk) - len(chunk.lstrip())
        body = chunk.strip()
        paragraphs.append(Paragraph(index=len(paragraphs), text=body,
                                    start=start + lead,
                                    end=start + lead + len(body)))
        pos = start + len(chunk)
    return paragraphs


# --------------------------------------------------------------------------
#                       разбиение на предложения
# --------------------------------------------------------------------------

# Сокращения, после которых точка не заканчивает предложение
_ABBREVIATIONS = {
    # русские
    "т", "тт", "д", "п", "пп", "г", "гг", "в", "вв", "стр", "рис", "табл", "см",
    "ср", "им", "др", "пр", "проф", "акад", "доц", "канд", "техн", "физ", "мат",
    "наук", "руб", "тыс", "млн", "млрд", "чел", "обл", "респ", "ул", "жур",
    "изд", "ред", "сост", "гл", "ч", "мин", "сек", "ок", "напр", "англ", "нем",
    "фр", "лат", "греч", "рус", "нач", "кон", "ст", "н", "э", "вып", "кн",
    # английские
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g",
    "i.e", "fig", "eq", "al", "ed", "eds", "vol", "no", "pp", "ca", "cf",
    "inc", "ltd", "dept", "univ", "approx", "est", "min", "max", "ph",
}

_SENT_END = re.compile(r"[.!?…]+[\"»'”\)\]]*")
_WORD_CHARS = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_sentence_boundary(text: str, match: re.Match[str]) -> bool:
    """Решает, действительно ли найденная точка завершает предложение."""
    end = match.end()
    start = match.start()

    # конец текста — всегда граница
    if end >= len(text):
        return True

    # ...после точки должен идти пробельный символ
    if not text[end].isspace():
        return False

    # слово перед знаком препинания
    left = text[:start]
    m = re.search(r"([^\W\d_]+|\d+)\s*$", left, re.UNICODE)
    token = m.group(0).strip().lower() if m else ""

    if match.group(0).startswith("."):
        # инициалы и однобуквенные сокращения: «А. С. Пушкин», «т. д.»
        if len(token) == 1 and _WORD_CHARS.match(token):
            return False
        if token in _ABBREVIATIONS:
            return False
        # числовые перечисления «1.» в начале строки
        if token.isdigit() and (start - len(token) == 0 or text[start - len(token) - 1] == "\n"):
            return False

    # следующее непробельное слово должно начинаться с заглавной буквы,
    # цифры или кавычки (эвристика для русского и английского текста)
    rest = text[end:].lstrip()
    if not rest:
        return True
    ch = rest[0]
    if ch.islower() and unicodedata.category(ch).startswith("L"):
        return False
    return True


def split_sentences(text: str, paragraphs: list[Paragraph]) -> list[Sentence]:
    """Разбивает каждый абзац на предложения с сохранением смещений."""
    sentences: list[Sentence] = []
    for para in paragraphs:
        body = para.text
        cursor = 0
        bounds: list[tuple[int, int]] = []
        for match in _SENT_END.finditer(body):
            if _is_sentence_boundary(body, match):
                bounds.append((cursor, match.end()))
                cursor = match.end()
                while cursor < len(body) and body[cursor].isspace():
                    cursor += 1
        if cursor < len(body):
            bounds.append((cursor, len(body)))

        for s_start, s_end in bounds:
            raw = body[s_start:s_end]
            stripped = raw.strip()
            if len(stripped) < 2 or not _WORD_CHARS.search(stripped):
                continue
            lead = len(raw) - len(raw.lstrip())
            local_start = s_start + lead
            sentence = Sentence(
                index=len(sentences),
                text=stripped,
                start=para.start + local_start,
                end=para.start + local_start + len(stripped),
                paragraph=para.index,
                para_start=local_start,
                para_len=para.length,
            )
            para.sentences.append(sentence.index)
            sentences.append(sentence)
    return sentences


# --------------------------------------------------------------------------
#                        определение языка документа
# --------------------------------------------------------------------------

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """Определяет язык документа по преобладающему алфавиту («ru» или «en»)."""
    cyr = len(_CYRILLIC.findall(text))
    lat = len(_LATIN.findall(text))
    return "ru" if cyr >= lat else "en"
