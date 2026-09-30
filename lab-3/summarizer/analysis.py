# -*- coding: utf-8 -*-
"""Полный цикл реферирования одного документа.

Модуль связывает воедино все этапы обработки и формирует структуру
результата, пригодную для передачи в интерфейс (JSON), сохранения в файл
и печати:

    сегментация -> токенизация -> стемминг -> веса терминов (TF-IDF)
    -> веса предложений (Posd * Posp * Score) -> генерация реферата
    -> метрики качества -> фрагмент семантической сети (SC-код).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import SummaryParams
from .collection import Collection, Document
from .metrics import (compression, keyword_coverage, rouge_l, rouge_n,
                      selection_agreement)
from .summary import SentenceScore, render_summary, score_sentences, select_sentences
from .textrank import hybrid, lead_baseline, textrank
from .tokenizer import tokenize
from .weights import TermWeight, compute_term_weights, top_keywords

METHOD_TITLES = {
    "tfidf": "Sentence extraction (формула методических указаний)",
    "textrank": "TextRank (PageRank по графу предложений)",
    "lead": "Lead-N (базовая эвристика «первые предложения»)",
    "hybrid": "Гибрид: Posd · Posp · (Score + TextRank)",
}


@dataclass(slots=True)
class MethodResult:
    """Результат работы одного метода отбора предложений."""

    method: str
    indices: list[int]
    text: str
    ranking: dict[int, float] = field(default_factory=dict)
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class Analysis:
    """Полный результат реферирования документа."""

    document: Document
    params: SummaryParams
    term_weights: dict[str, TermWeight]
    keywords: list[TermWeight]
    sentences: list[SentenceScore]
    methods: dict[str, MethodResult]
    timings: dict[str, float]
    db_size: int

    # ------------------------------------------------------------------
    @property
    def primary(self) -> MethodResult:
        return self.methods[self.params.method]

    def summary_terms(self) -> set[str]:
        chosen = set(self.primary.indices)
        terms: set[str] = set()
        for sentence in self.sentences:
            if sentence.index in chosen:
                terms.update(t for t, _, _ in sentence.terms)
        return terms

    # ------------------------------------------------------------------
    def quality(self) -> dict:
        """Метрики качества и диагностика позиционного перекоса."""
        doc = self.document
        primary = self.primary
        stems = {k.term for k in self.keywords}
        summary_chars = len(primary.text)

        def token_stems(indices: list[int]) -> list[str]:
            by_index = {s.index: s for s in self.sentences}
            out: list[str] = []
            for i in sorted(indices):
                sentence = by_index.get(i)
                if sentence:
                    out.extend(tok.term for tok in tokenize(sentence.text, doc.language))
            return out

        reference = token_stems(self.methods["tfidf"].indices)
        comparisons = {}
        for name, result in self.methods.items():
            if name == "tfidf":
                continue
            candidate = token_stems(result.indices)
            comparisons[name] = {
                "rouge1": rouge_n(candidate, reference, 1).as_dict(),
                "rouge2": rouge_n(candidate, reference, 2).as_dict(),
                "rougeL": rouge_l(candidate, reference).as_dict(),
                "agreement": round(selection_agreement(result.indices,
                                                       self.methods["tfidf"].indices), 4),
            }

        # диагностика позиционного перекоса формулы
        by_score = sorted(self.sentences, key=lambda s: -s.score)[: self.params.sentences]
        top_content = {s.index for s in by_score}
        chosen = set(primary.indices)
        positions = [round(s.start / doc.length, 4) for s in self.sentences
                     if s.index in chosen]

        return {
            "compression": round(compression(summary_chars, doc.length), 4),
            "summary_chars": summary_chars,
            "summary_sentences": len(primary.indices),
            "keyword_coverage": round(keyword_coverage(self.summary_terms(),
                                                       list(stems)), 4),
            "comparisons": comparisons,
            "position_bias": {
                "content_top_kept": len(top_content & chosen),
                "content_top_total": len(top_content),
                "mean_relative_position": round(sum(positions) / len(positions), 4)
                                          if positions else 0.0,
                "last_third_selected": sum(1 for p in positions if p > 2 / 3),
            },
        }

    # ------------------------------------------------------------------
    def as_dict(self, *, include_sentences: bool = True) -> dict:
        doc = self.document
        data = {
            "document": {
                "id": doc.doc_id,
                "title": doc.title,
                "language": doc.language,
                "domain": doc.domain,
                "source": doc.source,
                "chars": doc.length,
                "words": doc.total_words,
                "significant_words": len(doc.tokens),
                "paragraphs": len(doc.paragraphs),
                "sentences": len(doc.sentences),
                "terms": len(doc.tf),
                "tf_max": doc.tf_max,
            },
            "params": {
                "sentences": self.params.sentences,
                "keywords": self.params.keywords,
                "alpha": self.params.alpha,
                "beta": self.params.beta,
                "method": self.params.method,
                "method_title": METHOD_TITLES.get(self.params.method, self.params.method),
                "conflate_stems": self.params.conflate_stems,
                "mmr_lambda": self.params.mmr_lambda,
                "length_norm": self.params.length_norm,
                "db_size": self.db_size,
            },
            "keywords": [k.as_dict() for k in self.keywords],
            "terms": [w.as_dict() for w in sorted(
                self.term_weights.values(),
                key=lambda w: (-w.weight, -w.tf))[:400]],
            "summary": {
                "indices": self.primary.indices,
                "text": self.primary.text,
            },
            "methods": {
                name: {"indices": result.indices, "text": result.text,
                       "title": METHOD_TITLES.get(name, name),
                       "elapsed_ms": round(result.elapsed_ms, 2)}
                for name, result in self.methods.items()
            },
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
            "quality": self.quality(),
        }
        if include_sentences:
            data["sentences"] = [s.as_dict(self.term_weights) for s in self.sentences]
        return data


# ----------------------------------------------------------------------
def analyze(document: Document, collection: Collection, params: SummaryParams,
            *, temporary: bool = False) -> Analysis:
    """Выполняет полный цикл реферирования документа."""
    params.clamp()
    timings: dict[str, float] = {}

    started = time.perf_counter()
    if not document.sentences:
        document.analyze()
    timings["segmentation_ms"] = (time.perf_counter() - started) * 1000

    extra_docs = 1 if temporary else 0
    extra_df = 1 if temporary else 0

    started = time.perf_counter()
    term_weights = compute_term_weights(document, collection,
                                        extra_docs=extra_docs, extra_df=extra_df)
    keywords = top_keywords(term_weights, params.keywords)
    timings["term_weights_ms"] = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    sentences = score_sentences(document, term_weights, params)
    timings["sentence_weights_ms"] = (time.perf_counter() - started) * 1000

    methods: dict[str, MethodResult] = {}

    def run(name: str, ranking: dict[int, float] | None) -> None:
        began = time.perf_counter()
        indices = select_sentences(sentences, params.sentences,
                                   mmr_lambda=params.mmr_lambda, ranking=ranking)
        methods[name] = MethodResult(
            method=name, indices=indices,
            text=render_summary(sentences, indices),
            ranking=ranking or {s.index: s.weight for s in sentences},
            elapsed_ms=(time.perf_counter() - began) * 1000,
        )

    run("tfidf", None)
    run("textrank", textrank(sentences, term_weights))
    run("lead", lead_baseline(sentences))
    run("hybrid", hybrid(sentences, term_weights, params))

    timings["generation_ms"] = sum(m.elapsed_ms for m in methods.values())
    timings["total_ms"] = sum(timings.values())

    return Analysis(document=document, params=params, term_weights=term_weights,
                    keywords=keywords, sentences=sentences, methods=methods,
                    timings=timings, db_size=collection.size + extra_docs)
