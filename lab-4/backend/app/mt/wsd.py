"""Stage 3 of the pipeline: word-sense disambiguation. (Additional feature 2.)

A bilingual dictionary does not map words to words, it maps *senses* to words. "character"
has seven noun senses in this dictionary, and picking the wrong one is the difference
between «персонаж» and «символ». A direct-translation system takes the first sense and
accepts the damage; this one weighs six signals and can explain every choice.

    score = 3.0·topical label match
          + 1.2·domain keyword profile
          + 1.5·Lesk overlap with the sentence
          + 0.6·distributional similarity
          + 0.8·dictionary sense prior
          − 2.0·competing-domain label
          − 2.5·register penalty

The weights encode a single judgement: curated evidence beats statistics. A topical label
was written by a lexicographer and is worth more than any amount of vector similarity, and
an "obsolete" marker is worth more still - negatively - because a fluent translation into
the wrong century is the most expensive kind of error a dictionary-driven system makes.

A user-locked sense short-circuits all of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.mt.analysis import Analyzer, Sentence, Token
from app.mt.domains import Domain, competing_fields, register_penalty
from app.mt.lexicon import EntryRecord, SenseRecord, TranslationRecord

W_LABEL = 3.0
W_SYNTAX = 1.8
W_CROSS_DOMAIN = 2.0
W_DOMAIN_KEYWORDS = 1.2
W_LESK = 1.5
W_VECTOR = 0.6
W_REGISTER = 2.5
W_PRIOR = 0.8

# Raw cosines between short word lists cluster in a narrow band; this maps the band that
# actually discriminates onto 0..1 so the signal is comparable with the others.
VECTOR_FLOOR = 0.35
VECTOR_CEILING = 0.65

# Below this score margin the interface flags the word as genuinely ambiguous and invites
# the user to choose. Calibrated so a single decisive label never looks like a coin toss.
AMBIGUITY_MARGIN = 1.0


@dataclass(frozen=True, slots=True)
class SyntaxHints:
    """What the English parse already proves about the token being disambiguated.

    A verb with a direct object cannot have an intransitive sense; a plural noun cannot have
    an uncountable one. These are constraints, not preferences, and the dictionary labels
    them explicitly - so they are worth more than any statistical signal.
    """

    has_object: bool = False
    is_plural: bool = False
    is_predicate: bool = False

    @classmethod
    def of(cls, sentence: Sentence, token: Token) -> SyntaxHints:
        children = sentence.children(token)
        return cls(
            has_object=any(
                child.dep in {"dobj", "obj", "ccomp", "xcomp", "attr", "oprd"} for child in children
            ),
            is_plural="Number=Plur" in token.morph,
            is_predicate=token.dep in {"acomp", "attr", "oprd"},
        )


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    value: float
    weight: float
    detail: str

    @property
    def contribution(self) -> float:
        return round(self.value * self.weight, 3)


@dataclass(frozen=True, slots=True)
class SenseChoice:
    entry: EntryRecord
    sense: SenseRecord
    translation: TranslationRecord | None
    score: float
    signals: tuple[Signal, ...]
    locked: bool = False

    @property
    def surface(self) -> str:
        return self.translation.plain if self.translation else ""


@dataclass(frozen=True, slots=True)
class Disambiguation:
    chosen: SenseChoice | None
    alternatives: tuple[SenseChoice, ...]

    @property
    def ambiguous(self) -> bool:
        """Whether the runner-up is close enough that the user should be asked."""
        if self.chosen is None or not self.alternatives:
            return False
        if self.chosen.locked:
            return False
        return (self.chosen.score - self.alternatives[0].score) < AMBIGUITY_MARGIN

    @property
    def candidate_count(self) -> int:
        return len(self.alternatives) + (1 if self.chosen else 0)


class Disambiguator:
    def __init__(
        self,
        domain: Domain,
        analyzer: Analyzer,
        overrides: dict[tuple[str, str], tuple[int, int | None]] | None = None,
    ) -> None:
        self.domain = domain
        self.analyzer = analyzer
        self.overrides = overrides or {}

    # ------------------------------------------------------------------ public API

    def choose(
        self,
        token: Token,
        entries: list[EntryRecord],
        context: ContextWindow,
        hints: SyntaxHints | None = None,
    ) -> Disambiguation:
        hints = hints or SyntaxHints()
        candidates: list[SenseChoice] = []
        for entry in entries:
            for sense in entry.senses:
                if not sense.translations:
                    continue
                candidates.append(self._score(token, entry, sense, context, hints))

        if not candidates:
            return Disambiguation(None, ())

        locked = [c for c in candidates if c.locked]
        if locked:
            rest = sorted(
                (c for c in candidates if c is not locked[0]),
                key=lambda c: c.score,
                reverse=True,
            )
            return Disambiguation(locked[0], tuple(rest))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return Disambiguation(candidates[0], tuple(candidates[1:]))

    # ------------------------------------------------------------------ scoring

    def _score(
        self,
        token: Token,
        entry: EntryRecord,
        sense: SenseRecord,
        context: ContextWindow,
        hints: SyntaxHints,
    ) -> SenseChoice:
        override = self.overrides.get((entry.headword_norm, entry.pos or ""))
        if override and override[0] == sense.id:
            translation = self._pick_translation(sense, override[1])
            return SenseChoice(
                entry=entry,
                sense=sense,
                translation=translation,
                score=100.0,
                signals=(Signal("user lock", 1.0, 100.0, "sense locked for this domain"),),
                locked=True,
            )

        signals: list[Signal] = []
        labels = {label.lower() for label in sense.labels}

        syntax = self._syntax_signal(token, labels, hints)
        if syntax is not None:
            signals.append(syntax)

        matched = labels & self.domain.labels
        if matched:
            signals.append(
                Signal("topical label", 1.0, W_LABEL, f"labelled {', '.join(sorted(matched))}")
            )

        # A field label pointing at another subject area is evidence against the sense.
        # With no subject area selected there is no competing area either.
        competing = competing_fields(list(sense.labels), self.domain)
        if competing:
            signals.append(
                Signal(
                    "competing domain",
                    -1.0,
                    W_CROSS_DOMAIN,
                    f"labelled {', '.join(sorted(competing))}, another subject area",
                )
            )

        if self.domain.keywords:
            overlap = sense.definition_words & self.domain.keywords
            if overlap:
                value = min(1.0, len(overlap) / 3.0)
                shown = ", ".join(sorted(overlap)[:4])
                signals.append(
                    Signal(
                        "domain vocabulary",
                        value,
                        W_DOMAIN_KEYWORDS,
                        f"definition mentions {shown}",
                    )
                )

        lesk = sense.definition_words & context.lemmas
        if lesk:
            value = min(1.0, len(lesk) / 2.0)
            signals.append(
                Signal("context overlap", value, W_LESK, f"shares {', '.join(sorted(lesk)[:4])}")
            )

        similarity = self._similarity(sense, context)
        if similarity > 0:
            signals.append(
                Signal("similarity", similarity, W_VECTOR, f"distributional match {similarity:.2f}")
            )

        penalty = register_penalty(list(sense.labels), self.domain)
        if penalty > 0:
            marks = ", ".join(sorted(labels & set(_penalised_labels())))
            signals.append(Signal("register", -penalty, W_REGISTER, f"marked {marks}"))

        if not sense.definition.strip():
            # An undefined sense offers nothing any signal can act on, and in this
            # dictionary those are almost always obscure - currencies, dialect forms,
            # fragments. Its dictionary position must not carry it on its own.
            signals.append(
                Signal("no definition", -1.0, 1.0, "this sense has no definition to check")
            )

        prior = 1.0 / (1.0 + sense.idx)
        signals.append(
            Signal("dictionary order", prior, W_PRIOR, f"sense {sense.idx + 1} of this entry")
        )

        # An entry whose part of speech does not match the token at all is a fallback
        # reading; keep it available but never let it outrank a real match.
        if entry.pos and token.upos:
            from app.mt.lexicon import POS_COMPATIBILITY

            if (entry.pos or "").lower() not in POS_COMPATIBILITY.get(token.upos, ()):
                signals.append(
                    Signal(
                        "part of speech",
                        -1.0,
                        1.5,
                        f"entry is {entry.pos}, token is tagged {token.upos}",
                    )
                )

        if sense.translations and sense.translations[0].is_user:
            signals.append(Signal("user edit", 1.0, 2.0, "translation was corrected by the user"))

        score = sum(signal.contribution for signal in signals)
        return SenseChoice(
            entry=entry,
            sense=sense,
            translation=sense.first,
            score=round(score, 3),
            signals=tuple(signals),
        )

    @staticmethod
    def _syntax_signal(token: Token, labels: set[str], hints: SyntaxHints) -> Signal | None:
        """Check the sense's syntactic labels against what the parse actually shows."""
        if token.upos in {"VERB", "AUX"}:
            if "ambitransitive" in labels:
                return None
            if hints.has_object:
                if "transitive" in labels:
                    return Signal("syntax", 1.0, W_SYNTAX, "transitive, and the verb has an object")
                if "intransitive" in labels:
                    return Signal(
                        "syntax", -1.0, W_SYNTAX, "intransitive, but the verb has an object"
                    )
            else:
                if "intransitive" in labels:
                    return Signal("syntax", 0.6, W_SYNTAX, "intransitive, and there is no object")
                if "transitive" in labels:
                    return Signal("syntax", -0.4, W_SYNTAX, "transitive, but there is no object")
            return None

        if token.upos in {"NOUN", "PROPN"}:
            plural_only = bool(labels & {"in the plural", "often plural", "usually plural"})
            if hints.is_plural:
                if "uncountable" in labels:
                    return Signal("syntax", -0.8, W_SYNTAX, "uncountable, but the noun is plural")
                if plural_only:
                    return Signal("syntax", 0.8, W_SYNTAX, "mostly plural, and the noun is plural")
            elif plural_only:
                return Signal("syntax", -0.5, W_SYNTAX, "mostly plural, but the noun is singular")
            return None

        if token.upos == "ADJ" and hints.is_predicate and "attributive" in labels:
            return Signal("syntax", -0.6, W_SYNTAX, "attributive only, but used as a predicate")
        return None

    def _similarity(self, sense: SenseRecord, context: ContextWindow) -> float:
        """Cosine between the centroid of the context and the centroid of the definition.

        The obvious alternative - the best cosine between *any* context word and *any*
        definition word - was measured and rejected: two lists of English content words
        almost always contain one similar pair, so the signal saturated at 1.0 for senses
        that had nothing to do with the sentence and drowned out the curated evidence. A
        centroid averages that noise away. It is still the weakest signal here, which is why
        it carries the smallest weight and only breaks ties.
        """
        if not self.analyzer.has_vectors or not context.lemmas or not sense.definition_words:
            return 0.0
        context_centroid = context.centroid(self.analyzer)
        if context_centroid is None:
            return 0.0
        definition_centroid = _centroid(
            [self.analyzer.vector(word) for word in sorted(sense.definition_words)[:24]]
        )
        if definition_centroid is None:
            return 0.0
        cosine = float(context_centroid @ definition_centroid)
        if cosine <= VECTOR_FLOOR:
            return 0.0
        return min(1.0, (cosine - VECTOR_FLOOR) / (VECTOR_CEILING - VECTOR_FLOOR))

    @staticmethod
    def _pick_translation(
        sense: SenseRecord, translation_id: int | None
    ) -> TranslationRecord | None:
        if translation_id is not None:
            for translation in sense.translations:
                if translation.id == translation_id:
                    return translation
        return sense.first


class ContextWindow:
    """The content words a sense is compared against: its sentence, minus the target word."""

    __slots__ = ("_centroid", "_centroid_done", "_vectors", "lemmas")

    def __init__(self, lemmas: frozenset[str]) -> None:
        self.lemmas = lemmas
        # Vectors are numpy arrays, and numpy is imported lazily so this module can be read
        # without it. `Any` is the honest annotation for a type that is not in scope.
        self._vectors: list[Any] | None = None
        self._centroid: Any = None
        self._centroid_done = False

    @classmethod
    def for_token(cls, sentence: Sentence, token: Token) -> ContextWindow:
        lemmas = {
            t.lemma.lower()
            for t in sentence.tokens
            if t.is_content and not t.is_stop and t.index != token.index and len(t.lemma) > 2
        }
        return cls(frozenset(lemmas))

    def vectors(self, analyzer: Analyzer) -> list[Any]:
        if self._vectors is None:
            found = [analyzer.vector(word) for word in sorted(self.lemmas)[:24]]
            self._vectors = [v for v in found if v is not None]
        return self._vectors

    def centroid(self, analyzer: Analyzer) -> Any:
        if not self._centroid_done:
            self._centroid = _centroid(self.vectors(analyzer))
            self._centroid_done = True
        return self._centroid


def _centroid(vectors: list[Any]) -> Any:
    """Mean of unit vectors, renormalised. `None` when nothing had a vector."""
    present = [v for v in vectors if v is not None]
    if not present:
        return None
    import numpy as np

    mean = np.mean(present, axis=0)
    norm = float(np.linalg.norm(mean))
    return mean / norm if norm else None


def _penalised_labels() -> frozenset[str]:
    from app.mt.domains import REGISTER_PENALTY

    return frozenset(REGISTER_PENALTY)
