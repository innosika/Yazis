"""Command matching across the four languages, plus the negatives that must not fire."""

from typing import Any

import pytest

from app.commands.catalog import CATALOG
from app.commands.matcher import CommandSpec, Matcher, Section, prepare
from app.commands.normalize import normalize
from app.commands.numbers import words_to_digits

SECTIONS = [
    Section("Abstract", 0, None),
    Section("1 Introduction", 2, "1"),
    Section("2 Background", 5, "2"),
    Section("3 Model Architecture", 8, "3"),
    Section("3.2 Attention", 12, "3.2"),
    Section("4 Why Self-Attention", 20, "4"),
    Section("7 Conclusion", 40, "7"),
]


def matcher(lang: str) -> Matcher:
    return Matcher(
        [CommandSpec(c.id, c.title, c.phrases[lang], c.slots, c.needs_llm) for c in CATALOG], lang
    )


def best(lang: str, utterance: str, strict: bool = False) -> tuple[str | None, dict[str, Any]]:
    m = matcher(lang)
    n = prepare(utterance, lang)
    found = m.templates(n, SECTIONS)
    if not found:
        found = [x for x in m.fuzzy(n, strict) if x.method == "fuzzy"]
    return (found[0].command_id, found[0].slots) if found else (None, {})


EN = [
    ("Pause.", "pause", {}),
    ("Could you pause, please?", "pause", {}),
    ("Hold on", "pause", {}),
    ("continue", "resume", {}),
    ("keep reading", "resume", {}),
    ("Stop.", "stop", {}),
    ("stop reading", "stop", {}),
    ("Next.", "next_sentence", {}),
    ("skip this", "next_sentence", {}),
    ("go back", "previous_sentence", {}),
    ("next paragraph", "next_paragraph", {}),
    ("next section", "next_section", {}),
    ("say that again", "repeat", {}),
    ("start over", "start_over", {}),
    ("go to section three", "go_to_section", {"number": 3.0}),
    ("Go to the third section", "go_to_section", {"number": 3.0}),
    ("section 3.2", "go_to_section", {"number": 3.2}),
    ("read the conclusion", "go_to_section", {"section_title": "7 Conclusion"}),
    ("jump to attention", "go_to_section", {"section_title": "3.2 Attention"}),
    ("go to the introduction", "go_to_section", {"section_title": "1 Introduction"}),
    ("read the abstract", "read_abstract", {}),
    ("what is this paper about", "read_abstract", {}),
    ("faster", "faster", {}),
    ("faster please", "faster", {}),
    ("slow down a bit", "slower", {}),
    ("not so fast", "slower", {}),
    ("set speed to one point five", "set_speed", {"number": 1.5}),
    ("speed 1.2", "set_speed", {"number": 1.2}),
    ("normal speed", "normal_speed", {}),
    ("louder", "louder", {}),
    ("turn it down", "quieter", {}),
    ("mute", "mute", {}),
    ("next voice", "next_voice", {}),
    ("switch to Emma", "switch_voice", {"voice": "bf_emma"}),
    ("let George read", "switch_voice", {"voice": "bm_george"}),
    ("male voice", "male_voice", {}),
    ("british accent", "british_accent", {}),
    ("where am I?", "where_am_i", {}),
    ("how much is left", "time_left", {}),
    ("what is multi-head attention?", "explain", {"term": "multi-head attention"}),
    ("explain the softmax function", "explain", {"term": "softmax function"}),
    ("summarize this section", "summarize", {}),
    ("read the clipboard", "read_clipboard", {}),
    ("open library", "open_library", {}),
    ("dark mode", "dark_mode", {}),
    ("What can I say?", "show_commands", {}),
    ("stop listening", "stop_listening", {}),
    ("Hey Lector, read the abstract.", "read_abstract", {}),
    ("okay lector pause", "pause", {}),
]


@pytest.mark.parametrize(("utterance", "command", "slots"), EN)
def test_english(utterance: str, command: str, slots: dict[str, Any]) -> None:
    got, got_slots = best("en", utterance)
    assert got == command, (utterance, got, got_slots)
    for k, v in slots.items():
        assert got_slots.get(k) == v


RU = [
    ("пауза", "pause"),
    ("подожди пожалуйста", "pause"),
    ("продолжай", "resume"),
    ("дальше", "next_sentence"),
    ("назад", "previous_sentence"),
    ("быстрее", "faster"),
    ("помедленнее", "slower"),
    ("громче", "louder"),
    ("повтори", "repeat"),
    ("перейди к разделу три", "go_to_section"),
    ("читай аннотацию", "read_abstract"),
    ("что такое трансформер", "explain"),
    ("тёмная тема", "dark_mode"),
    ("стоп", "stop"),
    ("скорость полтора", "set_speed"),
]
DE = [
    ("Pause", "pause"),
    ("weiter", "resume"),
    ("schneller", "faster"),
    ("langsamer", "slower"),
    ("nächster Satz", "next_sentence"),
    ("Abschnitt drei", "go_to_section"),
    ("lies die Zusammenfassung", "read_abstract"),
    ("lauter bitte", "louder"),
    ("was ist Aufmerksamkeit", "explain"),
    ("stopp", "stop"),
]
FR = [
    ("pause", "pause"),
    ("reprends", "resume"),
    ("plus vite", "faster"),
    ("moins vite", "slower"),
    ("suivant", "next_sentence"),
    ("section trois", "go_to_section"),
    ("lis le résumé", "read_abstract"),
    ("plus fort", "louder"),
    ("qu'est-ce que l'attention", "explain"),
    ("arrête", "stop"),
]


@pytest.mark.parametrize(("utterance", "command"), RU)
def test_russian(utterance: str, command: str) -> None:
    assert best("ru", utterance)[0] == command


@pytest.mark.parametrize(("utterance", "command"), DE)
def test_german(utterance: str, command: str) -> None:
    assert best("de", utterance)[0] == command


@pytest.mark.parametrize(("utterance", "command"), FR)
def test_french(utterance: str, command: str) -> None:
    assert best("fr", utterance)[0] == command


# Sentences from papers (what the microphone hears as echo) must not trigger commands.
NOT_COMMANDS = [
    "The dominant sequence transduction models are based on complex recurrent networks",
    "We propose a new simple network architecture based solely on attention mechanisms",
    "Experiments on two machine translation tasks show these models to be superior",
    "In this work we present the Transformer",
    "The encoder maps an input sequence of symbol representations",
    "Most competitive neural sequence transduction models have an encoder decoder structure",
    "We trained the base models for a total of 100000 steps",
    "Residual dropout is applied to the output of each sub layer",
    "The learning rate was varied over the course of training",
    "We achieve a new state of the art on the English to German task",
    "I think we should go to lunch",
    "go to lunch",
    "the weather is nice today",
    "this is a test of the microphone",
    "hello there",
    "thanks everyone for coming",
    "what a beautiful day",
    "the results are shown in table two",
    "our model outperforms previous approaches by a large margin",
    "the attention function can be described as mapping a query",
]


@pytest.mark.parametrize("utterance", NOT_COMMANDS)
def test_prose_is_not_a_command(utterance: str) -> None:
    assert best("en", utterance, strict=True)[0] is None


def test_numbers() -> None:
    assert words_to_digits("go to section twenty one", "en") == "go to section 21"
    assert words_to_digits("speed one point five", "en") == "speed 1.5"
    assert words_to_digits("one and a half", "en") == "1.5"
    assert words_to_digits("скорость полтора", "ru") == "скорость 1.5"
    assert words_to_digits("раздел двадцать три", "ru") == "раздел 23"
    assert words_to_digits("abschnitt einundzwanzig", "de") == "abschnitt 21"
    assert words_to_digits("section vingt et un", "fr") == "section 21"


def test_normalize_fillers_and_ordinals() -> None:
    assert (
        normalize("Hey Lector, could you please go to the second section?", "en")
        == "go to section 2"
    )
    assert normalize("Перейди ко второму разделу, пожалуйста", "ru") == "перейди ко раздел 2"


def test_commands_api(client: Any) -> None:
    body = client.get("/api/commands").json()
    ids = {c["id"] for c in body["commands"]}
    assert {"pause", "go_to_section", "explain"} <= ids
    assert body["languages"] == ["en", "ru", "de", "fr"]
    r = client.post("/api/commands/test", json={"text": "slow down a bit"})
    assert r.json()["match"]["command"] == "slower"
    # disable, then it no longer matches
    assert client.put("/api/commands/slower", json={"enabled": False}).json()["enabled"] is False
    assert client.post("/api/commands/test", json={"text": "slower"}).json()["match"] is None
    client.delete("/api/commands/slower/override")
    # replace phrases
    client.put("/api/commands/pause", json={"phrases": {"en": ["freeze"]}})
    assert (
        client.post("/api/commands/test", json={"text": "freeze"}).json()["match"]["command"]
        == "pause"
    )
    client.delete("/api/commands/pause/override")
    # custom macro
    r = client.post(
        "/api/commands/custom",
        json={
            "name": "Study mode",
            "phrases": {"en": ["study mode"]},
            "steps": [
                {"action": "set_speed", "value": 0.9},
                {"action": "switch_voice", "value": "bf_emma"},
            ],
            "reply": "Study mode on",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    m = client.post("/api/commands/test", json={"text": "study mode please"}).json()["match"]
    assert (
        m["command"] == cid
        and m["steps"][0]["action"] == "set_speed"
        and m["reply"] == "Study mode on"
    )
    bad = client.post(
        "/api/commands/custom",
        json={"name": "x", "phrases": {"en": ["x"]}, "steps": [{"action": "format_disk"}]},
    )
    assert bad.status_code == 422
    assert client.delete(f"/api/commands/custom/{cid.split(':')[1]}").status_code == 204


def test_recognize_api(client: Any) -> None:
    import io

    import numpy as np
    import soundfile as sf

    from app.main import _FakeASR

    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000, dtype=np.float32), 16000, format="WAV")
    wav = buf.getvalue()

    _FakeASR.next_text = "Go to the third section, please."
    r = client.post(
        "/api/voice/recognize",
        files={"audio": ("u.wav", wav, "audio/wav")},
        data={"language": "en"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["outcome"]["match"]["command"] == "go_to_section"
    assert out["outcome"]["match"]["slots"]["number"] == 3

    _FakeASR.next_text = "Thank you."
    assert (
        client.post("/api/voice/recognize", files={"audio": ("u.wav", wav, "audio/wav")}).json()[
            "rejected"
        ]
        == "stock phrase"
    )

    # echo: the transcript is what the TTS was saying, plus the user's "pause"
    _FakeASR.next_text = "the encoder maps an input sequence pause"
    out = client.post(
        "/api/voice/recognize",
        files={"audio": ("u.wav", wav, "audio/wav")},
        data={
            "playing": "true",
            "played_text": "Here, the encoder maps an input sequence of symbols",
        },
    ).json()
    assert out["echo_ratio"] > 0.5
    assert out["outcome"]["match"]["command"] == "pause"

    _FakeASR.next_text = "the encoder maps an input sequence"
    out = client.post(
        "/api/voice/recognize",
        files={"audio": ("u.wav", wav, "audio/wav")},
        data={
            "playing": "true",
            "played_text": "Here, the encoder maps an input sequence of symbols",
        },
    ).json()
    assert out["rejected"] == "echo"


def test_short_command_inside_prompt_is_not_prompt_echo() -> None:
    from app.asr.base import Transcript
    from app.asr.filters import is_hallucination
    from app.commands.service import PROMPTS

    prompt = PROMPTS["en"]
    assert is_hallucination(Transcript("Read the abstract.", "x"), prompt) is None
    assert is_hallucination(Transcript("Go to section 3.", "x"), prompt) is None
    echoed = "Voice commands for a research paper reader: pause, resume, next sentence"
    assert is_hallucination(Transcript(echoed, "x"), prompt) == "prompt echo"


def test_fragments_do_not_fuzzy_match_longer_phrases() -> None:
    # regression: "a" was a token subset of "back a paragraph"
    for fragment in ["a", "the", "a section", "to"]:
        assert best("en", fragment, strict=True)[0] is None, fragment
    assert best("en", "slow down a bit", strict=True)[0] == "slower"
