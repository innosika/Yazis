"""Reject what is not the user speaking: recogniser hallucinations and Lector's own echo.

Whisper, given near-silence or noise, tends to produce stock phrases ("Thank you.",
"Thanks for watching!") or to repeat its prompt. Those are caught here.

Echo is the harder case. On Linux, Chrome's echo canceller does not remove audio the
page plays through Web Audio, so the microphone hears the synthetic voice. The
frontend sends the text of the words that were audible during the capture window; any
run of transcript words that lines up with that text is removed, and only what is left
is matched against commands. "...the encoder maps an input pause" still yields "pause".
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from app.asr.base import Transcript

HALLUCINATIONS = {
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching!",
    "you",
    "bye",
    "bye.",
    "okay.",
    "so",
    "uh",
    "um",
    "hmm",
    "mm",
    "oh",
    "the end",
    "subtitles by",
    "subtitles by the amara.org community",
    "please subscribe",
    "продолжение следует",
    "спасибо",
    "спасибо за внимание",
    "субтитры сделал",
    "редактор субтитров",
    "vielen dank",
    "untertitel im auftrag des zdf",
    "merci",
    "sous-titres réalisés par",
    "♪",
    "...",
    ".",
    "",
}
_WORD = re.compile(r"[\w']+", re.UNICODE)


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def is_hallucination(t: Transcript, prompt: str = "") -> str | None:
    """Return a reason string when the transcript should be discarded."""
    text = t.text.strip()
    low = re.sub(r"\s+", " ", text.lower()).strip()
    if not low or low.strip(".!?, ") == "":
        return "empty"
    if low in HALLUCINATIONS or low.rstrip(".!") in HALLUCINATIONS:
        return "stock phrase"
    if t.no_speech_prob > 0.6 and t.avg_logprob < -0.8:
        return "no speech"
    if t.avg_logprob < -1.4:
        return "low confidence"
    ws = words(low)
    if len(ws) >= 4 and len(set(ws)) <= len(ws) // 3:
        return "repetition"
    # Whisper echoing its prompt produces a long stretch of it; a short command that
    # happens to appear in the prompt ("read the abstract") is genuine.
    if prompt and len(ws) >= 6:
        prompt_words = " ".join(words(prompt))
        if " ".join(ws) in prompt_words:
            return "prompt echo"
    return None


@dataclass(frozen=True, slots=True)
class EchoResult:
    residual: str
    echo_ratio: float  # share of transcript words explained by the played audio


def subtract_echo(transcript: str, played: str) -> EchoResult:
    heard = words(transcript)
    if not heard or not played.strip():
        return EchoResult(" ".join(heard), 0.0)
    ref = words(played)
    matcher = difflib.SequenceMatcher(a=heard, b=ref, autojunk=False)
    remove: set[int] = set()
    for block in matcher.get_matching_blocks():
        # Single-word coincidences ("the", "pause") are kept unless the whole
        # utterance is one word that also sounded - that is almost always echo.
        if block.size >= 2 or (block.size == 1 and len(heard) == 1 and len(ref) > 3):
            remove.update(range(block.a, block.a + block.size))
    residual = [w for i, w in enumerate(heard) if i not in remove]
    return EchoResult(" ".join(residual), len(remove) / len(heard))
