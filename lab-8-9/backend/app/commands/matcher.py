"""Match a normalized utterance against the enabled commands.

Three stages, cheapest first; the first confident answer wins:

1. **Templates.** Every phrase is compiled to a regular expression, slots becoming
   capture groups. A phrase may match anywhere in the utterance; the score is how much
   of the utterance it explains (a literal phrase scores slightly above a template, so
   "what is this paper about" beats "what is {term}").
2. **Fuzzy.** Slot-free phrases are compared with RapidFuzz: plain similarity, or
   token-set similarity for multi-word phrases ("slow down a bit" ~ "slow down").
3. **LLM.** Only when nothing matched and it is allowed (see ``service``).

Slots are resolved here too: section names against the document's headings, voice
names against the voice list. A slot that cannot be resolved invalidates the match, so
"go to lunch" is not a navigation command.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from app.commands.normalize import normalize
from app.commands.numbers import parse_number
from app.tts.voices import ALL_VOICES

SLOT_PATTERNS = {
    "number": r"(?P<number>-?\d+(?:\.\d+)?)",
    "section": r"(?P<section>[\w' -]{2,60})",
    "voice": r"(?P<voice>[\w'-]{2,20})",
    "term": r"(?P<term>.{2,80})",
}
TEMPLATE_MIN_COVERAGE = 0.5
FUZZY_THRESHOLD = 82.0
STRICT_FUZZY_THRESHOLD = 90.0


@dataclass(frozen=True)
class CompiledPhrase:
    command_id: str
    phrase: str
    normalized: str
    regex: re.Pattern[str]
    slots: tuple[str, ...]
    literal_len: int


@dataclass
class CommandSpec:
    """A command as the matcher sees it: built-in or custom, already filtered to one language."""

    id: str
    title: str
    phrases: Sequence[str]
    slots: tuple[str, ...] = ()
    needs_llm: bool = False
    description: str = ""


@dataclass
class Match:
    command_id: str
    title: str
    phrase: str
    method: str  # template | fuzzy | llm
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Section:
    title: str
    block: int
    number: str | None


def _compile(cmd: CommandSpec, phrase: str, lang: str) -> CompiledPhrase:
    """Normalize the literal parts exactly like utterances are normalized, keep slots."""
    tokens: list[tuple[str, str]] = []
    for part in re.split(r"(\{\w+\})", phrase):
        m = re.fullmatch(r"\{(\w+)\}", part)
        if m:
            tokens.append(("slot", m.group(1)))
        elif norm := normalize(part, lang):
            tokens.append(("lit", norm))
    regex = r"\s".join(
        SLOT_PATTERNS.get(v, rf"(?P<{v}>.+?)")
        if k == "slot"
        else r"\s".join(map(re.escape, v.split()))
        for k, v in tokens
    )
    normalized = " ".join(f"{{{v}}}" if k == "slot" else v for k, v in tokens)
    literal = sum(len(v) for k, v in tokens if k == "lit")
    slots = tuple(v for k, v in tokens if k == "slot")
    pattern = re.compile(rf"(?:^|(?<=\s)){regex}(?=\s|$)")
    return CompiledPhrase(cmd.id, phrase, normalized, pattern, slots, literal)


class Matcher:
    def __init__(self, commands: Sequence[CommandSpec], lang: str) -> None:
        self.lang = lang
        self.commands = {c.id: c for c in commands}
        self.phrases: list[CompiledPhrase] = []
        for c in commands:
            for p in c.phrases:
                if p.strip():
                    self.phrases.append(_compile(c, p, lang))
        self._literal = [p for p in self.phrases if not p.slots]
        self._literal_norm = [p.normalized for p in self._literal]

    # ----------------------------------------------------------------- stage 1

    def templates(self, utterance: str, sections: Sequence[Section]) -> list[Match]:
        found: list[Match] = []
        if not utterance:
            return found
        for p in self.phrases:
            m = p.regex.search(utterance)
            if not m:
                continue
            slots = self._resolve(m.groupdict(), sections)
            if slots is None:
                continue
            coverage = (m.end() - m.start()) / max(1, len(utterance))
            # A literal phrase beats a template covering the same words: slots are greedy.
            score = coverage * (0.97 if p.slots else 1.0)
            if score < TEMPLATE_MIN_COVERAGE:
                continue
            cmd = self.commands[p.command_id]
            found.append(
                Match(cmd.id, cmd.title, p.phrase, "template", round(min(1.0, score), 3), slots)
            )
        found.sort(key=lambda x: (x.confidence, len(x.phrase)), reverse=True)
        return _dedupe(found)

    # ----------------------------------------------------------------- stage 2

    def fuzzy(self, utterance: str, strict: bool) -> list[Match]:
        # A one- or two-letter leftover (often what echo subtraction leaves) is never a command.
        if len(utterance.replace(" ", "")) < 3 or not self._literal:
            return []
        threshold = STRICT_FUZZY_THRESHOLD if strict else FUZZY_THRESHOLD
        results: list[Match] = []
        scored = process.extract(utterance, self._literal_norm, scorer=_score, limit=5)
        for _norm, score, index in scored:
            p = self._literal[index]
            cmd = self.commands[p.command_id]
            results.append(Match(cmd.id, cmd.title, p.phrase, "fuzzy", round(score / 100, 3)))
        results = _dedupe(results)
        return [r for r in results if r.confidence * 100 >= threshold] or [
            Match(r.command_id, r.title, r.phrase, "fuzzy-weak", r.confidence) for r in results[:2]
        ]

    # --------------------------------------------------------------- slots

    def _resolve(
        self, groups: dict[str, str | None], sections: Sequence[Section]
    ) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        for name, value in groups.items():
            if value is None:
                continue
            value = value.strip()
            if name == "number":
                num = parse_number(value)
                if num is None:
                    return None
                out["number"] = num
            elif name == "section":
                sec = resolve_section(value, sections)
                if sec is None:
                    return None
                out["section"] = value
                out["section_block"] = sec.block
                out["section_title"] = sec.title
            elif name == "voice":
                voice = resolve_voice(value)
                if voice is None:
                    return None
                out["voice"] = voice
            elif name == "term":
                term = re.sub(r"^(?:the|a|an)\s+", "", value).strip()
                if len(term) < 2:
                    return None
                out["term"] = term
        return out


def _score(a: str, b: str, **_: Any) -> float:
    """Similarity of utterance ``a`` to phrase ``b``.

    Token-set similarity only counts in one direction: the phrase's words inside a
    longer utterance ("slow down a bit" ~ "slow down"). The reverse - a fragment such
    as "a" being a subset of "back a paragraph" - is not evidence of anything.
    """
    plain = fuzz.ratio(a, b)
    a_words, b_words = a.split(), b.split()
    if len(b_words) >= 2 and len(a_words) >= len(b_words):
        return max(plain, 0.9 * fuzz.token_set_ratio(a, b))
    return plain


def _dedupe(matches: list[Match]) -> list[Match]:
    seen: set[str] = set()
    best: list[Match] = []
    for m in matches:
        if m.command_id in seen:
            continue
        seen.add(m.command_id)
        best.append(m)
    if best:
        best[0].alternatives = [
            {"command": m.command_id, "title": m.title, "confidence": m.confidence}
            for m in best[1:4]
        ]
    return best


_SECTION_ALIASES = {
    "intro": "introduction",
    "conclusions": "conclusion",
    "method": "methods",
    "methodology": "methods",
    "experiment": "experiments",
    "result": "results",
    "background section": "background",
    "related": "related work",
}


def resolve_section(value: str, sections: Sequence[Section]) -> Section | None:
    if not sections:
        return None
    v = value.lower().strip()
    v = re.sub(r"^(?:the|a|an)\s+|\s+section$|^section\s+", "", v).strip()
    num = re.fullmatch(r"\d+(?:\.\d+)*", v)
    if num:
        for s in sections:
            if s.number == v:
                return s
        # no numbered headings: count sections instead
        idx = int(float(v)) - 1
        top = [s for s in sections if s.number is None or "." not in s.number]
        return top[idx] if 0 <= idx < len(top) and not any(s.number for s in sections) else None
    v = _SECTION_ALIASES.get(v, v)
    titles = [re.sub(r"^[\dIVX.]+\s+", "", s.title).lower() for s in sections]
    hit = process.extractOne(v, titles, scorer=fuzz.WRatio, score_cutoff=80)
    if hit is None:
        return None
    return sections[hit[2]]


_VOICE_NAMES = {v.name.lower(): v.id for v in ALL_VOICES}


def resolve_voice(value: str) -> str | None:
    v = value.lower().strip()
    if v in _VOICE_NAMES:
        return _VOICE_NAMES[v]
    hit = process.extractOne(v, list(_VOICE_NAMES), scorer=fuzz.ratio, score_cutoff=75)
    return _VOICE_NAMES[hit[0]] if hit else None


def sections_from_structure(structure: dict[str, Any] | None) -> list[Section]:
    out: list[Section] = []
    for s in (structure or {}).get("sections", []):
        title = str(s.get("title", ""))
        m = re.match(r"^(\d+(?:\.\d+)*)\s", title)
        out.append(Section(title, int(s.get("block", 0)), m.group(1) if m else None))
    return out


def prepare(utterance: str, lang: str) -> str:
    return normalize(utterance, lang)
