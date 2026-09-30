# -*- coding: utf-8 -*-
"""Формирование тестовой коллекции документов из Wikipedia.

Вариант 1: языки — русский и английский; предметные области —
научные статьи по computer science и сочинения (эссе) по литературе.

Скрипт скачивает статьи через MediaWiki API (action=query&prop=extracts),
очищает их от служебной разметки и сохраняет в data/collection/*.txt,
приводя все документы к сопоставимому объёму (~10 страниц формата А4).

Запуск:  python3 tools/fetch_collection.py
"""
from __future__ import annotations

import json
import os
import time
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "collection")

# ~10 страниц А4 машинописного текста
TARGET_CHARS = 22000
MIN_CHARS = 9000

USER_AGENT = "YAZIS-lab3-summarizer/1.0 (educational project; BSUIR)"

# (идентификатор файла, язык, предметная область, заголовок статьи в Wikipedia)
SOURCES = [
    ("ru_cs_ai",                 "ru", "computer science", "Искусственный интеллект"),
    ("ru_cs_neural_network",     "ru", "computer science", "Искусственная нейронная сеть"),
    ("ru_cs_cryptography",       "ru", "computer science", "Криптография"),
    ("ru_lit_crime_punishment",  "ru", "литература",       "Преступление и наказание"),
    ("ru_lit_war_and_peace",     "ru", "литература",       "Война и мир"),
    ("en_cs_computer_vision",    "en", "computer science", "Computer vision"),
    ("en_cs_operating_system",   "en", "computer science", "Operating system"),
    ("en_cs_database",           "en", "computer science", "Database"),
    ("en_lit_hamlet",            "en", "литература",       "Hamlet"),
    ("en_lit_moby_dick",         "en", "литература",       "Moby-Dick"),
]

# Служебные разделы, не несущие содержательного текста
SKIP_SECTIONS = {
    "см. также", "примечания", "литература", "ссылки", "источники",
    "библиография", "комментарии", "внешние ссылки",
    "see also", "references", "external links", "further reading",
    "bibliography", "notes", "citations", "works cited", "sources",
}

HEADING_RE = re.compile(r"^\s*(=+)\s*(.+?)\s*\1\s*$")


def fetch_extract(lang: str, title: str, attempts: int = 4) -> tuple[str, str]:
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts"
        f"&explaintext=1&redirects=1&format=json&titles="
        + urllib.parse.quote(title)
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as exc:      # 429 Too Many Requests и т.п.
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    page = next(iter(data["query"]["pages"].values()))
    if "extract" not in page:
        raise RuntimeError(f"нет текста для статьи {title!r} ({lang})")
    canonical = page.get("title", title)
    return canonical, page["extract"]


def clean(extract: str) -> str:
    """Убирает заголовки и служебные разделы, оставляя абзацы текста."""
    paragraphs: list[str] = []
    skipping = False
    for raw_line in extract.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = HEADING_RE.match(line)
        if m:
            # Разделы верхнего уровня (==) могут переключить режим пропуска
            if len(m.group(1)) == 2:
                skipping = m.group(2).strip().lower() in SKIP_SECTIONS
            continue
        if skipping:
            continue
        # Отбрасываем обрывки списков и слишком короткие строки без точки
        if len(line) < 40 and not line.endswith((".", "!", "?")):
            continue
        paragraphs.append(line)
    return "\n\n".join(paragraphs)


def trim(text: str, limit: int) -> str:
    """Обрезает текст по границе абзаца, чтобы объёмы документов совпадали."""
    if len(text) <= limit:
        return text
    out: list[str] = []
    total = 0
    for para in text.split("\n\n"):
        if total + len(para) > limit and out:
            break
        out.append(para)
        total += len(para) + 2
    return "\n\n".join(out)


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = []
    for doc_id, lang, domain, title in SOURCES:
        canonical, extract = fetch_extract(lang, title)
        text = trim(clean(extract), TARGET_CHARS)
        if len(text) < MIN_CHARS:
            print(f"  !! {doc_id}: всего {len(text)} символов", file=sys.stderr)
        path = os.path.join(OUT_DIR, doc_id + ".txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        url = f"https://{lang}.wikipedia.org/wiki/" + canonical.replace(" ", "_")
        meta.append({
            "id": doc_id,
            "file": doc_id + ".txt",
            "title": canonical,
            "language": lang,
            "domain": domain,
            "source": url,
            "chars": len(text),
        })
        print(f"{doc_id:28s} {lang}  {len(text):6d} симв.  {canonical}")
        time.sleep(2)   # вежливая пауза между запросами к API

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"collection": "YAZIS lab3, вариант 1", "documents": meta},
                  fh, ensure_ascii=False, indent=2)
    print(f"\nСохранено документов: {len(meta)} -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
