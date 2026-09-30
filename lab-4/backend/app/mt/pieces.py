"""The output representation shared by both translation architectures.

A translation is not a string but a list of pieces, each of which remembers which source
tokens produced it. That is what makes the alignment view, the per-word grammatical
information and the stage trace possible - and it is also what lets the detokeniser decide
spacing from a token's kind rather than by guessing from characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    WORD = "word"
    """A translated word or multiword unit."""
    PUNCT = "punct"
    FUNCTION = "function"
    """A function word supplied by a rule rather than by the dictionary: «не», «и», «однако»."""
    PREPOSITION = "preposition"
    """A Russian preposition inserted by the transfer rules."""
    AUXILIARY = "auxiliary"
    """An auxiliary the rules had to add: «будет», «был», «должен»."""
    UNTRANSLATED = "untranslated"
    """No dictionary entry; kept in Latin script or transcribed."""
    DROPPED = "dropped"
    """Present in the source, deliberately absent from the output."""


@dataclass(slots=True)
class Piece:
    surface: str
    kind: Kind
    source_indices: tuple[int, ...] = ()
    source_text: str = ""
    lemma: str = ""
    tag: str = ""
    decoded: tuple[str, ...] = ()
    case: str | None = None
    note: str = ""
    order: float = 0.0
    """Sort key for the output. Fractional so a piece can be slotted between two others."""

    @property
    def visible(self) -> bool:
        return self.kind is not Kind.DROPPED and bool(self.surface)


@dataclass(slots=True)
class SentenceTranslation:
    index: int
    source: str
    target: str
    pieces: list[Piece] = field(default_factory=list)
    stages: dict[str, str] = field(default_factory=dict)
    """Intermediate result after each pipeline stage, for the architecture comparison."""
    tm_match: dict[str, Any] | None = None
    edited: bool = False


_NO_SPACE_BEFORE = frozenset(".,;:!?)]}»…%’'")
_NO_SPACE_AFTER = frozenset("([{«‘")
_SENTENCE_END = re.compile(r"[.!?…]$")


def detokenise(pieces: list[Piece]) -> str:
    """Join pieces into Russian text with correct spacing and capitalisation."""
    out: list[str] = []
    for piece in pieces:
        if not piece.visible:
            continue
        surface = piece.surface
        if not out:
            out.append(surface)
            continue
        previous = out[-1]
        no_space = (
            surface[0] in _NO_SPACE_BEFORE
            or previous[-1:] in _NO_SPACE_AFTER
            or surface.startswith("-")
            or previous.endswith("-")
        )
        out.append(surface if no_space else " " + surface)

    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:!?)»…])", r"\1", text)
    text = re.sub(r"([(«])\s+", r"\1", text)
    return capitalise(text)


def capitalise(text: str) -> str:
    """Capitalise the first letter without touching the rest, which may be an acronym."""
    for index, character in enumerate(text):
        if character.isalpha():
            return text[:index] + character.upper() + text[index + 1 :]
    return text


def join_sentences(sentences: list[SentenceTranslation]) -> str:
    """Join translated sentences, keeping paragraph breaks from the source."""
    out: list[str] = []
    for translation in sentences:
        target = translation.target.strip()
        if not target:
            continue
        if out and not _SENTENCE_END.search(out[-1]):
            out.append(".")
        out.append(target)
    return " ".join(out).replace(" .", ".")
