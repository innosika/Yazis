"""Part-of-speech tags and their decoding, for both languages.

The assignment asks for «теги частей речи и их расшифровка» - the tag *and* a decoding a
non-linguist can read. Three tagsets meet in this system and each needs its own table:

* **Universal POS** - spaCy's coarse tag, the one the translator branches on.
* **Penn Treebank** - spaCy's fine tag, which is where tense, number and degree actually
  live for English (`VBZ` = 3rd-person singular present, `NNS` = plural noun).
* **OpenCorpora** - pymorphy3's tagset, describing the Russian forms this system *generates*.

The tables are exhaustive on purpose: `test_tagset.py` asserts that every tag the pipeline
can emit has an entry, so the interface can never show a bare code with no explanation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TagInfo:
    code: str
    name: str
    description: str
    examples: str = ""


def _table(rows: list[tuple[str, str, str, str]]) -> dict[str, TagInfo]:
    return {
        code: TagInfo(code, name, description, examples)
        for code, name, description, examples in rows
    }


# ---------------------------------------------------------------- Universal POS (coarse)

UPOS: dict[str, TagInfo] = _table(
    [
        ("ADJ", "adjective", "Describes a property of a noun.", "large, neural, unclear"),
        ("ADP", "preposition", "Relates a noun to the rest of the clause.", "of, in, with"),
        ("ADV", "adverb", "Modifies a verb, adjective or clause.", "however, quickly, very"),
        (
            "AUX",
            "auxiliary verb",
            "Carries tense, mood or voice for a main verb.",
            "is, have, will",
        ),
        ("CCONJ", "coordinating conjunction", "Joins equal elements.", "and, or, but"),
        ("DET", "determiner", "Specifies a noun; Russian has no articles.", "the, a, this"),
        ("INTJ", "interjection", "Stands outside the sentence structure.", "oh, alas"),
        ("NOUN", "noun", "Names a thing, person or concept.", "network, model, essay"),
        ("NUM", "numeral", "Expresses a quantity or order.", "two, 42, third"),
        ("PART", "particle", "Function word with no independent meaning.", "not, 's, to"),
        ("PRON", "pronoun", "Stands in for a noun phrase.", "it, they, which"),
        (
            "PROPN",
            "proper noun",
            "Names a specific entity; usually transcribed.",
            "Turing, Tolstoy",
        ),
        ("PUNCT", "punctuation", "Punctuation mark.", ". , ; —"),
        (
            "SCONJ",
            "subordinating conjunction",
            "Introduces a dependent clause.",
            "that, because, if",
        ),
        ("SYM", "symbol", "Non-alphabetic symbol.", "%, ©, +"),
        ("VERB", "verb", "Names an action or state.", "learns, studied, remains"),
        ("X", "other", "Foreign or unanalysable material.", ""),
        ("SPACE", "whitespace", "Layout only; carries no meaning.", ""),
        ("EOL", "line break", "Layout only; carries no meaning.", ""),
    ]
)

# --------------------------------------------------------------- Penn Treebank (fine)

PENN: dict[str, TagInfo] = _table(
    [
        ("CC", "coordinating conjunction", "Joins equal elements.", "and, or"),
        ("CD", "cardinal number", "A counting number.", "one, 2025"),
        ("DT", "determiner", "Article or demonstrative.", "the, a, those"),
        ("EX", "existential there", "Subject of an existential clause.", "there is"),
        ("FW", "foreign word", "Not English.", "de facto"),
        (
            "IN",
            "preposition / subordinating conjunction",
            "Introduces a phrase or clause.",
            "of, that",
        ),
        ("JJ", "adjective", "Positive degree.", "large, neural"),
        ("JJR", "adjective, comparative", "Comparative degree.", "larger, better"),
        ("JJS", "adjective, superlative", "Superlative degree.", "largest, best"),
        ("LS", "list marker", "Enumeration label.", "1., a)"),
        ("MD", "modal verb", "Expresses possibility, necessity or will.", "can, must, will"),
        ("NN", "noun, singular or mass", "Singular or uncountable noun.", "network, data"),
        ("NNS", "noun, plural", "Plural noun.", "networks, models"),
        ("NNP", "proper noun, singular", "Name of one entity.", "Turing, Python"),
        ("NNPS", "proper noun, plural", "Name of several entities.", "Romantics"),
        ("PDT", "predeterminer", "Precedes a determiner.", "all the, both the"),
        (
            "POS",
            "possessive ending",
            "The 's of the possessive; becomes a Russian genitive.",
            "author's",
        ),
        ("PRP", "personal pronoun", "Refers to a participant.", "he, they, it"),
        ("PRP$", "possessive pronoun", "Marks a possessor.", "his, their"),
        ("RB", "adverb", "Positive degree.", "however, quickly"),
        ("RBR", "adverb, comparative", "Comparative degree.", "faster, more"),
        ("RBS", "adverb, superlative", "Superlative degree.", "fastest, most"),
        ("RP", "particle", "Part of a phrasal verb.", "give up, point out"),
        ("SYM", "symbol", "Non-alphabetic symbol.", "%, ="),
        ("TO", "infinitival to", "Marks an infinitive.", "to learn"),
        ("UH", "interjection", "Outside the sentence structure.", "oh"),
        ("VB", "verb, base form", "Infinitive or imperative.", "learn, study"),
        ("VBD", "verb, past tense", "Simple past.", "learned, studied"),
        ("VBG", "verb, gerund or present participle", "-ing form.", "learning, studying"),
        ("VBN", "verb, past participle", "Perfect or passive participle.", "learned, written"),
        (
            "VBP",
            "verb, non-3rd person singular present",
            "Present, any person but he/she/it.",
            "learn, study",
        ),
        ("VBZ", "verb, 3rd person singular present", "Present with he/she/it.", "learns, studies"),
        ("WDT", "wh-determiner", "Question or relative determiner.", "which, whatever"),
        ("WP", "wh-pronoun", "Question or relative pronoun.", "who, what"),
        ("WP$", "possessive wh-pronoun", "Relative possessor.", "whose"),
        ("WRB", "wh-adverb", "Question or relative adverb.", "when, where, how"),
        ("AFX", "affix", "Bound morpheme written separately.", "pre-, post-"),
        ("ADD", "email or URL", "Machine address.", "example.com"),
        ("GW", "go-with", "Fragment of a split word.", ""),
        ("HYPH", "hyphen", "Hyphen inside a compound.", "-"),
        ("NFP", "superfluous punctuation", "Stray punctuation.", "***"),
        ("XX", "unknown", "Unanalysable token.", ""),
        ("$", "currency symbol", "Currency marker.", "$, €"),
        ("#", "number sign", "Hash mark.", "#"),
        ('"', "quotation mark", "Straight quote.", '"'),
        ("``", "opening quotation mark", "Left quote.", "“"),
        ("''", "closing quotation mark", "Right quote.", "”"),
        ("(", "opening bracket", "Left bracket.", "("),
        (")", "closing bracket", "Right bracket.", ")"),
        ("-LRB-", "opening bracket", "Left bracket.", "("),
        ("-RRB-", "closing bracket", "Right bracket.", ")"),
        (",", "comma", "Comma.", ","),
        (".", "sentence-final punctuation", "Full stop, question or exclamation mark.", ". ? !"),
        (":", "colon or ellipsis", "Colon, semicolon or ellipsis.", ": ; …"),
        ("_SP", "whitespace", "Layout only.", ""),
        ("SP", "whitespace", "Layout only.", ""),
    ]
)

# ------------------------------------------------- Universal Dependencies morphology

FEATURE_VALUES: dict[str, dict[str, str]] = {
    "Number": {"Sing": "singular", "Plur": "plural"},
    "Tense": {"Past": "past", "Pres": "present", "Fut": "future"},
    "Person": {"1": "1st person", "2": "2nd person", "3": "3rd person"},
    "Mood": {"Ind": "indicative", "Imp": "imperative", "Sub": "subjunctive"},
    "VerbForm": {
        "Fin": "finite",
        "Inf": "infinitive",
        "Part": "participle",
        "Ger": "gerund",
        "Sup": "supine",
    },
    "Aspect": {"Perf": "perfect", "Prog": "progressive", "Imp": "imperfective"},
    "Voice": {"Act": "active", "Pass": "passive"},
    "Degree": {"Pos": "positive", "Cmp": "comparative", "Sup": "superlative", "Abs": "absolute"},
    "Case": {
        "Nom": "nominative",
        "Acc": "accusative",
        "Gen": "genitive",
        "Dat": "dative",
        "Ins": "instrumental",
        "Loc": "locative",
    },
    "Gender": {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter"},
    "Definite": {"Def": "definite", "Ind": "indefinite"},
    "PronType": {
        "Art": "article",
        "Prs": "personal",
        "Dem": "demonstrative",
        "Int": "interrogative",
        "Rel": "relative",
        "Neg": "negative",
        "Tot": "total",
        "Ind": "indefinite",
    },
    "NumType": {"Card": "cardinal", "Ord": "ordinal", "Mult": "multiplicative", "Frac": "fraction"},
    "Poss": {"Yes": "possessive"},
    "Reflex": {"Yes": "reflexive"},
    "Foreign": {"Yes": "foreign"},
    "Abbr": {"Yes": "abbreviation"},
    "Typo": {"Yes": "typo"},
    "ConjType": {"Cmp": "comparative"},
    "Polarity": {"Neg": "negative", "Pos": "positive"},
    "PunctType": {
        "Peri": "full stop",
        "Comm": "comma",
        "Qest": "question mark",
        "Excl": "exclamation mark",
        "Dash": "dash",
        "Brck": "bracket",
        "Quot": "quotation mark",
        "Colo": "colon",
        "Semi": "semicolon",
    },
    "PunctSide": {"Ini": "opening", "Fin": "closing"},
    "PartType": {"Inf": "infinitive marker", "Neg": "negation"},
    "AdvType": {"Ex": "existential"},
    "NounType": {"Prop": "proper"},
    "Style": {"Arch": "archaic", "Coll": "colloquial", "Expr": "expressive"},
}

FEATURE_NAMES: dict[str, str] = {
    "Number": "number",
    "Tense": "tense",
    "Person": "person",
    "Mood": "mood",
    "VerbForm": "verb form",
    "Aspect": "aspect",
    "Voice": "voice",
    "Degree": "degree",
    "Case": "case",
    "Gender": "gender",
    "Definite": "definiteness",
    "PronType": "pronoun type",
    "NumType": "numeral type",
    "Poss": "possession",
    "Reflex": "reflexivity",
    "Foreign": "foreign",
    "Abbr": "abbreviation",
    "Typo": "typo",
    "ConjType": "conjunction type",
    "Polarity": "polarity",
    "PunctType": "punctuation",
    "PunctSide": "punctuation side",
    "PartType": "particle type",
    "AdvType": "adverb type",
    "NounType": "noun type",
    "Style": "style",
}

# ----------------------------------------------------------- OpenCorpora (Russian output)

OPENCORPORA: dict[str, TagInfo] = _table(
    [
        ("NOUN", "noun", "Russian noun; inflects for case and number.", "сеть, модель"),
        (
            "ADJF",
            "adjective, full form",
            "Agrees with its noun in gender, number and case.",
            "нейронный",
        ),
        ("ADJS", "adjective, short form", "Predicative adjective.", "проста"),
        ("COMP", "comparative", "Comparative form.", "быстрее"),
        ("VERB", "verb, finite", "Inflects for person, number, tense and gender.", "изучает"),
        ("INFN", "verb, infinitive", "Dictionary form of a verb.", "изучать"),
        ("PRTF", "participle, full form", "Verbal adjective, declined.", "изучающий"),
        ("PRTS", "participle, short form", "Predicative participle.", "изучен"),
        ("GRND", "gerund", "Verbal adverb.", "изучая"),
        ("NUMR", "numeral", "Counting word.", "два"),
        ("ADVB", "adverb", "Modifies a verb or adjective.", "быстро"),
        ("NPRO", "pronoun-noun", "Pronoun used as a noun.", "он, который"),
        ("PRED", "predicative", "Impersonal predicate.", "нужно"),
        ("PREP", "preposition", "Governs a case.", "в, с, из"),
        ("CONJ", "conjunction", "Joins clauses or phrases.", "и, но"),
        ("PRCL", "particle", "Function word.", "не, бы"),
        ("INTJ", "interjection", "Outside the sentence structure.", "ах"),
        # Grammemes, decoded so the Russian column can be read without a linguistics course.
        ("nomn", "nominative", "Subject case.", "сеть"),
        ("gent", "genitive", "Of-case: possession, absence, quantity.", "сети"),
        ("datv", "dative", "To-case: recipient.", "сети"),
        ("accs", "accusative", "Direct-object case.", "сеть"),
        ("ablt", "instrumental", "By-case: means, agent.", "сетью"),
        ("loct", "prepositional", "In/about-case, always with a preposition.", "сети"),
        ("voct", "vocative", "Address form.", "Господи"),
        ("gen1", "genitive", "First genitive.", ""),
        ("gen2", "partitive genitive", "Quantity genitive.", "чаю"),
        ("acc2", "second accusative", "Accusative in a fixed frame.", ""),
        ("loc1", "prepositional", "First prepositional.", ""),
        ("loc2", "locative", "Locative in -у.", "в лесу"),
        ("sing", "singular", "One.", ""),
        ("plur", "plural", "More than one.", ""),
        ("masc", "masculine", "Masculine gender.", ""),
        ("femn", "feminine", "Feminine gender.", ""),
        ("neut", "neuter", "Neuter gender.", ""),
        ("ms-f", "common gender", "Masculine or feminine.", ""),
        ("Ms-f", "common gender", "Masculine or feminine.", ""),
        ("anim", "animate", "Animate noun.", ""),
        ("inan", "inanimate", "Inanimate noun.", ""),
        ("perf", "perfective", "Completed action.", "изучить"),
        ("impf", "imperfective", "Ongoing or habitual action.", "изучать"),
        ("tran", "transitive", "Takes a direct object.", ""),
        ("intr", "intransitive", "Takes no direct object.", ""),
        ("pres", "present tense", "Now.", ""),
        ("past", "past tense", "Before now.", ""),
        ("futr", "future tense", "After now.", ""),
        ("1per", "1st person", "Speaker.", ""),
        ("2per", "2nd person", "Addressee.", ""),
        ("3per", "3rd person", "Neither speaker nor addressee.", ""),
        ("indc", "indicative", "Statement.", ""),
        ("impr", "imperative", "Command.", ""),
        ("actv", "active voice", "Subject performs the action.", ""),
        ("pssv", "passive voice", "Subject undergoes the action.", ""),
        ("Infr", "informal", "Colloquial register.", ""),
        ("Arch", "archaic", "Obsolete register.", ""),
        ("Erro", "erroneous", "Misspelling.", ""),
        ("Name", "given name", "Personal name.", ""),
        ("Surn", "surname", "Family name.", ""),
        ("Patr", "patronymic", "Middle name.", ""),
        ("Geox", "toponym", "Place name.", ""),
        ("Orgn", "organisation", "Organisation name.", ""),
        ("Abbr", "abbreviation", "Shortened form.", ""),
        ("Fixd", "indeclinable", "Never inflects.", ""),
        ("Sgtm", "singular only", "No plural.", ""),
        ("Pltm", "plural only", "No singular.", ""),
        ("Qual", "qualitative", "Gradable adjective.", ""),
        ("Apro", "pronominal", "Pronoun-like adjective.", ""),
        ("Anum", "numeral-like", "Ordinal-like adjective.", ""),
        ("Poss", "possessive", "Expresses possession.", ""),
        ("Supr", "superlative", "Highest degree.", ""),
        ("V-ey", "variant form", "Alternative ending -ей.", ""),
        ("V-oy", "variant form", "Alternative ending -ою.", ""),
        ("V-ej", "variant form", "Alternative ending -ей.", ""),
        ("Vpre", "variant with preposition", "Form used after a preposition.", ""),
        ("Af-p", "after preposition", "Only after a preposition.", ""),
        ("Inmx", "animacy ambiguous", "Animate or inanimate.", ""),
        ("GNdr", "gender ambiguous", "Gender undetermined.", ""),
        ("Dist", "distorted", "Non-standard spelling.", ""),
        ("Litr", "literary", "Bookish register.", ""),
        ("Prdx", "predicative", "Can act as a predicate.", ""),
        ("Coun", "collective numeral", "Counting form.", ""),
        ("Coll", "collective", "Collective noun.", ""),
        ("Slng", "slang", "Slang register.", ""),
        ("Subx", "possibly noun", "Possibly substantivised.", ""),
        ("Supn", "supine", "Supine form.", ""),
        ("Anph", "anaphoric", "Refers back.", ""),
        ("Init", "initial", "Initialism.", ""),
        ("Adjx", "possibly adjective", "Possibly adjectival.", ""),
        ("Ques", "interrogative", "Question word.", ""),
        ("Dmns", "demonstrative", "Pointing word.", ""),
        ("Prnt", "parenthetical", "Aside.", ""),
        ("V-be", "variant form", "Alternative ending -ье.", ""),
        ("V-en", "variant form", "Alternative ending -ен.", ""),
        ("V-ie", "variant form", "Alternative ending -ие.", ""),
        ("V-bi", "variant form", "Alternative ending -ьи.", ""),
        ("Fimp", "imperfective source", "Base of an imperfective pair.", ""),
        ("Prdk", "predicative only", "Only predicative.", ""),
        ("Or-8", "variant spelling", "Spelling with ё.", ""),
        ("Impe", "impersonal", "No subject.", ""),
        ("Impx", "possibly impersonal", "Possibly subjectless.", ""),
        ("Mult", "iterative", "Repeated action.", ""),
        ("Refl", "reflexive", "Action on the subject.", ""),
        ("Trad", "traditional", "Traditional spelling.", ""),
        ("Hypo", "hypocoristic", "Diminutive.", ""),
        ("Dist", "distorted", "Non-standard spelling.", ""),
    ]
)


def explain_upos(tag: str) -> TagInfo:
    return UPOS.get(tag, TagInfo(tag, tag.lower(), "No decoding available for this tag."))


def explain_penn(tag: str) -> TagInfo:
    return PENN.get(tag, TagInfo(tag, tag.lower(), "No decoding available for this tag."))


def explain_features(morph: str) -> list[str]:
    """Decode a spaCy morph string, "Number=Sing|Tense=Pres", into readable phrases."""
    decoded: list[str] = []
    for item in (morph or "").split("|"):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        name = FEATURE_NAMES.get(key, key.lower())
        readable = FEATURE_VALUES.get(key, {}).get(value, value.lower())
        decoded.append(f"{name}: {readable}")
    return decoded


def explain_opencorpora(tag: str) -> list[str]:
    """Decode a pymorphy3 tag, "NOUN,inan,femn sing,gent", into readable phrases."""
    decoded: list[str] = []
    for grammeme in str(tag or "").replace(" ", ",").split(","):
        grammeme = grammeme.strip()
        if not grammeme:
            continue
        info = OPENCORPORA.get(grammeme)
        decoded.append(info.name if info else grammeme)
    return decoded
