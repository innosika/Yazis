"""Span-rewriting text normalizer.

The normalizer never rewrites a string in place. It keeps a list of segments, each
tying a range of the *source* text to what should be *spoken* for it::

    "O(n log n) time [12]"
    ├─ Segment(0, 10, "big O of n log n", frozen)
    ├─ Segment(10, 16, " time ", open)
    └─ Segment(16, 20, "", frozen)            # citation skipped

A rule only ever looks inside *open* segments (whose spoken text still equals the
source) and splits them around its matches; the replacement segment is frozen so no
later rule rewrites it again. The spoken text is the concatenation of all segments,
and because every spoken character belongs to exactly one segment, any word timing the
synthesizer reports on the spoken text maps back to an exact source range. That is
what drives word highlighting in the reader.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

# A replacement callback returns the spoken text, or None to leave the match alone.
Replacer = Callable[[re.Match[str], "Context"], str | None]


@dataclass(slots=True)
class Segment:
    start: int
    end: int
    spoken: str
    frozen: bool


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    replace: Replacer


@dataclass(slots=True)
class Context:
    """Per-call options every rule can read."""

    citations: str = "skip"  # skip | read
    urls: str = "domain"  # skip | link | domain
    math: str = "verbalize"  # verbalize | skip
    acronyms: str = "auto"  # auto | spell
    heading: bool = False
    lexicon: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Piece:
    spoken_start: int
    spoken_end: int
    src_start: int
    src_end: int
    exact: bool  # open segment: characters map one-to-one


@dataclass(frozen=True, slots=True)
class SpokenText:
    source: str
    text: str
    pieces: tuple[Piece, ...]

    def source_span(self, spoken_start: int, spoken_end: int) -> tuple[int, int] | None:
        """Map a spoken range to the source range it was produced from.

        Inside an unmodified stretch the mapping is exact per character; inside a
        replacement the whole replaced source expression is returned. Returns None
        when the range only covers inserted whitespace.
        """
        if spoken_end <= spoken_start:
            return None
        starts = [p.spoken_start for p in self.pieces]
        i = max(0, bisect.bisect_right(starts, spoken_start) - 1)
        src_a: int | None = None
        src_b: int | None = None
        for p in self.pieces[i:]:
            if p.spoken_start >= spoken_end:
                break
            if p.spoken_end <= spoken_start or p.spoken_end == p.spoken_start:
                continue
            if p.exact:
                a = p.src_start + max(0, spoken_start - p.spoken_start)
                b = p.src_start + min(p.spoken_end, spoken_end) - p.spoken_start
            else:
                a, b = p.src_start, p.src_end
            if b <= a:
                continue
            src_a = a if src_a is None else min(src_a, a)
            src_b = b if src_b is None else max(src_b, b)
        if src_a is None or src_b is None:
            return None
        # Trim whitespace that leaked in from an exact piece's edges.
        while src_a < src_b and self.source[src_a].isspace():
            src_a += 1
        while src_b > src_a and self.source[src_b - 1].isspace():
            src_b -= 1
        return (src_a, src_b) if src_b > src_a else None


def apply_rule(segments: list[Segment], source: str, rule: Rule, ctx: Context) -> list[Segment]:
    out: list[Segment] = []
    for seg in segments:
        if seg.frozen:
            out.append(seg)
            continue
        cursor = seg.start
        chunk = source[seg.start : seg.end]
        for m in rule.pattern.finditer(chunk):
            if m.end() == m.start():
                continue
            spoken = rule.replace(m, ctx)
            if spoken is None:
                continue
            a, b = seg.start + m.start(), seg.start + m.end()
            if a > cursor:
                out.append(Segment(cursor, a, source[cursor:a], False))
            out.append(Segment(a, b, spoken, True))
            cursor = b
        if cursor < seg.end:
            out.append(Segment(cursor, seg.end, source[cursor : seg.end], False))
    return out


def run(source: str, rules: Iterable[Rule], ctx: Context) -> list[Segment]:
    segments = [Segment(0, len(source), source, False)] if source else []
    for rule in rules:
        segments = apply_rule(segments, source, rule, ctx)
    return segments


_PUNCT_NO_SPACE_BEFORE = set(",.;:!?)]")


def join(source: str, segments: list[Segment]) -> SpokenText:
    """Concatenate segments into the spoken string, tidying whitespace at the seams.

    Replacements are written with generous spaces ("n  less than or equal to  m");
    here runs of whitespace collapse to one space and no space is left before
    punctuation. Tidying happens per segment, so the piece table stays exact.
    """
    buf: list[str] = []
    length = 0
    pieces: list[Piece] = []
    for seg in segments:
        text = seg.spoken
        if seg.frozen:
            text = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"\s+", " ", text))
        # collapse whitespace across the seam
        prev_space = length == 0 or (buf and (buf[-1][-1:].isspace() or buf[-1][-1:] in "(["))
        if prev_space:
            stripped = text.lstrip()
            lead = len(text) - len(stripped)
            text = stripped
        else:
            lead = 0
        if text and text[0] in _PUNCT_NO_SPACE_BEFORE and buf and buf[-1][-1:] == " ":
            buf[-1] = buf[-1][:-1]
            length -= 1
            # the last non-empty piece now ends one character earlier
            for k in range(len(pieces) - 1, -1, -1):
                p = pieces[k]
                if p.spoken_end > p.spoken_start:
                    pieces[k] = Piece(
                        p.spoken_start,
                        p.spoken_end - 1,
                        p.src_start,
                        p.src_end - (1 if p.exact else 0),
                        p.exact,
                    )
                    break
        if not text:
            pieces.append(Piece(length, length, seg.start, seg.end, not seg.frozen))
            continue
        exact = not seg.frozen
        src_start = seg.start + (lead if exact else 0)
        pieces.append(Piece(length, length + len(text), src_start, seg.end, exact))
        buf.append(text)
        length += len(text)
    spoken = "".join(buf)
    # Trailing whitespace is dropped; leading was never emitted.
    if spoken.endswith(" "):
        spoken = spoken.rstrip()
    return SpokenText(source, spoken, tuple(pieces))
