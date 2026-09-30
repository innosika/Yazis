# -*- coding: utf-8 -*-
"""Весовые коэффициенты значимости терминов (модифицированная TF-IDF).

Формула из методических указаний:

    w(t, D) = 0.5 * (1 + tf(t, D) / tf_max(D)) * log(|DB| / df(t))

где
    tf(t, D)   — частота термина t в документе D;
    tf_max(D)  — максимальная частота термина в документе D (нормировка,
                 уравнивающая документы разной длины);
    df(t)      — количество документов коллекции, содержащих термин t;
    |DB|       — количество документов коллекции.

Множитель 0.5 * (1 + x) сжимает нормированную частоту в диапазон [0.5, 1.0],
а логарифм обнуляет вес слов, встречающихся во всех документах коллекции.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class TermWeight:
    """Вес одного термина документа со всеми составляющими."""

    term: str            # основа слова
    form: str            # наиболее частая словоформа (для показа пользователю)
    tf: int              # tf(t, D)
    tf_norm: float       # tf(t, D) / tf_max(D)
    df: int              # df(t)
    idf: float           # log(|DB| / df(t))
    weight: float        # w(t, D)

    def as_dict(self) -> dict:
        return {
            "term": self.term, "form": self.form, "tf": self.tf,
            "tf_norm": round(self.tf_norm, 4), "df": self.df,
            "idf": round(self.idf, 4), "weight": round(self.weight, 4),
        }


def term_weight(tf: int, tf_max: int, df: int, db_size: int) -> float:
    """Вычисляет w(t, D) по формуле методических указаний."""
    if tf <= 0 or tf_max <= 0 or df <= 0 or db_size <= 0:
        return 0.0
    idf = math.log(db_size / df)
    if idf <= 0.0:                       # термин есть во всех документах
        return 0.0
    return 0.5 * (1.0 + tf / tf_max) * idf


def compute_term_weights(document, collection, *, extra_docs: int = 0,
                         extra_df: int = 0) -> dict[str, TermWeight]:
    """Считает веса всех терминов документа.

    ``extra_docs``/``extra_df`` учитывают документ пользователя, который
    не входит в постоянную коллекцию, но должен участвовать в |DB| и df(t).
    """
    db_size = collection.size + extra_docs
    weights: dict[str, TermWeight] = {}
    tf_max = document.tf_max
    for term, tf in document.tf.items():
        df = collection.df.get(term, 0) + extra_df
        df = min(df, db_size) or 1
        idf = math.log(db_size / df) if db_size > 0 else 0.0
        w = 0.0 if idf <= 0 else 0.5 * (1.0 + tf / tf_max) * idf
        weights[term] = TermWeight(
            term=term,
            form=document.most_frequent_form(term),
            tf=tf,
            tf_norm=tf / tf_max if tf_max else 0.0,
            df=df,
            idf=idf,
            weight=w,
        )
    return weights


def top_keywords(weights: dict[str, TermWeight], count: int) -> list[TermWeight]:
    """Реферат в виде списка ключевых слов: ``count`` самых весомых терминов."""
    ordered = sorted(weights.values(), key=lambda w: (-w.weight, -w.tf, w.term))
    return [w for w in ordered if w.weight > 0][:count]
