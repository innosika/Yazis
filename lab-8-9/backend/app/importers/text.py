"""Plain text and Markdown: what gets pasted, typed or uploaded as .txt/.md."""

from __future__ import annotations

import re

from app.importers.structure import ImportedDocument, RawBlock, clean_text, looks_like_heading
from app.text.segment import MATH_PATTERN

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_DISPLAY_MATH = re.compile(r"^\s*\$\$(.+?)\$\$\s*$|^\s*\\\[(.+?)\\\]\s*$", re.DOTALL)
# A line the editor escaped because it would otherwise read as markup ("\# of params").
_ESCAPED = re.compile(r"^\\(?=[#>|*+\-\d])")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•+]|\d{1,2}[.)])\s+(.+)$")
_FENCE = re.compile(r"^\s*```")
_MD_NOISE = [
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),  # images
    (re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)"), r"\1"),  # links -> text
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),  # bold
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),  # italics
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"), r"\1"),
    # stray html tags - a tag name must follow "<", so "n < m and m > k" survives
    (re.compile(r"</?[A-Za-z][\w-]*(?:\s[^<>]{0,80})?/?>"), ""),
]


def _strip_markdown(line: str) -> str:
    """Remove emphasis, links and tags - never inside formulas (x_{i}, a*b stay intact)."""
    out: list[str] = []
    pos = 0
    for m in MATH_PATTERN.finditer(line):
        out.append(_strip_plain(line[pos : m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_strip_plain(line[pos:]))
    return "".join(out)


def _strip_plain(text: str) -> str:
    for pattern, repl in _MD_NOISE:
        text = pattern.sub(repl, text)
    return text


def _paragraph(text: str) -> RawBlock:
    """A paragraph that is nothing but one formula is shown and read as an equation."""
    display = _DISPLAY_MATH.match(text)
    if display:
        return RawBlock("equation", f"\\({(display.group(1) or display.group(2)).strip()}\\)")
    only = MATH_PATTERN.fullmatch(text)
    return RawBlock("equation" if only else "paragraph", text)


def parse(
    text: str, *, title: str | None = None, dehyphenate: bool = False, strict: bool = False
) -> ImportedDocument:
    """Plain text or Markdown to blocks.

    ``strict`` is for text written in Lector's own editor: headings are only lines that
    start with ``#`` and a leading backslash escapes markup, so what the user typed is
    exactly what they get back. Otherwise short title-like lines are guessed to be
    headings, which suits text pasted from a PDF viewer.
    """
    blocks: list[RawBlock] = []
    para: list[str] = []
    in_code = False

    def flush() -> None:
        if para:
            joined = clean_text("\n".join(para), dehyphenate=dehyphenate)
            if joined:
                blocks.append(_paragraph(joined))
            para.clear()

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(raw_line):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue  # code listings are not read aloud
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        if _ESCAPED.match(line):
            para.append(_strip_markdown(line[1:]))
            continue
        if _TABLE_ROW.match(line) or re.fullmatch(r"\s*[-=*_]{3,}\s*", line):
            flush()  # tables and rules
            continue
        m = _MD_HEADING.match(line)
        if m:
            flush()
            blocks.append(
                RawBlock("heading", clean_text(_strip_markdown(m.group(2))), len(m.group(1)))
            )
            continue
        item = _LIST_ITEM.match(line)
        if item and not para:
            blocks.append(RawBlock("item", clean_text(_strip_markdown(item.group(1)))))
            continue
        if not para and not strict:
            is_heading, level = looks_like_heading(_strip_markdown(line))
            if is_heading:
                blocks.append(RawBlock("heading", clean_text(_strip_markdown(line)), level))
                continue
        if line.lstrip().startswith(">"):
            line = line.lstrip()[1:]
        para.append(_strip_markdown(line))
    flush()

    doc_title = title
    # A short first line is the title only when there is text after it; a one-line
    # paste ("Hello, I am ...") is the text itself and must stay readable.
    if doc_title is None and len(blocks) > 1:
        first = blocks[0]
        if first.kind == "heading" or (
            len(first.text.split()) <= 16 and not first.text.endswith(".")
        ):
            doc_title = first.text
            blocks = blocks[1:]
    if not doc_title:
        words = blocks[0].text.split() if blocks else ["Untitled"]
        doc_title = " ".join(words[:8]) + ("…" if len(words) > 8 else "")
    return ImportedDocument(title=doc_title, blocks=blocks, source={"kind": "text"})
