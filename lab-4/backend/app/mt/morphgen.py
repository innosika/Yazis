"""Stage 4 of the pipeline: generation of Russian word forms.

This is what separates a transfer system from a word-for-word one. The dictionary gives a
lemma - «сеть», «нейронный», «изучать» - and English grammar says nothing about how it
should be inflected, because English marks with word order and prepositions what Russian
marks with endings. The transfer stage decides *which* form is needed; this module produces
it, using pymorphy3's OpenCorpora dictionary.

Agreement is the interesting part. «нейронный сеть изучать» is three correct dictionary
lemmas and still not Russian. The generator therefore takes a target feature set - gender,
number, case, tense, person - and pushes it onto every dependent that has to agree.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.mt.tagset import explain_opencorpora
from app.mt.textnorm import strip_stress

log = logging.getLogger(__name__)

# pymorphy3 ships no type information, so its `Parse` objects are opaque here. Naming the
# alias is more honest than spelling `Any` at each use site.
Parse = Any

# OpenCorpora case names, keyed by the internal names the transfer stage speaks.
CASES = {
    "nom": "nomn",
    "gen": "gent",
    "dat": "datv",
    "acc": "accs",
    "ins": "ablt",
    "prep": "loct",
}
CASE_TITLES = {
    "nom": "nominative",
    "gen": "genitive",
    "dat": "dative",
    "acc": "accusative",
    "ins": "instrumental",
    "prep": "prepositional",
}


@dataclass(frozen=True, slots=True)
class Target:
    """The Russian form the transfer stage is asking for.

    Every field is optional: an adverb needs none of them, a participle needs most.
    """

    case: str | None = None
    number: str | None = None  # "sing" | "plur"
    gender: str | None = None  # "masc" | "femn" | "neut"
    animacy: str | None = None  # "anim" | "inan"
    """Animacy of the head noun, needed only in the accusative - see `grammemes`."""
    tense: str | None = None  # "pres" | "past" | "futr"
    person: str | None = None  # "1per" | "2per" | "3per"
    infinitive: bool = False
    short: bool = False
    comparative: bool = False
    participle: str | None = None
    """One of "active", "passive" (declined participles) or "short-passive".

    A short passive participle is how Russian renders an English passive: "is computed"
    becomes «вычислено», agreeing with its subject in gender and number but taking no case.
    """

    def grammemes(self) -> set[str]:
        wanted: set[str] = set()

        if self.participle == "short-passive":
            # A short participle agrees in gender and number and has no case at all.
            wanted.add("PRTS")
            wanted.add("pssv")
        elif self.participle:
            # English modifies nouns with participles as freely as with adjectives
            # ("distributed representations", "hidden states"), and Russian does the same -
            # but with a declined participle that agrees with its noun.
            wanted.add("PRTF")
            if self.participle == "passive":
                wanted.add("pssv")
            if self.case:
                wanted.add(CASES.get(self.case, self.case))
        elif self.short:
            # Russian predicate adjectives take the short form: «модель проста», not
            # «модель простая». Asking pymorphy3 for ADJS is the only way to get it.
            wanted.add("ADJS")
        elif self.case:
            wanted.add(CASES.get(self.case, self.case))

        # Russian syncretism: in the accusative, an adjective or participle copies the
        # nominative when its noun is inanimate and the genitive when it is animate.
        # «распределённые представления» but «распределённых исследователей». Nouns carry
        # their own animacy, so this only matters for the words that agree with them - and
        # only in the accusative, where asking for it anywhere else makes generation fail.
        if self.animacy and self.case == "acc":
            wanted.add(self.animacy)

        for value in (self.number, self.gender, self.tense, self.person):
            if value:
                wanted.add(value)
        return wanted


@dataclass(slots=True)
class GeneratedForm:
    """A generated Russian word, with everything the interface needs to explain it."""

    surface: str
    lemma: str
    tag: str
    decoded: list[str] = field(default_factory=list)
    inflected: bool = True
    note: str = ""

    @property
    def gender(self) -> str | None:
        for value in ("masc", "femn", "neut"):
            if value in self.tag:
                return value
        return None

    @property
    def number(self) -> str | None:
        for value in ("sing", "plur"):
            if value in self.tag:
                return value
        return None


class MorphGenerator:
    """Russian morphological analyser and generator."""

    def __init__(self) -> None:
        import pymorphy3

        log.info("loading pymorphy3 Russian dictionary")
        self._morph = pymorphy3.MorphAnalyzer()

    # ------------------------------------------------------------------ analysis

    @lru_cache(maxsize=100_000)  # noqa: B019 - one generator per process, bounded by design
    def _parses(self, word: str) -> tuple[Parse, ...]:
        return tuple(self._morph.parse(word))

    def parse_best(self, word: str, want_pos: str | None = None) -> Parse | None:
        """Most probable parse of `word`, optionally restricted to a part of speech.

        pymorphy3 returns parses sorted by corpus probability. Preferring a requested part
        of speech matters for words like «данные», which is both a noun («data») and an
        adjective participle - the dictionary knows which one it meant, pymorphy3 does not.
        """
        parses = self._parses(strip_stress(word).lower())
        if not parses:
            return None
        if want_pos:
            for parse in parses:
                if want_pos == parse.tag.POS:
                    return parse
        return parses[0]

    def describe(self, word: str) -> GeneratedForm:
        """Analyse an existing Russian word - used when no inflection is required."""
        parse = self.parse_best(word)
        tag = str(parse.tag) if parse else ""
        return GeneratedForm(
            surface=word,
            lemma=parse.normal_form if parse else word,
            tag=tag,
            decoded=explain_opencorpora(tag),
            inflected=False,
        )

    def gender_of(self, word: str) -> str | None:
        parse = self.parse_best(word, want_pos="NOUN") or self.parse_best(word)
        if parse is None:
            return None
        gender = parse.tag.gender
        if gender in {"masc", "femn", "neut"}:
            return str(gender)
        # Plural-only nouns («данные», «ножницы») have no gender at all. Returning nothing
        # lets the caller omit gender from its request, which is correct: Russian plural
        # agreement is gender-neutral, so inventing a value could only cause a mismatch.
        return None

    def number_of(self, word: str) -> str | None:
        parse = self.parse_best(word, want_pos="NOUN") or self.parse_best(word)
        return parse.tag.number if parse else None

    def aspect_of(self, word: str) -> str | None:
        """Aspect of a Russian verb: "perf" or "impf".

        English has no aspect, so the choice between «изучать» and «изучить» cannot be read
        off the source. It can be read off the *tense* the transfer stage is asking for,
        which is what `TransferEngine` uses this for.
        """
        parse = self.parse_best(word, want_pos="INFN") or self.parse_best(word)
        return str(parse.tag.aspect) if parse and parse.tag.aspect else None

    def is_known(self, word: str) -> bool:
        """Whether the Russian morphological dictionary contains this word.

        Used by the dictionary-replenishment utility to tell a derivation that produced a
        real Russian word from one that produced a plausible-looking string.
        """
        return bool(self._morph.word_is_known(strip_stress(word).lower()))

    def can_inflect(self, lemma: str, target: Target, want_pos: str | None = None) -> bool:
        return self.inflect(lemma, target, want_pos=want_pos).inflected

    def is_animate(self, word: str) -> bool:
        parse = self.parse_best(word, want_pos="NOUN")
        return bool(parse and parse.tag.animacy == "anim")

    # ---------------------------------------------------------------- generation

    def inflect(self, lemma: str, target: Target, want_pos: str | None = None) -> GeneratedForm:
        """Produce the form of `lemma` that satisfies `target`.

        Degrades in three steps rather than failing: the full feature set, then the same
        set minus gender (pymorphy3 refuses gender on plural nouns and on past-tense plural
        verbs), then the lemma itself marked as uninflected. A translator that raises on an
        unusual word is worse than one that leaves that word in its dictionary form.
        """
        plain = strip_stress(lemma).strip()
        if not plain:
            return GeneratedForm(surface=lemma, lemma=lemma, tag="", inflected=False)

        # Multiword equivalents («действующее лицо», «тем не менее») are inflected on their
        # head word only; everything else is copied through.
        if " " in plain:
            return self._inflect_phrase(plain, target, want_pos)

        parse = self.parse_best(plain, want_pos=want_pos)
        if parse is None:
            return GeneratedForm(
                surface=plain,
                lemma=plain,
                tag="",
                inflected=False,
                note="not in the Russian morphological dictionary",
            )

        if target.infinitive and parse.tag.POS in {"VERB", "INFN"}:
            infinitive = parse.inflect({"INFN"}) or parse
            return self._form(infinitive, inflected=infinitive is not parse)

        wanted = target.grammemes()
        if not wanted:
            return self._form(parse, inflected=False)

        for attempt, grammemes in enumerate(self._relaxations(wanted, parse)):
            if not grammemes:
                continue
            result = parse.inflect(grammemes)
            if result is not None:
                return self._form(
                    result,
                    inflected=True,
                    note="" if attempt == 0 else "partial agreement",
                )

        return self._form(
            parse,
            inflected=False,
            note=f"cannot inflect to {', '.join(sorted(wanted))}",
        )

    def _relaxations(self, wanted: set[str], parse: Parse) -> list[set[str]]:
        """Progressively weaker feature sets to try.

        Order matters: gender is dropped before number, and person before tense, because
        Russian genuinely has no gender in the plural and no person in the past, while
        losing a case would change the sentence's meaning.
        """
        attempts = [set(wanted)]

        if wanted & {"anim", "inan"}:
            # Animacy is not distinguished in every paradigm cell - the feminine singular
            # accusative has one form - so a request carrying it may have no match.
            attempts.append(wanted - {"anim", "inan"})

        if wanted & {"PRTF", "PRTS"}:
            # Which participle exists depends on aspect, which English does not mark: a
            # perfective verb has a past passive participle («распределённые») and no present
            # one, an imperfective verb the reverse («распределяемые»). Try the other tense
            # before giving up on the voice, and the voice before giving up on the form.
            other_tense = {"past": "pres", "pres": "past"}
            for tense, swap in other_tense.items():
                if tense in wanted:
                    attempts.append((wanted - {tense}) | {swap})
            attempts.append(wanted - {"past", "pres", "futr"})
            attempts.append(wanted - {"pssv", "past", "pres", "futr"})

        if wanted & {"masc", "femn", "neut"}:
            attempts.append(wanted - {"masc", "femn", "neut"})
        if "pres" in wanted and parse.tag.aspect == "perf":
            # Russian perfective verbs have no present tense at all - their present-tense
            # morphology *is* the future. When the dictionary offers only a perfective
            # equivalent, «исследователи оценят» is grammatical and readable, where refusing
            # to inflect would leave a bare infinitive in the middle of the sentence.
            attempts.append((wanted - {"pres"}) | {"futr"})

        if wanted & {"1per", "2per", "3per"}:
            attempts.append(wanted - {"1per", "2per", "3per"})
            attempts.append(wanted - {"1per", "2per", "3per", "masc", "femn", "neut"})
        if wanted & {"sing", "plur"} and parse.tag.POS == "NOUN":
            # Singular-only and plural-only nouns («research», «data») keep their own number.
            attempts.append(wanted - {"sing", "plur"})
        if "ADJS" in wanted:
            # A short form does not exist for every adjective; fall back to the full form
            # in the nominative rather than leaving the predicate untranslated.
            attempts.append((wanted - {"ADJS"}) | {"nomn"})
        case_only = {g for g in wanted if g in set(CASES.values())}
        if case_only:
            attempts.append(case_only)
        return attempts

    def _inflect_phrase(self, phrase: str, target: Target, want_pos: str | None) -> GeneratedForm:
        """Inflect the head of a multiword equivalent and keep its modifiers in agreement."""
        words = phrase.split()
        head_index = self._phrase_head(words)
        if head_index is None:
            return GeneratedForm(surface=phrase, lemma=phrase, tag="", inflected=False)

        head = self.inflect(words[head_index], target, want_pos=want_pos)
        pieces = list(words)
        pieces[head_index] = head.surface

        # Adjectives in front of the head agree with it, so «действующее лицо» in the
        # genitive becomes «действующего лица», not «действующее лица». Animacy comes from
        # the head word itself, not from the caller: «нейронная сеть» in the accusative
        # plural is «нейронные сети», with the inanimate form of the adjective.
        head_gender = head.gender or target.gender
        head_number = head.number or target.number
        head_animacy = "anim" if self.is_animate(words[head_index]) else "inan"
        for i, word in enumerate(words):
            if i == head_index:
                continue
            parse = self.parse_best(word)
            if parse is None or parse.tag.POS not in {"ADJF", "PRTF"}:
                continue
            agreed = self.inflect(
                word,
                Target(
                    case=target.case,
                    number=head_number,
                    gender=head_gender,
                    animacy=head_animacy,
                ),
                want_pos=parse.tag.POS,
            )
            pieces[i] = agreed.surface

        return GeneratedForm(
            surface=" ".join(pieces),
            lemma=phrase,
            tag=head.tag,
            decoded=head.decoded,
            inflected=head.inflected,
            note=head.note,
        )

    def _phrase_head(self, words: list[str]) -> int | None:
        """The noun of a nominal phrase, or the verb of a verbal one; last word otherwise."""
        for wanted in ("NOUN", "INFN", "VERB"):
            for i, word in enumerate(words):
                parse = self.parse_best(word)
                if parse is not None and wanted == parse.tag.POS:
                    return i
        return len(words) - 1 if words else None

    def _form(self, parse: Parse, inflected: bool, note: str = "") -> GeneratedForm:
        tag = str(parse.tag)
        return GeneratedForm(
            surface=parse.word,
            lemma=parse.normal_form,
            tag=tag,
            decoded=explain_opencorpora(tag),
            inflected=inflected,
            note=note,
        )
