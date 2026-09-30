"""The pipeline: analysis -> lexical transfer -> disambiguation -> generation -> output.

Everything in this module is synchronous and database-free. It receives the dictionary
already materialised as a `LexiconIndex` and returns a complete result object; the async
service layer above it is responsible for fetching that index, persisting the run and
looking up the translation memory.

Keeping the two apart is what makes the pipeline testable: `test_pipeline.py` builds an
index from literal data and asserts on translations without a database in sight.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.mt.analysis import Analysis, Analyzer, Sentence, Token
from app.mt.direct import translate_direct
from app.mt.domains import Domain
from app.mt.lexicon import EntryRecord, LexiconIndex, Unit, segment_units, token_keys
from app.mt.morphgen import MorphGenerator
from app.mt.pieces import Kind, Piece, SentenceTranslation, join_sentences
from app.mt.stats import Stats, TokenTranslation, WordRow, build_word_rows, compute_stats
from app.mt.transfer import TransferEngine
from app.mt.tree import TreeNode, build_tree
from app.mt.wsd import (
    ContextWindow,
    Disambiguation,
    Disambiguator,
    SenseChoice,
    SyntaxHints,
)

# A long text can contain the same ambiguous word a hundred times. The panel lists each
# ambiguous lemma once - the user resolves a word, not an occurrence.
MAX_AMBIGUITIES = 200


@dataclass(slots=True)
class CandidateView:
    sense_id: int
    translation_id: int | None
    entry_pos: str | None
    sense_index: int
    gloss: str
    labels: list[str]
    translation: str
    translation_accented: str
    alternatives: list[str]
    score: float
    signals: list[dict[str, Any]]
    selected: bool
    locked: bool

    @classmethod
    def of(cls, choice: SenseChoice, selected: bool) -> CandidateView:
        return cls(
            sense_id=choice.sense.id,
            translation_id=choice.translation.id if choice.translation else None,
            entry_pos=choice.entry.pos,
            sense_index=choice.sense.idx,
            gloss=choice.sense.gloss,
            labels=list(choice.sense.labels),
            translation=choice.translation.plain if choice.translation else "",
            translation_accented=choice.translation.accented if choice.translation else "",
            alternatives=[t.plain for t in choice.sense.translations[1:6]],
            score=choice.score,
            signals=[
                {
                    "name": signal.name,
                    "value": round(signal.value, 3),
                    "weight": signal.weight,
                    "contribution": signal.contribution,
                    "detail": signal.detail,
                }
                for signal in choice.signals
            ],
            selected=selected,
            locked=choice.locked,
        )


@dataclass(slots=True)
class Ambiguity:
    """One ambiguous word, with every sense the disambiguator considered."""

    sentence: int
    token: int
    text: str
    lemma: str
    upos: str
    pos_name: str
    context: str
    candidates: list[CandidateView]
    margin: float


@dataclass(slots=True)
class OovMention:
    lemma: str
    upos: str
    context: str
    occurrences: int = 1


@dataclass(slots=True)
class TranslationResult:
    source: str
    target: str
    domain: str
    mode: str
    sentences: list[SentenceTranslation]
    tokens: list[TokenTranslation]
    words: list[WordRow]
    stats: Stats
    ambiguities: list[Ambiguity]
    oov: list[OovMention]
    analysis: Analysis
    duration_ms: float
    direct: list[SentenceTranslation] = field(default_factory=list)
    direct_target: str = ""

    def sentence_tree(self, index: int) -> TreeNode | None:
        if not 0 <= index < len(self.analysis.sentences):
            return None
        sentence = self.analysis.sentences[index]
        tokens = [token for token in self.tokens if token.sentence == index]
        return build_tree(sentence, tokens)


class Pipeline:
    def __init__(self, analyzer: Analyzer, morph: MorphGenerator) -> None:
        self.analyzer = analyzer
        self.transfer = TransferEngine(morph)

    def run(
        self,
        text: str,
        index: LexiconIndex,
        domain: Domain,
        overrides: dict[tuple[str, str], tuple[int, int | None]] | None = None,
        mode: str = "transfer",
        include_direct: bool = False,
    ) -> TranslationResult:
        started = time.monotonic()
        analysis = self.analyzer.analyse(text)
        disambiguator = Disambiguator(domain, self.analyzer, overrides)

        sentences: list[SentenceTranslation] = []
        direct_sentences: list[SentenceTranslation] = []
        tokens: list[TokenTranslation] = []
        ambiguities: list[Ambiguity] = []
        seen_ambiguous: set[tuple[str, str]] = set()
        oov: dict[tuple[str, str], OovMention] = {}
        dropped = inserted = 0

        for sentence in analysis.sentences:
            units = segment_units(sentence, index)
            choices = self._disambiguate(sentence, units, index, disambiguator)

            if mode == "direct":
                translated = translate_direct(sentence, units, index)
            else:
                translated = self.transfer.translate(sentence, units, choices)
            sentences.append(translated)

            if include_direct and mode != "direct":
                direct_sentences.append(translate_direct(sentence, units, index))

            dropped += sum(1 for piece in translated.pieces if piece.kind is Kind.DROPPED)
            inserted += sum(
                1 for piece in translated.pieces if piece.kind in {Kind.AUXILIARY, Kind.PREPOSITION}
            )

            tokens.extend(self._token_decisions(sentence, units, choices, translated))
            self._collect_ambiguities(sentence, units, choices, ambiguities, seen_ambiguous, domain)
            self._collect_oov(sentence, units, choices, index, oov)

        target = join_sentences(sentences)
        stats = compute_stats(analysis, tokens, dropped, inserted)

        return TranslationResult(
            source=text,
            target=target,
            domain=domain.code,
            mode=mode,
            sentences=sentences,
            tokens=tokens,
            words=build_word_rows(tokens),
            stats=stats,
            ambiguities=ambiguities,
            oov=sorted(oov.values(), key=lambda m: -m.occurrences),
            analysis=analysis,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            direct=direct_sentences,
            direct_target=join_sentences(direct_sentences) if direct_sentences else "",
        )

    # ------------------------------------------------------------------ internals

    def _disambiguate(
        self,
        sentence: Sentence,
        units: list[Unit],
        index: LexiconIndex,
        disambiguator: Disambiguator,
    ) -> dict[int, Disambiguation]:
        choices: dict[int, Disambiguation] = {}
        for unit in units:
            head = unit.tokens[0]
            if head.is_punct or not head.is_word:
                continue
            entries = self._entries_for(unit, index)
            if not entries:
                continue
            anchor = self._unit_context_token(unit)
            context = ContextWindow.for_token(sentence, anchor)
            # The hints come from the *unit's* head token, which is the one whose syntactic
            # role the transfer stage will use.
            hints = SyntaxHints.of(sentence, unit.tokens[-1] if unit.size > 1 else head)
            choices[unit.start] = disambiguator.choose(head, entries, context, hints)
        return choices

    @staticmethod
    def _unit_context_token(unit: Unit) -> Token:
        return unit.tokens[0]

    @staticmethod
    def _entries_for(unit: Unit, index: LexiconIndex) -> list[EntryRecord]:
        if unit.size > 1:
            expected = len(unit.key.split())
            matching = [e for e in index.get(unit.key) if e.word_count == expected]
            return matching or index.get(unit.key)
        token = unit.tokens[0]
        for key in token_keys(token):
            entries = index.get(key, token.upos)
            if entries:
                return entries
        return []

    def _token_decisions(
        self,
        sentence: Sentence,
        units: list[Unit],
        choices: dict[int, Disambiguation],
        translated: SentenceTranslation,
    ) -> list[TokenTranslation]:
        """One record per source token, joining analysis with what the pipeline decided."""
        by_source: dict[int, list[Piece]] = {}
        for piece in translated.pieces:
            for source_index in piece.source_indices:
                by_source.setdefault(source_index, []).append(piece)

        unit_of_token: dict[int, Unit] = {}
        for unit in units:
            for token in unit.tokens:
                unit_of_token[token.index] = unit

        out: list[TokenTranslation] = []
        for token in sentence.tokens:
            owner: Unit | None = unit_of_token.get(token.index)
            decision = choices.get(owner.start) if owner else None
            chosen = decision.chosen if decision else None
            pieces = by_source.get(token.index, [])
            emitted = next((p for p in pieces if p.kind not in {Kind.DROPPED, Kind.PUNCT}), None)
            # Articles, do-support and the possessive 's are deliberately absent from the
            # output. Reporting the sense the disambiguator found for them would claim a
            # translation the reader cannot find in the text, so the row shows the reason
            # for the drop instead.
            dropped_piece = next((p for p in pieces if p.kind is Kind.DROPPED), None)
            if dropped_piece is not None and emitted is None:
                out.append(
                    TokenTranslation(
                        sentence=sentence.index,
                        index=token.index,
                        text=token.text,
                        lemma=token.lemma,
                        upos=token.upos,
                        tag=token.tag,
                        morph=token.morph,
                        dep=token.dep,
                        head=token.head,
                        sense_count=decision.candidate_count if decision else 0,
                        dropped_by_rule=True,
                        note=dropped_piece.note or "dropped by a transfer rule",
                    )
                )
                continue
            out.append(
                TokenTranslation(
                    sentence=sentence.index,
                    index=token.index,
                    text=token.text,
                    lemma=token.lemma,
                    upos=token.upos,
                    tag=token.tag,
                    morph=token.morph,
                    dep=token.dep,
                    head=token.head,
                    translation=(
                        chosen.surface if chosen else (emitted.surface if emitted else "")
                    ),
                    translation_accented=(
                        chosen.translation.accented if chosen and chosen.translation else ""
                    ),
                    gloss=chosen.sense.gloss if chosen else "",
                    sense_index=chosen.sense.idx if chosen else -1,
                    sense_count=decision.candidate_count if decision else 0,
                    ambiguous=bool(decision and decision.ambiguous),
                    translated=bool(chosen and chosen.translation),
                    from_user=bool(chosen and chosen.translation and chosen.translation.is_user),
                    target_tag=emitted.tag if emitted else "",
                    target_decoded=list(emitted.decoded) if emitted else [],
                    note=(emitted.note if emitted else (pieces[0].note if pieces else "")),
                )
            )
        return out

    def _collect_ambiguities(
        self,
        sentence: Sentence,
        units: list[Unit],
        choices: dict[int, Disambiguation],
        out: list[Ambiguity],
        seen: set[tuple[str, str]],
        domain: Domain,
    ) -> None:
        from app.mt.tagset import explain_upos

        for unit in units:
            decision = choices.get(unit.start)
            if decision is None or decision.chosen is None or decision.candidate_count < 2:
                continue
            token = unit.tokens[0]
            # Only content words. A preposition or an article technically has several
            # dictionary senses, but the transfer rules decide those, not the disambiguator,
            # and listing them would bury the words a reader might actually want to change.
            if token.upos not in {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}:
                continue
            key = (token.lemma.lower(), token.upos)
            if key in seen or len(out) >= MAX_AMBIGUITIES:
                continue
            seen.add(key)

            candidates = [CandidateView.of(decision.chosen, selected=True)]
            # Several senses often share their first Russian equivalent - «модель» is the
            # first equivalent of four senses of "model". Offering the same word four times
            # is not a choice, so only the best-scoring sense per equivalent is shown.
            offered: set[str] = {decision.chosen.surface}
            for alternative in decision.alternatives:
                if len(candidates) >= 8:
                    break
                if alternative.surface in offered:
                    continue
                offered.add(alternative.surface)
                candidates.append(CandidateView.of(alternative, selected=False))
            margin = (
                decision.chosen.score - decision.alternatives[0].score
                if decision.alternatives
                else 0.0
            )
            out.append(
                Ambiguity(
                    sentence=sentence.index,
                    token=token.index,
                    text="".join(t.text + t.whitespace for t in unit.tokens).strip(),
                    lemma=token.lemma.lower(),
                    upos=token.upos,
                    pos_name=explain_upos(token.upos).name,
                    context=sentence.text,
                    candidates=candidates,
                    margin=round(margin, 3),
                )
            )

    @staticmethod
    def _collect_oov(
        sentence: Sentence,
        units: list[Unit],
        choices: dict[int, Disambiguation],
        index: LexiconIndex,
        out: dict[tuple[str, str], OovMention],
    ) -> None:
        """Record content words the dictionary could not translate.

        Only content words: an unrecognised determiner is a tagging accident, while an
        unrecognised noun is a real gap worth queueing for the replenishment utility.
        """
        for unit in units:
            token = unit.tokens[0]
            if not token.is_word or not token.is_content:
                continue
            decision = choices.get(unit.start)
            if decision is not None and decision.chosen is not None:
                continue
            # A capitalised word is lemmatised by rule, and the rules are written for
            # lower-case English: spaCy tags "Turing" as a gerund and lemmatises it to
            # "ture", a word that does not exist. The surface form is what should be
            # queued - "turing" is a real gap a user can fill with «Тьюринг».
            lemma = (token.text if token.is_title else token.lemma).lower()
            if len(lemma) < 2 or any(character.isdigit() for character in lemma):
                continue
            if token.upos == "PROPN" or token.ent_type:
                # Names are transcribed by the transfer stage, not missing from the
                # dictionary; queueing them would bury the real gaps.
                continue
            key = (lemma, token.upos)
            existing = out.get(key)
            if existing:
                existing.occurrences += 1
            else:
                out[key] = OovMention(lemma=lemma, upos=token.upos, context=sentence.text[:300])
