from app.text.segment import split_sentences, split_units


def sentences(text: str) -> list[str]:
    return [text[a:b] for a, b in split_sentences(text)]


def test_basic_split() -> None:
    assert sentences("We propose a model. It works well! Does it scale?") == [
        "We propose a model.",
        "It works well!",
        "Does it scale?",
    ]


def test_scientific_abbreviations_do_not_split() -> None:
    text = "As shown in Fig. 3 and Eq. 2, the loss drops. See Sec. 4 for details."
    assert sentences(text) == [
        "As shown in Fig. 3 and Eq. 2, the loss drops.",
        "See Sec. 4 for details.",
    ]


def test_et_al_and_eg() -> None:
    text = "Vaswani et al. proposed the Transformer. Many tasks, e.g. translation, benefit."
    assert sentences(text) == [
        "Vaswani et al. proposed the Transformer.",
        "Many tasks, e.g. translation, benefit.",
    ]


def test_initials_and_decimals() -> None:
    text = "A. Turing introduced the test in 1950. Accuracy reached 97.5 percent."
    assert sentences(text) == [
        "A. Turing introduced the test in 1950.",
        "Accuracy reached 97.5 percent.",
    ]


def test_closing_quote_and_bracket_stay_with_sentence() -> None:
    text = 'He called it "attention." Then (in 2017) it spread.'
    assert sentences(text) == ['He called it "attention."', "Then (in 2017) it spread."]


def test_math_is_never_split() -> None:
    text = r"Let $x. Y$ be given. Next sentence."
    assert sentences(text) == [r"Let $x. Y$ be given.", "Next sentence."]


def test_lowercase_continuation_does_not_split() -> None:
    assert sentences("It runs in approx. linear time. Done.") == [
        "It runs in approx. linear time.",
        "Done.",
    ]


def test_spans_exclude_surrounding_whitespace() -> None:
    text = "  First one.   Second one.  "
    for a, b in split_sentences(text):
        assert not text[a].isspace() and not text[b - 1].isspace()


def test_units_cut_long_sentences_at_semicolons_first() -> None:
    first = " ".join(["word"] * 30)
    second = " ".join(["more"] * 30)
    text = f"{first}, still going; {second}."
    units = [text[a:b] for a, b in split_units(text, (0, len(text)), max_words=40)]
    assert len(units) == 2
    assert units[0].endswith("going;")
    assert all(len(u.split()) <= 40 for u in units)


def test_short_sentence_is_one_unit() -> None:
    text = "Short sentence, with a comma."
    assert split_units(text, (0, len(text))) == [(0, len(text))]
