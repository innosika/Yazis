"""Сборка корпуса из Wikipedia.

train/<lang>/*.txt  — тренировочный набор (цель: 60–100 КБ на язык, в пределах 20–120 КБ по методичке)
test/*.html         — тестовая коллекция: HTML-документы объёмом ~1 страница A4 (≈3500 символов)
test/manifest.json  — истинный язык, заголовок, источник каждого документа

Запуск: python scripts/build_corpus.py  (переменная DATA_DIR задаёт папку data)
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
TRAIN_TARGET_BYTES = 90_000     # ≈90 КБ на язык
TEST_CHARS = 3500               # ≈ одна страница A4
UA = "LangDetectLab/1.0 (university lab work; contact: student)"

TRAIN_TITLES = {
    "ru": [
        "Россия", "Москва", "Санкт-Петербург", "Русский язык", "Пушкин, Александр Сергеевич",
        "Толстой, Лев Николаевич", "Достоевский, Фёдор Михайлович", "Байкал", "Волга", "Сибирь",
        "Математика", "Физика", "Химия", "Биология", "История", "Философия", "Музыка", "Живопись",
        "Архитектура", "Космонавтика", "Гагарин, Юрий Алексеевич", "Менделеев, Дмитрий Иванович",
        "Компьютер", "Интернет", "Программирование", "Искусственный интеллект", "Экономика",
        "Медицина", "Футбол", "Шахматы", "Кино", "Театр", "Литература", "Солнечная система",
        "Земля", "Луна", "Океан", "Климат", "Лес", "Железная дорога",
    ],
    "en": [
        "United Kingdom", "London", "New York City", "English language", "William Shakespeare",
        "Charles Dickens", "Jane Austen", "Grand Canyon", "Mississippi River", "Australia",
        "Mathematics", "Physics", "Chemistry", "Biology", "History", "Philosophy", "Music", "Painting",
        "Architecture", "Spaceflight", "Neil Armstrong", "Isaac Newton",
        "Computer", "Internet", "Computer programming", "Artificial intelligence", "Economics",
        "Medicine", "Association football", "Chess", "Film", "Theatre", "Literature", "Solar System",
        "Earth", "Moon", "Ocean", "Climate", "Forest", "Rail transport",
    ],
}

TEST_TITLES = {
    "ru": [
        "Кофе", "Велосипед", "Фотография", "Древний Рим", "Антарктида", "Париж", "Джаз",
        "Дельфины", "Вулкан", "Олимпийские игры", "Пирамида Хеопса", "Шоколад", "Балет",
        "Молекула", "Электричество",
    ],
    "en": [
        "Coffee", "Bicycle", "Photography", "Ancient Rome", "Antarctica", "Paris", "Jazz",
        "Dolphin", "Volcano", "Olympic Games", "Great Pyramid of Giza", "Chocolate", "Ballet",
        "Molecule", "Electricity",
    ],
}


def fetch_extract(lang: str, title: str) -> tuple[str, str] | None:
    """Возвращает (нормализованный заголовок, plain-text статьи) или None."""
    params = {
        "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
        "redirects": 1, "titles": title, "format": "json", "formatversion": 2,
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            time.sleep(1.0)  # вежливая пауза между запросами к Wikipedia
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            page = data["query"]["pages"][0]
            text = page.get("extract", "")
            if len(text) < 2000:
                return None
            return page["title"], text
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {lang}:{title} — {exc} (попытка {attempt + 1})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))  # экспоненциальное ожидание при 429
    return None


def slugify(title: str, idx: int, lang: str) -> str:
    return f"{lang}_{idx:02d}"


def build_train(lang: str) -> None:
    out_dir = DATA_DIR / "train" / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.txt"):
        f.unlink()
    total = 0
    for i, title in enumerate(TRAIN_TITLES[lang]):
        if total >= TRAIN_TARGET_BYTES:
            break
        got = fetch_extract(lang, title)
        if not got:
            continue
        real_title, text = got
        text = text[:6000]  # берём не более 6000 символов из статьи — больше разнообразия тем
        path = out_dir / f"{slugify(real_title, i, lang)}.txt"
        path.write_text(f"# {real_title}\n{text}\n", encoding="utf-8")
        total += len(text.encode("utf-8"))
        print(f"  train {lang}: {real_title!r:45} → {total/1024:6.1f} КБ")
    print(f"train/{lang}: итого {total/1024:.1f} КБ")


def make_html(title: str, lang: str, text: str, source: str) -> str:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    body = "\n".join(f"    <p>{html.escape(p)}</p>" for p in paragraphs)
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 720px; margin: 40px auto; line-height: 1.55; color: #222; }}
  h1 {{ font-size: 1.6rem; }} .src {{ color: #777; font-size: .85rem; }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p class="src">Источник / Source: <a href="{source}">{source}</a></p>
{body}
</body>
</html>
"""


def build_test() -> None:
    out_dir = DATA_DIR / "test"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.html"):
        f.unlink()
    manifest = []
    for lang in ("ru", "en"):
        for i, title in enumerate(TEST_TITLES[lang]):
            got = fetch_extract(lang, title)
            if not got:
                continue
            real_title, text = got
            # обрезаем по границе абзаца до ~TEST_CHARS символов
            cut, acc = [], 0
            for p in text.split("\n"):
                if acc + len(p) > TEST_CHARS and acc > 0:
                    break
                cut.append(p)
                acc += len(p) + 1
            text = "\n".join(cut)
            doc_id = f"{lang}_{i + 1:02d}"
            source = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(real_title.replace(" ", "_"))
            (out_dir / f"{doc_id}.html").write_text(make_html(real_title, lang, text, source), encoding="utf-8")
            manifest.append({"id": doc_id, "file": f"{doc_id}.html", "title": real_title,
                             "lang": lang, "source": source, "chars": len(text)})
            print(f"  test {doc_id}: {real_title!r:40} {len(text)} симв.")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"test: {len(manifest)} документов")


if __name__ == "__main__":
    print(f"DATA_DIR = {DATA_DIR}")
    what = sys.argv[1] if len(sys.argv) > 1 else "all"   # all | train | test
    if what in ("all", "train"):
        for lang in ("ru", "en"):
            build_train(lang)
    if what in ("all", "test"):
        build_test()
