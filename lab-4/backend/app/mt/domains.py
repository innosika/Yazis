"""Subject areas of variant 1, and the label vocabulary that identifies them.

Variant 1 names two subject areas - computer-science papers and literary essays - so the
translator is domain-aware rather than domain-blind. Two independent signals decide whether
a dictionary sense belongs to a domain:

*Topical labels.* Every gloss in the source dictionary may open with a parenthesised label
list - "(computing, Internet) A computer network: ...". These come from Wiktionary's own
topic templates, so they are curated data, not a heuristic: matching them is the single
strongest disambiguation signal available.

*Keyword profile.* A hand-built vocabulary of each field. Used when a sense carries no
topical label, which is the majority of senses.

Register labels work in the opposite direction. "computer" has an unlabelled-for-topic but
"(now, rare, chiefly, historical)" first sense - «вычислитель», a human calculator. Without a
register penalty a word-for-word translator would confidently render every "computer" in a
2025 paper as a 19th-century clerk.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Domain:
    code: str
    title: str
    description: str
    labels: frozenset[str]
    keywords: frozenset[str]
    # Register labels that are *not* penalised here: archaic diction is a legitimate
    # choice in a literary essay, but never in a systems paper.
    exempt_registers: frozenset[str] = field(default_factory=frozenset)


# The language sciences belong to the computer-science area, because variant 1's technical
# texts are papers about language processing. They are deliberately *not* added to the
# literary area: an essay on style is not about grammar, and treating «voice» in the
# grammatical sense as on-topic for a literary essay turns «голос» into «залог».
SHARED_LABELS: frozenset[str] = frozenset(
    {
        "linguistics",
        "computational linguistics",
        "grammar",
        "semantics",
        "syntax",
        "morphology",
        "phonetics",
        "phonology",
        "orthography",
        "lexicography",
        "translation studies",
        "typography",
        "philosophy",
        "logic",
        "history",
        "education",
        "statistics",
    }
)

COMPUTER_SCIENCE = Domain(
    code="cs",
    title="Computer Science",
    description="Scientific articles on computer science: systems, algorithms, ML, theory.",
    labels=frozenset(
        {
            "computing",
            "computer science",
            "programming",
            "software",
            "hardware",
            "internet",
            "networking",
            "databases",
            "database",
            "cryptography",
            "information technology",
            "electronics",
            "electrical engineering",
            "engineering",
            "telecommunications",
            "telephony",
            "cybernetics",
            "robotics",
            "automation",
            "mathematics",
            "arithmetic",
            "algebra",
            "geometry",
            "topology",
            "calculus",
            "logic",
            "mathematical logic",
            "set theory",
            "graph theory",
            "number theory",
            "category theory",
            "probability theory",
            "probability",
            "statistics",
            "machine learning",
            "artificial intelligence",
            "data science",
            "information theory",
            "computational linguistics",
            "physics",
            "mechanics",
            "units of measure",
            "typography",
            "sciences",
            "technology",
        }
    )
    | SHARED_LABELS,
    keywords=frozenset(
        {
            "computer",
            "computing",
            "computation",
            "computational",
            "algorithm",
            "data",
            "dataset",
            "database",
            "program",
            "programming",
            "software",
            "hardware",
            "code",
            "compiler",
            "processor",
            "memory",
            "storage",
            "file",
            "server",
            "client",
            "network",
            "protocol",
            "internet",
            "web",
            "system",
            "machine",
            "digital",
            "electronic",
            "binary",
            "bit",
            "byte",
            "encryption",
            "cipher",
            "interface",
            "function",
            "variable",
            "parameter",
            "argument",
            "value",
            "type",
            "class",
            "object",
            "instance",
            "pointer",
            "array",
            "matrix",
            "vector",
            "tensor",
            "graph",
            "node",
            "edge",
            "tree",
            "queue",
            "stack",
            "buffer",
            "cache",
            "thread",
            "process",
            "model",
            "neural",
            "neuron",
            "training",
            "learning",
            "inference",
            "classification",
            "regression",
            "optimisation",
            "optimization",
            "gradient",
            "probability",
            "statistical",
            "number",
            "integer",
            "set",
            "sequence",
            "symbol",
            "string",
            "token",
            "input",
            "output",
            "signal",
            "circuit",
            "device",
            "operation",
            "instruction",
            "register",
            "bandwidth",
            "latency",
            "throughput",
            "query",
            "index",
            "schema",
            "transaction",
            "packet",
            "router",
            # Variant 1 names *scientific articles* on computer science, not the field in
            # the abstract. The vocabulary of academic writing is therefore part of the
            # domain profile - it is what distinguishes "paper" the publication from
            # "paper" the sheet material.
            "paper",
            "article",
            "publication",
            "journal",
            "document",
            "written",
            "text",
            "academic",
            "science",
            "scientific",
            "research",
            "researcher",
            "study",
            "experiment",
            "hypothesis",
            "theory",
            "theorem",
            "proof",
            "method",
            "methodology",
            "approach",
            "technique",
            "analysis",
            "result",
            "conclusion",
            "evidence",
            "measurement",
            "experimental",
            "empirical",
            "report",
            "thesis",
            "citation",
            "reference",
            "abstract",
            "figure",
            "table",
            "equation",
            "formula",
            "definition",
            "property",
            "framework",
            "architecture",
            "implementation",
            "performance",
            "accuracy",
            "error",
            "benchmark",
            "evaluation",
            "corpus",
            # The vocabulary of a computer-science *paper*, which is what variant 1
            # names - not the field in the abstract.
            "problem",
            "solution",
            "solving",
            "solve",
            "task",
            "procedure",
            "step",
            "policy",
            "quality",
            "efficiency",
            "complexity",
            "measure",
            "metric",
            "criterion",
        }
    ),
)

LITERATURE = Domain(
    code="lit",
    title="Literature",
    description="Literary essays: prose, poetry, criticism, narrative and rhetoric.",
    labels=frozenset(
        {
            "literature",
            "literary",
            "literary criticism",
            "poetry",
            "poetic",
            "prosody",
            "rhetoric",
            "narratology",
            "fiction",
            "theater",
            "theatre",
            "drama",
            "performing arts",
            "arts",
            "art",
            "philosophy",
            "aesthetics",
            "ethics",
            "mythology",
            "greek mythology",
            "roman mythology",
            "norse mythology",
            "religion",
            "christianity",
            "bible",
            "biblical",
            "figuratively",
            "figurative",
            "publishing",
            "journalism",
            "printing",
            "typography",
            "music",
            "history",
            "psychology",
            "sociology",
        }
    ),
    keywords=frozenset(
        {
            "story",
            "stories",
            "narrative",
            "narrator",
            "narration",
            "novel",
            "novella",
            "poem",
            "poetry",
            "poet",
            "verse",
            "stanza",
            "rhyme",
            "rhythm",
            "metre",
            "meter",
            "prose",
            "fiction",
            "nonfiction",
            "essay",
            "chapter",
            "passage",
            "book",
            "text",
            "work",
            "writing",
            "writer",
            "author",
            "reader",
            "audience",
            "character",
            "protagonist",
            "hero",
            "heroine",
            "villain",
            "plot",
            "theme",
            "motif",
            "symbol",
            "symbolism",
            "imagery",
            "image",
            "metaphor",
            "simile",
            "allegory",
            "irony",
            "satire",
            "parody",
            "tone",
            "voice",
            "style",
            "diction",
            "genre",
            "tragedy",
            "comedy",
            "romance",
            "drama",
            "play",
            "stage",
            "act",
            "scene",
            "dialogue",
            "monologue",
            "soliloquy",
            "criticism",
            "critic",
            "interpretation",
            "meaning",
            "emotion",
            "feeling",
            "beauty",
            "myth",
            "legend",
            "fable",
            "epic",
            "ballad",
            "sonnet",
            "literature",
            "literary",
            "aesthetic",
            "moral",
            "human",
            "life",
            "love",
            "death",
            "memory",
            "time",
            "society",
            "rhetoric",
            "figure",
            # An essay about literature is also a piece of academic writing, so the
            # vocabulary of criticism belongs here for the same reason as above.
            "critique",
            "review",
            "argument",
            "reading",
            "quotation",
            "publication",
            "published",
            "written",
            "speech",
            "language",
            "word",
            "sentence",
            "phrase",
            "device",
            "allusion",
        }
    ),
    exempt_registers=frozenset({"poetic", "literary", "figurative", "figuratively", "formal"}),
)

GENERAL = Domain(
    code="general",
    title="General",
    description="No subject area assumed: senses are ranked by context and dictionary order.",
    labels=frozenset(),
    keywords=frozenset(),
)

DOMAINS: dict[str, Domain] = {d.code: d for d in (GENERAL, COMPUTER_SCIENCE, LITERATURE)}
DEFAULT_DOMAIN = "general"

# How hard each register label argues against a sense being the intended one.
# Calibrated so that one strong label (obsolete, archaic) outweighs a full keyword
# match, while "informal" only breaks ties.
REGISTER_PENALTY: dict[str, float] = {
    "obsolete": 1.0,
    "archaic": 0.9,
    "vulgar": 0.9,
    "offensive": 0.9,
    "rare": 0.7,
    "derogatory": 0.7,
    "pejorative": 0.7,
    "proscribed": 0.6,
    "historical": 0.6,
    "slang": 0.6,
    "dated": 0.5,
    "dialectal": 0.5,
    "dialect": 0.5,
    "nonstandard": 0.5,
    "humorous": 0.4,
    "euphemistic": 0.3,
    "informal": 0.25,
    "colloquial": 0.25,
    "poetic": 0.2,
}

# Labels describing the *syntax* a sense requires. These are the two most frequent labels in
# the whole dictionary (4 072 "transitive", 1 923 "intransitive"), and they are the strongest
# constraint available for verbs: the parse already says whether the token has a direct
# object, so a sense that disagrees can be ruled out on grammatical grounds rather than
# guessed at. They are kept in the label list and consumed by `app.mt.wsd`.
SYNTAX_LABELS: frozenset[str] = frozenset(
    {
        "transitive",
        "intransitive",
        "ambitransitive",
        "reflexive",
        "impersonal",
        "countable",
        "uncountable",
        "in the plural",
        "attributive",
        "predicative",
        "postpositive",
        "idiomatic",
        "idiom",
    }
)

# Labels that hedge or qualify rather than classify. They carry no disambiguation signal and
# are dropped so they cannot dilute a keyword match.
STRUCTURAL_LABELS: frozenset[str] = frozenset(
    {
        "singular",
        "plural",
        "by extension",
        "also",
        "often",
        "usually",
        "sometimes",
        "now",
        "chiefly",
        "especially",
        "specifically",
        "generally",
        "typically",
        "or",
        "and",
        "of a person",
        "of a thing",
        "with",
        "followed by",
        "used",
        "uncommon",
        "obsolete except in",
        "originally",
        "in the singular",
        "countable and uncountable",
    }
)

# Geographic labels: real information, but never a reason to prefer or reject a sense here.
REGIONAL_LABELS: frozenset[str] = frozenset(
    {
        "us",
        "uk",
        "british",
        "american",
        "canada",
        "canadian",
        "australia",
        "australian",
        "new zealand",
        "ireland",
        "irish",
        "scotland",
        "scottish",
        "india",
        "south africa",
        "north america",
        "commonwealth",
        "philippines",
        "singapore",
        "hong kong",
    }
)


# Usage notes: they say *how* a sense is being used, not *what field* it belongs to.
# «figuratively» is the most frequent of them, and treating it as a field was actively
# harmful: every figurative sense of "approach" was penalised in a technical text, leaving
# the aviation sense - «заход на посадку» - to win by default.
USAGE_LABELS: frozenset[str] = frozenset(
    {
        "figuratively",
        "figurative",
        "literally",
        "literal",
        "broadly",
        "narrowly",
        "loosely",
        "strictly",
        "metonymically",
        "synecdoche",
        "hyperbolic",
        "ironic",
        "proverbial",
        "euphemism",
        "metaphorically",
        "poetically",
        "collectively",
        "emphatic",
        "emphatically",
        "rhetorical",
        "rhetorically",
        "figure of speech",
    }
)


def is_field_label(label: str) -> bool:
    """Whether a label names a subject field rather than a register, a usage or a region.

    Defined by exclusion on purpose. Wiktionary's topic vocabulary has hundreds of entries
    and grows; enumerating the fields would leave «aviation», «nautical», «finance» and the
    rest silently unclassified, which is how a technical text ends up translating
    "attention" as «стойка „смирно"». Everything that is not a register, a syntactic note,
    a hedge or a region is treated as a field.
    """
    key = label.lower()
    return not (
        key in REGISTER_PENALTY
        or key in STRUCTURAL_LABELS
        or key in SYNTAX_LABELS
        or key in REGIONAL_LABELS
        or key in USAGE_LABELS
    )


def competing_fields(labels: list[str] | tuple[str, ...], domain: Domain) -> set[str]:
    """Field labels on a sense that point at a subject area other than the active one."""
    if not domain.labels:
        return set()
    return {
        label.lower()
        for label in labels
        if is_field_label(label) and label.lower() not in domain.labels
    }


def get_domain(code: str | None) -> Domain:
    return DOMAINS.get((code or DEFAULT_DOMAIN).lower(), GENERAL)


def register_penalty(labels: list[str] | tuple[str, ...], domain: Domain) -> float:
    """Total register penalty of a sense in `domain`, capped at 1.0."""
    total = 0.0
    for label in labels:
        key = label.lower()
        if key in domain.exempt_registers:
            continue
        total += REGISTER_PENALTY.get(key, 0.0)
    return min(total, 1.0)


def domain_affinity(labels: list[str] | tuple[str, ...], gloss_words: set[str]) -> dict[str, float]:
    """Per-domain affinity of a sense, precomputed at seed time.

    0.7 of the score comes from curated topical labels and 0.3 from the keyword profile,
    because a label is evidence and a keyword is only a hint.
    """
    lowered = {label.lower() for label in labels} - SYNTAX_LABELS
    scores: dict[str, float] = {}
    for domain in DOMAINS.values():
        if not domain.labels and not domain.keywords:
            continue
        label_score = 1.0 if lowered & domain.labels else 0.0
        overlap = len(gloss_words & domain.keywords)
        keyword_score = min(1.0, overlap / 3.0)
        score = 0.7 * label_score + 0.3 * keyword_score
        if score > 0:
            scores[domain.code] = round(score, 3)
    return scores
