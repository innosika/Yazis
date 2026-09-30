"""Real-model checks (`make test-all`): the voice loads, times words, speaks unknown words."""

from __future__ import annotations

import pytest

from app.config import get_settings

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def kokoro():  # type: ignore[no-untyped-def]
    from app.tts.engine import KokoroEngine

    engine = KokoroEngine(get_settings().kokoro_repo, threads=4)
    engine.load()
    return engine


def test_word_timestamps(kokoro) -> None:  # type: ignore[no-untyped-def]
    from app.tts.align import align
    from app.tts.engine import VoiceMix

    spoken = "Hello world. Attention is all you need."
    audio, chunks = kokoro.synthesize(spoken, VoiceMix("af_heart"), 1.0)
    words = align(spoken, chunks)
    assert [spoken[w.spoken_start : w.spoken_end] for w in words] == [
        "Hello",
        "world",
        "Attention",
        "is",
        "all",
        "you",
        "need",
    ]
    assert all(w.end > w.start for w in words)
    assert words == sorted(words, key=lambda w: w.start)
    assert len(audio) / 24_000 > words[-1].end


def test_unknown_word_is_spoken(kokoro) -> None:  # type: ignore[no-untyped-def]
    from app.tts.engine import VoiceMix

    assert kokoro.health()["espeak_fallback"] is True
    _, chunks = kokoro.synthesize("zyxwvnet", VoiceMix("am_michael"), 1.0)
    token = next(t for c in chunks for t in c.tokens if t.text == "zyxwvnet")
    assert token.start is not None and token.end is not None


def test_parakeet_recognizes_speech(kokoro) -> None:  # type: ignore[no-untyped-def]
    import io

    import numpy as np
    import soundfile as sf
    import soxr

    from app.asr.local import ParakeetASR
    from app.tts.engine import VoiceMix

    audio, _ = kokoro.synthesize("Go to section three.", VoiceMix("am_michael"), 1.0)
    audio16 = np.asarray(soxr.resample(audio, 24_000, 16_000), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio16, 16_000, format="WAV")
    asr = ParakeetASR(get_settings().parakeet_dir)
    text, _ = asr._recognize(buf.getvalue())
    assert "section" in text.lower()
