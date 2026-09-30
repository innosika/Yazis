# -*- coding: utf-8 -*-
"""Сохранение результатов реферирования в файлы разных форматов.

Поддерживаются:
  * .txt  — простой текстовый отчёт;
  * .html — оформленный отчёт, пригодный для печати из браузера;
  * .json — полный машинночитаемый результат (все веса и метрики);
  * .csv  — таблица весов предложений для анализа в Excel;
  * .scs  — фрагмент семантической сети в SC-коде (OSTIS).
"""
from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime

from .analysis import METHOD_TITLES, Analysis
from .scs import to_scs

FORMATS = ("txt", "html", "json", "csv", "scs")


def _header(analysis: Analysis) -> list[str]:
    doc = analysis.document
    return [
        "СИСТЕМА АВТОМАТИЧЕСКОГО РЕФЕРИРОВАНИЯ ДОКУМЕНТОВ",
        "Метод: sentence extraction + OSTIS (вариант 1)",
        "=" * 78,
        f"Документ:           {doc.title}",
        f"Источник:           {doc.source or '—'}",
        f"Язык:               {'русский' if doc.language == 'ru' else 'английский'}",
        f"Предметная область: {doc.domain or '—'}",
        f"Объём:              {doc.length} символов, {doc.total_words} слов, "
        f"{len(doc.paragraphs)} абзацев, {len(doc.sentences)} предложений",
        f"Коллекция:          |DB| = {analysis.db_size} документов",
        f"Метод отбора:       {METHOD_TITLES.get(analysis.params.method)}",
        f"Дата:               {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 78,
    ]


def to_text(analysis: Analysis) -> str:
    """Текстовый отчёт."""
    doc = analysis.document
    quality = analysis.quality()
    by_index = {s.index: s for s in analysis.sentences}
    lines = _header(analysis)

    alpha, beta = analysis.params.alpha, analysis.params.beta
    pd_label = "Posd" if alpha == 1 else f"Posd^{alpha:g}"
    pp_label = "Posp" if beta == 1 else f"Posp^{beta:g}"

    lines += ["", "РАЗДЕЛ 1. КЛАССИЧЕСКИЙ РЕФЕРАТ", "-" * 78]
    for order, index in enumerate(analysis.primary.indices, start=1):
        sentence = by_index[index]
        lines.append(f"{order:2d}. {sentence.text}")
        lines.append(f"    [предложение №{index + 1}; W={sentence.weight:.3f} = "
                     f"{pd_label} {sentence.posd ** alpha:.3f} × "
                     f"{pp_label} {sentence.posp ** beta:.3f} × "
                     f"Score {sentence.score:.3f}]")

    lines += ["", "РАЗДЕЛ 2. РЕФЕРАТ В ВИДЕ СПИСКА КЛЮЧЕВЫХ СЛОВ", "-" * 78]
    for order, keyword in enumerate(analysis.keywords, start=1):
        lines.append(f"{order:2d}. {keyword.form:<28s} w={keyword.weight:.4f}  "
                     f"tf={keyword.tf:<4d} df={keyword.df}  основа: {keyword.term}")

    lines += ["", "ПОКАЗАТЕЛИ", "-" * 78,
              f"Степень сжатия:                {quality['compression'] * 100:.1f}% "
              f"({quality['summary_chars']} из {doc.length} символов)",
              f"Покрытие ключевых слов:        {quality['keyword_coverage'] * 100:.1f}%",
              f"Среднее положение предложений: "
              f"{quality['position_bias']['mean_relative_position'] * 100:.1f}% длины документа",
              f"Время обработки:               {analysis.timings['total_ms']:.2f} мс"]
    return "\n".join(lines) + "\n"


def to_html(analysis: Analysis) -> str:
    """Оформленный отчёт для просмотра и печати."""
    doc = analysis.document
    quality = analysis.quality()
    by_index = {s.index: s for s in analysis.sentences}
    esc = html.escape

    rows = "\n".join(
        f"<tr><td>{order}</td><td class='txt'>{esc(by_index[i].text)}</td>"
        f"<td>{by_index[i].posd:.3f}</td><td>{by_index[i].posp:.3f}</td>"
        f"<td>{by_index[i].score:.2f}</td><td><b>{by_index[i].weight:.2f}</b></td></tr>"
        for order, i in enumerate(analysis.primary.indices, start=1))

    keywords = "\n".join(
        f"<tr><td>{order}</td><td><b>{esc(k.form)}</b></td><td>{esc(k.term)}</td>"
        f"<td>{k.tf}</td><td>{k.df}</td><td>{k.idf:.3f}</td><td>{k.weight:.4f}</td></tr>"
        for order, k in enumerate(analysis.keywords, start=1))

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<title>Реферат — {esc(doc.title)}</title>
<style>
 body {{ font: 15px/1.6 "PT Serif", Georgia, serif; max-width: 900px; margin: 2rem auto;
        padding: 0 1.5rem; color: #1a1a1a; }}
 h1 {{ font-size: 1.6rem; }} h2 {{ font-size: 1.2rem; margin-top: 2rem;
        border-bottom: 2px solid #3d5a80; padding-bottom: .3rem; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 13px; font-family: system-ui, sans-serif; }}
 th, td {{ border: 1px solid #ccd; padding: .4rem .5rem; text-align: right; vertical-align: top; }}
 th {{ background: #eef2f7; }} td.txt {{ text-align: left; }}
 .meta {{ background: #f6f8fb; padding: 1rem; border-left: 4px solid #3d5a80; font-size: 13px;
          font-family: system-ui, sans-serif; }}
 .summary p {{ text-align: justify; }}
 .kw span {{ display: inline-block; background: #e8eef7; border: 1px solid #c3d0e4;
             border-radius: 4px; padding: .2rem .5rem; margin: .15rem; font-family: system-ui, sans-serif; }}
 @media print {{ body {{ margin: 0; max-width: none; }} h2 {{ page-break-after: avoid; }} }}
</style></head><body>
<h1>Реферат документа «{esc(doc.title)}»</h1>
<div class="meta">
 <div><b>Источник:</b> <a href="{esc(doc.source)}">{esc(doc.source or '—')}</a></div>
 <div><b>Язык:</b> {'русский' if doc.language == 'ru' else 'английский'};
      <b>предметная область:</b> {esc(doc.domain or '—')}</div>
 <div><b>Объём:</b> {doc.length} символов, {len(doc.paragraphs)} абзацев,
      {len(doc.sentences)} предложений; <b>|DB|</b> = {analysis.db_size}</div>
 <div><b>Метод:</b> {esc(METHOD_TITLES.get(analysis.params.method, ''))}</div>
 <div><b>Сжатие:</b> {quality['compression'] * 100:.1f}%;
      <b>покрытие ключевых слов:</b> {quality['keyword_coverage'] * 100:.1f}%;
      <b>время:</b> {analysis.timings['total_ms']:.1f} мс</div>
</div>
<h2>1. Классический реферат</h2>
<div class="summary"><p>{esc(analysis.primary.text)}</p></div>
<table><tr><th>№</th><th>Предложение</th><th>Posd</th><th>Posp</th><th>Score</th><th>W</th></tr>
{rows}</table>
<h2>2. Реферат в виде списка ключевых слов</h2>
<div class="kw">{''.join(f'<span>{esc(k.form)}</span>' for k in analysis.keywords)}</div>
<table><tr><th>№</th><th>Словоформа</th><th>Основа</th><th>tf</th><th>df</th><th>IDF</th><th>w(t,D)</th></tr>
{keywords}</table>
<p style="font-size:12px;color:#666;margin-top:2rem">Сформировано системой автоматического
реферирования (sentence extraction + OSTIS), {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body></html>"""


def to_json(analysis: Analysis) -> str:
    data = analysis.as_dict()
    data["scs"] = to_scs(analysis)
    return json.dumps(data, ensure_ascii=False, indent=2)


def to_csv(analysis: Analysis) -> str:
    """Таблица весов всех предложений документа."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["index", "paragraph", "BD(Si)", "BP(Si)", "|P|", "Posd", "Posp",
                     "Score", "W(Si)", "selected", "text"])
    chosen = set(analysis.primary.indices)
    doc_sentences = {s.index: s for s in analysis.document.sentences}
    for s in analysis.sentences:
        raw = doc_sentences[s.index]
        writer.writerow([s.index, s.paragraph, raw.start, raw.para_start, raw.para_len,
                         f"{s.posd:.4f}", f"{s.posp:.4f}", f"{s.score:.4f}",
                         f"{s.weight:.4f}", int(s.index in chosen), s.text])
    return buffer.getvalue()


def render(analysis: Analysis, fmt: str) -> tuple[str, str]:
    """Возвращает (содержимое, MIME-тип) для указанного формата."""
    if fmt == "txt":
        return to_text(analysis), "text/plain; charset=utf-8"
    if fmt == "html":
        return to_html(analysis), "text/html; charset=utf-8"
    if fmt == "json":
        return to_json(analysis), "application/json; charset=utf-8"
    if fmt == "csv":
        return to_csv(analysis), "text/csv; charset=utf-8"
    if fmt == "scs":
        return to_scs(analysis), "text/plain; charset=utf-8"
    raise ValueError(f"неизвестный формат: {fmt}")
