# -*- coding: utf-8 -*-
"""Коллекция документов и индекс терминов.

Коллекция нужна для расчёта IDF: вес слова тем выше, чем в меньшем числе
документов коллекции оно встречается. Класс :class:`Collection` хранит
документы, документные частоты df(t) и общее число документов |DB|.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import config
from .text import Paragraph, Sentence, detect_language, split_paragraphs, split_sentences
from .tokenizer import Token, count_tokens, tokenize


@dataclass(slots=True)
class Document:
    """Документ коллекции со всей извлечённой из него структурой."""

    doc_id: str
    title: str
    text: str
    language: str
    domain: str = ""
    source: str = ""
    path: str = ""
    added_by_user: bool = False

    paragraphs: list[Paragraph] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)
    tokens: list[Token] = field(default_factory=list)
    sentence_tokens: list[list[Token]] = field(default_factory=list)

    tf: Counter = field(default_factory=Counter)          # tf(t, D)
    tf_max: int = 0                                       # tf_max(D)
    surface_forms: dict = field(default_factory=dict)     # term -> Counter словоформ
    total_words: int = 0                                  # всего словоформ в тексте

    # ---------------------------------------------------------------
    @property
    def length(self) -> int:
        """|D| — число символов в документе."""
        return len(self.text)

    def most_frequent_form(self, term: str) -> str:
        """Самая частая словоформа термина — её показывают пользователю."""
        forms = self.surface_forms.get(term)
        if not forms:
            return term
        return forms.most_common(1)[0][0]

    def analyze(self) -> None:
        """Выполняет сегментацию и подсчёт частот терминов документа."""
        self.paragraphs = split_paragraphs(self.text)
        self.sentences = split_sentences(self.text, self.paragraphs)
        self.tokens = tokenize(self.text, self.language)
        self.total_words = count_tokens(self.text)
        self.sentence_tokens = [tokenize(s.text, self.language) for s in self.sentences]

        self.tf = Counter(tok.term for tok in self.tokens)
        self.tf_max = max(self.tf.values(), default=0)
        forms: dict[str, Counter] = defaultdict(Counter)
        for tok in self.tokens:
            forms[tok.term][tok.norm] += 1
        self.surface_forms = dict(forms)

    def apply_stem_map(self, mapping: dict[str, str]) -> None:
        """Применяет склейку основ (term -> канонический term)."""
        if not mapping:
            return
        for tok in self.tokens:
            tok.term = mapping.get(tok.term, tok.term)
        for toks in self.sentence_tokens:
            for tok in toks:
                tok.term = mapping.get(tok.term, tok.term)
        self.tf = Counter(tok.term for tok in self.tokens)
        self.tf_max = max(self.tf.values(), default=0)
        forms: dict[str, Counter] = defaultdict(Counter)
        for tok in self.tokens:
            forms[tok.term][tok.norm] += 1
        self.surface_forms = dict(forms)


class Collection:
    """Набор документов |DB| с документными частотами df(t)."""

    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents: list[Document] = documents or []
        self.df: Counter = Counter()
        self.load_time: float = 0.0
        self._by_id: dict[str, Document] = {}

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, directory: str | None = None) -> "Collection":
        """Загружает коллекцию из каталога (файлы *.txt + meta.json)."""
        directory = directory or config.COLLECTION_DIR
        started = time.perf_counter()
        meta_path = os.path.join(directory, "meta.json")
        meta: dict[str, dict] = {}
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as fh:
                data = json.load(fh)
            meta = {item["file"]: item for item in data.get("documents", [])}

        documents: list[Document] = []
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".txt"):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
            info = meta.get(name, {})
            documents.append(Document(
                doc_id=info.get("id", os.path.splitext(name)[0]),
                title=info.get("title", os.path.splitext(name)[0]),
                text=text,
                language=info.get("language") or detect_language(text),
                domain=info.get("domain", ""),
                source=info.get("source", ""),
                path=path,
                added_by_user=bool(info.get("added_by_user")),
            ))
        collection = cls(documents)
        collection.build_index()
        collection.load_time = time.perf_counter() - started
        return collection

    # ------------------------------------------------------------------
    def build_index(self, conflate: bool = True) -> None:
        """Анализирует документы и считает документные частоты df(t)."""
        for doc in self.documents:
            doc.analyze()
        if conflate:
            self._conflate_stems()
        self._recount_df()
        self._by_id = {doc.doc_id: doc for doc in self.documents}

    def _recount_df(self) -> None:
        self.df = Counter()
        for doc in self.documents:
            for term in doc.tf:
                self.df[term] += 1

    def _conflate_stems(self) -> None:
        """Склейка родственных основ, «разъехавшихся» из-за стеммера.

        Алгоритм Snowball иногда даёт для разных форм одного слова разные
        основы: «системы» -> «систем», а «систем» -> «сист»; «романа» ->
        «рома», а «романе» -> «роман». Признак такой пары строгий: более
        длинная основа B сама встречается в тексте как словоформа, основой
        которой стеммер назначил более короткую основу A. Тогда B и A —
        формы одного слова, и B отображается в A.

        Такая склейка не меняет формул методички, она лишь уточняет
        подсчёт tf(t, D); в интерфейсе её можно отключить.
        """
        forms_by_lang: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        terms_by_lang: dict[str, set[str]] = defaultdict(set)
        for doc in self.documents:
            terms_by_lang[doc.language].update(doc.tf)
            for term, forms in doc.surface_forms.items():
                forms_by_lang[doc.language][term].update(forms)

        mapping: dict[str, str] = {}
        for lang, terms in terms_by_lang.items():
            forms = forms_by_lang[lang]
            for short_term, word_forms in forms.items():
                for form in word_forms:
                    if form != short_term and form in terms:
                        # словоформа «систем» сама является основой другого термина
                        mapping[form] = short_term

        # транзитивное замыкание отображения
        for term in list(mapping):
            seen = {term}
            target = mapping[term]
            while target in mapping and target not in seen:
                seen.add(target)
                target = mapping[target]
            mapping[term] = target

        self.stem_map = mapping
        for doc in self.documents:
            doc.apply_stem_map(mapping)

    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        """|DB| — количество документов в коллекции."""
        return len(self.documents)

    def get(self, doc_id: str) -> Document | None:
        return self._by_id.get(doc_id)

    def document_frequency(self, term: str) -> int:
        """df(t) — число документов коллекции, содержащих термин t."""
        return self.df.get(term, 0)

    def idf(self, term: str, extra_docs: int = 0, extra_df: int = 0) -> float:
        """log(|DB| / df(t)) — обратная документная частота."""
        n = self.size + extra_docs
        df = self.df.get(term, 0) + extra_df
        if df <= 0 or n <= 0:
            return 0.0
        return math.log(n / df)

    def add_temporary(self, doc: Document) -> None:
        """Регистрирует документ пользователя во временном индексе."""
        doc.analyze()
        if getattr(self, "stem_map", None):
            doc.apply_stem_map(self.stem_map)


# ----------------------------------------------------------------------
#            управление составом коллекции (документы пользователя)
# ----------------------------------------------------------------------
MIN_DOCUMENT_CHARS = 400


def _read_meta(directory: str) -> dict:
    path = os.path.join(directory, "meta.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"collection": "YAZIS lab3, вариант 1", "documents": []}


def _write_meta(directory: str, meta: dict) -> None:
    with open(os.path.join(directory, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)


def save_document(text: str, title: str, *, language: str = "",
                  domain: str = "", source: str = "",
                  directory: str | None = None,
                  reuse_existing: bool = True) -> dict:
    """Сохраняет документ пользователя в коллекцию (постоянно, на диск).

    После добавления размер коллекции |DB| увеличивается, а документные
    частоты df(t) пересчитываются — веса терминов во всех документах
    изменятся, что и отражает суть коллекционной поправки IDF.

    Если такой же текст уже добавлялся (``reuse_existing``), повторная копия
    не создаётся: возвращается существующая запись с признаком ``existing``.
    """
    from .scs import to_identifier               # локальный импорт: циклы

    directory = directory or config.COLLECTION_DIR
    text = (text or "").strip()
    title = (title or "").strip() or "Документ пользователя"
    if len(text) < MIN_DOCUMENT_CHARS:
        raise ValueError(f"документ слишком короткий: нужно не менее "
                         f"{MIN_DOCUMENT_CHARS} символов")

    os.makedirs(directory, exist_ok=True)
    meta = _read_meta(directory)

    if reuse_existing:
        for item in meta["documents"]:
            if not item.get("added_by_user") or item.get("chars") != len(text):
                continue
            path = os.path.join(directory, item.get("file", item["id"] + ".txt"))
            try:
                with open(path, encoding="utf-8") as fh:
                    if fh.read().strip() == text:
                        return {**item, "existing": True}
            except OSError:
                continue

    existing = {item["id"] for item in meta["documents"]}

    base = "user_" + (to_identifier(title) or "document")
    doc_id, index = base[:60], 2
    while doc_id in existing or os.path.exists(os.path.join(directory, doc_id + ".txt")):
        doc_id = f"{base[:56]}_{index}"
        index += 1

    with open(os.path.join(directory, doc_id + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")

    record = {
        "id": doc_id,
        "file": doc_id + ".txt",
        "title": title[:200],
        "language": language or detect_language(text),
        "domain": domain or "документ пользователя",
        "source": source,
        "chars": len(text),
        "added_by_user": True,
    }
    meta["documents"].append(record)
    _write_meta(directory, meta)
    return {**record, "existing": False}


def delete_document(doc_id: str, *, directory: str | None = None) -> dict:
    """Удаляет из коллекции документ, добавленный пользователем."""
    directory = directory or config.COLLECTION_DIR
    meta = _read_meta(directory)
    record = next((item for item in meta["documents"] if item["id"] == doc_id), None)
    if record is None:
        raise KeyError(f"документ не найден: {doc_id}")
    if not record.get("added_by_user"):
        raise PermissionError("удалять можно только документы, добавленные пользователем")

    path = os.path.join(directory, record.get("file", doc_id + ".txt"))
    if os.path.exists(path):
        os.remove(path)
    meta["documents"] = [item for item in meta["documents"] if item["id"] != doc_id]
    _write_meta(directory, meta)
    return record
