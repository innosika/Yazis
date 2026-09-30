"""Stage 2 of the pipeline: lexical transfer - finding dictionary entries for the input.

Two decisions shape this module.

*Part-of-speech compatibility.* spaCy speaks Universal POS, the dictionary speaks its own
abbreviations (`n`, `v`, `adj`, `pn`). The mapping is deliberately many-to-many and ordered:
a token tagged PROPN should prefer a proper-noun entry but may fall back to a common noun,
because "Turing machine" is in the dictionary as a noun.

*One round trip per document.* A 400-word text has some 250 distinct lemmas; looking each one
up on its own would be 250 queries against a 62 000-row table for every translation. Instead
every candidate string in the document - single lemmas, surface forms and the multiword
n-grams - is collected first and fetched in one statement, then served from memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import DictEntry, DictSense
from app.mt.analysis import Analysis, Sentence, Token
from app.mt.glosses import content_words, parse_labels
from app.mt.textnorm import normalise_headword

# Universal POS -> dictionary part-of-speech tags, in preference order.
POS_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "NOUN": ("n", "pn"),
    "PROPN": ("pn", "n"),
    "VERB": ("v",),
    "AUX": ("v",),
    "ADJ": ("adj", "n", "v"),
    "ADV": ("adv", "adj"),
    "ADP": ("preposition", "postposition", "adv"),
    "PRON": ("pronoun", "determiner", "n"),
    "DET": ("determiner", "pronoun", "adj", "numeral"),
    "NUM": ("numeral", "adj", "n"),
    "CCONJ": ("conjunction",),
    "SCONJ": ("conjunction", "preposition"),
    "PART": ("particle", "prcl", "adv", "preposition"),
    "INTJ": ("interjection",),
    "SYM": ("symbol",),
    "X": (),
}

# Longest multiword unit the matcher will try, counted in tokens. Seven covers the four-word
# entries the dictionary has ("in order to", "point of view") plus the hyphens spaCy splits
# out: "state-of-the-art" is seven tokens and one headword.
MAX_UNIT_TOKENS = 7

# Punctuation allowed *inside* a unit. spaCy tokenises "rule-based" as three tokens, so
# without this a hyphenated headword could never be matched.
JOINERS = frozenset({"-", "\u2010", "\u2011", "/", "'", "\u2019", "."})


@dataclass(frozen=True, slots=True)
class TranslationRecord:
    id: int
    idx: int
    accented: str
    plain: str
    is_user: bool


@dataclass(frozen=True, slots=True)
class SenseRecord:
    id: int
    idx: int
    gloss: str
    definition: str
    """The gloss with its leading label block removed."""
    labels: tuple[str, ...]
    domain_scores: dict[str, float]
    translations: tuple[TranslationRecord, ...]
    definition_words: frozenset[str] = field(default_factory=frozenset)

    @property
    def first(self) -> TranslationRecord | None:
        return self.translations[0] if self.translations else None


@dataclass(frozen=True, slots=True)
class EntryRecord:
    id: int
    headword: str
    headword_norm: str
    pos: str | None
    ipa: str | None
    word_count: int
    is_user: bool
    senses: tuple[SenseRecord, ...]


@dataclass(frozen=True, slots=True)
class Unit:
    """A stretch of one or more tokens that the dictionary recognises as a single item."""

    start: int
    end: int
    """Exclusive."""
    key: str
    tokens: tuple[Token, ...]

    @property
    def size(self) -> int:
        return self.end - self.start


class LexiconIndex:
    """Every dictionary entry a single document might need, held in memory."""

    def __init__(self, entries: list[EntryRecord]) -> None:
        self._by_key: dict[str, list[EntryRecord]] = {}
        for entry in entries:
            self._by_key.setdefault(entry.headword_norm, []).append(entry)

    def __contains__(self, key: str) -> bool:
        return key in self._by_key

    def get(self, key: str, upos: str | None = None) -> list[EntryRecord]:
        """Entries for `key`, ordered so the best part-of-speech match comes first.

        An entry whose part of speech does not match at all is kept but demoted: an
        adjective reading of a noun is a worse translation than the right one, and a far
        better translation than leaving the word in English.
        """
        candidates = self._by_key.get(key, [])
        if not candidates or upos is None:
            return list(candidates)

        preferred = POS_COMPATIBILITY.get(upos, ())

        def rank(entry: EntryRecord) -> tuple[int, int]:
            pos = (entry.pos or "").lower()
            if pos in preferred:
                return (0, preferred.index(pos))
            return (1, 0)

        return sorted(candidates, key=rank)

    def matches(self, key: str, upos: str | None = None) -> bool:
        """Whether `key` has an entry with a compatible part of speech."""
        preferred = POS_COMPATIBILITY.get(upos or "", ())
        for entry in self._by_key.get(key, []):
            if not preferred or (entry.pos or "").lower() in preferred:
                return True
        return False


def span_keys(span: tuple[Token, ...] | list[Token]) -> list[str]:
    """Dictionary keys for a run of tokens, surface form first then lemmas.

    The surface form is rebuilt from the original whitespace rather than joined with spaces,
    so the three tokens spaCy produces for "rule-based" come back as one hyphenated word
    instead of as "rule - based".
    """
    surface = "".join(token.text + token.whitespace for token in span).strip()
    lemmas = "".join(
        (token.lemma if token.is_word else token.text) + token.whitespace for token in span
    ).strip()
    out: list[str] = []
    for candidate in (normalise_headword(surface), normalise_headword(lemmas)):
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def candidate_keys(analysis: Analysis) -> set[str]:
    """Every dictionary key the document could need: lemmas, surface forms, n-grams."""
    keys: set[str] = set()
    for sentence in analysis.sentences:
        tokens = sentence.tokens
        for token in tokens:
            if token.is_word:
                keys.update(token_keys(token))
        for size in range(2, MAX_UNIT_TOKENS + 1):
            for start in range(len(tokens) - size + 1):
                span = tokens[start : start + size]
                if _joinable(span):
                    keys.update(span_keys(span))
    keys.discard("")
    return keys


def _joinable(span: tuple[Token, ...] | list[Token]) -> bool:
    """Whether a token run could be one dictionary headword.

    A unit starts and ends with a word; inside it, only the punctuation that occurs inside
    English headwords is allowed.
    """
    if len(span) < 2 or not span[0].is_word or not span[-1].is_word:
        return False
    return all(token.is_word or token.text in JOINERS for token in span[1:-1])


def token_keys(token: Token) -> list[str]:
    """Lookup keys for one token, most specific first.

    The lemma is tried before the surface form, and both before a hyphen-joined variant,
    because "e-mail" and "email" are separate headwords and only one of them may exist.
    """
    keys = [normalise_headword(token.lemma), normalise_headword(token.text)]
    if "-" in token.text:
        keys.append(normalise_headword(token.text.replace("-", " ")))
        keys.append(normalise_headword(token.text.replace("-", "")))
    seen: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.append(key)
    return seen


def segment_units(sentence: Sentence, index: LexiconIndex) -> list[Unit]:
    """Split a sentence into dictionary units, matching multiword entries longest-first.

    Greedy longest match is the standard approach for a direct-translation system and is
    what makes "machine learning" render as «машинное обучение» instead of «машина» +
    «учение». Only word tokens can start or end a unit, so punctuation never gets glued
    into one.
    """
    tokens = sentence.tokens
    units: list[Unit] = []
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if not token.is_word:
            units.append(Unit(position, position + 1, "", (token,)))
            position += 1
            continue

        match = _longest_unit(tokens, position, index)
        if match is not None:
            units.append(match)
            position = match.end
            continue

        keys = [key for key in token_keys(token) if key in index]
        units.append(Unit(position, position + 1, keys[0] if keys else "", (token,)))
        position += 1
    return units


def _longest_unit(tokens: tuple[Token, ...], start: int, index: LexiconIndex) -> Unit | None:
    for size in range(MAX_UNIT_TOKENS, 1, -1):
        end = start + size
        if end > len(tokens):
            continue
        span = tokens[start:end]
        if not _joinable(span):
            continue
        for key in span_keys(span):
            # The entry's own word count has to match the key's, not the token count: a
            # hyphenated headword is one word spread over three tokens.
            expected_words = len(key.split())
            if index.matches(key) and any(
                entry.word_count == expected_words for entry in index.get(key)
            ):
                return Unit(start, end, key, span)
    return None


async def build_index(session: AsyncSession, analysis: Analysis) -> LexiconIndex:
    """Fetch, in one statement, every entry the document might need."""
    keys = candidate_keys(analysis)
    if not keys:
        return LexiconIndex([])

    stmt = (
        select(DictEntry)
        .where(DictEntry.headword_norm.in_(keys))
        .options(selectinload(DictEntry.senses).selectinload(DictSense.translations))
    )
    rows = (await session.scalars(stmt)).unique().all()
    return LexiconIndex([to_record(row) for row in rows])


def to_record(entry: DictEntry) -> EntryRecord:
    senses: list[SenseRecord] = []
    for sense in entry.senses:
        labels, definition = parse_labels(sense.gloss or "")
        # `labels` on the row was written by the seeder from the same parser; re-deriving
        # here keeps user-created senses, which are stored with an empty array, consistent.
        stored = tuple(sense.labels or ())
        senses.append(
            SenseRecord(
                id=sense.id,
                idx=sense.idx,
                gloss=sense.gloss or "",
                definition=definition,
                labels=stored or tuple(labels),
                domain_scores=dict(sense.domain_scores or {}),
                translations=tuple(
                    TranslationRecord(t.id, t.idx, t.form_accented, t.form_plain, t.is_user)
                    for t in sense.translations
                ),
                definition_words=frozenset(content_words(definition)),
            )
        )
    return EntryRecord(
        id=entry.id,
        headword=entry.headword,
        headword_norm=entry.headword_norm,
        pos=entry.pos,
        ipa=entry.ipa,
        word_count=entry.word_count,
        is_user=entry.is_user,
        senses=tuple(senses),
    )
