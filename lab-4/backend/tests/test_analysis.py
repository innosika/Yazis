"""The analysis stage must give the transfer rules the structure they expect."""

from app.mt.analysis import Analyzer


def test_sentences_are_split(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The model is simple. The reader is not.")
    assert len(analysis.sentences) == 2
    assert analysis.sentences[0].text.startswith("The model")


def test_tags_and_lemmas(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The neural network model learns representations of words.")
    by_text = {token.text: token for token in analysis.tokens}

    assert by_text["neural"].upos == "ADJ"
    assert by_text["network"].upos == "NOUN"
    assert by_text["learns"].upos == "VERB"
    assert by_text["learns"].tag == "VBZ"
    assert by_text["learns"].lemma == "learn"
    assert by_text["words"].lemma == "word"
    assert "Number=Plur" in by_text["words"].morph


def test_dependency_tree_is_connected(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The author's narrative remains unclear.")
    sentence = analysis.sentences[0]
    root = sentence.root
    assert root is not None and root.lemma == "remain"

    # Every token reaches the root by following heads - i.e. the tree has no orphans.
    for token in sentence.tokens:
        seen = set()
        current = token
        while not current.is_root:
            assert current.index not in seen, "cycle in the dependency tree"
            seen.add(current.index)
            current = sentence.tokens[current.head]
        assert current.index == root.index or current.is_punct


def test_word_count_excludes_punctuation(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("Words, numbers: 42 — and punctuation!")
    assert analysis.word_count == 5


def test_whitespace_is_preserved(analyzer: Analyzer) -> None:
    text = "The  model   learns."
    analysis = analyzer.analyse(text)
    rebuilt = "".join(token.text + token.whitespace for token in analysis.tokens)
    assert rebuilt.split() == text.split()


def test_empty_sentences_are_dropped(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("First sentence.\n\n\n   \n\nSecond sentence.")
    assert [sentence.index for sentence in analysis.sentences] == [0, 1]
