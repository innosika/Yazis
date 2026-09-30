"""The parse tree of a chosen sentence (requirement R7)."""

from app.mt.domains import get_domain
from app.mt.pipeline import Pipeline
from app.mt.tree import DEP_DESCRIPTIONS, tree_to_dict
from tests.test_transfer import DICTIONARY


def test_tree_has_a_single_root(pipeline: Pipeline) -> None:
    result = pipeline.run("The author's narrative remains simple.", DICTIONARY, get_domain("cs"))
    root = result.sentence_tree(0)
    assert root is not None
    assert root.lemma == "remain"
    assert root.depth == 0


def test_every_token_appears_exactly_once(pipeline: Pipeline) -> None:
    text = "Researchers evaluate the quality of the machine learning system with data."
    result = pipeline.run(text, DICTIONARY, get_domain("cs"))
    root = result.sentence_tree(0)
    assert root is not None

    seen: list[int] = []

    def walk(node) -> None:
        seen.append(node.id)
        for child in node.children:
            walk(child)

    walk(root)
    expected = len(result.analysis.sentences[0].tokens)
    assert sorted(seen) == list(range(expected))


def test_children_are_in_source_order(pipeline: Pipeline) -> None:
    result = pipeline.run(
        "Researchers evaluate the quality with data.", DICTIONARY, get_domain("cs")
    )
    root = result.sentence_tree(0)
    assert root is not None
    ids = [child.id for child in root.children]
    assert ids == sorted(ids)


def test_nodes_carry_decoding_and_translation(pipeline: Pipeline) -> None:
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    payload = tree_to_dict(result.sentence_tree(0))
    stack = [payload]
    while stack:
        node = stack.pop()
        assert node["pos_name"]
        assert node["tag_name"]
        assert node["dep_description"]
        stack.extend(node["children"])


def test_every_emitted_dependency_label_is_described(pipeline: Pipeline, analyzer) -> None:
    text = (
        "Researchers who evaluated the quality of the machine learning system with data "
        "have not published their results, although the author's narrative remains simple "
        "and the model was studied carefully by Vaswani in 2017."
    )
    analysis = analyzer.analyse(text)
    unknown = {
        token.dep for token in analysis.tokens if token.dep and token.dep not in DEP_DESCRIPTIONS
    }
    assert not unknown, f"dependency labels without a description: {unknown}"


def test_out_of_range_sentence_returns_nothing(pipeline: Pipeline) -> None:
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    assert result.sentence_tree(99) is None
