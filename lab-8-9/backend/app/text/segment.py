"""Rule-based sentence segmentation tuned for scientific prose.

A period ends a sentence only when it is followed by whitespace and then something
that can start a sentence (a capital, a digit, an opening quote or bracket), and when
the word it closes is not a known abbreviation ("Fig.", "et al.", "e.g.") or an
initial ("J. Smith"). Inline math written as ``\\( ... \\)`` or ``$ ... $`` is never
split. Every result is a (start, end) span into the original string, so the reader
can highlight exactly the characters that are being spoken.

Long sentences are further cut into playback *units* at ``;`` / ``:`` / ``,`` so the
first audio of a long sentence arrives about a second after pressing play.
"""

from __future__ import annotations

import re

Span = tuple[int, int]

# Lower-cased, without the final period. Multi-dot forms ("e.g", "i.e") are matched
# on the whole token that precedes the period.
ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "al",
        "e.g",
        "i.e",
        "cf",
        "vs",
        "etc",
        "approx",
        "resp",
        "w.r.t",
        "a.k.a",
        "s.t",
        "i.i.d",
        "w.l.o.g",
        "fig",
        "figs",
        "eq",
        "eqs",
        "sec",
        "secs",
        "tab",
        "tbl",
        "alg",
        "thm",
        "def",
        "lem",
        "prop",
        "cor",
        "ref",
        "refs",
        "no",
        "nos",
        "pp",
        "p",
        "vol",
        "ch",
        "chap",
        "app",
        "appx",
        "ex",
        "dr",
        "prof",
        "mr",
        "mrs",
        "ms",
        "st",
        "jr",
        "inc",
        "ltd",
        "co",
        "corp",
        "dept",
        "univ",
        "est",
        "min",
        "max",
        "avg",
        "std",
        "incl",
        "excl",
        "viz",
        "ca",
        "op",
        "ed",
        "eds",
        "trans",
        "proc",
        "conf",
        "int",
    }
)
# Abbreviations that often *do* end a sentence; only split after them when the next
# word is capitalised and is not itself obviously a continuation.
SOFT_ABBREVIATIONS: frozenset[str] = frozenset({"etc", "al", "resp", "min", "max", "ex"})

# Inline math: \( ... \) or $ ... $ (a "$" followed by a digit is money, not math).
MATH_PATTERN = re.compile(r"\\\((?:.|\n)*?\\\)|\$(?!\d)(?=\S)[^$\n]{1,300}?(?<=\S)\$(?!\d)")
_MATH = MATH_PATTERN
_BOUNDARY = re.compile(r"([.!?…]+)([\"'”’)\]]*)(\s+)")
_TOKEN_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*)$")
_STARTER = re.compile(r"[A-Z0-9\"'“‘(\[]")


def _math_spans(text: str) -> list[Span]:
    return [(m.start(), m.end()) for m in _MATH.finditer(text)]


def _inside(pos: int, spans: list[Span]) -> bool:
    return any(a <= pos < b for a, b in spans)


def split_sentences(text: str) -> list[Span]:
    """Return sentence spans; leading/trailing whitespace is excluded from each span."""
    math = _math_spans(text)
    cuts: list[int] = []
    for m in _BOUNDARY.finditer(text):
        punct_start = m.start(1)
        if _inside(punct_start, math):
            continue
        after = m.end()
        if after >= len(text):
            continue
        nxt = text[after]
        if not _STARTER.match(nxt):
            continue
        if m.group(1) == ".":
            before = text[:punct_start]
            tok = _TOKEN_BEFORE.search(before)
            if tok:
                word = tok.group(1).rstrip(".").lower()
                # Initials: a single capital letter ("J. Smith", "A. Turing").
                if len(tok.group(1)) == 1 and tok.group(1).isupper():
                    continue
                if word in ABBREVIATIONS and word not in SOFT_ABBREVIATIONS:
                    continue
                if word in SOFT_ABBREVIATIONS and not nxt.isupper():
                    continue
                # "Fig. 3", "No. 5", "pp. 10" - an abbreviation followed by a number.
                if word in ABBREVIATIONS and nxt.isdigit():
                    continue
        cuts.append(m.end(2))
    spans: list[Span] = []
    start = 0
    for cut in [*cuts, len(text)]:
        a, b = _strip(text, start, cut)
        if b > a:
            spans.append((a, b))
        start = cut
    return spans


def _strip(text: str, a: int, b: int) -> Span:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


_UNIT_BREAK = re.compile(r"[;:](?=\s)|,(?=\s)|\s[–—]\s")


def split_units(text: str, span: Span, max_words: int = 20) -> list[Span]:
    """Cut one sentence span into playback units of at most ~``max_words`` words.

    Prefers breaking at a semicolon or colon, then at a comma, as close to the middle
    of the over-long stretch as possible. Math is never broken.
    """
    a, b = span
    if _words(text[a:b]) <= max_words:
        return [span]
    math = _math_spans(text)
    candidates: list[tuple[int, int]] = []  # (priority, cut position)
    for m in _UNIT_BREAK.finditer(text, a, b):
        pos = m.end()
        if _inside(m.start(), math):
            continue
        prio = 0 if text[m.start()] in ";:" else 1
        candidates.append((prio, pos))
    if not candidates:
        return [span]
    mid = a + (b - a) // 2
    # Close to the middle matters most; a semicolon or colon wins a near tie.
    _, cut = min(candidates, key=lambda c: abs(c[1] - mid) / (b - a) + 0.15 * c[0])
    left = _strip(text, a, cut)
    right = _strip(text, cut, b)
    if left[1] <= left[0] or right[1] <= right[0]:
        return [span]
    return [*split_units(text, left, max_words), *split_units(text, right, max_words)]


def _words(s: str) -> int:
    return len(s.split())
