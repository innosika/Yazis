"""Рисунки для объяснения: реальная речь Kokoro и результаты loopback-теста.

Запуск (при работающем `make up`): ~/.venvs/claude/bin/python figures.py
"""
import io
import json
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

API = "http://localhost:8030"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False})
INK, ACCENT, MARKER = "#1b1d22", "#1d3b8a", "#f5c518"


def synth(text: str) -> tuple[int, np.ndarray, list[dict]]:
    req = urllib.request.Request(f"{API}/api/tts/synthesize",
                                 json.dumps({"text": text, "voice": {"id": "am_michael"}}).encode(),
                                 {"Content-Type": "application/json"})
    body = json.load(urllib.request.urlopen(req))
    rate, audio = wavfile.read(io.BytesIO(urllib.request.urlopen(API + body["audio_url"]).read()))
    return rate, audio.astype(np.float32) / 32768, body["words"]


def mel_filterbank(sr: int, n_fft: int, n_mels: int = 80) -> np.ndarray:
    def hz_to_mel(f): return 2595 * np.log10(1 + f / 700)
    def mel_to_hz(m): return 700 * (10 ** (m / 2595) - 1)
    mels = np.linspace(hz_to_mel(0), hz_to_mel(sr / 2), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel_to_hz(mels) / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        fb[m - 1, a:b] = (np.arange(a, b) - a) / max(1, b - a)
        fb[m - 1, b:c] = (c - np.arange(b, c)) / max(1, c - b)
    return fb


def speech_figure() -> None:
    text = "Sorting takes O(n log n) time."
    sr, x, words = synth(text)
    t = np.arange(len(x)) / sr
    n_fft = 1024
    f, tt, Z = stft(x, sr, nperseg=600, noverlap=360, nfft=n_fft)  # окно 25 мс, шаг 10 мс
    S = np.abs(Z) ** 2
    fig, ax = plt.subplots(3, 1, figsize=(9, 7.2), sharex=True, gridspec_kw={"height_ratios": [1, 1.3, 1.1]})
    ax[0].plot(t, x, color=INK, lw=0.5)
    ax[0].set_ylabel("амплитуда")
    ax[0].set_title("Осциллограмма и границы слов из таймингов Kokoro (24 000 отсчётов в секунду)", loc="left", fontsize=10)
    top = np.abs(x).max()
    ax[0].set_ylim(-1.1 * top, 1.55 * top)
    for i, w in enumerate(words):
        ax[0].axvspan(w["start"], w["end"], color=MARKER if i % 2 == 0 else "#9fb3e8", alpha=0.25, lw=0)
        ax[0].axvline(w["start"], color=ACCENT, lw=0.6, ls="--")
        ax[0].text((w["start"] + w["end"]) / 2, 1.3 * top, f"«{w['text']}»", ha="center", va="center", fontsize=8.5, color=ACCENT)
    ax[1].pcolormesh(tt, f / 1000, 10 * np.log10(S + 1e-10), shading="auto", cmap="magma", vmin=-110, vmax=-30)
    ax[1].set_ylim(0, 8)
    ax[1].set_ylabel("частота, кГц")
    ax[1].set_title("Спектрограмма: какие частоты звучат в каждый момент (светлее — громче)", loc="left", fontsize=10)
    mel = mel_filterbank(sr, n_fft) @ S
    ax[2].pcolormesh(tt, np.arange(mel.shape[0]), 10 * np.log10(mel + 1e-10), shading="auto", cmap="magma", vmin=-110, vmax=-30)
    ax[2].set_ylabel("мел-полоса")
    ax[2].set_xlabel("время, с")
    ax[2].set_title("Мел-спектрограмма: 80 полос по шкале слуха — вход распознавателя и выход акустической модели", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig("img/10_speech.png", dpi=170)
    print("words:", [(w["text"], w["start"], w["end"]) for w in words])


def results_figure() -> None:
    rows = [
        ("Чистые команды\n(279 фраз)", 98.6),
        ("Шум 20 дБ\n(93)", 94.6),
        ("Команда поверх\nэха −20 дБ (93)", 79.6),
        ("Команда поверх\nэха −12 дБ (93)", 58.1),
        ("Проза статьи —\nигнорировать (20)", 100.0),
        ("Собственный голос —\nигнорировать (20)", 100.0),
    ]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    colors = [ACCENT, ACCENT, "#8a93a8", "#b9bfcc", "#1f7a4d", "#1f7a4d"]
    bars = ax.bar([r[0] for r in rows], [r[1] for r in rows], color=colors, width=0.62)
    for b, (_, v) in zip(bars, rows):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.1f} %".replace(".", ","), ha="center", fontsize=9)
    ax.set_ylim(0, 110)
    ax.set_ylabel("верно, %")
    ax.tick_params(axis="x", labelsize=8.5)
    ax.set_title("Loopback-тест: Kokoro произносит команды, Parakeet распознаёт (make loopback)", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig("img/11_results.png", dpi=170)


def pitch_figure() -> None:
    sr = 24000
    t = np.arange(int(0.02 * sr)) / sr
    base = np.sin(2 * np.pi * 150 * t) + 0.5 * np.sin(2 * np.pi * 300 * t)
    p = 2 ** (3 / 12)
    shifted = np.sin(2 * np.pi * 150 * p * t) + 0.5 * np.sin(2 * np.pi * 300 * p * t)
    fig, ax = plt.subplots(figsize=(9, 2.3))
    ax.plot(t * 1000, base, color=INK, lw=1.2, label="исходный тон 150 Гц")
    ax.plot(t * 1000, shifted, color=ACCENT, lw=1.2, label="+3 полутона: 150 · 2^(3/12) ≈ 178 Гц")
    ax.set_xlabel("время, мс")
    ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    ax.set_title("Высота тона — это частота колебаний голосовых связок; полутон = множитель 2^(1/12)", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig("img/12_pitch.png", dpi=170)


speech_figure()
results_figure()
pitch_figure()
