"""Конфигурация приложения."""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
TRAIN_DIR = DATA_DIR / "train"
TEST_DIR = DATA_DIR / "test"
UPLOADS_DIR = DATA_DIR / "uploads"
MODELS_DIR = DATA_DIR / "models"

LANGUAGES = ("ru", "en")
LANGUAGE_NAMES = {"ru": "Русский", "en": "Английский"}

# Метод N-грамм (Cavnar & Trenkle, 1994)
NGRAM_MAX_N = 5
NGRAM_PROFILE_SIZE = 300
NGRAM_MISSING_PENALTY = NGRAM_PROFILE_SIZE  # штраф за отсутствующую N-грамму

# Нейросеть
NN_FEATURES = 4096
NN_HIDDEN = 128
NN_EPOCHS = 12
NN_CHUNK_MIN = 40
NN_CHUNK_MAX = 600
NN_SEED = 42

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_WHISPER_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")
GROQ_LLM_MODEL = os.environ.get("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
