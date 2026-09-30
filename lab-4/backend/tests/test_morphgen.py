"""Russian morphological generation and agreement."""

import pytest

from app.mt.morphgen import MorphGenerator, Target


@pytest.mark.parametrize(
    ("lemma", "target", "expected"),
    [
        ("сеть", Target(case="gen"), "сети"),
        ("сеть", Target(case="gen", number="plur"), "сетей"),
        ("сеть", Target(case="ins"), "сетью"),
        ("модель", Target(case="acc", number="plur"), "модели"),
        ("слово", Target(case="gen", number="plur"), "слов"),
        ("корпус", Target(case="gen", number="plur"), "корпусов"),
    ],
)
def test_noun_declension(morph: MorphGenerator, lemma, target, expected) -> None:
    assert morph.inflect(lemma, target, want_pos="NOUN").surface == expected


@pytest.mark.parametrize(
    ("lemma", "target", "expected"),
    [
        ("нейронный", Target(case="nom", gender="femn", number="sing"), "нейронная"),
        ("нейронный", Target(case="gen", gender="femn", number="sing"), "нейронной"),
        ("нейронный", Target(case="gen", number="plur"), "нейронных"),
        ("большой", Target(case="prep", number="plur"), "больших"),
    ],
)
def test_adjective_agreement(morph: MorphGenerator, lemma, target, expected) -> None:
    assert morph.inflect(lemma, target, want_pos="ADJF").surface == expected


@pytest.mark.parametrize(
    ("lemma", "target", "expected"),
    [
        ("изучать", Target(tense="pres", person="3per", number="sing"), "изучает"),
        ("изучать", Target(tense="pres", person="3per", number="plur"), "изучают"),
        ("изучать", Target(tense="past", gender="femn", number="sing"), "изучала"),
        ("изучать", Target(tense="past", number="plur"), "изучали"),
        ("изучать", Target(infinitive=True), "изучать"),
    ],
)
def test_verb_conjugation(morph: MorphGenerator, lemma, target, expected) -> None:
    assert morph.inflect(lemma, target, want_pos="VERB").surface == expected


def test_short_adjective_form(morph: MorphGenerator) -> None:
    form = morph.inflect("простой", Target(gender="masc", number="sing", short=True), "ADJF")
    assert form.surface == "прост"


def test_short_form_falls_back_to_the_full_one(morph: MorphGenerator) -> None:
    """«нейронный» has no short form; the generator must not return an empty string."""
    form = morph.inflect("нейронный", Target(gender="masc", number="sing", short=True), "ADJF")
    assert form.surface


def test_latin_script_is_returned_unchanged(morph: MorphGenerator) -> None:
    """A word the Russian analyser cannot read must pass through, never raise."""
    form = morph.inflect("representations", Target(case="gen"))
    assert form.surface == "representations"
    assert not form.inflected
    assert form.note


def test_unknown_russian_word_is_inflected_by_analogy(morph: MorphGenerator) -> None:
    """pymorphy3 predicts unseen words from their endings, and the generator uses that.

    This is what lets an accepted dictionary suggestion - «токенизатор», which is not in
    the Russian morphological dictionary - still decline correctly in the output.
    """
    assert morph.inflect("флубберизация", Target(case="gen")).surface == "флубберизации"
    assert morph.inflect("токенизатор", Target(case="ins")).surface == "токенизатором"


def test_gender_is_dropped_in_the_plural(morph: MorphGenerator) -> None:
    """Russian has no gender in the plural; asking for both must not fail."""
    form = morph.inflect("сеть", Target(case="nom", number="plur", gender="femn"), "NOUN")
    assert form.surface == "сети"
    assert form.inflected


def test_multiword_equivalent_inflects_its_head(morph: MorphGenerator) -> None:
    form = morph.inflect("действующее лицо", Target(case="gen"), want_pos="NOUN")
    assert form.surface == "действующего лица"


def test_gender_and_number_are_readable(morph: MorphGenerator) -> None:
    form = morph.inflect("сеть", Target(case="nom"), want_pos="NOUN")
    assert form.gender == "femn"
    assert form.number == "sing"
    assert "feminine" in form.decoded


def test_aspect_detection(morph: MorphGenerator) -> None:
    assert morph.aspect_of("изучать") == "impf"
    assert morph.aspect_of("изучить") == "perf"


def test_is_known(morph: MorphGenerator) -> None:
    assert morph.is_known("алгоритмический")
    assert not morph.is_known("флубберизация")
