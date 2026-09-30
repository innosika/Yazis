"""Шаги 2–3: распознавание и сравнение методов; сводная статистика; кривая обучения."""
from __future__ import annotations

import random
import time
from dataclasses import asdict
from typing import Any

from .config import LANGUAGES
from .corpus import Collection, Document
from .methods import Detection, LanguageDetector
from .preprocessing import normalize


class Engine:
    def __init__(self, detectors: list[LanguageDetector]) -> None:
        self.detectors = detectors

    def detect(self, text: str) -> dict[str, Any]:
        norm = normalize(text)
        results = [asdict(d.predict(norm)) for d in self.detectors]
        votes = {}
        for r in results:
            votes[r["lang"]] = votes.get(r["lang"], 0) + 1
        consensus = max(votes, key=votes.get) if votes else None
        return {
            "text_chars": len(text), "normalized_chars": len(norm), "words": len(norm.split()),
            "results": results, "consensus": consensus, "agree": len(votes) == 1,
        }

    def evaluate(self, collection: Collection) -> dict[str, Any]:
        rows = []
        per_method: dict[str, dict[str, Any]] = {
            d.id: {"correct": 0, "total": 0, "time_ms": 0.0,
                   "confusion": {t: {p: 0 for p in LANGUAGES} for t in LANGUAGES}}
            for d in self.detectors
        }
        t_start = time.perf_counter()
        for doc in collection.list():
            text = collection.read_text(doc)
            norm = normalize(text)
            row = {"id": doc.id, "title": doc.title, "true_lang": doc.lang, "chars": len(text),
                   "source": doc.source, "origin": doc.origin, "url": f"/api/documents/{doc.id}",
                   "group": doc.group, "note": doc.note, "predictions": {}}
            for d in self.detectors:
                det = d.predict(norm)
                m = per_method[d.id]
                m["total"] += 1
                m["time_ms"] += det.elapsed_ms
                m["correct"] += int(det.lang == doc.lang)
                g = m.setdefault("groups", {}).setdefault(doc.group, {"correct": 0, "total": 0})
                g["total"] += 1; g["correct"] += int(det.lang == doc.lang)
                if doc.lang in m["confusion"]:
                    m["confusion"][doc.lang][det.lang] += 1
                row["predictions"][d.id] = {"lang": det.lang, "correct": det.lang == doc.lang,
                                            "confidence": det.confidence, "elapsed_ms": det.elapsed_ms,
                                            "scores": det.scores}
            rows.append(row)
        summary = {}
        for d in self.detectors:
            m = per_method[d.id]
            n = m["total"] or 1
            summary[d.id] = {
                "title": d.title, "accuracy": round(m["correct"] / n, 4), "correct": m["correct"],
                "total": m["total"], "errors": m["total"] - m["correct"],
                "avg_time_ms": round(m["time_ms"] / n, 3), "total_time_ms": round(m["time_ms"], 2),
                "confusion": m["confusion"],
                "groups": {gname: {"accuracy": round(g["correct"] / (g["total"] or 1), 4),
                                   "correct": g["correct"], "total": g["total"]}
                           for gname, g in m.get("groups", {}).items()},
            }
        return {"documents": rows, "summary": summary, "count": len(rows),
                "total_elapsed_ms": round((time.perf_counter() - t_start) * 1000, 1),
                "languages": list(LANGUAGES)}

    def learning_curve(self, collection: Collection, lengths: list[int], samples: int = 8,
                       seed: int = 7) -> dict[str, Any]:
        """Точность каждого метода на случайных фрагментах длиной L символов."""
        rng = random.Random(seed)
        docs = [(doc, normalize(collection.read_text(doc))) for doc in collection.list()]
        points = []
        for L in lengths:
            stats = {d.id: {"correct": 0, "total": 0, "time_ms": 0.0} for d in self.detectors}
            for doc, norm in docs:
                if len(norm) < 5:
                    continue
                for _ in range(samples):
                    frag = _fragment(norm, L, rng)
                    for d in self.detectors:
                        det = d.predict(frag)
                        s = stats[d.id]
                        s["total"] += 1; s["time_ms"] += det.elapsed_ms
                        s["correct"] += int(det.lang == doc.lang)
            points.append({"length": L, **{
                d.id: {"accuracy": round(s["correct"] / (s["total"] or 1), 4),
                       "avg_time_ms": round(s["time_ms"] / (s["total"] or 1), 3),
                       "total": s["total"]}
                for d in self.detectors for s in [stats[d.id]]
            }})
        min_len = {}
        for d in self.detectors:
            reached = [p["length"] for p in points if p[d.id]["accuracy"] >= 0.95]
            min_len[d.id] = reached[0] if reached else None
        return {"lengths": lengths, "samples_per_doc": samples, "documents": len(docs),
                "points": points, "min_length_95": min_len,
                "methods": {d.id: d.title for d in self.detectors}}


def _fragment(text: str, length: int, rng: random.Random) -> str:
    if len(text) <= length:
        return text
    start = rng.randint(0, len(text) - length)
    return text[start:start + length]
