"""The reading structure every importer produces: blocks, sentences, playback units.

A document is a flat list of blocks (headings, paragraphs, list items, display
equations). Each block carries its text once; sentences and playback units are spans
into that text, computed here on the server so the reader and the extension segment
text identically. Sections are an index over the heading blocks.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from app.text.segment import MATH_PATTERN, split_sentences, split_units

BlockKind = Literal["heading", "paragraph", "item", "equation"]

# Headings after which the rest of a paper is not worth reading aloud.
STOP_HEADINGS = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(references|bibliography|works cited|acknowledg(?:e)?ments?)\s*$",
    re.IGNORECASE,
)
_MATH = MATH_PATTERN


@dataclass
class RawBlock:
    kind: BlockKind
    text: str
    level: int = 0


@dataclass
class ImportedDocument:
    title: str
    blocks: list[RawBlock]
    authors: list[str] = field(default_factory=list)
    source: dict[str, Any] = field(default_factory=dict)


LIGATURES = str.maketrans(
    {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "ft",
        "ﬆ": "st",
        "­": "",
        "​": "",
        "‌": "",
        "﻿": "",
    }
)


def clean_text(text: str, *, dehyphenate: bool = False) -> str:
    """One paragraph's text: NFC, ligatures resolved, whitespace collapsed."""
    text = unicodedata.normalize("NFC", text).translate(LIGATURES)
    if dehyphenate:
        # "exam-\nple" -> "example", but keep real compounds ("self-\nattention").
        text = re.sub(r"(\w)-\s*\n\s*([a-z])", _join_hyphen, text)
    text = re.sub(r"[ \t\r\f\v]*\n[ \t\r\f\v]*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


_COMPOUND_PREFIXES = {
    "self",
    "non",
    "multi",
    "cross",
    "pre",
    "post",
    "co",
    "re",
    "sub",
    "semi",
    "well",
    "high",
    "low",
    "long",
    "short",
    "end",
    "real",
    "state",
}


def _join_hyphen(m: re.Match[str]) -> str:
    before = m.string[: m.start() + 1]
    word = re.search(r"(\w+)$", before)
    head = word.group(1).lower() if word else ""
    return (
        f"{m.group(1)}-{m.group(2)}" if head in _COMPOUND_PREFIXES else f"{m.group(1)}{m.group(2)}"
    )


def build(doc: ImportedDocument, *, drop_after_references: bool = True) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    words = 0
    for raw in doc.blocks:
        text = raw.text.strip()
        if not text:
            continue
        if raw.kind == "heading" and drop_after_references and STOP_HEADINGS.match(text):
            break
        index = len(blocks)
        if raw.kind == "heading":
            sentences = [{"start": 0, "end": len(text), "units": [[0, len(text)]]}]
            sections.append({"title": text, "block": index, "level": raw.level or 1})
        else:
            sentences = []
            for a, b in split_sentences(text):
                units = [[u, v] for u, v in split_units(text, (a, b))]
                sentences.append({"start": a, "end": b, "units": units})
        blocks.append(
            {
                "id": f"b{index}",
                "kind": raw.kind,
                "level": raw.level,
                "text": text,
                "sentences": sentences,
                "math": [[m.start(), m.end()] for m in _MATH.finditer(text)],
            }
        )
        words += len(_MATH.sub(" x ", text).split())
    return {"blocks": blocks, "sections": sections, "word_count": words}


_HEADING_LINE = re.compile(
    r"^(?:(?P<num>(?:\d+(?:\.\d+)*|[IVX]+|[A-Z])\.?)\s+)?(?P<title>[A-Z][^.!?]{1,80})$"
)
_KNOWN_HEADINGS = re.compile(
    r"^(abstract|introduction|background|related work|method(s|ology)?|approach|experiments?|"
    r"results|evaluation|discussion|conclusions?|future work|limitations|references|"
    r"appendix|acknowledg(e)?ments?|preliminaries|model|analysis|summary)$",
    re.IGNORECASE,
)


def looks_like_heading(line: str) -> tuple[bool, int]:
    """Plain-text heuristic: '2.1 Model Architecture', 'Abstract', 'III. RESULTS'."""
    s = line.strip()
    if not s or len(s.split()) > 12:
        return False, 0
    if s.endswith((".", ",", ";", ":", "?", "!")):
        return False, 0
    if _KNOWN_HEADINGS.match(s):
        return True, 1
    m = _HEADING_LINE.match(s)
    if m and m.group("num"):
        level = m.group("num").rstrip(".").count(".") + 1
        return True, min(level, 3)
    if s.isupper() and 1 <= len(s.split()) <= 6 and len(s) > 3:
        return True, 1
    return False, 0
