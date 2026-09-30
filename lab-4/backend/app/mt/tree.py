"""The syntactic parse tree of a chosen sentence (tab 2).

spaCy produces a *dependency* parse: every word points at its syntactic head, and the verb
of the main clause points at itself. That is the structure the transfer rules read, so it is
the structure the interface should draw - a constituency tree would be a second, unrelated
analysis that nothing in the system actually uses.

The layout is computed here rather than in the browser because the depth and the subtree
widths are what determine whether the drawing is readable, and that is a property of the
parse, not of the viewport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.mt.analysis import Sentence
from app.mt.stats import TokenTranslation
from app.mt.tagset import explain_features, explain_penn, explain_upos


@dataclass(slots=True)
class TreeNode:
    id: int
    text: str
    lemma: str
    upos: str
    pos_name: str
    tag: str
    tag_name: str
    tag_description: str
    dep: str
    dep_description: str
    features: list[str]
    translation: str = ""
    target_decoded: list[str] = field(default_factory=list)
    depth: int = 0
    children: list[TreeNode] = field(default_factory=list)

    @property
    def width(self) -> int:
        """Number of leaves under this node - the horizontal space the subtree needs."""
        return sum(child.width for child in self.children) or 1


# Universal Dependencies / ClearNLP labels spaCy emits for English, in plain language.
DEP_DESCRIPTIONS: dict[str, str] = {
    "ROOT": "root of the sentence",
    "acl": "clausal modifier of a noun",
    "acomp": "adjectival complement",
    "advcl": "adverbial clause modifier",
    "advmod": "adverbial modifier",
    "agent": "agent of a passive verb",
    "amod": "adjectival modifier",
    "appos": "appositional modifier",
    "attr": "attribute of a copula",
    "aux": "auxiliary verb",
    "auxpass": "passive auxiliary",
    "case": "case marker",
    "cc": "coordinating conjunction",
    "ccomp": "clausal complement",
    "compound": "compound noun modifier",
    "conj": "conjunct",
    "csubj": "clausal subject",
    "csubjpass": "clausal passive subject",
    "dative": "dative object",
    "dep": "unclassified dependent",
    "det": "determiner",
    "dobj": "direct object",
    "expl": "expletive",
    "intj": "interjection",
    "mark": "subordinating marker",
    "meta": "meta modifier",
    "neg": "negation modifier",
    "nmod": "nominal modifier",
    "npadvmod": "noun phrase as adverbial modifier",
    "nsubj": "nominal subject",
    "nsubjpass": "passive nominal subject",
    "nummod": "numeric modifier",
    "oprd": "object predicate",
    "parataxis": "parataxis",
    "pcomp": "complement of a preposition",
    "pobj": "object of a preposition",
    "poss": "possession modifier",
    "preconj": "pre-correlative conjunction",
    "predet": "predeterminer",
    "prep": "prepositional modifier",
    "prt": "particle of a phrasal verb",
    "punct": "punctuation",
    "quantmod": "modifier of a quantifier",
    "relcl": "relative clause modifier",
    "xcomp": "open clausal complement",
    "obj": "direct object",
    "obl": "oblique nominal",
    "": "unlabelled",
}


def build_tree(sentence: Sentence, tokens: list[TokenTranslation] | None = None) -> TreeNode | None:
    """Build the dependency tree of `sentence`, annotated with its translations."""
    by_index = {token.index: token for token in (tokens or [])}

    nodes: dict[int, TreeNode] = {}
    for token in sentence.tokens:
        upos_info = explain_upos(token.upos)
        tag_info = explain_penn(token.tag)
        decision = by_index.get(token.index)
        nodes[token.index] = TreeNode(
            id=token.index,
            text=token.text,
            lemma=token.lemma,
            upos=token.upos,
            pos_name=upos_info.name,
            tag=token.tag,
            tag_name=tag_info.name,
            tag_description=tag_info.description,
            dep=token.dep,
            dep_description=DEP_DESCRIPTIONS.get(token.dep, token.dep),
            features=explain_features(token.morph),
            translation=decision.translation if decision else "",
            target_decoded=list(decision.target_decoded) if decision else [],
        )

    root: TreeNode | None = None
    for token in sentence.tokens:
        node = nodes[token.index]
        if token.is_root:
            if root is None or not token.is_punct:
                root = node
            continue
        nodes[token.head].children.append(node)

    if root is None:
        return None

    _set_depth(root, 0)
    return root


def _set_depth(node: TreeNode, depth: int) -> None:
    node.depth = depth
    # Keep children in source order so the drawing reads left to right like the sentence.
    node.children.sort(key=lambda child: child.id)
    for child in node.children:
        _set_depth(child, depth + 1)


def tree_to_dict(node: TreeNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "text": node.text,
        "lemma": node.lemma,
        "upos": node.upos,
        "pos_name": node.pos_name,
        "tag": node.tag,
        "tag_name": node.tag_name,
        "tag_description": node.tag_description,
        "dep": node.dep,
        "dep_description": node.dep_description,
        "features": node.features,
        "translation": node.translation,
        "target_decoded": node.target_decoded,
        "depth": node.depth,
        "width": node.width,
        "children": [tree_to_dict(child) for child in node.children],
    }
