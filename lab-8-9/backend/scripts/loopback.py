"""Voice path test without a microphone: Lector talks to itself.

Every command phrase is synthesized by Kokoro (three voices, three speeds), resampled
to 16 kHz like the browser sends it, and posted to /api/voice/recognize. The harness
then checks that the recognised command is the expected one. Two harder conditions
are added: white noise at 20 dB SNR, and a sentence of the paper mixed in while
"playing" (the echo case, which also exercises echo subtraction). The echo sits at
-20 dB: in hands-free mode the reader ducks its voice to 20% as soon as the listener
starts speaking. Pass --echo-db -12 to see the undocked case. Finally,
sentences from the sample article are fed as they are, and must not trigger anything.

    make loopback                 # local recogniser (Parakeet), full grid
    make loopback ENGINE=cloud    # Groq Whisper, a small throttled sample

Results are printed as a table and saved to /data/loopback-<engine>.json.
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import soundfile as sf
import soxr

API = "http://localhost:8000/api"

# (utterance, expected command id, expected slots)
CASES: list[tuple[str, str, dict[str, Any]]] = [
    ("Pause.", "pause", {}),
    ("Hold on.", "pause", {}),
    ("Continue.", "resume", {}),
    ("Keep reading.", "resume", {}),
    ("Stop reading.", "stop", {}),
    ("Next sentence.", "next_sentence", {}),
    ("Go back.", "previous_sentence", {}),
    ("Next paragraph.", "next_paragraph", {}),
    ("Next section.", "next_section", {}),
    ("Say that again.", "repeat", {}),
    ("Start over.", "start_over", {}),
    ("Go to section three.", "go_to_section", {"number": 3.0}),
    ("Read the conclusion.", "go_to_section", {"section_title": "5 Conclusion"}),
    ("Read the abstract.", "read_abstract", {}),
    ("Faster.", "faster", {}),
    ("Slow down a bit.", "slower", {}),
    ("Set speed to one point two.", "set_speed", {"number": 1.2}),
    ("Normal speed.", "normal_speed", {}),
    ("Louder.", "louder", {}),
    ("Turn it down.", "quieter", {}),
    ("Next voice.", "next_voice", {}),
    ("Switch to George.", "switch_voice", {"voice": "bm_george"}),
    ("British accent.", "british_accent", {}),
    ("Where am I?", "where_am_i", {}),
    ("How much is left?", "time_left", {}),
    ("Explain the attention mechanism.", "explain", {"term": "attention mechanism"}),
    ("Summarize this section.", "summarize", {}),
    ("Open library.", "open_library", {}),
    ("Dark mode.", "dark_mode", {}),
    ("What can I say?", "show_commands", {}),
    ("Stop listening.", "stop_listening", {}),
]
VOICES = ["af_heart", "am_michael", "bf_emma"]
SPEEDS = [0.9, 1.0, 1.2]
ECHO_SENTENCE = (
    "Neural systems changed this, predicting spectrograms directly from characters "
    "and generating the waveform one sample at a time."
)


@dataclass
class Row:
    condition: str
    utterance: str
    voice: str
    speed: float
    expected: str | None
    got: str | None
    ok: bool
    transcript: str
    engine: str
    asr_ms: float
    rejected: str | None


def synth(client: httpx.Client, text: str, voice: str, speed: float) -> np.ndarray:
    r = client.post(
        f"{API}/tts/synthesize", json={"text": text, "voice": {"id": voice}, "speed": speed}
    )
    r.raise_for_status()
    wav = client.get(f"http://localhost:8000{r.json()['audio_url']}").content
    audio, rate = sf.read(io.BytesIO(wav), dtype="float32")
    return np.asarray(soxr.resample(audio, rate, 16_000), dtype=np.float32)


def to_wav(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1), 16_000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def add_noise(audio: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    power = float(np.mean(audio**2)) or 1e-6
    noise = rng.normal(0, np.sqrt(power / 10 ** (snr_db / 10)), audio.shape)
    return (audio + noise).astype(np.float32)


def mix_echo(command: np.ndarray, echo: np.ndarray, gain_db: float) -> np.ndarray:
    pad = np.zeros(4800, dtype=np.float32)  # the VAD keeps 300 ms before speech onset
    cmd = np.concatenate([pad, command])
    e = echo[: len(cmd)]
    e = np.pad(e, (0, max(0, len(cmd) - len(e))))
    return (cmd + e * 10 ** (gain_db / 20)).astype(np.float32)


def recognize(
    client: httpx.Client, wav: bytes, engine: str, doc: str, **extra: Any
) -> dict[str, Any]:
    data = {
        "language": "en",
        "engine": engine,
        "document_id": doc,
        **{k: str(v) for k, v in extra.items()},
    }
    r = client.post(
        f"{API}/voice/recognize", data=data, files={"audio": ("u.wav", wav, "audio/wav")}
    )
    r.raise_for_status()
    return dict(r.json())


def check(
    result: dict[str, Any], expected: str | None, slots: dict[str, Any]
) -> tuple[str | None, bool]:
    match = ((result.get("outcome") or {}).get("match")) or None
    got = match["command"] if match else None
    if expected is None:
        return got, got is None
    ok = (
        got == expected and all(match["slots"].get(k) == v for k, v in slots.items())
        if match
        else False
    )
    return got, ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["local", "cloud"], default="local")
    ap.add_argument("--echo-db", type=float, default=-20.0)
    args = ap.parse_args()
    cloud = args.engine == "cloud"
    rng = np.random.default_rng(7)
    rows: list[Row] = []
    with httpx.Client(timeout=120) as client:
        docs = client.get(f"{API}/documents").json()
        sample = next((d for d in docs if d["source"].get("kind") == "sample"), docs[0])
        doc_id = sample["id"]
        full = client.get(f"{API}/documents/{doc_id}").json()
        prose = [
            b["text"][s["start"] : s["end"]]
            for b in full["structure"]["blocks"]
            if b["kind"] == "paragraph"
            for s in b["sentences"]
        ][: 20 if not cloud else 5]
        echo_audio = synth(client, ECHO_SENTENCE, "af_heart", 1.0)
        cases = CASES if not cloud else CASES[::2]
        grid = [(v, s) for v in VOICES for s in SPEEDS] if not cloud else [("am_michael", 1.0)]
        started = time.monotonic()
        for utterance, expected, slots in cases:
            for voice, speed in grid:
                clean = synth(client, utterance, voice, speed)
                conditions: list[tuple[str, np.ndarray, dict[str, Any]]] = [("clean", clean, {})]
                if not cloud and speed == 1.0:
                    conditions.append(("noise 20 dB", add_noise(clean, 20, rng), {}))
                    conditions.append(
                        (
                            f"echo {args.echo_db:g} dB",
                            mix_echo(clean, echo_audio, args.echo_db),
                            {"playing": True, "played_text": ECHO_SENTENCE},
                        )
                    )
                for name, audio, extra in conditions:
                    res = recognize(client, to_wav(audio), args.engine, doc_id, **extra)
                    got, ok = check(res, expected, slots)
                    rows.append(
                        Row(
                            name,
                            utterance,
                            voice,
                            speed,
                            expected,
                            got,
                            ok,
                            res["transcript"],
                            res["engine"],
                            res["asr_ms"],
                            res["rejected"],
                        )
                    )
                    if cloud:
                        time.sleep(3.2)  # stay under Groq's 20 requests per minute
            print(
                f"  {utterance:36} {sum(r.ok for r in rows if r.utterance == utterance)}/"
                f"{sum(1 for r in rows if r.utterance == utterance)}",
                flush=True,
            )
        for sentence in prose:
            audio = synth(client, sentence, "af_heart", 1.0)
            res = recognize(client, to_wav(audio), args.engine, doc_id)
            got, ok = check(res, None, {})
            rows.append(
                Row(
                    "prose (must be ignored)",
                    sentence[:50],
                    "af_heart",
                    1.0,
                    None,
                    got,
                    ok,
                    res["transcript"],
                    res["engine"],
                    res["asr_ms"],
                    res["rejected"],
                )
            )
            if cloud:
                time.sleep(3.2)
                continue
            # Lector hearing itself through the loudspeaker while reading this sentence.
            res = recognize(
                client,
                to_wav(audio[: 16000 * 3]),
                args.engine,
                doc_id,
                playing=True,
                played_text=sentence,
            )
            got, ok = check(res, None, {})
            rows.append(
                Row(
                    "own voice (must be ignored)",
                    sentence[:50],
                    "af_heart",
                    1.0,
                    None,
                    got,
                    ok,
                    res["transcript"],
                    res["engine"],
                    res["asr_ms"],
                    res["rejected"],
                )
            )

    print()
    print(f"{'condition':26} {'correct':>9} {'accuracy':>9} {'median ASR':>11}")
    by_condition: dict[str, list[Row]] = {}
    for r in rows:
        by_condition.setdefault(r.condition, []).append(r)
    summary = {}
    for cond, items in by_condition.items():
        acc = sum(r.ok for r in items) / len(items)
        med = statistics.median(r.asr_ms for r in items)
        summary[cond] = {"n": len(items), "accuracy": round(acc, 4), "median_asr_ms": round(med, 1)}
        print(f"{cond:26} {sum(r.ok for r in items):>4}/{len(items):<4} {acc:>8.1%} {med:>9.0f} ms")
    failures = [r for r in rows if not r.ok]
    if failures:
        print("\nMisses:")
        for r in failures[:40]:
            print(
                f"  [{r.condition}] {r.utterance!r} ({r.voice} x{r.speed}) heard {r.transcript!r} -> {r.got}"
                f"{' (' + r.rejected + ')' if r.rejected else ''}"
            )
    out = Path("/data") / f"loopback-{args.engine}.json"
    out.write_text(
        json.dumps(
            {
                "engine": args.engine,
                "summary": summary,
                "seconds": round(time.monotonic() - started),
                "rows": [asdict(r) for r in rows],
            },
            indent=1,
        )
    )
    print(f"\nSaved {out}  ({round(time.monotonic() - started)} s)")
    commands = [r for r in rows if r.expected is not None and r.condition == "clean"]
    prose_rows = [r for r in rows if r.expected is None]  # prose and own voice
    clean_acc = sum(r.ok for r in commands) / max(1, len(commands))
    false_pos = 1 - sum(r.ok for r in prose_rows) / max(1, len(prose_rows))
    print(f"clean command accuracy {clean_acc:.1%}, false positives on prose {false_pos:.1%}")
    return 0 if clean_acc >= 0.95 and false_pos <= 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
