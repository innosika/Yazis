"""Работа с данными: тренировочный корпус и тестовая коллекция документов."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import LANGUAGES, TEST_DIR, TRAIN_DIR, UPLOADS_DIR
from .preprocessing import html_to_text, normalize


@dataclass
class Document:
    id: str
    file: str
    title: str
    lang: str            # истинный язык
    source: str          # URL источника (или "upload")
    chars: int
    origin: str          # "collection" | "upload"
    group: str = "standard"   # "standard" | "hard"
    note: str = ""            # чем документ сложен

    @property
    def path(self) -> Path:
        return (TEST_DIR if self.origin == "collection" else UPLOADS_DIR) / self.file


def load_training_corpus() -> tuple[dict[str, str], dict[str, dict]]:
    """Возвращает {lang: нормализованный текст} и статистику по корпусу."""
    corpus, stats = {}, {}
    for lang in LANGUAGES:
        files = sorted((TRAIN_DIR / lang).glob("*.txt"))
        raw_parts, titles = [], []
        for f in files:
            text = f.read_text(encoding="utf-8")
            first, _, rest = text.partition("\n")
            titles.append(first.lstrip("# ").strip())
            raw_parts.append(rest)
        raw = "\n".join(raw_parts)
        corpus[lang] = normalize(raw)
        stats[lang] = {"files": len(files), "bytes": sum(f.stat().st_size for f in files),
                       "chars": len(raw), "words": len(corpus[lang].split()), "titles": titles}
    return corpus, stats


class Collection:
    """Тестовая коллекция: встроенные документы + загруженные пользователем."""

    def __init__(self) -> None:
        self.docs: dict[str, Document] = {}
        self.reload()

    def reload(self) -> None:
        self.docs.clear()
        manifest = TEST_DIR / "manifest.json"
        if manifest.exists():
            for item in json.loads(manifest.read_text(encoding="utf-8")):
                self.docs[item["id"]] = Document(origin="collection", **item)
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        up_manifest = UPLOADS_DIR / "manifest.json"
        if up_manifest.exists():
            for item in json.loads(up_manifest.read_text(encoding="utf-8")):
                if (UPLOADS_DIR / item["file"]).exists():
                    self.docs[item["id"]] = Document(origin="upload", **item)

    def _save_uploads(self) -> None:
        items = [asdict(d) for d in self.docs.values() if d.origin == "upload"]
        for it in items:
            it.pop("origin")
        (UPLOADS_DIR / "manifest.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list(self) -> list[Document]:
        return sorted(self.docs.values(), key=lambda d: (d.origin != "collection", d.id))

    def get(self, doc_id: str) -> Document | None:
        return self.docs.get(doc_id)

    def read_text(self, doc: Document) -> str:
        return html_to_text(doc.path.read_bytes())

    def add_upload(self, filename: str, content: bytes, lang: str) -> Document:
        doc_id = "up_" + uuid.uuid4().hex[:8]
        safe = re.sub(r"[^\w.\-]+", "_", filename) or "document.html"
        file = f"{doc_id}_{safe}"
        if not file.lower().endswith((".html", ".htm")):
            file += ".html"
        (UPLOADS_DIR / file).write_bytes(content)
        text = html_to_text(content)
        title = _extract_title(content) or filename
        doc = Document(id=doc_id, file=file, title=title, lang=lang, source="upload",
                       chars=len(text), origin="upload")
        self.docs[doc_id] = doc
        self._save_uploads()
        return doc

    def remove_upload(self, doc_id: str) -> bool:
        doc = self.docs.get(doc_id)
        if not doc or doc.origin != "upload":
            return False
        doc.path.unlink(missing_ok=True)
        del self.docs[doc_id]
        self._save_uploads()
        return True


def _extract_title(content: bytes) -> str | None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else None
