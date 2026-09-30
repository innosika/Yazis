# -*- coding: utf-8 -*-
"""Представление реферата в виде фрагмента семантической сети (OSTIS).

Технология OSTIS предполагает единообразное представление любых знаний
в виде семантической сети — множества sc-узлов и связывающих их sc-дуг.
Текстовой нотацией SC-кода является язык SCs, на котором и выгружается
результат реферирования.

Строящийся фрагмент:

    concept_text_document
        |-> document_X
                => nrel_main_idtf: [заголовок]
                => nrel_text_language: lang_ru | lang_en
                => nrel_subject_domain: subject_domain_*
                => nrel_source_link: [URL]
                => nrel_abstract: abstract_X          (классический реферат)
                => nrel_key_word_set: keywords_X      (реферат-список слов)

Узлы предложений и ключевых слов входят в соответствующие множества
с ролевыми отношениями rrel_1 ... rrel_n, задающими порядок.
"""
from __future__ import annotations

import re
from datetime import datetime

# Транслитерация для построения системных идентификаторов sc-узлов
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_DOMAIN_NODES = {
    "computer science": "subject_domain_computer_science",
    "литература": "subject_domain_literature",
}


def to_identifier(text: str, fallback: str = "node") -> str:
    """Превращает произвольную строку в корректный системный идентификатор."""
    text = text.lower().strip()
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")
    return out or fallback


def _escape(text: str) -> str:
    """Экранирует содержимое sc-ссылки (файла) в нотации SCs."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _language_node(lang: str) -> str:
    return {"ru": "lang_ru", "en": "lang_en"}.get(lang, "lang_" + to_identifier(lang))


# ----------------------------------------------------------------------
def build_graph(analysis) -> dict:
    """Строит граф семантической сети для визуализации в интерфейсе."""
    doc = analysis.document
    base = to_identifier(doc.doc_id, "document")
    doc_node = f"document_{base}"

    nodes: list[dict] = [
        {"id": doc_node, "label": doc.title, "type": "document",
         "note": f"{doc.length} симв., {len(doc.sentences)} предл."},
        {"id": "concept_text_document", "label": "concept_text_document",
         "type": "class", "note": "класс «текстовый документ»"},
        {"id": _language_node(doc.language), "label": _language_node(doc.language),
         "type": "attribute", "note": "язык текста"},
        {"id": f"abstract_{base}", "label": "классический реферат",
         "type": "abstract", "note": f"{len(analysis.primary.indices)} предложений"},
        {"id": f"keywords_{base}", "label": "реферат — список ключевых слов",
         "type": "abstract", "note": f"{len(analysis.keywords)} терминов"},
        {"id": f"method_{analysis.params.method}", "label": analysis.params.method,
         "type": "method", "note": "метод построения реферата"},
    ]
    edges: list[dict] = [
        {"source": "concept_text_document", "target": doc_node, "label": "->"},
        {"source": doc_node, "target": _language_node(doc.language),
         "label": "nrel_text_language"},
        {"source": doc_node, "target": f"abstract_{base}", "label": "nrel_abstract"},
        {"source": doc_node, "target": f"keywords_{base}", "label": "nrel_key_word_set"},
        {"source": f"abstract_{base}", "target": f"method_{analysis.params.method}",
         "label": "nrel_method"},
    ]

    domain_node = _DOMAIN_NODES.get(doc.domain)
    if domain_node:
        nodes.append({"id": domain_node, "label": domain_node, "type": "attribute",
                      "note": "предметная область"})
        edges.append({"source": doc_node, "target": domain_node,
                      "label": "nrel_subject_domain"})

    by_index = {s.index: s for s in analysis.sentences}
    for order, index in enumerate(analysis.primary.indices, start=1):
        sentence = by_index[index]
        node_id = f"sentence_{base}_{index}"
        nodes.append({
            "id": node_id,
            "label": sentence.text[:60] + ("…" if len(sentence.text) > 60 else ""),
            "type": "sentence",
            "weight": round(sentence.weight, 3),
            "note": f"W={sentence.weight:.2f}; Posd={sentence.posd:.2f}; "
                    f"Posp={sentence.posp:.2f}; Score={sentence.score:.2f}",
        })
        edges.append({"source": f"abstract_{base}", "target": node_id,
                      "label": f"rrel_{order}"})

    for order, keyword in enumerate(analysis.keywords, start=1):
        node_id = f"keyword_{base}_{to_identifier(keyword.form, str(order))}"
        nodes.append({
            "id": node_id, "label": keyword.form, "type": "keyword",
            "weight": round(keyword.weight, 3),
            "note": f"w={keyword.weight:.3f}; tf={keyword.tf}; df={keyword.df}",
        })
        edges.append({"source": f"keywords_{base}", "target": node_id,
                      "label": f"rrel_{order}"})

    return {"nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------
def to_scs(analysis) -> str:
    """Выгружает результат реферирования в текстовой нотации SCs."""
    doc = analysis.document
    base = to_identifier(doc.doc_id, "document")
    doc_node = f"document_{base}"
    lang_node = _language_node(doc.language)
    by_index = {s.index: s for s in analysis.sentences}

    lines: list[str] = [
        "// ------------------------------------------------------------------",
        "// Фрагмент семантической сети в SC-коде (нотация SCs)",
        "// Система автоматического реферирования документов, вариант 1",
        f"// Документ: {doc.title}",
        f"// Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "// ------------------------------------------------------------------",
        "",
        "concept_text_document -> " + doc_node + ";;",
        f'{doc_node} => nrel_main_idtf: [{_escape(doc.title)}] (* <- {lang_node};; *);;',
        f"{doc_node} => nrel_text_language: {lang_node};;",
    ]

    domain_node = _DOMAIN_NODES.get(doc.domain)
    if domain_node:
        lines.append(f"{doc_node} => nrel_subject_domain: {domain_node};;")
    if doc.source:
        lines.append(f'{doc_node} => nrel_source_link: [{_escape(doc.source)}];;')
    lines += [
        f"{doc_node} => nrel_character_count: [{doc.length}];;",
        f"{doc_node} => nrel_sentence_count: [{len(doc.sentences)}];;",
        "",
        "// --- реферат классического типа (sentence extraction) ---",
        f"concept_abstract -> abstract_{base};;",
        f"{doc_node} => nrel_abstract: abstract_{base};;",
        f"abstract_{base} => nrel_method: method_{analysis.params.method};;",
        f"abstract_{base} => nrel_sentence_count: [{len(analysis.primary.indices)}];;",
    ]

    for order, index in enumerate(analysis.primary.indices, start=1):
        sentence = by_index[index]
        node_id = f"sentence_{base}_{index}"
        lines += [
            "",
            f"abstract_{base} -> rrel_{order}: {node_id};;",
            f"concept_sentence -> {node_id};;",
            f'{node_id} => nrel_text: [{_escape(sentence.text)}] (* <- {lang_node};; *);;',
            f"{node_id} => nrel_position_in_document: [{index}];;",
            f"{node_id} => nrel_weight: [{sentence.weight:.4f}];;",
            f"{node_id} => nrel_posd: [{sentence.posd:.4f}];;",
            f"{node_id} => nrel_posp: [{sentence.posp:.4f}];;",
            f"{node_id} => nrel_score: [{sentence.score:.4f}];;",
        ]

    lines += [
        "",
        "// --- реферат в виде списка ключевых слов ---",
        f"concept_key_word_set -> keywords_{base};;",
        f"{doc_node} => nrel_key_word_set: keywords_{base};;",
    ]
    for order, keyword in enumerate(analysis.keywords, start=1):
        node_id = f"keyword_{base}_{to_identifier(keyword.form, str(order))}"
        lines += [
            "",
            f"keywords_{base} -> rrel_{order}: {node_id};;",
            f"concept_key_word -> {node_id};;",
            f'{node_id} => nrel_main_idtf: [{_escape(keyword.form)}] (* <- {lang_node};; *);;',
            f'{node_id} => nrel_stem: [{_escape(keyword.term)}];;',
            f"{node_id} => nrel_tf: [{keyword.tf}];;",
            f"{node_id} => nrel_df: [{keyword.df}];;",
            f"{node_id} => nrel_tf_idf_weight: [{keyword.weight:.4f}];;",
        ]

    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
#          семантическая сеть уровня всей коллекции документов
# ----------------------------------------------------------------------
def build_collection_graph(analyses: list, *, keywords_per_document: int = 8,
                           similarity: list[dict] | None = None) -> dict:
    """Строит общий граф коллекции: документы, их ключевые слова и связи.

    Ключевое слово, встретившееся в нескольких документах, представлено
    одним sc-узлом — именно так в базе знаний OSTIS общие понятия
    связывают разные документы предметной области.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_keywords: dict[str, str] = {}
    domains: dict[str, str] = {}

    for analysis in analyses:
        doc = analysis.document
        base = to_identifier(doc.doc_id, "document")
        doc_node = f"document_{base}"
        nodes.append({"id": doc_node, "label": doc.title, "type": "document",
                      "note": f"{doc.language}; {doc.domain}; {doc.length} симв."})

        if doc.domain:
            domain_node = _DOMAIN_NODES.get(doc.domain, "subject_domain_" + to_identifier(doc.domain))
            if domain_node not in domains:
                domains[domain_node] = domain_node
                nodes.append({"id": domain_node, "label": domain_node, "type": "class",
                              "note": "предметная область"})
            edges.append({"source": doc_node, "target": domain_node,
                          "label": "nrel_subject_domain"})

        for keyword in analysis.keywords[:keywords_per_document]:
            key = f"{doc.language}:{keyword.term}"
            node_id = seen_keywords.get(key)
            if node_id is None:
                node_id = f"key_word_{to_identifier(keyword.form, keyword.term)}"
                seen_keywords[key] = node_id
                nodes.append({"id": node_id, "label": keyword.form, "type": "keyword",
                              "weight": round(keyword.weight, 3),
                              "note": f"df={keyword.df}"})
            edges.append({"source": doc_node, "target": node_id,
                          "label": "nrel_key_word", "weight": round(keyword.weight, 3)})

    for pair in similarity or []:
        edges.append({"source": f"document_{to_identifier(pair['a'])}",
                      "target": f"document_{to_identifier(pair['b'])}",
                      "label": f"nrel_similar {pair['score']:.2f}", "similarity": pair["score"]})

    return {"nodes": nodes, "edges": edges}


def to_scs_collection(analyses: list, *, keywords_per_document: int = 8) -> str:
    """Выгружает всю коллекцию как единый фрагмент семантической сети."""
    lines = [
        "// ------------------------------------------------------------------",
        "// Семантическая сеть тестовой коллекции документов (нотация SCs)",
        f"// Документов в коллекции: {len(analyses)}",
        f"// Сформировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "// ------------------------------------------------------------------",
        "",
        "document_collection <- concept_document_collection;;",
    ]
    seen: set[str] = set()
    for analysis in analyses:
        doc = analysis.document
        base = to_identifier(doc.doc_id, "document")
        doc_node = f"document_{base}"
        lines += [
            "",
            f"document_collection -> {doc_node};;",
            f'{doc_node} => nrel_main_idtf: [{_escape(doc.title)}] '
            f'(* <- {_language_node(doc.language)};; *);;',
            f"{doc_node} => nrel_text_language: {_language_node(doc.language)};;",
        ]
        domain_node = _DOMAIN_NODES.get(doc.domain)
        if domain_node:
            lines.append(f"{doc_node} => nrel_subject_domain: {domain_node};;")
        for keyword in analysis.keywords[:keywords_per_document]:
            node_id = f"key_word_{to_identifier(keyword.form, keyword.term)}"
            if node_id not in seen:
                seen.add(node_id)
                lines.append(f'concept_key_word -> {node_id};;')
                lines.append(f'{node_id} => nrel_main_idtf: [{_escape(keyword.form)}];;')
            lines.append(f"{doc_node} => nrel_key_word: {node_id};;")
    lines.append("")
    return "\n".join(lines)
