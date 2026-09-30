"""Word-sense disambiguation: the signals, and the domain behaviour of feature 2."""

from app.mt.analysis import Analyzer
from app.mt.domains import get_domain
from app.mt.lexicon import token_keys
from app.mt.wsd import ContextWindow, Disambiguator, SyntaxHints
from tests import factories

NETWORK = factories.entry(
    "network",
    "n",
    ("A set of people with sociocultural connections to one another.", ["связи", "сеть"]),
    ("(computing, Internet) A computer network: multiple computers linked together.", ["сеть"]),
)
CHARACTER = factories.entry(
    "character",
    "n",
    ("(countable) A being involved in the action of a story.", ["персонаж", "герой"]),
    ("(countable, computing) One of the basic elements making up a text.", ["символ", "знак"]),
)
COMPUTER = factories.entry(
    "computer",
    "n",
    (
        "(now, rare, chiefly, historical) A person employed to perform computations.",
        ["вычислитель"],
    ),
    ("A programmable electronic device that performs calculations.", ["компьютер"]),
)
INDEX = factories.index(NETWORK, CHARACTER, COMPUTER)


def _choose(analyzer: Analyzer, text: str, lemma: str, domain: str):
    analysis = analyzer.analyse(text)
    sentence = analysis.sentences[0]
    token = next(t for t in sentence.tokens if t.lemma.lower() == lemma)
    entries: list = []
    for key in token_keys(token):
        entries = INDEX.get(key, token.upos)
        if entries:
            break
    disambiguator = Disambiguator(get_domain(domain), analyzer)
    return disambiguator.choose(
        token, entries, ContextWindow.for_token(sentence, token), SyntaxHints.of(sentence, token)
    )


def test_topical_label_selects_the_computing_sense(analyzer: Analyzer) -> None:
    decision = _choose(analyzer, "The neural network model learns from data.", "network", "cs")
    assert decision.chosen is not None
    assert decision.chosen.surface == "сеть"
    assert any(signal.name == "topical label" for signal in decision.chosen.signals)


def test_general_domain_keeps_the_dictionary_order(analyzer: Analyzer) -> None:
    """With no subject area chosen, the lexicographer's first sense wins."""
    decision = _choose(analyzer, "She joined a network of friends.", "network", "general")
    assert decision.chosen is not None
    assert decision.chosen.surface == "связи"


def test_literature_and_computer_science_disagree_about_character(analyzer: Analyzer) -> None:
    literary = _choose(
        analyzer, "The main character of the novel is an unreliable narrator.", "character", "lit"
    )
    technical = _choose(
        analyzer, "The string contains a null character in the buffer.", "character", "cs"
    )
    assert literary.chosen is not None and technical.chosen is not None
    assert literary.chosen.surface == "персонаж"
    assert technical.chosen.surface == "символ"


def test_register_penalty_suppresses_the_historical_sense(analyzer: Analyzer) -> None:
    """«вычислитель» - a human calculator - must never win in a modern text."""
    decision = _choose(analyzer, "The computer performs the calculation.", "computer", "cs")
    assert decision.chosen is not None
    assert decision.chosen.surface == "компьютер"
    loser = decision.alternatives[0]
    assert any(signal.name == "register" for signal in loser.signals)


def test_competing_domain_label_counts_against_a_sense(analyzer: Analyzer) -> None:
    decision = _choose(
        analyzer, "The main character of the novel is an unreliable narrator.", "character", "lit"
    )
    computing_sense = next(
        candidate
        for candidate in [decision.chosen, *decision.alternatives]
        if candidate and "computing" in candidate.sense.labels
    )
    assert any(signal.name == "competing domain" for signal in computing_sense.signals)


def test_override_beats_every_signal(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The neural network model learns from data.")
    sentence = analysis.sentences[0]
    token = next(t for t in sentence.tokens if t.lemma == "network")
    social_sense = NETWORK.senses[0]

    disambiguator = Disambiguator(
        get_domain("cs"),
        analyzer,
        overrides={("network", "n"): (social_sense.id, None)},
    )
    decision = disambiguator.choose(
        token, INDEX.get("network", "NOUN"), ContextWindow.for_token(sentence, token)
    )
    assert decision.chosen is not None
    assert decision.chosen.locked
    assert decision.chosen.surface == "связи"
    assert not decision.ambiguous, "a locked sense is never reported as ambiguous"


def test_transitivity_rules_out_an_intransitive_sense(analyzer: Analyzer) -> None:
    index = factories.index(
        factories.entry(
            "run",
            "v",
            ("(intransitive) To move quickly on foot.", ["бежать"]),
            ("(transitive) To operate or manage something.", ["управлять"]),
        )
    )
    analysis = analyzer.analyse("They run the system every day.")
    sentence = analysis.sentences[0]
    token = next(t for t in sentence.tokens if t.lemma == "run")
    hints = SyntaxHints.of(sentence, token)
    assert hints.has_object

    decision = Disambiguator(get_domain("cs"), analyzer).choose(
        token, index.get("run", "VERB"), ContextWindow.for_token(sentence, token), hints
    )
    assert decision.chosen is not None
    assert decision.chosen.surface == "управлять"


def test_signals_are_explainable(analyzer: Analyzer) -> None:
    decision = _choose(analyzer, "The neural network model learns.", "network", "cs")
    assert decision.chosen is not None
    for signal in decision.chosen.signals:
        assert signal.name and signal.detail
        assert isinstance(signal.contribution, float)
    assert decision.chosen.score == sum(s.contribution for s in decision.chosen.signals)
