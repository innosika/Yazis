"""Place the synthesizer's word timestamps onto the spoken string.

Kokoro (through misaki) reports, per synthesized chunk, a list of tokens with their
text, trailing whitespace and start/end times relative to that chunk's audio. The
tokens of one chunk concatenate back to the chunk's text, so walking them in order
gives exact character offsets. Chunks are located in the spoken string one after the
other; their times are shifted by the audio already produced.

If a token cannot be found where expected (misaki normalised a character, say), a
character-level diff between the chunk text and the token stream recovers the
position instead of dropping the word.
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    whitespace: str
    start: float | None
    end: float | None


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    tokens: Sequence[Token]
    duration: float  # seconds of audio this chunk produced


@dataclass(frozen=True, slots=True)
class TimedSpan:
    """A word in the spoken string (character offsets) and when it is heard."""

    spoken_start: int
    spoken_end: int
    start: float
    end: float


def _is_word(text: str) -> bool:
    return any(c.isalnum() for c in text)


def align(spoken: str, chunks: Sequence[Chunk]) -> list[TimedSpan]:
    out: list[TimedSpan] = []
    cursor = 0
    offset = 0.0
    for chunk in chunks:
        base = spoken.find(chunk.text, cursor) if chunk.text else -1
        if base < 0:
            base = _skip_space(spoken, cursor)
        positions = _token_positions(spoken, base, chunk)
        for tok, pos in zip(chunk.tokens, positions, strict=True):
            if pos is None or tok.start is None or tok.end is None or not _is_word(tok.text):
                continue
            out.append(TimedSpan(pos, pos + len(tok.text), tok.start + offset, tok.end + offset))
        cursor = base + len(chunk.text)
        offset += chunk.duration
    return out


def _skip_space(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _token_positions(spoken: str, base: int, chunk: Chunk) -> list[int | None]:
    joined = "".join(t.text + t.whitespace for t in chunk.tokens)
    if spoken.startswith(joined, base):
        positions: list[int | None] = []
        pos = base
        for t in chunk.tokens:
            positions.append(pos)
            pos += len(t.text) + len(t.whitespace)
        return positions
    # Slow path: tokens do not reproduce the text verbatim. Search each token near
    # the running position, and fall back to a character diff for the rest.
    log.debug("token stream diverges from spoken text; aligning by search")
    positions = []
    pos = base
    window = spoken[base : base + len(joined) + 64]
    matcher = difflib.SequenceMatcher(a=joined, b=window, autojunk=False)
    blocks = matcher.get_matching_blocks()
    jpos = 0
    for t in chunk.tokens:
        found = spoken.find(t.text, pos, pos + len(t.text) + 16) if t.text else -1
        if found >= 0:
            positions.append(found)
            pos = found + len(t.text)
        else:
            positions.append(_map_through_blocks(jpos, blocks, base))
        jpos += len(t.text) + len(t.whitespace)
    return positions


def _map_through_blocks(j: int, blocks: list[difflib.Match], base: int) -> int | None:
    for b in blocks:
        if b.a <= j < b.a + b.size:
            return base + b.b + (j - b.a)
    return None
