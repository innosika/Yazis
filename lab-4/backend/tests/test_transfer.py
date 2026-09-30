"""The transfer rules: drops, cases, agreement, reordering."""

import pytest

from app.mt.domains import get_domain
from app.mt.pipeline import Pipeline
from tests import factories

DICTIONARY = factories.index(
    factories.entry("the", "adv", ("With a comparative.", ["чем"])),
    factories.entry("a", "determiner", ("One.", ["один"])),
    factories.entry("an", "determiner", ("One.", ["один"])),
    factories.entry("model", "n", ("A representation.", ["модель"])),
    factories.entry("network", "n", ("(computing) A computer network.", ["сеть"])),
    factories.entry("neural", "adj", ("Of the nerves.", ["нейронный"])),
    factories.entry("author", "n", ("A creator of a work.", ["автор"])),
    factories.entry("narrative", "n", ("A recitation of events.", ["повествование"])),
    factories.entry("simple", "adj", ("Not complex.", ["простой"])),
    factories.entry("remain", "v", ("To stay.", ["оставаться", "остаться"])),
    factories.entry("study", "v", ("(transitive) To examine.", ["изучать", "изучить"])),
    factories.entry("word", "n", ("A unit of language.", ["слово"])),
    factories.entry("system", "n", ("An organised whole.", ["система"])),
    factories.entry("data", "n", ("(computing) Information.", ["данные"])),
    factories.entry("result", "n", ("An outcome.", ["результат"])),
    factories.entry(
        "translate",
        "v",
        ("(transitive) To render in another language.", ["переводить", "перевести"]),
    ),
    factories.entry("machine learning", "n", ("(computing) …", ["машинное обучение"])),
    factories.entry("researcher", "n", ("One who researches.", ["исследователь"])),
    factories.entry("evaluate", "v", ("(transitive) To judge.", ["оценивать", "оценить"])),
    factories.entry("quality", "n", ("A degree of excellence.", ["качество"])),
    factories.entry("compute", "v", ("(transitive) To calculate.", ["вычислять", "вычислить"])),
    factories.entry(
        "learn", "v", ("(transitive) To acquire knowledge of.", ["изучать", "изучить"])
    ),
    factories.entry("publish", "v", ("(transitive) To issue.", ["публиковать", "опубликовать"])),
    factories.entry(
        "distribute", "v", ("(transitive) To spread out.", ["распределять", "распределить"])
    ),
    factories.entry("hide", "v", ("(transitive) To conceal.", ["скрывать", "скрыть"])),
    factories.entry("representation", "n", ("A depiction.", ["представление"])),
    factories.entry("state", "n", ("A condition.", ["состояние"])),
    factories.entry("with", "preposition", ("Accompanied by.", ["с"])),
    factories.entry("of", "preposition", ("Belonging to.", ["из"])),
    factories.entry("in", "preposition", ("Inside.", ["в"])),
)


def translate(pipeline: Pipeline, text: str, domain: str = "cs", mode: str = "transfer") -> str:
    result = pipeline.run(text, DICTIONARY, get_domain(domain), mode=mode)
    return result.target


def test_articles_are_dropped(pipeline: Pipeline) -> None:
    assert "чем" not in translate(pipeline, "The model is simple.")
    assert "один" not in translate(pipeline, "A model is simple.")


def test_of_phrase_becomes_a_genitive(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The quality of the model.")
    assert "модели" in out
    assert "из" not in out


def test_possessive_becomes_a_postposed_genitive(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The author's narrative remains simple.")
    assert out.startswith("Повествование автора")


def test_noun_compound_becomes_a_postposed_genitive(pipeline: Pipeline) -> None:
    """English "network model"; Russian «модель сети» - the modifier moves and declines."""
    out = translate(pipeline, "The network model is simple.")
    assert "модель сети" in out.lower()


def test_adjective_modifier_stays_in_front_and_agrees(pipeline: Pipeline) -> None:
    """The mirror case: an adjectival equivalent must *not* be postposed.

    With no "neural network" entry in the dictionary, "neural" is translated on its own as
    the adjective «нейронный» and agrees with its head, while "network" - a noun - still
    moves behind it.
    """
    out = translate(pipeline, "The neural network model is simple.").lower()
    assert out.startswith("нейронная модель")
    assert "сети" in out


def test_multiword_nominal_modifier_is_postposed_as_a_whole(pipeline: Pipeline) -> None:
    """When the dictionary has the phrase, the phrase moves and declines together."""
    index = factories.index(
        factories.entry("neural network", "n", ("(computing) …", ["нейронная сеть"])),
        factories.entry("model", "n", ("A representation.", ["модель"])),
        factories.entry("simple", "adj", ("Not complex.", ["простой"])),
    )
    result = pipeline.run("The neural network model is simple.", index, get_domain("cs"))
    assert "модель нейронной сети" in result.target.lower()


def test_present_copula_is_absent(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The model is simple.")
    assert "есть" not in out
    assert "быть" not in out


def test_predicate_adjective_takes_the_short_form(pipeline: Pipeline) -> None:
    assert "проста" in translate(pipeline, "The model is simple.")


def test_do_support_carries_its_tense_to_the_main_verb(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The system did not translate the words.")
    assert "не перевела" in out or "не переводила" in out
    assert "сделал" not in out


def test_negation_is_rendered(pipeline: Pipeline) -> None:
    assert "не" in translate(pipeline, "The system did not translate the words.")


def test_direct_object_is_accusative(pipeline: Pipeline) -> None:
    out = translate(pipeline, "Researchers evaluate the quality.")
    assert "качество" in out


def test_plural_subject_takes_a_plural_verb(pipeline: Pipeline) -> None:
    out = translate(pipeline, "Researchers evaluate the quality.")
    assert "оценивают" in out


def test_preposition_governs_its_case(pipeline: Pipeline) -> None:
    out = translate(pipeline, "Researchers evaluate quality with data.")
    assert "с данными" in out


def test_past_tense_agrees_with_the_subject_gender(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The system studied the words.")
    # «система» is feminine, so the Russian past tense must be feminine too.
    assert "изучала" in out or "изучила" in out


def test_aspect_follows_the_tense(pipeline: Pipeline) -> None:
    """A perfective verb has no present tense, so the present must pick the imperfective."""
    assert "остаётся" in translate(pipeline, "The narrative remains simple.")


def test_multiword_unit_is_translated_as_a_unit(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The machine learning system is simple.")
    assert "машинного обучения" in out


def test_unknown_word_stays_visible(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The tokenizer studies data.")
    assert "tokenizer" in out


def test_unknown_name_is_transcribed(pipeline: Pipeline) -> None:
    """A name absent from the dictionary is transcribed, not left in Latin script."""
    assert "Васвани" in translate(pipeline, "The model of Vaswani is simple.")


def test_name_is_recognised_even_when_the_tagger_misses_it(pipeline: Pipeline) -> None:
    """Sentence-initial names are tagged as common nouns; the entity recogniser catches them.

    spaCy tags "Vaswani" in "Vaswani studied…" as NN, because every word at the start of a
    sentence is capitalised. Its named-entity recogniser still labels it PERSON, which is
    what the transfer stage uses to decide to transcribe.
    """
    assert "Васвани" in translate(pipeline, "Vaswani studied the words.")


def test_capitalised_common_word_is_not_transcribed(pipeline: Pipeline) -> None:
    """The mirror case: the first word of a sentence must not become a fake name."""
    out = translate(pipeline, "Tokenizers are simple.")
    assert "Tokenizers" in out


def test_output_is_capitalised_and_punctuated(pipeline: Pipeline) -> None:
    out = translate(pipeline, "the model is simple.")
    assert out[0].isupper()
    assert out.endswith(".")
    assert " ." not in out


@pytest.mark.parametrize(
    "text",
    [
        "The model is simple.",
        "Researchers evaluate the quality of the machine learning system with data.",
        "The author's narrative remains simple, and the system did not translate it.",
        "",
        "   ",
        "!!!",
        "42",
    ],
)
def test_pipeline_never_raises(pipeline: Pipeline, text: str) -> None:
    result = pipeline.run(text, DICTIONARY, get_domain("cs"))
    assert isinstance(result.target, str)


def test_direct_architecture_keeps_articles_and_skips_agreement(pipeline: Pipeline) -> None:
    """The baseline must visibly differ from the transfer output."""
    text = "The author's narrative remains simple."
    direct = translate(pipeline, text, mode="direct")
    transfer = translate(pipeline, text, mode="transfer")
    assert direct != transfer
    assert "чем" in direct.lower(), "a direct system substitutes the article instead of dropping it"
    assert "оставаться" in direct, "a direct system does not conjugate"


# ------------------------------------------------------------------- participles, passives


def test_past_participle_modifies_its_noun(pipeline: Pipeline) -> None:
    """English attaches participles to nouns; a translator must not conjugate them."""
    out = translate(pipeline, "The model learns distributed representations.").lower()
    assert "распределённые представления" in out
    assert "распределил" not in out


def test_participle_agrees_with_its_noun(pipeline: Pipeline) -> None:
    """«представление» is inanimate, so the accusative plural copies the nominative.

    Without the animacy feature pymorphy3 returns «распределённых» - the animate form,
    which is also the genitive, and which would read as "of the distributed".
    """
    out = translate(pipeline, "The model learns distributed representations.").lower()
    assert "распределённые" in out
    assert "распределённых" not in out


def test_modifier_of_an_animate_noun_takes_the_animate_accusative(
    pipeline: Pipeline,
) -> None:
    index = factories.index(
        factories.entry("study", "v", ("(transitive) To examine.", ["изучать"])),
        factories.entry("great", "adj", ("Large.", ["великий"])),
        factories.entry("writer", "n", ("An author.", ["писатель"])),
    )
    result = pipeline.run("Researchers study great writers.", index, get_domain("lit"))
    assert "великих писателей" in result.target.lower()


def test_passive_becomes_a_short_participle(pipeline: Pipeline) -> None:
    """«качество» is neuter, so the participle is «вычислено»."""
    out = translate(pipeline, "The quality is computed by the system.")
    assert "вычислено" in out
    # Russian has no present-tense copula, so the auxiliary must be gone.
    assert "есть" not in out
    assert "быть" not in out


def test_passive_agent_becomes_instrumental(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The quality is computed by the system.")
    assert "системой" in out


def test_past_passive_inserts_a_form_of_be(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The quality was computed by the system.")
    assert "было вычислено" in out


def test_passive_agrees_with_a_feminine_subject(pipeline: Pipeline) -> None:
    """The gender comes from the *Russian* subject, which English never marks."""
    out = translate(pipeline, "The model was computed.")
    assert "была вычислена" in out


def test_future_passive_inserts_the_future_of_be(pipeline: Pipeline) -> None:
    out = translate(pipeline, "The results will be published.")
    assert "будут опубликованы" in out


def test_passive_prefers_the_perfective_equivalent(pipeline: Pipeline) -> None:
    """«вычисляемо» exists but nobody writes it; the perfective participle is the form."""
    out = translate(pipeline, "The quality was computed.")
    assert "вычислено" in out
    assert "вычисляемо" not in out


def test_passive_verb_counts_as_transitive_for_disambiguation(pipeline: Pipeline) -> None:
    """The object of a passive has been promoted to subject, so the verb is still transitive."""
    index = factories.index(
        factories.entry("quality", "n", ("A degree of excellence.", ["качество"])),
        factories.entry(
            "run",
            "v",
            ("(intransitive) To move quickly on foot.", ["бежать"]),
            ("(transitive) To operate.", ["управлять", "управить"]),
        ),
    )
    result = pipeline.run("The quality is run.", index, get_domain("cs"))
    assert "бежать" not in result.target
    assert "бежа" not in result.target


def test_stage_trace_is_recorded(pipeline: Pipeline) -> None:
    result = pipeline.run("The neural network model studies data.", DICTIONARY, get_domain("cs"))
    stages = result.sentences[0].stages
    assert set(stages) == {
        "analysis",
        "lexical transfer",
        "morphological generation",
        "syntactic transfer",
    }
    assert stages["lexical transfer"] != stages["syntactic transfer"]
