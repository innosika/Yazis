# -*- coding: utf-8 -*-
"""HTTP-сервер системы автоматического реферирования.

Интерфейс системы выполнен как локальное веб-приложение: серверная часть
на стандартной библиотеке Python (http.server), клиентская — HTML/CSS/JS.
Такое решение не требует установки каких-либо зависимостей и позволяет
пользоваться привычными средствами браузера для печати и сохранения.

Маршруты API:
    GET  /api/collection            — список документов коллекции;
    POST /api/analyze               — реферирование документа или своего текста;
    GET  /api/export                — выгрузка результата (txt|html|json|csv|scs);
    GET  /api/batch                 — пакетная обработка всей коллекции.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summarizer import config, export  # noqa: E402
from summarizer.analysis import METHOD_TITLES, analyze  # noqa: E402
from summarizer.collection import (Collection, Document,  # noqa: E402
                                   delete_document, save_document)
from summarizer.config import SummaryParams  # noqa: E402
from summarizer.metrics import cosine_similarity  # noqa: E402
from summarizer.scs import (build_collection_graph, build_graph, to_scs,  # noqa: E402
                            to_scs_collection)
from summarizer.stats import collection_statistics  # noqa: E402
from summarizer.text import detect_language  # noqa: E402
from summarizer.webfetch import WebFetchError, fetch_url  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}

_lock = threading.Lock()
_state: dict = {"collection": None, "no_conflate": None, "cache": {}}


# ----------------------------------------------------------------------
def get_collection(conflate: bool = True) -> Collection:
    """Возвращает проиндексированную коллекцию (кэшируется на время работы).

    Коллекция индексируется в двух вариантах: со склейкой близких основ
    и без неё, — чтобы пользователь мог сравнить оба режима.
    """
    key = "collection" if conflate else "no_conflate"
    with _lock:
        if _state[key] is None:
            if conflate:
                _state[key] = Collection.load()
            else:
                collection = Collection([])
                loaded = Collection.load()          # чтение файлов и meta.json
                collection.documents = [
                    Document(doc_id=d.doc_id, title=d.title, text=d.text,
                             language=d.language, domain=d.domain,
                             source=d.source, path=d.path)
                    for d in loaded.documents
                ]
                collection.build_index(conflate=False)
                _state[key] = collection
        return _state[key]


def params_from(data: dict) -> SummaryParams:
    params = SummaryParams(
        sentences=int(data.get("sentences", config.DEFAULT_SUMMARY_SENTENCES)),
        keywords=int(data.get("keywords", config.DEFAULT_KEYWORDS)),
        alpha=float(data.get("alpha", 1.0)),
        beta=float(data.get("beta", 1.0)),
        method=str(data.get("method", "tfidf")),
        conflate_stems=bool(data.get("conflate_stems", True)),
        mmr_lambda=float(data.get("mmr_lambda", 1.0)),
        length_norm=str(data.get("length_norm", "none")),
    )
    return params.clamp()


def run_analysis(data: dict) -> dict:
    """Реферирует документ коллекции либо переданный пользователем текст."""
    params = params_from(data)
    collection = get_collection(params.conflate_stems)

    started = time.perf_counter()
    custom_text = (data.get("text") or "").strip()
    if custom_text:
        language = data.get("language") or detect_language(custom_text)
        document = Document(doc_id="user_document", title=data.get("title") or "Документ пользователя",
                            text=custom_text, language=language,
                            domain=data.get("domain", ""), source=data.get("source", ""))
        collection.add_temporary(document)
        analysis = analyze(document, collection, params, temporary=True)
    else:
        document = collection.get(data.get("doc_id", ""))
        if document is None:
            raise KeyError(data.get("doc_id", ""))
        analysis = analyze(document, collection, params)

    payload = analysis.as_dict()
    payload["text"] = document.text          # нужен интерфейсу для карты весов
    payload["graph"] = build_graph(analysis)
    payload["scs"] = to_scs(analysis)
    payload["timings"]["request_ms"] = round((time.perf_counter() - started) * 1000, 2)
    payload["method_titles"] = METHOD_TITLES
    return payload


def reset_cache() -> None:
    """Сбрасывает кэш коллекции: состав документов изменился."""
    with _lock:
        _state["collection"] = None
        _state["no_conflate"] = None
        _state["cache"].clear()


def statistics() -> dict:
    """Статистика коллекции для одноимённой вкладки интерфейса."""
    started = time.perf_counter()
    data = collection_statistics(get_collection(True))
    data["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return data


def add_document(data: dict) -> dict:
    """Постоянно добавляет документ пользователя в коллекцию."""
    record = save_document(
        text=data.get("text", ""),
        title=data.get("title", ""),
        language=data.get("language", ""),
        domain=data.get("domain", ""),
        source=data.get("source", ""),
    )
    if not record.get("existing"):
        reset_cache()
    return {"document": record, "collection": collection_info()}


def remove_document(data: dict) -> dict:
    """Удаляет из коллекции документ, добавленный пользователем."""
    record = delete_document(str(data.get("id", "")))
    reset_cache()
    return {"removed": record["id"], "collection": collection_info()}


def collection_info() -> dict:
    collection = get_collection(True)
    return {
        "size": collection.size,
        "documents": [
            {"id": d.doc_id, "title": d.title, "language": d.language,
             "domain": d.domain, "source": d.source, "chars": d.length,
             "words": d.total_words, "sentences": len(d.sentences),
             "paragraphs": len(d.paragraphs), "terms": len(d.tf),
             "added_by_user": d.added_by_user}
            for d in collection.documents
        ],
        "stem_map_size": len(getattr(collection, "stem_map", {})),
        "index_time_ms": round(collection.load_time * 1000, 2),
    }


def batch_report(data: dict) -> dict:
    """Пакетная обработка всей коллекции — таблица показателей для отчёта."""
    params = params_from(data)
    collection = get_collection(params.conflate_stems)
    rows = []
    started = time.perf_counter()
    for document in collection.documents:
        analysis = analyze(document, collection, params)
        quality = analysis.quality()
        rows.append({
            "id": document.doc_id,
            "title": document.title,
            "language": document.language,
            "domain": document.domain,
            "chars": document.length,
            "sentences": len(document.sentences),
            "terms": len(document.tf),
            "time_ms": round(analysis.timings["total_ms"], 2),
            "compression": quality["compression"],
            "keyword_coverage": quality["keyword_coverage"],
            "mean_position": quality["position_bias"]["mean_relative_position"],
            "content_top_kept": quality["position_bias"]["content_top_kept"],
            "agreement_textrank": quality["comparisons"]["textrank"]["agreement"],
            "rouge1_textrank": quality["comparisons"]["textrank"]["rouge1"]["f1"],
            "agreement_lead": quality["comparisons"]["lead"]["agreement"],
            "keywords": [k.form for k in analysis.keywords[:5]],
        })
    return {"rows": rows, "total_time_ms": round((time.perf_counter() - started) * 1000, 2),
            "params": {"sentences": params.sentences, "keywords": params.keywords,
                       "method": params.method, "alpha": params.alpha, "beta": params.beta}}


def collection_graph(data: dict) -> dict:
    """Семантическая сеть всей коллекции и матрица близости документов."""
    params = params_from(data)
    per_document = max(3, min(15, int(data.get("keywords_per_document", 8))))
    collection = get_collection(params.conflate_stems)
    started = time.perf_counter()

    analyses = [analyze(document, collection, params) for document in collection.documents]
    vectors = {
        analysis.document.doc_id: {term: weight.weight
                                   for term, weight in analysis.term_weights.items()
                                   if weight.weight > 0}
        for analysis in analyses
    }

    ids = list(vectors)
    titles = {a.document.doc_id: a.document.title for a in analyses}
    matrix = [[round(cosine_similarity(vectors[a], vectors[b]), 4) for b in ids] for a in ids]

    pairs = []
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j <= i:
                continue
            score = matrix[i][j]
            if score >= 0.08:
                pairs.append({"a": a, "b": b, "score": score})
    pairs.sort(key=lambda p: -p["score"])

    return {
        "graph": build_collection_graph(analyses, keywords_per_document=per_document,
                                        similarity=pairs[:12]),
        "scs": to_scs_collection(analyses, keywords_per_document=per_document),
        "similarity": {"ids": ids, "titles": [titles[i] for i in ids], "matrix": matrix},
        "pairs": pairs[:12],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "SummarizerHTTP/1.0"

    # ---------------------------- служебное ----------------------------
    def log_message(self, fmt: str, *args) -> None:       # тише в консоли
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, relative))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        with open(full, "rb") as fh:
            body = fh.read()
        ext = os.path.splitext(full)[1]
        self._send(200, body, MIME.get(ext, "application/octet-stream"))

    # ------------------------------ GET --------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        try:
            if route == "/api/collection":
                self._json(collection_info())
            elif route == "/api/batch":
                self._json(batch_report(query))
            elif route == "/api/collection_graph":
                self._json(collection_graph(query))
            elif route == "/api/stats":
                self._json(statistics())
            elif route == "/api/export":
                self._export(query)
            elif route == "/api/document":
                collection = get_collection(True)
                document = collection.get(query.get("id", ""))
                if document is None:
                    self._json({"error": "документ не найден"}, 404)
                else:
                    self._json({"id": document.doc_id, "title": document.title,
                                "text": document.text})
            elif route.startswith("/api/"):
                self._json({"error": "неизвестный маршрут"}, 404)
            else:
                self._static(route if route != "/" else "index.html")
        except KeyError as exc:
            self._json({"error": f"документ не найден: {exc}"}, 404)
        except Exception as exc:                      # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ------------------------------ POST -------------------------------
    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json({"error": "некорректный JSON"}, 400)
            return
        try:
            if parsed.path == "/api/analyze":
                self._json(run_analysis(data))
            elif parsed.path == "/api/batch":
                self._json(batch_report(data))
            elif parsed.path == "/api/collection_graph":
                self._json(collection_graph(data))
            elif parsed.path == "/api/stats":
                self._json(statistics())
            elif parsed.path == "/api/fetch_url":
                try:
                    self._json(fetch_url(str(data.get("url", ""))))
                except WebFetchError as exc:
                    self._json({"error": str(exc)}, 400)
            elif parsed.path == "/api/collection/add":
                try:
                    self._json(add_document(data))
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
            elif parsed.path == "/api/collection/remove":
                try:
                    self._json(remove_document(data))
                except PermissionError as exc:
                    self._json({"error": str(exc)}, 403)
            elif parsed.path == "/api/export":
                self._export(data)
            else:
                self._json({"error": "неизвестный маршрут"}, 404)
        except KeyError as exc:
            self._json({"error": f"документ не найден: {exc}"}, 404)
        except Exception as exc:                      # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ----------------------------- экспорт ------------------------------
    def _export(self, data: dict) -> None:
        fmt = str(data.get("format", "txt")).lower()
        if fmt not in export.FORMATS:
            self._json({"error": f"неизвестный формат: {fmt}"}, 400)
            return
        params = params_from(data)
        collection = get_collection(params.conflate_stems)

        # SC-код семантической сети всей коллекции, а не одного документа
        if data.get("scope") == "collection":
            if fmt != "scs":
                self._json({"error": "для всей коллекции доступен только формат scs"}, 400)
                return
            analyses = [analyze(document, collection, params)
                        for document in collection.documents]
            body = to_scs_collection(analyses, keywords_per_document=min(params.keywords, 10))
            self._send(200, body.encode("utf-8"), "text/plain; charset=utf-8",
                       {"Content-Disposition": 'attachment; filename="collection.scs"'})
            return

        text = (data.get("text") or "").strip()
        if text:
            document = Document(doc_id="user_document",
                                title=data.get("title") or "Документ пользователя",
                                text=text,
                                language=data.get("language") or detect_language(text))
            collection.add_temporary(document)
            analysis = analyze(document, collection, params, temporary=True)
        else:
            document = collection.get(data.get("doc_id", ""))
            if document is None:
                self._json({"error": "документ не найден"}, 404)
                return
            analysis = analyze(document, collection, params)

        body, mime = export.render(analysis, fmt)
        name = f"{document.doc_id}_abstract.{fmt}"
        self._send(200, body.encode("utf-8"), mime,
                   {"Content-Disposition": f'attachment; filename="{name}"'})


def serve(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
