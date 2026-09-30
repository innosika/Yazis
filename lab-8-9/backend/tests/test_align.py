from app.tts.align import Chunk, Token, align


def test_exact_token_stream() -> None:
    spoken = "Hello world. Again"
    chunk = Chunk(
        spoken,
        [
            Token("Hello", " ", 0.0, 0.5),
            Token("world", "", 0.5, 1.0),
            Token(".", " ", None, None),
            Token("Again", "", 1.1, 1.5),
        ],
        1.6,
    )
    spans = align(spoken, [chunk])
    assert [(spoken[s.spoken_start : s.spoken_end], s.start) for s in spans] == [
        ("Hello", 0.0),
        ("world", 0.5),
        ("Again", 1.1),
    ]


def test_chunks_accumulate_time_offsets() -> None:
    spoken = "One two. Three four."
    c1 = Chunk(
        "One two.",
        [Token("One", " ", 0.0, 0.3), Token("two", "", 0.3, 0.6), Token(".", "", None, None)],
        0.8,
    )
    c2 = Chunk(
        "Three four.",
        [Token("Three", " ", 0.0, 0.4), Token("four", "", 0.4, 0.7), Token(".", "", None, None)],
        0.9,
    )
    spans = align(spoken, [c1, c2])
    assert [round(s.start, 2) for s in spans] == [0.0, 0.3, 0.8, 1.2]
    assert spoken[spans[2].spoken_start : spans[2].spoken_end] == "Three"


def test_divergent_tokens_still_located() -> None:
    spoken = "It costs 5 dollars now"
    # misaki may render a token differently from the input text
    chunk = Chunk(
        spoken,
        [
            Token("It", " ", 0.0, 0.1),
            Token("costs", " ", 0.1, 0.4),
            Token("five", " ", 0.4, 0.6),
            Token("dollars", " ", 0.6, 0.9),
            Token("now", "", 0.9, 1.1),
        ],
        1.2,
    )
    spans = align(spoken, [chunk])
    words = [spoken[s.spoken_start : s.spoken_end] for s in spans]
    assert "dollars" in words and "now" in words
