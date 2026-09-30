"""Экспорт результатов: CSV и печатная HTML-версия."""
from __future__ import annotations

import csv
import html
import io
from datetime import datetime
from typing import Any

from .config import LANGUAGE_NAMES


def to_csv(evaluation: dict[str, Any]) -> str:
    buf = io.StringIO()
    methods = list(evaluation["summary"].keys())
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "Документ", "Группа", "Истинный язык", "Символов", "Ссылка"]
               + [f"{evaluation['summary'][m]['title']}: язык" for m in methods]
               + [f"{evaluation['summary'][m]['title']}: верно" for m in methods]
               + [f"{evaluation['summary'][m]['title']}: мс" for m in methods])
    for row in evaluation["documents"]:
        p = row["predictions"]
        w.writerow([row["id"], row["title"], LANGUAGE_NAMES.get(row["true_lang"], row["true_lang"]),
                    row["chars"], row["source"]]
                   + [LANGUAGE_NAMES.get(p[m]["lang"], p[m]["lang"]) for m in methods]
                   + ["да" if p[m]["correct"] else "нет" for m in methods]
                   + [p[m]["elapsed_ms"] for m in methods])
    w.writerow([])
    w.writerow(["Метод", "Точность", "Верно", "Всего", "Среднее время, мс", "Точность (обычные)", "Точность (сложные)"])
    for m in methods:
        s = evaluation["summary"][m]
        g = s.get("groups", {})
        w.writerow([s["title"], s["accuracy"], s["correct"], s["total"], s["avg_time_ms"],
                    g.get("standard", {}).get("accuracy", ""), g.get("hard", {}).get("accuracy", "")])
    return "﻿" + buf.getvalue()  # BOM — чтобы Excel открыл UTF-8 корректно


def to_html(evaluation: dict[str, Any], corpus_stats: dict[str, Any] | None = None) -> str:
    methods = list(evaluation["summary"].keys())
    L = LANGUAGE_NAMES
    e = html.escape
    rows = []
    for r in evaluation["documents"]:
        cells = "".join(
            f'<td class="{"ok" if r["predictions"][m]["correct"] else "bad"}">'
            f'{e(L.get(r["predictions"][m]["lang"], ""))}<small>{r["predictions"][m]["elapsed_ms"]:.2f} мс</small></td>'
            for m in methods)
        grp = f'<span title="{e(r.get("note", ""))}">сложный</span>' if r.get("group") == "hard" else "обычный"
        link = f'<a href="{e(r["source"])}">{e(r["title"])}</a>' if r["source"].startswith("http") else e(r["title"])
        rows.append(f'<tr><td>{e(r["id"])}</td><td>{link}</td><td>{grp}</td>'
                    f'<td>{e(L.get(r["true_lang"], ""))}</td><td>{r["chars"]}</td>{cells}</tr>')
    def _g(s, name):
        g = s.get("groups", {}).get(name)
        return f'{g["accuracy"]*100:.1f}% ({g["correct"]}/{g["total"]})' if g else "—"
    summary = "".join(
        f'<tr><td>{e(s["title"])}</td><td>{s["accuracy"]*100:.1f}%</td><td>{s["correct"]}/{s["total"]}</td>'
        f'<td>{_g(s, "standard")}</td><td>{_g(s, "hard")}</td>'
        f'<td>{s["avg_time_ms"]:.3f}</td><td>{s["total_time_ms"]:.1f}</td></tr>'
        for s in evaluation["summary"].values())
    conf = ""
    for m in methods:
        s = evaluation["summary"][m]
        conf += f'<h3>{e(s["title"])}</h3><table class="mini"><tr><th></th>' + "".join(
            f'<th>→ {e(L[p])}</th>' for p in evaluation["languages"]) + "</tr>"
        for t in evaluation["languages"]:
            conf += f'<tr><th>{e(L[t])}</th>' + "".join(
                f'<td>{s["confusion"][t][p]}</td>' for p in evaluation["languages"]) + "</tr>"
        conf += "</table>"
    corpus = ""
    if corpus_stats:
        corpus = "<h2>Тренировочный корпус</h2><table><tr><th>Язык</th><th>Файлов</th><th>Размер, КБ</th><th>Слов</th></tr>" + "".join(
            f'<tr><td>{e(L[l])}</td><td>{c["files"]}</td><td>{c["bytes"]/1024:.1f}</td><td>{c["words"]}</td></tr>'
            for l, c in corpus_stats.items()) + "</table>"
    head_cells = "".join(f'<th>{e(evaluation["summary"][m]["title"])}</th>' for m in methods)
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<title>Отчёт: распознавание языка текста</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1000px;margin:32px auto;color:#1a1a1a;padding:0 16px}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:28px}} h3{{font-size:1rem;margin:14px 0 6px}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}} th,td{{border:1px solid #ddd;padding:6px 8px;text-align:left}}
th{{background:#f4f4f5}} td.ok{{background:#ecfdf3}} td.bad{{background:#fef2f2;font-weight:600}}
td small{{display:block;color:#777;font-size:.75rem}} .mini{{width:auto;margin-bottom:8px}}
.meta{{color:#666;font-size:.85rem}} a{{color:#2563eb}}
@media print{{ body{{margin:0}} a{{color:inherit;text-decoration:none}} }}
</style></head><body>
<h1>Автоматическое распознавание языка текста — отчёт</h1>
<p class="meta">Сформировано {datetime.now():%d.%m.%Y %H:%M}. Документов: {evaluation["count"]}. Языки: русский, английский. Методы: N-грамм, алфавитный, нейросетевой.</p>
<h2>Сводная статистика</h2>
<table><tr><th>Метод</th><th>Точность</th><th>Верно</th><th>Обычные документы</th><th>Сложные документы</th><th>Среднее время, мс</th><th>Суммарное время, мс</th></tr>{summary}</table>
<h2>Матрицы ошибок (строка — истинный язык, столбец — ответ)</h2>{conf}
<h2>Результаты по документам</h2>
<table><tr><th>ID</th><th>Документ</th><th>Группа</th><th>Истинный язык</th><th>Символов</th>{head_cells}</tr>{"".join(rows)}</table>
{corpus}
</body></html>"""
