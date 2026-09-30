"""Audio post-processing: pitch shift without tempo change, and WAV encoding.

Pitch uses the tape-speed trick. Asking Kokoro for speech at ``speed / p`` and then
resampling it so it plays ``p`` times faster gives the requested tempo with every
frequency multiplied by ``p = 2 ** (semitones / 12)``. Formants move with the pitch,
so it sounds like a different speaker rather than a processed one; that is why the
range is clamped to four semitones either way.
"""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf
import soxr

SAMPLE_RATE = 24_000
MIN_SPEED, MAX_SPEED = 0.5, 2.0
MAX_SEMITONES = 4.0


def pitch_factor(semitones: float) -> float:
    st = max(-MAX_SEMITONES, min(MAX_SEMITONES, semitones))
    return float(2.0 ** (st / 12.0))


def synthesis_speed(speed: float, semitones: float) -> float:
    """The speed to ask the model for so that, after the pitch shift, tempo == speed."""
    s = max(MIN_SPEED, min(MAX_SPEED, speed))
    return max(MIN_SPEED, min(MAX_SPEED, s / pitch_factor(semitones)))


def shift_pitch(audio: np.ndarray, semitones: float) -> np.ndarray:
    p = pitch_factor(semitones)
    if abs(p - 1.0) < 1e-3:
        return audio
    # Resample to a rate p times lower; played back at 24 kHz it is p times faster/higher.
    out = soxr.resample(audio.astype(np.float32), SAMPLE_RATE, SAMPLE_RATE / p, quality="HQ")
    return np.asarray(out, dtype=np.float32)


def apply_gain(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    """Normalise so the loudest sample sits at ``peak`` (never boosts silence)."""
    m = float(np.max(np.abs(audio))) if audio.size else 0.0
    if m < 1e-4:
        return audio
    return (audio * (peak / m)).astype(np.float32)


def to_wav(audio: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1.0, 1.0), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def silence(seconds: float, rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(rate * max(0.0, seconds)), dtype=np.float32)
