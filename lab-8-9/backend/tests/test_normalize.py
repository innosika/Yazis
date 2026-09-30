"""Golden cases: how Lector reads typical computer-science prose."""

import pytest

from app.text.normalize import Context, normalize

GOLDEN = [
    # Big-O and complexity
    ("Sorting takes O(n log n) time [12].", "Sorting takes big O of n log n time."),
    ("Dijkstra runs in O((V + E) log V) time.", "Dijkstra runs in big O of V plus E log V time."),
    ("It runs in O(|V|^2) steps.", "It runs in big O of the size of V squared steps."),
    (
        r"It is $O(n^2)$ vs. $\Theta(n \log n)$.",
        "It is big O of n squared versus big theta of n log n.",
    ),
    # citations
    ("Transformers (Vaswani et al., 2017) use attention.", "Transformers use attention."),
    ("Prior work (e.g., Chen and Liu, 2019; Wang, 2021a) exists.", "Prior work exists."),
    ("Attention [VSP+17] and CNNs [3, 5-7] help.", "Attention and C N N's help."),
    ("Convolutions [Smith et al., 2020] help.", "Convolutions help."),
    # references and abbreviations
    (
        "See Fig. 3b and Eq. (2), e.g., the loss.",
        "See Figure 3 b and Equation 2, for example, the loss.",
    ),
    (
        "Results are in Table 2 (see Section 4.1).",
        "Results are in Table 2 (see Section 4 point 1).",
    ),
    ("The algorithm (Alg. 1) is simple.", "The algorithm (Algorithm 1) is simple."),
    ("See also pp. 10-12 and No. 5.", "See also pages 10 to 12 and number 5."),
    ("E.g. convolutions work.", "For example convolutions work."),
    ("This holds, i.e., always.", "This holds, that is, always."),
    ("Dr. Smith & colleagues, etc.", "Doctor Smith and colleagues, etcetera."),
    ("CNN vs. RNN", "C N N versus R N N"),
    # numbers and units
    (
        "It has 175B parameters and 16GB of RAM.",
        "It has 175 billion parameters and 16 gigabytes of ram.",
    ),
    ("Latency fell from 120 ms to 45ms.", "Latency fell from 120 milliseconds to 45 milliseconds."),
    ("A 2.7x speedup.", "A 2 point 7 times speedup."),
    ("A learning rate of 1e-4.", "A learning rate of 1 times ten to the minus 4."),
    ("Accuracy rose by 3.5%.", "Accuracy rose by 3 point 5 percent."),
    ("Each 224x224 image.", "Each 224 by 224 image."),
    ("It is ~3x faster.", "It is approximately 3 times faster."),
    ("3000 tokens/s on 8 GPUs.", "3000 tokens per second on 8 G P U's."),
    ("About 10^6 samples.", "About ten to the 6 samples."),
    ("Results for 2015–2020.", "Results for 2015 to 2020."),
    ("It cost $5M to train.", "It cost 5 million dollars to train."),
    ("The F1 score was 0.93.", "The F 1 score was 0 point 9 3."),
    ("We saw 10,000 users.", "We saw 10000 users."),
    ("A 1 GB file.", "A 1 gigabyte file."),
    ("An 82M-parameter network.", "An 82 million parameter network."),
    # versions
    (
        "Trained with PyTorch 2.1 on Python 3.11.",
        "Trained with pie torch 2 point 1 on Python 3 point 11.",
    ),
    ("Use v1.2.3 of the tool.", "Use version 1 point 2 point 3 of the tool."),
    # acronyms and lexicon
    ("Our CNN beats LSTMs; NASA uses SLAM.", "Our C N N beats L S T M's; nasa uses slam."),
    ("The GPT-4 and BERT models.", "The G P T 4 and bert models."),
    ("Use SQL and JSON; the GUI uses LaTeX.", "Use sequel and jay son; the gooey uses lah tek."),
    ("SQLite and PostgreSQL both work.", "sequel lite and postgres Q L both work."),
    ("BLEU-4 was 27.3.", "blue 4 was 27 point 3."),
    ("An FPGA and an ONNX model.", "An F P G ay and an O N N X model."),
    ("A RAID array.", "A raid array."),
    # math
    (
        "Let x_i be the input and y^2 the output.",
        "Let x sub i be the input and y squared the output.",
    ),
    ("with α ≤ β", "with alpha less than or equal to beta"),
    (
        r"We compute $\frac{QK^{T}}{\sqrt{d_k}}$ first.",
        "We compute Q K transpose over square root of d sub k first.",
    ),
    (
        r"Let $f(x) = \sum_{i=1}^{n} w_i x_i + b$.",
        "Let f of x equals the sum from i equals 1 to n of w sub i x sub i plus b.",
    ),
    (r"Here $\hat{y} = \sigma(z)$.", "Here y hat equals sigma of z."),
    (r"The loss $\mathcal{L} = -\log P(y \mid x)$.", "The loss L equals minus log P of y given x."),
    (r"Each $\mathbf{x} \in \mathbb{R}^{d}$.", "Each x in R to the d."),
    (r"We set $\lambda = 0.01$.", "We set lambda equals 0 point 0 1."),
    ("P(y | x) is computed.", "P of y given x is computed."),
    ("for all n ≥ 1", "for all n greater than or equal to 1"),
    ("x² + y²", "x squared plus y squared"),
    # code, links
    ("See https://github.com/foo/bar now.", "See a link to github dot com now."),
    ("Edit train_model.py first.", "Edit train model dot py first."),
    ("Call get_batch() with numEpochs.", "Call get batch with num epochs."),
    ("Set `max_seq_len` to 512.", "Set max seq len to 512."),
    ("Mail team@example.org.", "Mail an email address."),
    # punctuation
    ("encoder–decoder models", "encoder decoder models"),
    ("fast — but costly", "fast, but costly"),
    ("the (ii) second item", "the two, second item"),
]


@pytest.mark.parametrize(("source", "spoken"), GOLDEN)
def test_golden(source: str, spoken: str) -> None:
    assert normalize(source).text == spoken


def test_heading_gets_section_prefix_and_final_stop() -> None:
    assert (
        normalize("3.2 Related Work", Context(heading=True)).text
        == "Section 3 point 2. Related Work."
    )
    assert normalize("Abstract", Context(heading=True)).text == "Abstract."


def test_citations_can_be_read() -> None:
    ctx = Context(citations="read")
    assert normalize("As in [3, 5–7].", ctx).text == "As in citing 3, 5 to 7."


def test_math_can_be_skipped() -> None:
    assert normalize(r"Let $x^2$ be.", Context(math="skip")).text == "Let a formula be."


def test_urls_options() -> None:
    assert normalize("At https://x.org now.", Context(urls="link")).text == "At a link now."
    assert normalize("At https://x.org now.", Context(urls="skip")).text == "At now."


def test_spell_all_acronyms() -> None:
    assert normalize("NASA and SLAM", Context(acronyms="spell")).text == "N ay S ay and S L ay M"


def test_user_lexicon_wins() -> None:
    ctx = Context(lexicon={"LaTeX": "lay tek", "Kubernetes": "k eight s"})
    assert normalize("LaTeX on Kubernetes", ctx).text == "lay tek on k eight s"


# ------------------------------------------------------------------ offset invariants

CORPUS = [src for src, _ in GOLDEN] + [
    "The Transformer (Vaswani et al., 2017) replaces recurrence with self-attention, "
    "reducing the path length to O(1) and training 3.5x faster on 8 P100 GPUs.",
]


@pytest.mark.parametrize("source", CORPUS)
def test_every_spoken_word_maps_to_a_source_range(source: str) -> None:
    spoken = normalize(source)
    import re

    for m in re.finditer(r"[A-Za-z0-9']+", spoken.text):
        span = spoken.source_span(m.start(), m.end())
        assert span is not None, (m.group(), spoken.text)
        a, b = span
        assert 0 <= a < b <= len(source)
        assert source[a:b].strip()


@pytest.mark.parametrize("source", CORPUS)
def test_pieces_are_monotonic_and_cover_the_source(source: str) -> None:
    spoken = normalize(source)
    prev_src = 0
    prev_spoken = 0
    for p in spoken.pieces:
        assert p.src_start >= prev_src - 1
        assert p.spoken_start >= prev_spoken
        prev_src, prev_spoken = p.src_end, p.spoken_end


def test_unchanged_words_map_exactly() -> None:
    source = "Attention is all you need."
    spoken = normalize(source)
    assert spoken.text == source
    i = spoken.text.index("all")
    assert spoken.source_span(i, i + 3) == (source.index("all"), source.index("all") + 3)


def test_replacement_maps_to_whole_expression() -> None:
    source = "It takes O(n log n) time."
    spoken = normalize(source)
    i = spoken.text.index("log")
    assert spoken.source_span(i, i + 3) == (9, 19)
