# How a Neural Voice Reads a Research Paper

## Abstract

Reading a computer-science paper aloud is harder than reading a novel. Papers are dense with notation such as $O(n \log n)$, acronyms like CNN and LSTM, citations [3, 7], version numbers, units and formulas. This short article walks through the pipeline a modern text-to-speech (TTS) system uses to turn such text into natural speech, and shows where each step can go wrong. We focus on small models: an 82M-parameter network runs about 3x faster than real time on an ordinary laptop CPU, so no GPU is required.

## 1 Introduction

Early speech synthesizers concatenated recorded fragments of speech, e.g. diphones, and smoothed the joins (Moulines and Charpentier, 1990). The result was intelligible but robotic. Neural systems changed this: Tacotron [1] predicted spectrograms directly from characters, and WaveNet [2] generated the waveform one sample at a time. Today, compact models such as Kokoro-82M reach a mean opinion score close to much larger systems while producing 24 kHz audio in a fraction of the time.

A synthesizer, however, only pronounces what it is given. If the input says O(n^2), a naive system reads the letters and symbols one by one. The job of the *front end* is to rewrite the text into words a human reader would actually say, i.e. "big O of n squared", before any neural network is involved.

## 2 From Text to Phonemes

The front end has three stages. First, sentence segmentation splits the text into sentences. This is not trivial: in "see Fig. 3 and Eq. 2" the periods do not end a sentence, and neither does the one in "Vaswani et al. proposed". Second, normalization expands everything that is not a plain word:

- abbreviations such as e.g., i.e. and w.r.t.;
- numbers with units, like 16GB, 120 ms or a 2.7x speedup;
- scientific notation, for instance a learning rate of 1e-4;
- math, for example $\hat{y} = \sigma(Wx + b)$ or $x_i^2$;
- identifiers and file names such as train_model.py;
- links like https://arxiv.org, which are better summarised than spelled out.

Third, grapheme-to-phoneme conversion (G2P) maps each word to phonemes. A dictionary covers common words; a fallback model handles unknown ones like zyxwvnet. Acronyms need a policy of their own: SQL is usually said "sequel", NASA is read as a word, and GPU is spelled letter by letter.

## 3 Acoustic Model and Vocoder

Given phonemes and a voice embedding $s \in \mathbb{R}^{256}$, the acoustic model predicts how long each phoneme lasts and what it sounds like. The predicted durations are useful beyond synthesis: summing them gives the start and end time of every word, which is exactly what a reader needs to highlight the word currently being spoken.

Speaking rate is controlled by scaling the durations. Pitch can be shifted independently with a simple trick: synthesize at speed $s / p$ and resample the audio by a factor $p = 2^{k/12}$, where $k$ is the shift in semitones. Voices can even be blended, because a voice is just a vector; a 70/30 mix of two speakers produces a plausible third one.

## 4 Evaluation

TTS quality is usually measured with the mean opinion score (MOS), where listeners rate naturalness from 1 to 5. Speed is measured with the real-time factor, $\mathrm{RTF} = t_{synth} / t_{audio}$; any RTF below 1 means the system speaks faster than it computes. For interactive reading, the time to first audio matters more than throughput, so long sentences are split at commas and semicolons into shorter playback units.

Speech recognition, the reverse task, is evaluated with the word error rate: $\mathrm{WER} = (S + D + I) / N$, where $S$, $D$ and $I$ count substituted, deleted and inserted words and $N$ is the length of the reference. A voice-controlled reader only needs to recognise a small set of commands, so it can combine a general recogniser with exact, fuzzy and semantic matching against that set.

## 5 Conclusion

Most of what makes synthetic reading of scientific text sound right happens before the neural network runs. A careful front end, a small model and word-level timing together make a paper pleasant to listen to, and a handful of voice commands make it pleasant to control.

## References

[1] Wang et al. Tacotron: Towards End-to-End Speech Synthesis. 2017.

[2] van den Oord et al. WaveNet: A Generative Model for Raw Audio. 2016.
