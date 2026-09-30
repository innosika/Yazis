"""Stage 5 of the pipeline: syntactic transfer, and the transfer architecture itself.

A direct system substitutes words. A transfer system substitutes *structures*: it reads the
dependency tree of the English sentence, decides what each node's role means in Russian, and
rebuilds the sentence from that decision. Four groups of rules do the work here.

**Drops.** English marks with separate words what Russian marks with endings or with
nothing at all. Articles have no Russian equivalent; do-support has none; the infinitive
marker "to" has none; the possessive 's becomes a case ending; "of" becomes a case ending;
the present-tense copula is simply absent - «модель проста», not «модель есть проста».

**Case assignment.** Every dependency label implies a case: a subject is nominative, a
direct object accusative, a possessor genitive. Prepositions override this with their own
government, and a handful of Russian verbs override it again - «управлять» takes an
instrumental where English "control" takes a plain object.

**Agreement.** Adjectives, participles and determiners copy gender, number and case from
the noun they modify; finite verbs copy person and number - and, in the past tense, gender -
from their subject. This is why generation happens in four phases: heads before dependents.

**Reordering.** English noun-noun compounds and possessives stand before their head and
Russian puts them after it, as a genitive: "network model" -> «модель сети», "the author's
narrative" -> «повествование автора». Subject-verb-object order carries over unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.mt.analysis import Sentence, Token
from app.mt.grammar import (
    ARTICLES,
    COMPOUND_PREPOSITIONS,
    DEP_CASE,
    FUNCTION_WORDS,
    KEPT_DETERMINERS,
    MODALS,
    POSSESSIVES,
    PREPOSITIONS,
    PRONOUNS,
    VERB_GOVERNMENT,
    euphonic,
)
from app.mt.lexicon import Unit
from app.mt.morphgen import GeneratedForm, MorphGenerator, Target
from app.mt.pieces import Kind, Piece, SentenceTranslation, detokenise
from app.mt.translit import transcribe
from app.mt.wsd import Disambiguation

# Dependency labels that mark a modifier of a noun. Whether such a modifier stays in front
# of its head or moves behind it as a genitive is decided by what the *Russian* equivalent
# turns out to be, not by the English label - see `_mark_nominal_modifiers`.
NOUN_MODIFIERS = frozenset({"compound", "poss", "nmod", "amod", "npadvmod"})

# Modifiers that are postposed even when their equivalent is not a noun.
POSTPOSED = frozenset({"compound", "poss", "nmod"})

PUNCT_MAP = {"“": "«", "”": "»", "‘": "«", "’": "»", '"': "«", "--": "—", "---": "—"}

# Entity types whose members are names, and are therefore transcribed rather than left in
# Latin script. The named-entity recogniser is used here because it is right where the
# tagger is not: sentence-initial "Vaswani" is tagged a common noun and recognised as a
# PERSON, and capitalisation cannot tell the two apart at the start of a sentence.
NAME_ENTITIES = frozenset(
    {
        "PERSON",
        "ORG",
        "GPE",
        "LOC",
        "FAC",
        "NORP",
        "PRODUCT",
        "WORK_OF_ART",
        "EVENT",
        "LANGUAGE",
    }
)


@dataclass(slots=True)
class Item:
    """One dictionary unit of a sentence, plus every transfer decision about it."""

    index: int
    unit: Unit
    head: Token
    parent: int | None = None
    children: list[int] = field(default_factory=list)
    disambiguation: Disambiguation | None = None

    dropped: bool = False
    note: str = ""
    nominal_modifier: bool = False
    """Modifies a noun, and its Russian equivalent is itself a noun - so it takes the
    genitive and moves behind its head."""
    case: str | None = None
    preposition: str | None = None
    target: Target = field(default_factory=Target)
    form: GeneratedForm | None = None
    surface: str = ""
    kind: Kind = Kind.WORD
    order: float = 0.0
    inserted_before: list[Piece] = field(default_factory=list)

    @property
    def dep(self) -> str:
        return self.head.dep

    @property
    def upos(self) -> str:
        return self.head.upos

    @property
    def lemma(self) -> str:
        return self.head.lemma.lower()

    @property
    def chosen_lemma(self) -> str:
        choice = self.disambiguation.chosen if self.disambiguation else None
        return choice.surface if choice and choice.translation else ""


class TransferEngine:
    """Applies the transfer rules to one sentence at a time."""

    def __init__(self, morph: MorphGenerator) -> None:
        self.morph = morph

    def translate(
        self,
        sentence: Sentence,
        units: list[Unit],
        choices: dict[int, Disambiguation],
    ) -> SentenceTranslation:
        items = self._build_items(sentence, units, choices)

        lexical = self._stage_text(items, lexical_only=True)

        self._apply_drops(items)
        self._mark_nominal_modifiers(items)
        self._assign_prepositions(items)
        self._assign_cases(items)
        self._assign_verb_targets(items)
        self._generate(items)
        morphology = self._stage_text(items, ordered=False)

        self._assign_order(items)
        pieces = self._emit(items)
        target = detokenise(pieces)

        return SentenceTranslation(
            index=sentence.index,
            source=sentence.text,
            target=target,
            pieces=pieces,
            stages={
                "analysis": " ".join(f"{t.text}/{t.tag}" for t in sentence.tokens),
                "lexical transfer": lexical,
                "morphological generation": morphology,
                "syntactic transfer": target,
            },
        )

    # -------------------------------------------------------------- item construction

    def _build_items(
        self,
        sentence: Sentence,
        units: list[Unit],
        choices: dict[int, Disambiguation],
    ) -> list[Item]:
        items: list[Item] = []
        token_to_item: dict[int, int] = {}

        for index, unit in enumerate(units):
            head = self._unit_head(unit)
            items.append(
                Item(
                    index=index,
                    unit=unit,
                    head=head,
                    disambiguation=choices.get(unit.start),
                    order=float(head.index),
                )
            )
            for token in unit.tokens:
                token_to_item[token.index] = index

        for item in items:
            head_token_index = item.head.head
            parent_item = token_to_item.get(head_token_index)
            if parent_item is not None and parent_item != item.index:
                item.parent = parent_item
                items[parent_item].children.append(item.index)

        return items

    @staticmethod
    def _unit_head(unit: Unit) -> Token:
        """The token of a multiword unit that carries its role in the sentence.

        A dictionary unit is not always a connected subtree: in "the neural network model"
        the parser attaches both "neural" and "network" to "model", so both tokens of the
        unit "neural network" point outside it. Taking the first such token would make the
        unit inherit "neural"'s `amod` role and stay in the adjective slot. English noun
        phrases are head-final, so the last word is the right fallback - which gives the
        unit "network"'s `compound` role, and with it the genitive and the postposition
        that turn "network model" into «модель сети».
        """
        inside = {token.index for token in unit.tokens}
        roots = [token for token in unit.tokens if token.head not in inside or token.is_root]
        if len(roots) == 1:
            return roots[0]
        for token in reversed(unit.tokens):
            if token in roots:
                return token
        return unit.tokens[-1]

    # -------------------------------------------------------------------- rule passes

    def _apply_drops(self, items: list[Item]) -> None:
        for item in items:
            head = item.head

            if head.is_punct:
                item.kind = Kind.PUNCT
                item.surface = PUNCT_MAP.get(head.text, head.text)
                continue

            if head.upos == "DET" and item.lemma in ARTICLES:
                item.dropped = True
                item.note = "Russian has no articles"
                continue

            if item.lemma in {"do", "does", "did"} and head.dep in {"aux", "auxpass"}:
                item.dropped = True
                item.note = "do-support has no Russian equivalent"
                continue

            if head.dep == "auxpass":
                # "is told", "was computed": Russian marks the passive on the participle,
                # and has no present-tense copula to carry it. The tense the auxiliary was
                # holding is read off it by `_assign_verb_targets` before it goes.
                item.dropped = True
                item.note = "the passive is marked on the participle"
                continue

            if item.lemma == "have" and head.dep == "aux":
                # A perfect auxiliary: Russian has no perfect, so the tense lands on the
                # main verb and the auxiliary goes.
                item.dropped = True
                item.note = "Russian has no perfect auxiliary"
                continue

            if head.tag == "TO" and head.dep in {"aux", "prep", "mark"}:
                item.dropped = True
                item.note = "the infinitive is marked by the verb form, not by a particle"
                continue

            if head.tag == "POS":
                item.dropped = True
                item.note = "possession is marked by the genitive case"
                continue

            if item.lemma == "be" and self._is_zero_copula(item, items):
                item.dropped = True
                item.note = "the present-tense copula is absent in Russian"
                continue

            if item.lemma in {"not", "n't"}:
                item.kind = Kind.FUNCTION
                item.surface = "не"
                continue

            if head.upos == "DET" and item.lemma in KEPT_DETERMINERS:
                item.note = "determiner kept: it carries meaning"

    def _mark_nominal_modifiers(self, items: list[Item]) -> None:
        """Decide which noun modifiers are nominal, and therefore genitive and postposed.

        English lets a bare noun modify another noun - "network model", "machine learning
        system" - and the parser labels the modifier inconsistently: `compound` for
        "network", but `amod` for "learning" in "machine learning system", because it is
        tagged as a participle. Russian has no such construction at all: the modifier
        becomes a genitive *after* its head, «модель сети», «система машинного обучения».

        What matters is therefore not the English label but the part of speech of the
        Russian equivalent. If the dictionary gave a noun, the modifier is nominal; if it
        gave an adjective, it stays in front and agrees.
        """
        for item in items:
            if item.dropped or item.dep not in NOUN_MODIFIERS or item.parent is None:
                continue
            # A pronoun is never a nominal modifier in this sense: «его статья» keeps the
            # possessive in front, where «статья автора» moves the noun behind its head.
            if item.upos in {"PRON", "DET"} or item.lemma in POSSESSIVES:
                continue
            # A *finite* verb cannot modify a noun in English. When the parser says one
            # does, the parse is broken - which happens on sentences opening with an
            # unknown name, where "Turing studied…" is read as a noun compound. Conjugating
            # the verb is the safer reading of a broken parse than declining it as a noun.
            if item.head.tag in {"VBD", "VBZ", "VBP", "MD"}:
                continue
            parent = items[item.parent]
            if parent.upos not in {"NOUN", "PROPN", "PRON"}:
                continue
            lemma = item.chosen_lemma
            if not lemma:
                continue
            head_word = lemma.split()[-1] if " " in lemma else lemma
            parse = self.morph.parse_best(head_word)
            if parse is not None and parse.tag.POS == "NOUN":
                item.nominal_modifier = True

    def _is_zero_copula(self, item: Item, items: list[Item]) -> bool:
        """Whether this "be" is a present-tense copula, which Russian omits.

        Past and future copulas are kept («был», «будет»), and an auxiliary of a passive or
        a progressive is handled by the verb rules rather than dropped.
        """
        if item.head.tag not in {"VBZ", "VBP", "VB"}:
            return False
        if item.head.dep in {"auxpass"}:
            return False
        if item.head.dep == "aux":
            # "is learning" - a progressive; Russian uses a simple present, so the
            # auxiliary goes and the tense lands on the main verb.
            return True
        # A copular root: "The model is simple" / "The model is a network".
        return any(items[child].dep in {"acomp", "attr", "oprd", "prep"} for child in item.children)

    def _assign_prepositions(self, items: list[Item]) -> None:
        """Turn English prepositions into a Russian preposition plus a governed case."""
        for item in items:
            if item.head.upos != "ADP" or item.dropped:
                continue

            mapping = self._preposition_mapping(item, items)
            if mapping is None:
                continue
            russian, case = mapping

            objects = [
                items[child]
                for child in item.children
                if items[child].dep in {"pobj", "pcomp", "obj", "dobj"}
            ]
            for obj in objects:
                obj.case = case
                obj.note = obj.note or f"case governed by «{russian or '—'}»"

            if russian is None:
                item.dropped = True
                item.note = item.note or "the case replaces the preposition"
            else:
                item.kind = Kind.PREPOSITION
                item.surface = russian
                item.note = f"governs the {case}"

    def _preposition_mapping(self, item: Item, items: list[Item]) -> tuple[str | None, str] | None:
        """Look the preposition up, trying compound prepositions first."""
        if item.parent is not None:
            phrase = f"{items[item.parent].lemma} {item.lemma}"
            if phrase in COMPOUND_PREPOSITIONS:
                items[item.parent].dropped = True
                items[item.parent].note = "part of a compound preposition"
                return COMPOUND_PREPOSITIONS[phrase]
        for child in item.children:
            phrase = f"{item.lemma} {items[child].lemma}"
            if phrase in COMPOUND_PREPOSITIONS:
                items[child].dropped = True
                items[child].note = "part of a compound preposition"
                return COMPOUND_PREPOSITIONS[phrase]
        return PREPOSITIONS.get(item.lemma)

    def _assign_cases(self, items: list[Item]) -> None:
        for item in items:
            if item.dropped or item.kind is not Kind.WORD or item.case is not None:
                continue
            nominal = item.upos in {"NOUN", "PROPN", "PRON", "NUM", "ADJ", "DET", "X"}
            if not nominal and not item.nominal_modifier:
                continue

            case = DEP_CASE.get(item.dep)
            if item.nominal_modifier:
                case = "gen"

            if item.dep in {"dobj", "obj"} and item.parent is not None:
                governed = VERB_GOVERNMENT.get(items[item.parent].chosen_lemma)
                if governed:
                    case = governed
                    item.note = f"«{items[item.parent].chosen_lemma}» governs the {governed}"

            if item.dep == "conj" and item.parent is not None:
                case = items[item.parent].case or case

            item.case = case

    def _assign_verb_targets(self, items: list[Item]) -> None:
        for item in items:
            if item.dropped or item.upos not in {"VERB", "AUX"}:
                continue

            subject = self._subject_of(item, items)
            modal = self._modal_of(item, items)
            passive = any(items[child].dep == "auxpass" for child in item.children)
            future = any(
                items[child].lemma in {"will", "shall"} and items[child].dep == "aux"
                for child in item.children
            )
            for child in item.children:
                if items[child].lemma in {"will", "shall"} and items[child].dep == "aux":
                    items[child].dropped = True
                    items[child].note = "future is marked on the verb"

            if modal is not None:
                item.target = Target(infinitive=True)
                item.note = "infinitive under a modal"
                continue

            if passive:
                # «рассказан», «вычислено», «оценены» - a short passive participle, which
                # agrees with its subject in gender and number and takes no case. The
                # English tense lives on the dropped auxiliary, and decides whether a form
                # of «быть» has to be inserted in front of it.
                item.target = Target(
                    participle="short-passive",
                    tense="past",
                    number=self._number_of(subject),
                )
                item.note = "passive voice"
                continue

            if item.dep in {"xcomp", "acl"} and item.head.tag == "VB":
                item.target = Target(infinitive=True)
                item.note = "infinitive complement"
                continue

            tense = self._tense_of(item, items, future=future)
            person = self._person_of(subject)
            number = self._number_of(subject)
            item.target = Target(
                tense=tense,
                person=None if tense == "past" else person,
                number=number,
                # Russian past-tense verbs agree with their subject in gender, which English
                # never marks - the value has to come from the *Russian* subject noun.
                gender=None,
            )
            if passive:
                item.note = "passive voice"

    def _subject_of(self, item: Item, items: list[Item]) -> Item | None:
        for child in item.children:
            if items[child].dep in {"nsubj", "nsubjpass", "csubj", "expl"}:
                return items[child]
        return None

    def _modal_of(self, item: Item, items: list[Item]) -> Item | None:
        for child in item.children:
            candidate = items[child]
            if candidate.dep == "aux" and candidate.lemma in MODALS:
                return candidate
        return None

    @staticmethod
    def _tense_of(item: Item, items: list[Item], future: bool) -> str:
        """Tense of a verb, reading it off the auxiliary when English put it there.

        "did not translate" carries its tense on the dropped "did", and the main verb is
        left in the base form. Without this the past tense silently becomes a present:
        «не перевёл» would come out as «не переводит».
        """
        if future:
            return "futr"
        if item.head.tag in {"VBD", "VBN"}:
            return "past"
        for child in item.children:
            auxiliary = items[child]
            if auxiliary.dep not in {"aux", "auxpass"}:
                continue
            if auxiliary.head.tag == "VBD":
                return "past"
            if auxiliary.lemma == "have":
                # "has studied" / "have studied" - a perfect, rendered as a Russian past.
                return "past"
        return "pres"

    @staticmethod
    def _person_of(subject: Item | None) -> str:
        if subject is None:
            return "3per"
        lemma = subject.lemma
        if lemma in {"i", "we"}:
            return "1per"
        if lemma == "you":
            return "2per"
        return "3per"

    @staticmethod
    def _number_of(subject: Item | None) -> str | None:
        if subject is None:
            return "sing"
        if "Number=Plur" in subject.head.morph or subject.lemma in {"we", "they", "you"}:
            return "plur"
        return "sing"

    # -------------------------------------------------------------------- generation

    def _generate(self, items: list[Item]) -> None:
        """Generate Russian forms, heads before the dependents that agree with them."""
        nominal = {"NOUN", "PROPN", "PRON", "NUM"}

        for item in items:
            if not item.dropped and item.upos in nominal:
                self._generate_one(item)

        for item in items:
            if item.dropped or item.upos not in {"VERB", "AUX"}:
                continue
            if item.nominal_modifier:
                # Tagged a verb, used as a noun modifier, and the dictionary gave a noun:
                # decline it as the nominal it is rather than conjugating it.
                self._generate_one(item)
            elif self._is_participle(item, items):
                self._generate_participle(item, items)
            else:
                self._generate_verb(item, items)

        for item in items:
            if item.dropped or item.upos not in {"ADJ", "DET"}:
                continue
            if item.nominal_modifier:
                self._generate_one(item)
            elif self._is_participle(item, items):
                self._generate_participle(item, items)
            else:
                self._generate_modifier(item, items)

        for item in items:
            if not item.dropped and item.surface == "" and item.kind is Kind.WORD:
                self._generate_one(item)

    def _generate_one(self, item: Item) -> None:
        head = item.head

        if head.upos == "PRON" and item.lemma in PRONOUNS:
            forms = PRONOUNS[item.lemma]
            item.surface = forms.get(item.case or "nom", forms["nom"])
            item.kind = Kind.FUNCTION
            item.note = item.note or "pronoun form chosen by case"
            return

        if item.lemma in FUNCTION_WORDS and item.upos in {"ADV", "CCONJ", "SCONJ", "PART", "DET"}:
            item.surface = FUNCTION_WORDS[item.lemma]
            item.kind = Kind.FUNCTION
            return

        lemma = item.chosen_lemma
        if not lemma:
            self._untranslated(item)
            return

        number = "plur" if "Number=Plur" in head.morph else "sing"
        target = Target(case=item.case, number=number)
        form = self.morph.inflect(lemma, target, want_pos=self._want_pos(item))
        item.form = form
        item.surface = form.surface
        item.target = target

    def _generate_verb(self, item: Item, items: list[Item]) -> None:
        lemma = item.chosen_lemma
        modal = self._modal_of(item, items)

        if modal is not None:
            self._insert_modal(item, modal, items)

        if not lemma:
            self._untranslated(item)
            return

        target = item.target
        subject = self._subject_of(item, items)

        if target.participle == "short-passive":
            self._generate_passive(item, items, subject, lemma)
            return

        if target.tense == "past" and subject is not None and subject.form is not None:
            # Now that the subject exists in Russian, its gender is known and the past-tense
            # verb can agree with it: «модель изучала», «метод изучал».
            gender = subject.form.gender or self.morph.gender_of(subject.surface)
            if target.number != "plur" and gender:
                target = Target(
                    tense=target.tense, number=target.number, gender=gender, person=None
                )

        lemma = self._pick_aspect(item, lemma, target)
        form = self.morph.inflect(lemma, target, want_pos="INFN" if target.infinitive else "VERB")

        if target.tense == "futr" and not form.inflected:
            # Imperfective verbs have no simple future: «будет изучать», not «*изучает».
            auxiliary = "будут" if target.number == "plur" else "будет"
            item.inserted_before.append(
                Piece(
                    surface=auxiliary,
                    kind=Kind.AUXILIARY,
                    source_indices=tuple(t.index for t in item.unit.tokens),
                    source_text=item.unit.tokens[0].text,
                    note="compound future of an imperfective verb",
                )
            )
            form = self.morph.inflect(lemma, Target(infinitive=True), want_pos="INFN")

        item.form = form
        item.surface = form.surface
        item.target = target

    def _pick_aspect(self, item: Item, lemma: str, target: Target) -> str:
        """Choose between a sense's perfective and imperfective equivalents.

        English marks no aspect, so the dictionary offers both - «остаться» and
        «оставаться», «изучить» and «изучать» - and picks whichever the lexicographer listed
        first. Russian, though, has no present tense for a perfective verb: asking «остаться»
        for a present-tense form fails and the word comes out as a bare infinitive. The tense
        the transfer stage wants therefore decides the aspect: imperfective for the present,
        perfective for the future, and for the past whichever form actually inflects.
        """
        choice = item.disambiguation.chosen if item.disambiguation else None
        if choice is None or len(choice.sense.translations) < 2:
            return lemma

        wanted = {"pres": "impf", "futr": "perf"}.get(target.tense or "")
        candidates = [t.plain for t in choice.sense.translations[:6]]

        best: str | None = None
        for candidate in candidates:
            if " " in candidate:
                continue
            aspect = self.morph.aspect_of(candidate)
            inflects = self.morph.can_inflect(candidate, target, want_pos="VERB")
            if wanted and aspect == wanted and inflects:
                return candidate
            if best is None and inflects:
                best = candidate
        return best or lemma

    def _generate_passive(
        self, item: Item, items: list[Item], subject: Item | None, lemma: str
    ) -> None:
        """Render an English passive as a Russian short passive participle."""
        gender = None
        if subject is not None:
            gender = (
                subject.form.gender
                if subject.form is not None
                else self.morph.gender_of(subject.surface or subject.lemma)
            )
        number = item.target.number or "sing"
        target = Target(participle="short-passive", tense="past", number=number, gender=gender)

        # Only a perfective verb has a past passive participle; the imperfective offers
        # «вычисляемы», which no one writes. Pick the equivalent that actually inflects.
        lemma = self._pick_participle_aspect(item, lemma, target)
        form = self.morph.inflect(lemma, target, want_pos="INFN")

        english_tense = self._english_passive_tense(item, items)
        if english_tense in {"past", "futr"}:
            auxiliary = self._be_form(english_tense, number, gender)
            item.inserted_before.append(
                Piece(
                    surface=auxiliary,
                    kind=Kind.AUXILIARY,
                    source_indices=tuple(t.index for t in item.unit.tokens),
                    source_text=item.unit.tokens[0].text,
                    lemma="быть",
                    note=f"{english_tense} passive needs a form of «быть»",
                )
            )

        if not form.inflected:
            # No participle exists: fall back to a finite verb, which is wrong in voice but
            # right in meaning, and say so in the trace.
            form = self.morph.inflect(
                lemma,
                Target(tense="pres", number=number, person="3per"),
                want_pos="VERB",
            )
            item.note = "passive rendered as active: no Russian participle for this verb"

        item.form = form
        item.target = target
        item.surface = form.surface

    def _english_passive_tense(self, item: Item, items: list[Item]) -> str:
        """Tense of the passive, read off the auxiliary that was dropped."""
        for child in item.children:
            auxiliary = items[child]
            if auxiliary.head.dep != "auxpass":
                continue
            if auxiliary.head.tag == "VBD":
                return "past"
            if auxiliary.head.tag == "VB":
                # "will be told" - the modal was already turned into a future marker.
                return "futr"
        if item.head.tag == "VBN" and any(
            items[child].lemma in {"have", "has", "had"} for child in item.children
        ):
            return "past"
        return "pres"

    def _be_form(self, tense: str, number: str, gender: str | None) -> str:
        if tense == "futr":
            return "будут" if number == "plur" else "будет"
        if number == "plur":
            return "были"
        return {"femn": "была", "neut": "было"}.get(gender or "masc", "был")

    def _insert_modal(self, item: Item, modal: Item, items: list[Item]) -> None:
        """Realise an English modal as a Russian modal word or predicative."""
        russian, mode = MODALS[modal.lemma]
        modal.dropped = True
        modal.note = f"realised as «{russian}»"

        subject = self._subject_of(item, items)
        number = self._number_of(subject)

        if mode == "predicative":
            gender = None
            if subject is not None and subject.form is not None:
                gender = subject.form.gender
            surface = self.morph.inflect(
                russian, Target(number=number, gender=gender), want_pos="ADJS"
            ).surface
        elif mode == "impersonal":
            surface = russian
        elif mode == "past":
            surface = self.morph.inflect(russian, Target(tense="past", number=number)).surface
        else:
            surface = self.morph.inflect(
                russian, Target(tense="pres", person=self._person_of(subject), number=number)
            ).surface

        item.inserted_before.append(
            Piece(
                surface=surface,
                kind=Kind.AUXILIARY,
                source_indices=(modal.head.index,),
                source_text=modal.head.text,
                lemma=russian,
                note=f"modal «{modal.head.text}»",
            )
        )

    @staticmethod
    def _is_participle(item: Item, items: list[Item]) -> bool:
        """Whether this word modifies a noun with a verb form.

        "distributed representations", "hidden states", "a weighted sum", "the training
        procedure" - English attaches participles to nouns constantly, and a translator that
        conjugates them instead produces «распределил представления», a finite verb where a
        modifier belongs. The test is the tag, not the tagger's part of speech: spaCy calls
        the same word ADJ in one sentence and VERB in another.
        """
        if item.head.tag not in {"VBN", "VBG"}:
            return False
        if item.dep not in {"amod", "acl", "relcl", "advcl", "npadvmod", "compound"}:
            return False
        if item.parent is None:
            return False
        return items[item.parent].upos in {"NOUN", "PROPN", "PRON"}

    def _generate_participle(self, item: Item, items: list[Item]) -> None:
        """Generate a declined participle agreeing with the noun it modifies."""
        lemma = item.chosen_lemma
        if not lemma:
            self._untranslated(item)
            return

        head_item = items[item.parent] if item.parent is not None else None
        gender = number = animacy = None
        case = item.case
        if head_item is not None:
            if head_item.form is not None:
                gender = head_item.form.gender
                number = head_item.form.number
            if gender is None:
                gender = self.morph.gender_of(head_item.surface or head_item.lemma)
            if number is None:
                number = "plur" if "Number=Plur" in head_item.head.morph else "sing"
            case = head_item.case or case
            animacy = self._animacy_of(head_item)

        # A past participle is passive ("the distributed representations" - they were
        # distributed); a present participle is active ("the learning model" - it learns).
        voice = "passive" if item.head.tag == "VBN" else "active"
        tense = "past" if voice == "passive" else "pres"
        target = Target(
            case=case or "nom",
            number=number,
            gender=gender,
            animacy=animacy,
            tense=tense,
            participle=voice,
        )

        lemma = self._pick_participle_aspect(item, lemma, target)
        form = self.morph.inflect(lemma, target, want_pos="INFN")
        if not form.inflected:
            # No participle exists for this verb; an adjectival reading of the dictionary
            # form is still better than a conjugated one.
            item.surface = self._agree(lemma, item, head_item, want_pos="ADJF")
            item.note = "no Russian participle available; rendered as a modifier"
            return

        item.form = form
        item.target = target
        item.surface = form.surface
        item.note = f"{voice} participle, agreeing with its noun"

    def _pick_participle_aspect(self, item: Item, lemma: str, target: Target) -> str:
        """Prefer the equivalent whose aspect owns the participle we actually want.

        A past passive participle exists only for perfective verbs - «оценено» from
        «оценить». Asking an imperfective for one and letting the generator relax the tense
        produces «оцениваемо»: a real form that no one writes. So a perfective equivalent
        that inflects exactly is preferred over an imperfective one that only inflects after
        the request has been weakened.
        """
        choice = item.disambiguation.chosen if item.disambiguation else None
        if choice is None or len(choice.sense.translations) < 2:
            return lemma

        wanted_aspect = "perf" if target.tense == "past" else "impf"
        fallback: str | None = None
        for candidate in (t.plain for t in choice.sense.translations[:6]):
            if " " in candidate:
                continue
            if not self.morph.can_inflect(candidate, target, want_pos="INFN"):
                continue
            if self.morph.aspect_of(candidate) == wanted_aspect:
                return candidate
            fallback = fallback or candidate
        return fallback or lemma

    def _generate_modifier(self, item: Item, items: list[Item]) -> None:
        """Adjectives, participles and determiners agree with the noun they modify."""
        head_item = items[item.parent] if item.parent is not None else None

        if item.upos == "DET":
            lemma = KEPT_DETERMINERS.get(item.lemma) or POSSESSIVES.get(item.lemma)
            if lemma is None:
                if not item.dropped:
                    item.dropped = True
                    item.note = item.note or "determiner with no Russian equivalent"
                return
            if item.lemma in POSSESSIVES and lemma in {"его", "её", "их"}:
                # Third-person possessives do not decline in Russian.
                item.surface = lemma
                item.kind = Kind.FUNCTION
                return
            item.surface = self._agree(lemma, item, head_item, want_pos="ADJF")
            item.kind = Kind.FUNCTION
            return

        lemma = item.chosen_lemma
        if not lemma:
            self._untranslated(item)
            return

        if item.dep in {"acomp", "oprd"}:
            # A predicate adjective after a dropped copula: the short form is the
            # scientific-prose default - «модель проста».
            subject = (
                self._subject_of(items[item.parent], items) if item.parent is not None else None
            )
            short = self._agree(lemma, item, subject, want_pos="ADJF", short=True)
            if short and short != lemma:
                item.surface = short
                item.note = "short form: predicate of a zero copula"
                return

        item.surface = self._agree(lemma, item, head_item, want_pos="ADJF")

    def _agree(
        self,
        lemma: str,
        item: Item,
        head_item: Item | None,
        want_pos: str,
        short: bool = False,
    ) -> str:
        """Inflect `lemma` to agree with `head_item`."""
        gender = number = animacy = None
        case = item.case
        if head_item is not None:
            if head_item.form is not None:
                gender = head_item.form.gender
                number = head_item.form.number
            if gender is None:
                gender = self.morph.gender_of(head_item.surface or head_item.lemma)
            if number is None:
                number = "plur" if "Number=Plur" in head_item.head.morph else "sing"
            case = head_item.case or case
            animacy = self._animacy_of(head_item)

        target = Target(
            case=case or "nom",
            number=number,
            gender=gender,
            animacy=animacy,
            short=short,
        )
        form = self.morph.inflect(lemma, target, want_pos=want_pos)
        item.form = form
        item.target = target
        return form.surface if form.surface else lemma

    def _animacy_of(self, head_item: Item) -> str | None:
        """Animacy of a head noun, for the modifiers that have to agree with it."""
        word = head_item.surface or head_item.chosen_lemma
        if not word:
            return None
        return "anim" if self.morph.is_animate(word) else "inan"

    def _untranslated(self, item: Item) -> None:
        """No dictionary entry: transcribe a name, keep anything else in Latin script.

        Capitalisation alone is not evidence of a name at the start of a sentence, where
        every word is capitalised - "Neural machine translation…" would otherwise open with
        a transcribed «Нюрал» rather than an honest, visibly untranslated "Neural". The
        named-entity recogniser is consulted instead, and it is right in exactly the cases
        the tagger is not.
        """
        text = item.unit.tokens[0].text if item.unit.tokens else ""
        is_name = (
            item.upos == "PROPN"
            or item.head.ent_type in NAME_ENTITIES
            or (item.head.is_title and item.head.index > 0)
        )
        if is_name:
            item.surface = transcribe(text)
            item.kind = Kind.UNTRANSLATED
            item.note = "not in the dictionary: transcribed"
        elif any(character.isdigit() for character in text):
            item.surface = text
            item.kind = Kind.WORD
        else:
            item.surface = text
            item.kind = Kind.UNTRANSLATED
            item.note = "not in the dictionary"

    # ----------------------------------------------------------------------- ordering

    def _assign_order(self, items: list[Item]) -> None:
        for item in items:
            item.order = float(item.head.index)

        for item in items:
            # A nominal modifier always moves behind its head. A possessive or nominal
            # modifier that is *not* nominal in Russian - «его статья» - stays in front.
            postposable = item.nominal_modifier or (
                item.dep in POSTPOSED and item.upos in {"NOUN", "PROPN", "NUM"}
            )
            if postposable and item.parent is not None:
                parent = items[item.parent]
                if item.head.index < parent.head.index:
                    # Half a step past the head, and a fraction of the source position on
                    # top, so two postposed modifiers keep their relative order.
                    item.order = parent.head.index + 0.5 + item.head.index / 1000.0
                    item.note = item.note or "postposed as a genitive, as Russian requires"

    def _emit(self, items: list[Item]) -> list[Piece]:
        pieces: list[Piece] = []
        for item in sorted(items, key=lambda i: i.order):
            source_indices = tuple(token.index for token in item.unit.tokens)
            source_text = "".join(
                token.text + token.whitespace for token in item.unit.tokens
            ).strip()

            for extra in item.inserted_before:
                extra.order = item.order - 0.01
                pieces.append(extra)

            if item.dropped or not item.surface:
                pieces.append(
                    Piece(
                        surface="",
                        kind=Kind.DROPPED,
                        source_indices=source_indices,
                        source_text=source_text,
                        note=item.note or "dropped",
                        order=item.order,
                    )
                )
                continue

            surface = item.surface
            if item.kind is Kind.PREPOSITION:
                surface = euphonic(surface, self._next_surface(items, item))

            pieces.append(
                Piece(
                    surface=surface,
                    kind=item.kind,
                    source_indices=source_indices,
                    source_text=source_text,
                    lemma=item.form.lemma if item.form else item.chosen_lemma,
                    tag=item.form.tag if item.form else "",
                    decoded=tuple(item.form.decoded) if item.form else (),
                    case=item.case,
                    note=item.note,
                    order=item.order,
                )
            )
        return pieces

    @staticmethod
    def _want_pos(item: Item) -> str | None:
        """Which Russian part of speech pymorphy3 should look for.

        «данные» is both a noun and a participle, «печать» both a noun and a verb form; the
        English tag already says which one the dictionary meant, so passing it through stops
        the analyser from guessing.
        """
        if item.nominal_modifier:
            return "NOUN"
        return {
            "NOUN": "NOUN",
            "PROPN": "NOUN",
            "PRON": "NPRO",
            "NUM": "NUMR",
            "VERB": "INFN",
            "AUX": "INFN",
            "ADJ": "ADJF",
            "ADV": "ADVB",
        }.get(item.upos)

    @staticmethod
    def _next_surface(items: list[Item], current: Item) -> str:
        following = [i for i in items if i.order > current.order and i.surface and not i.dropped]
        following.sort(key=lambda i: i.order)
        return following[0].surface if following else ""

    # --------------------------------------------------------------------- the trace

    def _stage_text(
        self, items: list[Item], lexical_only: bool = False, ordered: bool = True
    ) -> str:
        """Render the sentence as it stands after one stage, for the architecture trace."""
        sequence = sorted(items, key=lambda i: i.order) if ordered else items
        out: list[str] = []
        for item in sequence:
            if lexical_only:
                if item.head.is_punct:
                    out.append(item.head.text)
                    continue
                lemma = item.chosen_lemma
                out.append(lemma if lemma else item.unit.tokens[0].text)
                continue
            if item.dropped:
                continue
            for extra in item.inserted_before:
                out.append(extra.surface)
            if item.surface:
                out.append(item.surface)
        return detokenise([Piece(surface=word, kind=Kind.WORD) for word in out if word])
