"""FastAPI-приложение: распознавание языка текста (вариант 1: русский/английский, HTML)."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from . import voice as voice_mod
from .config import LANGUAGE_NAMES, LANGUAGES, NGRAM_MAX_N, NGRAM_PROFILE_SIZE
from .corpus import Collection, load_training_corpus
from .evaluation import Engine
from .methods import AlphabetDetector, NeuralDetector, NGramDetector
from .preprocessing import html_to_text
from .reports import to_csv, to_html
from .schemas import DetectRequest

log = logging.getLogger("langdetect")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

state: dict = {}

METHOD_INFO = {
    "ngram": {
        "title": "N-грамм",
        "short": "Сравнение профилей самых частых N-грамм (Cavnar–Trenkle, 1994).",
        "description": (
            f"Из каждого слова извлекаются подстроки длиной 1–{NGRAM_MAX_N} символов. Для каждого языка по "
            f"тренировочному корпусу строится профиль — {NGRAM_PROFILE_SIZE} самых частых N-грамм, упорядоченных по "
            "убыванию частоты. Для входного документа строится такой же профиль. Расстояние out-of-place — сумма "
            "разностей позиций каждой N-граммы документа в двух профилях; отсутствующая N-грамма получает "
            f"максимальный штраф {NGRAM_PROFILE_SIZE}. Язык с минимальным расстоянием — ответ."),
        "metric": "Расстояние out-of-place (меньше — лучше)",
    },
    "alphabet": {
        "title": "Алфавитный",
        "short": "Доля букв кириллицы и латиницы плюс сходство частот букв с эталоном языка.",
        "description": (
            "Считается, какая доля букв текста принадлежит алфавиту каждого языка (кириллица для русского, латиница "
            "для английского). Дополнительно распределение частот букв текста сравнивается косинусной мерой с "
            "распределением, вычисленным по тренировочному корпусу. Итоговая оценка = 0.7·доля + 0.3·сходство. "
            "Метод очень быстрый, но беспомощен для языков с общим алфавитом и текстов в транслите."),
        "metric": "Оценка принадлежности 0–1 (больше — лучше)",
    },
    "neural": {
        "title": "Нейросетевой",
        "short": "Многослойный перцептрон на hashing-признаках символьных 1–3-грамм.",
        "description": (
            "Текст превращается в вектор из 4096 признаков: каждая символьная 1-, 2- и 3-грамма хэшируется в одну "
            "из ячеек (feature hashing), вектор нормируется. Перцептрон 4096→128→2 (ReLU, dropout) обучается на "
            "случайных фрагментах тренировочного корпуса длиной 40–600 символов (Adam, 12 эпох). Выход softmax "
            "трактуется как вероятность языка. Обученные веса кэшируются и переобучаются при смене корпуса."),
        "metric": "Вероятность softmax (больше — лучше)",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    corpus, stats = load_training_corpus()
    for lang in LANGUAGES:
        log.info("корпус %s: %d файлов, %.1f КБ, %d слов", lang, stats[lang]["files"],
                 stats[lang]["bytes"] / 1024, stats[lang]["words"])
    detectors = [NGramDetector(), AlphabetDetector(), NeuralDetector()]
    fit_times = {}
    for d in detectors:
        t = time.perf_counter()
        d.fit(corpus)
        fit_times[d.id] = round((time.perf_counter() - t) * 1000, 1)
        log.info("обучен метод %-9s за %.0f мс", d.id, fit_times[d.id])
    state.update(engine=Engine(detectors), collection=Collection(), corpus_stats=stats,
                 fit_times=fit_times, started=time.time(),
                 neural_info=next(d for d in detectors if d.id == "neural").train_info)
    log.info("готово за %.1f с", time.perf_counter() - t0)
    yield
    state.clear()


app = FastAPI(title="Распознавание языка текста — ЛР2, вариант 1", version="1.0.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def engine() -> Engine:
    return state["engine"]


def collection() -> Collection:
    return state["collection"]


# ---------------- служебное ----------------
@app.get("/api/health")
def health():
    return {"status": "ok", "ready": "engine" in state}


@app.get("/api/info")
def info():
    info = {k: v for k, v in state["neural_info"].items() if k != "history"}
    return {"languages": [{"code": l, "name": LANGUAGE_NAMES[l]} for l in LANGUAGES],
            "methods": [{"id": k, **v} for k, v in METHOD_INFO.items()],
            "corpus": state["corpus_stats"], "fit_times_ms": state["fit_times"],
            "neural": info, "neural_history": state["neural_info"].get("history", []),
            "voice_available": bool(voice_mod.GROQ_API_KEY)}


# ---------------- распознавание ----------------
@app.post("/api/detect")
def detect(req: DetectRequest):
    text = html_to_text(req.text) if req.is_html or _looks_like_html(req.text) else req.text
    if not text.strip():
        raise HTTPException(400, "После очистки текст пуст — нечего распознавать")
    result = engine().detect(text)
    result["text_preview"] = text[:600]
    return result


@app.post("/api/detect/file")
async def detect_file(file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Файл пуст")
    text = html_to_text(raw) if _is_html_file(file.filename, raw) else raw.decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(400, "В файле не найден текст")
    result = engine().detect(text)
    result["text_preview"] = text[:600]
    result["filename"] = file.filename
    return result


# ---------------- коллекция ----------------
@app.get("/api/collection")
def list_collection():
    docs = collection().list()
    return {"count": len(docs), "documents": [
        {"id": d.id, "title": d.title, "lang": d.lang, "source": d.source, "chars": d.chars,
         "origin": d.origin, "group": d.group, "note": d.note, "url": f"/api/documents/{d.id}"} for d in docs]}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    doc = collection().get(doc_id)
    if not doc or not doc.path.exists():
        raise HTTPException(404, "Документ не найден")
    return FileResponse(doc.path, media_type="text/html; charset=utf-8")


@app.post("/api/collection/upload")
async def upload_document(file: UploadFile = File(...), lang: str = Form(...)):
    if lang not in LANGUAGES:
        raise HTTPException(400, f"Язык должен быть одним из: {', '.join(LANGUAGES)}")
    raw = await file.read()
    if not raw or not _is_html_file(file.filename, raw):
        raise HTTPException(400, "Ожидается непустой HTML-файл (.html/.htm)")
    doc = collection().add_upload(file.filename or "document.html", raw, lang)
    return {"id": doc.id, "title": doc.title, "lang": doc.lang, "chars": doc.chars,
            "origin": doc.origin, "url": f"/api/documents/{doc.id}", "source": doc.source}


@app.delete("/api/collection/{doc_id}")
def delete_document(doc_id: str):
    if not collection().remove_upload(doc_id):
        raise HTTPException(404, "Удалять можно только загруженные документы")
    return {"deleted": doc_id}


@app.post("/api/collection/evaluate")
def evaluate():
    result = engine().evaluate(collection())
    state["last_evaluation"] = result
    return result


@app.get("/api/collection/report")
def report(format: str = Query("json", pattern="^(json|csv|html)$")):
    evaluation = state.get("last_evaluation") or engine().evaluate(collection())
    state["last_evaluation"] = evaluation
    stamp = time.strftime("%Y%m%d-%H%M")
    if format == "csv":
        return Response(to_csv(evaluation), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="langdetect-{stamp}.csv"'})
    if format == "html":
        return HTMLResponse(to_html(evaluation, state["corpus_stats"]))
    return JSONResponse(evaluation, headers={"Content-Disposition": f'attachment; filename="langdetect-{stamp}.json"'})


# ---------------- кривая обучения ----------------
@app.get("/api/learning-curve")
def learning_curve(lengths: str = Query("5,10,20,40,80,160,320,640,1280"),
                   samples: int = Query(6, ge=1, le=30)):
    try:
        ls = sorted({int(x) for x in lengths.split(",") if x.strip()})
    except ValueError:
        raise HTTPException(400, "lengths — список целых через запятую")
    if not ls or len(ls) > 20 or max(ls) > 10000:
        raise HTTPException(400, "Допустимо до 20 длин, каждая ≤ 10000")
    return engine().learning_curve(collection(), ls, samples)


# ---------------- голос ----------------
@app.post("/api/voice")
async def voice(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        tr = await voice_mod.transcribe(raw, file.filename or "audio.webm", file.content_type or "")
    except voice_mod.VoiceError as exc:
        raise HTTPException(400, str(exc))
    if not any(ch.isalpha() for ch in tr["text"]):
        raise HTTPException(400, "Речь не распознана — попробуйте говорить громче и ближе к микрофону")
    result = engine().detect(tr["text"])
    result.update(transcript=tr["text"], whisper_language=tr["whisper_language"],
                  duration=tr["duration"])
    return result


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _is_html_file(filename: str | None, raw: bytes) -> bool:
    name = (filename or "").lower()
    return name.endswith((".html", ".htm")) or _looks_like_html(raw[:400].decode("utf-8", errors="ignore"))
