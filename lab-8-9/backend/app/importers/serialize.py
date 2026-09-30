"""A document back to the text a person edits: Markdown-like, one block per paragraph.

    # 1 Introduction            heading (one # per level)
    Plain paragraph text…       paragraph
    - list item                 item
    \\(E = mc^2\\)                equation (a paragraph that is only a formula)

Parsing this with ``text.parse(strict=True)`` gives the same blocks back, so opening
the editor and saving without changes never alters a document. A paragraph that
happens to start like markup ("# of params", "- 5 points", "3. Results") is escaped
with a backslash.
"""

from __future__ import annotations

import re
from typing import Any

_LOOKS_LIKE_MARKUP = re.compile(r"^(?:#|>|\||[-*+•]\s|\d{1,2}[.)]\s|```|[-=*_]{3,}\s*$)")


def _escape(text: str) -> str:
    return "\\" + text if _LOOKS_LIKE_MARKUP.match(text) else text


def to_text(blocks: list[dict[str, Any]]) -> str:
    out = ""
    previous: str | None = None
    for b in blocks:
        text = str(b.get("text", "")).strip()
        if not text:
            continue
        kind = str(b.get("kind"))
        if kind == "heading":
            level = min(6, max(1, int(b.get("level") or 1)))
            line = f"{'#' * level} {text}"
        elif kind == "item":
            line = f"- {text}"
        else:
            line = _escape(text)
        if previous is not None:
            # consecutive list items stay on adjacent lines, everything else is a paragraph
            out += "\n" if kind == "item" and previous == "item" else "\n\n"
        out += line
        previous = kind
    return out + "\n"
