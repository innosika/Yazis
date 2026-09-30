"""Download every model Lector needs into the `models` volume, once.

Run by the one-shot `models` compose service before the backend starts, so the
backend itself can run with HF_HUB_OFFLINE=1 and never downloads at request time.
Re-running is cheap: files already in the cache are skipped by huggingface_hub.
"""

from __future__ import annotations

import sys
import time

from huggingface_hub import hf_hub_download

from app.config import settings
from app.tts.voices import ALL_VOICES


def fetch_kokoro() -> None:
    repo = settings.kokoro_repo
    for name in ("config.json", "kokoro-v1_0.pth"):
        hf_hub_download(repo_id=repo, filename=name)
    for voice in ALL_VOICES:
        hf_hub_download(repo_id=repo, filename=f"voices/{voice.id}.pt")
    print(f"  kokoro     ok  ({len(ALL_VOICES)} voices)", flush=True)


def fetch_parakeet() -> None:
    import onnx_asr

    # A path that does not exist yet makes onnx-asr download the model into it.
    onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3", str(settings.parakeet_dir), quantization="int8"
    )
    print("  parakeet   ok  (int8)", flush=True)


def check_spacy() -> None:
    import spacy

    spacy.load("en_core_web_sm")
    print("  spacy      ok  (en_core_web_sm)", flush=True)


def main() -> int:
    started = time.monotonic()
    print("Preparing speech models (first run downloads about 1 GB)...", flush=True)
    check_spacy()
    fetch_kokoro()
    fetch_parakeet()
    print(f"Models ready in {time.monotonic() - started:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
