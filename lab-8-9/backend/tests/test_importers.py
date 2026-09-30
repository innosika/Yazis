from pathlib import Path
from typing import Any

import pymupdf

from app.importers import arxiv, pdf
from app.importers import text as text_importer
from app.importers.structure import build, clean_text, looks_like_heading

FIXTURES = Path(__file__).parent / "fixtures"


def test_arxiv_id_parsing() -> None:
    assert arxiv.parse_id("1706.03762") == "1706.03762"
    assert arxiv.parse_id("arXiv:1706.03762v7") == "1706.03762"
    assert arxiv.parse_id("https://arxiv.org/abs/2310.06825") == "2310.06825"
    assert arxiv.parse_id("https://arxiv.org/pdf/2310.06825v2") == "2310.06825"
    assert arxiv.parse_id("hep-th/9901001") == "hep-th/9901001"
    assert arxiv.parse_id("not an id") is None


def test_latexml_html_structure() -> None:
    doc = arxiv.parse_html((FIXTURES / "latexml_sample.html").read_text())
    assert doc.title == "A Tiny Paper on k -Means"
    kinds = [(b.kind, b.text) for b in doc.blocks]
    assert kinds[0] == ("heading", "Abstract")
    assert ("heading", "1 Introduction") in kinds
    assert ("heading", "1.1 Initialisation") in kinds
    intro = next(b.text for b in doc.blocks if b.text.startswith("Lloyd"))
    assert r"\(O(nkd)\)" in intro
    assert r"\(O(nkd)\) per iteration" in intro and " ." not in intro
    assert "[1]" in intro
    assert "footnote" not in intro
    assert any(b.kind == "equation" and r"\sum_{i=1}^{n}" in b.text for b in doc.blocks)
    assert all("caption" not in b.text for b in doc.blocks)
    assert [b.text for b in doc.blocks if b.kind == "item"] == [
        "Random seeds.",
        "The k-means++ scheme.",
    ]
    # order is document order
    order = [b.text for b in doc.blocks if b.kind == "heading"]
    assert (
        order.index("1 Introduction")
        < order.index("1.1 Initialisation")
        < order.index("2 Conclusion")
    )
    assert "References" not in build(doc)["blocks"][-1]["text"]


def test_markdown_import() -> None:
    md = "# My Paper\n\nIntro text here.\nSecond line joins.\n\n## 2 Method\n\n- first item\n- second item\n\n```\ncode is skipped\n```\n\n| a | b |\n\nDone."
    doc = text_importer.parse(md)
    assert doc.title == "My Paper"
    assert [(b.kind, b.text) for b in doc.blocks] == [
        ("paragraph", "Intro text here. Second line joins."),
        ("heading", "2 Method"),
        ("item", "first item"),
        ("item", "second item"),
        ("paragraph", "Done."),
    ]


def test_plain_text_headings_and_title() -> None:
    text = "Deep Nets for Graphs\n\nAbstract\n\nWe study graphs.\n\n1 Introduction\n\nGraphs are everywhere. They matter."
    doc = text_importer.parse(text)
    assert doc.title == "Deep Nets for Graphs"
    s = build(doc)
    assert [x["title"] for x in s["sections"]] == ["Abstract", "1 Introduction"]
    para = s["blocks"][-1]
    assert [para["text"][a:b] for a, b in ((x["start"], x["end"]) for x in para["sentences"])] == [
        "Graphs are everywhere.",
        "They matter.",
    ]


def test_untitled_long_text_uses_first_words() -> None:
    doc = text_importer.parse("This is a long first paragraph that clearly is not a title at all.")
    assert doc.title.startswith("This is a long first paragraph")


def test_heading_heuristic() -> None:
    assert looks_like_heading("2.1 Model Architecture") == (True, 2)
    assert looks_like_heading("Related Work")[0]
    assert looks_like_heading("III. RESULTS")[0]
    assert not looks_like_heading("This sentence ends with a period.")[0]


def test_clean_text_dehyphenates_but_keeps_compounds() -> None:
    assert (
        clean_text("exam-\nple of self-\nattention", dehyphenate=True)
        == "example of self-attention"
    )
    assert clean_text("ﬁne  ﬂow\n text") == "fine flow text"


def test_references_are_dropped() -> None:
    doc = text_importer.parse("Title\n\nBody text.\n\nReferences\n\n[1] Someone. 2020.")
    blocks = build(doc)["blocks"]
    assert blocks[-1]["text"] == "Body text."


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line, size in [
        ("A Study of Sorting", 18),
        ("1 Introduction", 13),
        ("Merge sort runs in O(n log n) time. It is stable.", 11),
        ("2 Results", 13),
        ("Quicksort is often faster in practice.", 11),
    ]:
        page.insert_text((72, y), line, fontsize=size)
        y += 30
    doc.set_metadata({"title": "A Study of Sorting"})
    return doc.tobytes()


def test_pdf_import() -> None:
    doc = pdf.parse(_make_pdf(), "sorting.pdf")
    assert doc.title == "A Study of Sorting"
    texts = " ".join(b.text for b in doc.blocks)
    assert "Merge sort runs in O(n log n) time." in texts
    assert "Quicksort is often faster in practice." in texts


def test_documents_api(client: Any) -> None:
    docs = client.get("/api/documents").json()
    assert any(d["source"].get("kind") == "sample" for d in docs), "sample is seeded"
    r = client.post(
        "/api/documents/text", json={"text": "Short Title\n\nOne sentence. Two sentences."}
    )
    assert r.status_code == 201
    doc = r.json()
    assert doc["title"] == "Short Title"
    assert doc["structure"]["blocks"][0]["sentences"][1]["start"] > 0
    r = client.patch(
        f"/api/documents/{doc['id']}/position", json={"block": 0, "sentence": 1, "progress": 0.5}
    )
    assert r.json()["progress"] == 0.5
    assert client.get(f"/api/documents/{doc['id']}").json()["position"] == {
        "block": 0,
        "sentence": 1,
    }
    up = client.post(
        "/api/documents/upload", files={"file": ("sort.pdf", _make_pdf(), "application/pdf")}
    )
    assert up.status_code == 201, up.text
    bad = client.post(
        "/api/documents/upload", files={"file": ("x.exe", b"MZ..", "application/octet-stream")}
    )
    assert bad.status_code == 415
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404


def test_sample_article_reads_cleanly(client: Any) -> None:
    sample = next(
        d for d in client.get("/api/documents").json() if d["source"].get("kind") == "sample"
    )
    full = client.get(f"/api/documents/{sample['id']}").json()
    titles = [s["title"] for s in full["structure"]["sections"]]
    assert titles[0] == "Abstract" and titles[-1] == "5 Conclusion"
    assert full["minutes"] > 3


def test_single_short_line_is_text_not_just_a_title() -> None:
    # regression: a one-line paste became the title and left nothing to read
    for text in ["Hello, I am Artem Belugin", "Abstract", "Transformers use attention"]:
        doc = text_importer.parse(text)
        assert doc.title == text
        assert [b.text for b in doc.blocks] == [text]
        assert build(doc)["blocks"], text


def test_short_paste_is_accepted_by_the_api(client: Any) -> None:
    r = client.post("/api/documents/text", json={"text": "Hello, I am Artem Belugin"})
    assert r.status_code == 201, r.text
    assert r.json()["structure"]["blocks"][0]["text"] == "Hello, I am Artem Belugin"


# ------------------------------------------------------------------ editing round trip

from app.importers import serialize  # noqa: E402


def _roundtrip(blocks: list[dict]) -> list[tuple[str, str, int]]:
    back = text_importer.parse(serialize.to_text(blocks), title="t", strict=True)
    return [(b.kind, b.text, b.level) for b in back.blocks]


def _shape(blocks: list[dict]) -> list[tuple[str, str, int]]:
    return [(b["kind"], b["text"], b["level"]) for b in blocks]


def test_roundtrip_preserves_the_sample_article() -> None:
    from app.api.routes_documents import SAMPLE_FILE

    blocks = build(text_importer.parse(SAMPLE_FILE.read_text()))["blocks"]
    assert _roundtrip(blocks) == _shape(blocks)


def test_roundtrip_preserves_an_arxiv_paper_with_formulas() -> None:
    doc = arxiv.parse_html((FIXTURES / "latexml_sample.html").read_text())
    blocks = build(doc)["blocks"]
    assert any(b["kind"] == "equation" for b in blocks)
    assert _roundtrip(blocks) == _shape(blocks)


def test_roundtrip_escapes_text_that_looks_like_markup() -> None:
    blocks = [
        {"kind": "paragraph", "text": "# of params grows linearly.", "level": 0},
        {"kind": "paragraph", "text": "- 5 points were dropped.", "level": 0},
        {"kind": "paragraph", "text": "3. Results come next.", "level": 0},
        {"kind": "paragraph", "text": "|V| vertices and |E| edges.", "level": 0},
        {"kind": "paragraph", "text": "> 90% of runs converge.", "level": 0},
        {"kind": "heading", "text": "2.1 Setup", "level": 2},
        {"kind": "item", "text": "a list item", "level": 0},
    ]
    assert _roundtrip(blocks) == _shape(blocks)


def test_markdown_stripping_leaves_formulas_and_inequalities_alone() -> None:
    doc = text_importer.parse(
        r"Here $x_{i}^{2} * y_{j}$ holds when n < m and m > k, see <b>this</b>.", title="t"
    )
    assert doc.blocks[0].text == r"Here $x_{i}^{2} * y_{j}$ holds when n < m and m > k, see this."


def test_display_math_paragraph_becomes_an_equation() -> None:
    doc = text_importer.parse("Intro text.\n\n$$E = mc^2$$\n\n\\(a + b\\)", title="t", strict=True)
    assert [(b.kind, b.text) for b in doc.blocks] == [
        ("paragraph", "Intro text."),
        ("equation", r"\(E = mc^2\)"),
        ("equation", r"\(a + b\)"),
    ]


def test_strict_mode_does_not_guess_headings() -> None:
    doc = text_importer.parse("Results\n\nThe numbers improved.", title="t", strict=True)
    assert [b.kind for b in doc.blocks] == ["paragraph", "paragraph"]


def test_edit_api_rename_and_rewrite(client: Any) -> None:
    doc = client.post(
        "/api/documents/text",
        json={
            "text": "Graph Notes\n\nFirst paragraph here. It has two sentences.\n\nSecond paragraph.",
        },
    ).json()
    doc_id = doc["id"]
    client.patch(
        f"/api/documents/{doc_id}/position", json={"block": 1, "sentence": 0, "progress": 0.5}
    )

    src = client.get(f"/api/documents/{doc_id}/source").json()
    assert src["title"] == "Graph Notes"
    assert src["text"] == "First paragraph here. It has two sentences.\n\nSecond paragraph.\n"

    # saving the untouched source changes nothing
    same = client.patch(f"/api/documents/{doc_id}", json={"text": src["text"]}).json()
    assert same["structure"] == doc["structure"]
    assert same["position"] == {"block": 1, "sentence": 0}

    renamed = client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "  Graph   notes, revised ", "authors": ["Ada", " "]},
    ).json()
    assert renamed["title"] == "Graph notes, revised"
    assert renamed["authors"] == ["Ada"]
    assert renamed["structure"] == doc["structure"]

    edited = client.patch(
        f"/api/documents/{doc_id}",
        json={
            "text": "# 1 Intro\n\nA new first paragraph about $O(n^2)$ cost.\n\n- one\n- two\n\n## References\n\nKept on purpose.",
        },
    ).json()
    kinds = [(b["kind"], b["text"]) for b in edited["structure"]["blocks"]]
    assert kinds[0] == ("heading", "1 Intro")
    assert ("item", "two") in kinds
    assert kinds[-1] == ("paragraph", "Kept on purpose.")
    assert [s["title"] for s in edited["structure"]["sections"]] == ["1 Intro", "References"]
    assert edited["word_count"] > 5
    assert edited["position"] == {"block": 1, "sentence": 0}

    listed = next(d for d in client.get("/api/documents").json() if d["id"] == doc_id)
    assert listed["title"] == "Graph notes, revised"

    assert client.patch(f"/api/documents/{doc_id}", json={"title": "   "}).status_code == 422
    assert client.patch(f"/api/documents/{doc_id}", json={"text": "  \n\n "}).status_code == 422
    assert client.patch("/api/documents/nope", json={"title": "x"}).status_code == 404
    client.delete(f"/api/documents/{doc_id}")


def test_edit_resets_position_past_the_end(client: Any) -> None:
    doc = client.post("/api/documents/text", json={"text": "T\n\nOne.\n\nTwo.\n\nThree."}).json()
    client.patch(
        f"/api/documents/{doc['id']}/position", json={"block": 2, "sentence": 0, "progress": 0.9}
    )
    out = client.patch(
        f"/api/documents/{doc['id']}", json={"text": "Only one paragraph now."}
    ).json()
    assert out["position"] == {} and out["progress"] == 0.0
    client.delete(f"/api/documents/{doc['id']}")
