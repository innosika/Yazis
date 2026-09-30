"""Нейросетевой метод.

Признаки: hashing-вектор символьных 1–3-грамм (4096 измерений, нормировка по частоте) —
классический приём (feature hashing), не требующий словаря.
Модель: многослойный перцептрон  4096 → 128 (ReLU, Dropout 0.2) → 2, softmax.
Обучение: тренировочный корпус нарезается на случайные фрагменты длиной 40–600 символов,
чтобы сеть уверенно работала и на коротких текстах. Оптимизатор Adam, ~12 эпох, CPU.
Веса кэшируются в data/models/mlp.pt; при изменении корпуса (хэш) сеть переобучается.
"""
from __future__ import annotations

import hashlib
import json
import random
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from ..config import (LANGUAGES, MODELS_DIR, NN_CHUNK_MAX, NN_CHUNK_MIN, NN_EPOCHS, NN_FEATURES,
                      NN_HIDDEN, NN_SEED)
from .base import LanguageDetector

torch.set_num_threads(max(1, min(4, torch.get_num_threads())))


def featurize(text: str, dim: int = NN_FEATURES) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    padded = f" {text} "
    L = len(padded)
    n_feats = 0
    for n in (1, 2, 3):
        for i in range(L - n + 1):
            gram = padded[i:i + n]
            if gram.isspace():
                continue
            h = zlib.crc32(gram.encode("utf-8")) % dim
            vec[h] += 1.0
            n_feats += 1
    if n_feats:
        vec /= n_feats
        vec *= 50.0  # масштаб, чтобы значения были порядка 0.1–1
    return vec


class MLP(nn.Module):
    def __init__(self, n_in: int = NN_FEATURES, n_hidden: int = NN_HIDDEN, n_out: int = len(LANGUAGES)):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, n_hidden), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(n_hidden, n_out),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def make_chunks(text: str, rng: random.Random, n_chunks: int) -> list[str]:
    chunks = []
    for _ in range(n_chunks):
        length = rng.randint(NN_CHUNK_MIN, NN_CHUNK_MAX)
        if len(text) <= length:
            chunks.append(text)
            continue
        start = rng.randint(0, len(text) - length)
        chunk = text[start:start + length]
        # выравниваем по границам слов
        a, b = chunk.find(" "), chunk.rfind(" ")
        if 0 <= a < b:
            chunk = chunk[a + 1:b]
        chunks.append(chunk)
    return chunks


class NeuralDetector(LanguageDetector):
    id = "neural"
    title = "Нейросетевой"
    metric_name = "вероятность (softmax)"
    lower_is_better = False

    def __init__(self, models_dir: Path = MODELS_DIR) -> None:
        self.models_dir = models_dir
        self.langs = list(LANGUAGES)
        self.model = MLP()
        self.train_info: dict[str, Any] = {}

    # ---------- обучение / кэш ----------
    def _corpus_hash(self, corpus: dict[str, str]) -> str:
        h = hashlib.sha1()
        for lang in self.langs:
            h.update(lang.encode()); h.update(corpus.get(lang, "").encode("utf-8"))
        h.update(f"{NN_FEATURES}-{NN_HIDDEN}-{NN_EPOCHS}-{NN_CHUNK_MIN}-{NN_CHUNK_MAX}".encode())
        return h.hexdigest()[:16]

    def fit(self, corpus: dict[str, str]) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        digest = self._corpus_hash(corpus)
        weights, meta = self.models_dir / "mlp.pt", self.models_dir / "mlp.json"
        if weights.exists() and meta.exists():
            info = json.loads(meta.read_text())
            if info.get("hash") == digest:
                self.model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
                self.model.eval()
                self.train_info = info
                return
        self.train_info = self._train(corpus)
        self.train_info["hash"] = digest
        torch.save(self.model.state_dict(), weights)
        meta.write_text(json.dumps(self.train_info, ensure_ascii=False, indent=2))

    def _train(self, corpus: dict[str, str]) -> dict[str, Any]:
        rng = random.Random(NN_SEED)
        torch.manual_seed(NN_SEED)
        X, y = [], []
        for idx, lang in enumerate(self.langs):
            text = corpus.get(lang, "")
            n_chunks = max(400, len(text) // 120)
            for chunk in make_chunks(text, rng, n_chunks):
                X.append(featurize(chunk)); y.append(idx)
        X_t = torch.tensor(np.stack(X)); y_t = torch.tensor(y)
        perm = torch.randperm(len(y_t))
        n_val = max(1, len(y_t) // 10)
        val_idx, tr_idx = perm[:n_val], perm[n_val:]

        self.model = MLP()
        opt = torch.optim.Adam(self.model.parameters(), lr=1e-3, weight_decay=1e-5)
        loss_fn = nn.CrossEntropyLoss()
        history = []
        for epoch in range(NN_EPOCHS):
            self.model.train()
            order = tr_idx[torch.randperm(len(tr_idx))]
            total = 0.0
            for i in range(0, len(order), 64):
                b = order[i:i + 64]
                opt.zero_grad()
                loss = loss_fn(self.model(X_t[b]), y_t[b])
                loss.backward(); opt.step()
                total += loss.item() * len(b)
            self.model.eval()
            with torch.no_grad():
                acc = (self.model(X_t[val_idx]).argmax(1) == y_t[val_idx]).float().mean().item()
            history.append({"epoch": epoch + 1, "loss": round(total / len(tr_idx), 4), "val_acc": round(acc, 4)})
        return {"samples": len(y_t), "epochs": NN_EPOCHS, "features": NN_FEATURES, "hidden": NN_HIDDEN,
                "history": history, "val_accuracy": history[-1]["val_acc"]}

    # ---------- предсказание ----------
    def _predict(self, text: str) -> tuple[str, float, dict[str, float], dict[str, Any]]:
        x = torch.tensor(featurize(text)).unsqueeze(0)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0].tolist()
        scores = {lang: round(p, 4) for lang, p in zip(self.langs, probs)}
        best = max(scores, key=scores.get)
        ordered = sorted(probs, reverse=True)
        confidence = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)
        return best, confidence, scores, {"probabilities": scores}
