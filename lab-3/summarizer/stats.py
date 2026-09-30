# -*- coding: utf-8 -*-
"""Статистика тестовой коллекции документов.

Раздел отчёта «информация о тестовой коллекции» и «результаты тестирования»
требует количественных характеристик обрабатываемых текстов. Модуль считает:

* сводку по каждому документу (объём, число абзацев, предложений, терминов);
* разбор отсева слов: сколько отброшено стоп-слов, чисел, слов чужого
  алфавита и коротких токенов;
* ранго-частотное распределение терминов (проверка закона Ципфа);
* распределение документных частот df(t) — сколько терминов встречается
  в одном, двух и т. д. документах, и сколько из них обнуляются IDF.
"""
from __future__ import annotations

import math
from collections import Counter

from .tokenizer import filter_report

#: сколько точек ранго-частотного распределения передаётся в интерфейс
ZIPF_POINTS = 220


def _zipf(counter: Counter, limit: int = ZIPF_POINTS) -> dict:
    """Ранго-частотное распределение и оценка показателя закона Ципфа.

    Закон Ципфа: f(r) ≈ C / r^s. Показатель s оценивается методом наименьших
    квадратов в логарифмических координатах.
    """
    ordered = [count for _, count in counter.most_common()]
    if not ordered:
        return {"points": [], "exponent": 0.0, "total_terms": 0}

    points = []
    for rank, frequency in enumerate(ordered[:limit], start=1):
        points.append({"rank": rank, "freq": frequency})

    # МНК по всем терминам с частотой > 1 (хвост из одиночных слов зашумлён)
    xs, ys = [], []
    for rank, frequency in enumerate(ordered, start=1):
        if frequency < 2:
            break
        xs.append(math.log(rank))
        ys.append(math.log(frequency))
    exponent = 0.0
    if len(xs) > 2:
        n = len(xs)
        mean_x, mean_y = sum(xs) / n, sum(ys) / n
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denominator = sum((x - mean_x) ** 2 for x in xs)
        exponent = -numerator / denominator if denominator else 0.0

    return {"points": points, "exponent": round(exponent, 3),
            "total_terms": len(ordered),
            "max_freq": ordered[0],
            "hapax": sum(1 for count in ordered if count == 1)}


def collection_statistics(collection) -> dict:
    """Собирает полную статистику по коллекции."""
    documents = []
    filtering = {"words": 0, "numbers": 0, "short": 0, "foreign": 0,
                 "stopwords": 0, "kept": 0}
    by_language: dict[str, Counter] = {}

    for document in collection.documents:
        report = filter_report(document.text, document.language)
        for key in filtering:
            filtering[key] += report[key]
        by_language.setdefault(document.language, Counter()).update(document.tf)

        sentences = len(document.sentences)
        paragraphs = len(document.paragraphs)
        documents.append({
            "id": document.doc_id,
            "title": document.title,
            "language": document.language,
            "domain": document.domain,
            "added_by_user": document.added_by_user,
            "chars": document.length,
            "words": document.total_words,
            "kept": report["kept"],
            "stopword_share": round(report["stopwords"] / report["words"], 4)
                              if report["words"] else 0.0,
            "paragraphs": paragraphs,
            "sentences": sentences,
            "terms": len(document.tf),
            "tf_max": document.tf_max,
            "avg_sentence_chars": round(document.length / sentences, 1) if sentences else 0,
            "avg_paragraph_sentences": round(sentences / paragraphs, 2) if paragraphs else 0,
            "hapax": sum(1 for count in document.tf.values() if count == 1),
        })

    # распределение документных частот
    df_histogram = Counter(collection.df.values())
    size = collection.size
    df_rows = [{"df": value, "terms": df_histogram.get(value, 0),
                "idf": round(math.log(size / value), 3) if value else 0.0}
               for value in range(1, size + 1)]

    zipf = {lang: _zipf(counter) for lang, counter in by_language.items()}

    return {
        "size": size,
        "documents": documents,
        "filtering": filtering,
        "df_histogram": df_rows,
        "zero_weight_terms": df_histogram.get(size, 0),
        "unique_terms": len(collection.df),
        "zipf": zipf,
        "totals": {
            "chars": sum(d["chars"] for d in documents),
            "words": sum(d["words"] for d in documents),
            "sentences": sum(d["sentences"] for d in documents),
            "paragraphs": sum(d["paragraphs"] for d in documents),
        },
    }
