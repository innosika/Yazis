"""Content-addressed audio cache on disk.

The key hashes everything that changes the sound: model, normalizer and lexicon
versions, voice (or blend), speed, pitch and the spoken text. A cached entry is a WAV
file plus a JSON sidecar with the duration and word timings (in spoken-text offsets;
the mapping back to the source is cheap and recomputed per request).

Eviction is least-recently-used by file mtime, run after writes once the cache grows
past its limit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from app.tts.align import TimedSpan

log = logging.getLogger(__name__)


def cache_key(*parts: object) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:40]


@dataclass(slots=True)
class CachedAudio:
    key: str
    duration: float
    words: list[TimedSpan]


class AudioCache:
    def __init__(self, root: Path, limit_mb: int) -> None:
        self.root = root
        self.limit = limit_mb * 1024 * 1024
        self._written = 0
        self._lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: str) -> tuple[Path, Path]:
        d = self.root / key[:2]
        return d / f"{key}.wav", d / f"{key}.json"

    def wav_path(self, key: str) -> Path | None:
        wav, _ = self._paths(key)
        return wav if wav.exists() else None

    def get(self, key: str) -> CachedAudio | None:
        wav, meta = self._paths(key)
        if not (wav.exists() and meta.exists()):
            return None
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            return None
        os.utime(wav)
        words = [TimedSpan(*w) for w in data["words"]]
        return CachedAudio(key, float(data["duration"]), words)

    def put(self, key: str, wav_bytes: bytes, duration: float, words: list[TimedSpan]) -> None:
        wav, meta = self._paths(key)
        wav.parent.mkdir(parents=True, exist_ok=True)
        tmp = wav.with_suffix(".tmp")
        tmp.write_bytes(wav_bytes)
        tmp.replace(wav)
        meta.write_text(
            json.dumps(
                {
                    "duration": round(duration, 4),
                    "words": [
                        [w.spoken_start, w.spoken_end, round(w.start, 4), round(w.end, 4)]
                        for w in words
                    ],
                }
            )
        )
        with self._lock:
            self._written += len(wav_bytes)
            if self._written > 64 * 1024 * 1024:
                self._written = 0
                self._evict()

    def size_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*.wav"))

    def _evict(self) -> None:
        files = sorted(self.root.rglob("*.wav"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        removed = 0
        for wav in files:
            if total <= self.limit:
                break
            total -= wav.stat().st_size
            wav.unlink(missing_ok=True)
            wav.with_suffix(".json").unlink(missing_ok=True)
            removed += 1
        if removed:
            log.info("audio cache: evicted %d files", removed)

    def clear(self) -> int:
        n = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
                n += 1
        return n
