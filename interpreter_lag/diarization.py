"""Pemisah penutur sederhana untuk rekaman berisi beberapa penerjemah.

Pipeline ringan tanpa dependensi tambahan (numpy murni):
  1. Deteksi ujaran (VAD berbasis energi RMS per frame).
  2. Ekstraksi ciri suara per ujaran (statistik MFCC).
  3. Pengelompokan k-means menjadi K penutur.
  4. Ekspor K file WAV: tiap file berisi ujaran satu penutur pada posisi
     waktu aslinya, hening di bagian lain — sehingga timestamp/EVS tetap
     valid saat dianalisis sebagai input penerjemah terpisah.

Akurasi pengelompokan bersifat heuristik (paling andal bila suara penutur
cukup berbeda, mis. pria/wanita). Hasilnya SELALU bisa dikoreksi manual di
dialog GUI sebelum dipakai — konsisten dengan filosofi human-in-the-loop.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .waveform import SAMPLE_RATE


@dataclass
class Utterance:
    """Satu ujaran terdeteksi pada rekaman campuran."""

    start: float
    end: float
    cluster: int = 0

    @property
    def duration(self) -> float:
        return self.end - self.start


# ------------------------------------------------------------------ VAD
def detect_utterances(
    audio: np.ndarray,
    rate: int = SAMPLE_RATE,
    min_speech: float = 0.5,
    max_gap: float = 0.6,
    pad: float = 0.12,
) -> list[Utterance]:
    """Deteksi rentang ujaran dengan ambang energi adaptif.

    min_speech: durasi minimum satu ujaran (detik) — lebih pendek dibuang.
    max_gap: hening antar-ujaran yang lebih pendek dari ini digabung.
    pad: pelebaran tiap sisi ujaran agar awal/akhir kata tidak terpotong.
    """
    if len(audio) == 0:
        return []

    signal = audio.astype(np.float32) / 32768.0
    frame = int(0.03 * rate)
    hop = int(0.01 * rate)
    n_frames = max(1, (len(signal) - frame) // hop + 1)

    # Energi RMS per frame (vektorisasi via cumsum kuadrat).
    squared = np.concatenate([[0.0], np.cumsum(signal.astype(np.float64) ** 2)])
    starts = np.arange(n_frames) * hop
    ends = np.minimum(starts + frame, len(signal))
    energy = np.sqrt((squared[ends] - squared[starts]) / np.maximum(ends - starts, 1))

    # Ambang adaptif: di atas lantai derau dan relatif terhadap puncak.
    noise_floor = np.percentile(energy, 20)
    threshold = max(noise_floor * 3.0, float(energy.max()) * 0.06, 1e-4)
    speech = energy > threshold

    # Susun region kontigu.
    regions: list[list[float]] = []
    in_speech = False
    region_start = 0.0
    for i, flag in enumerate(speech):
        t = i * hop / rate
        if flag and not in_speech:
            in_speech = True
            region_start = t
        elif not flag and in_speech:
            in_speech = False
            regions.append([region_start, t])
    if in_speech:
        regions.append([region_start, len(signal) / rate])

    # Gabungkan celah pendek.
    merged: list[list[float]] = []
    for region in regions:
        if merged and region[0] - merged[-1][1] <= max_gap:
            merged[-1][1] = region[1]
        else:
            merged.append(region)

    # Buang ujaran terlalu pendek, beri padding.
    total = len(signal) / rate
    utterances = [
        Utterance(max(0.0, s - pad), min(total, e + pad))
        for s, e in merged
        if e - s >= min_speech
    ]
    return utterances


# ----------------------------------------------------------------- MFCC
def _mel_filterbank(n_filters: int, n_fft: int, rate: int) -> np.ndarray:
    def hz_to_mel(hz: float) -> float:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def mel_to_hz(mel: np.ndarray) -> np.ndarray:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mel_points = np.linspace(hz_to_mel(0), hz_to_mel(rate / 2), n_filters + 2)
    hz_points = mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / rate).astype(int)

    fbank = np.zeros((n_filters, n_fft // 2 + 1))
    for m in range(1, n_filters + 1):
        left, center, right = bins[m - 1], bins[m], bins[m + 1]
        for k in range(left, center):
            if center > left:
                fbank[m - 1, k] = (k - left) / (center - left)
        for k in range(center, right):
            if right > center:
                fbank[m - 1, k] = (right - k) / (right - center)
    return fbank


def _mfcc(signal: np.ndarray, rate: int, n_mfcc: int = 13) -> np.ndarray:
    """MFCC sederhana [n_frame, n_mfcc] untuk pembeda warna suara penutur."""
    n_fft = 512
    frame = int(0.025 * rate)
    hop = int(0.01 * rate)
    if len(signal) < frame:
        return np.zeros((0, n_mfcc))

    emphasized = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])
    n_frames = (len(emphasized) - frame) // hop + 1
    idx = np.arange(frame)[None, :] + (np.arange(n_frames) * hop)[:, None]
    frames = emphasized[idx] * np.hamming(frame)

    spectrum = np.abs(np.fft.rfft(frames, n_fft)) ** 2 / n_fft
    fbank = _mel_filterbank(26, n_fft, rate)
    features = np.log(spectrum @ fbank.T + 1e-10)

    # DCT-II ortho via matriks (hindari dependensi scipy).
    n = features.shape[1]
    dct = np.cos(np.pi / n * (np.arange(n)[:, None] + 0.5) * np.arange(n_mfcc)[None, :])
    dct *= np.sqrt(2.0 / n)
    dct[:, 0] /= np.sqrt(2.0)
    return features @ dct


def utterance_features(
    audio: np.ndarray,
    utterances: list[Utterance],
    rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Vektor ciri per ujaran: rata-rata + simpangan MFCC (26 dimensi)."""
    signal = audio.astype(np.float32) / 32768.0
    vectors = []
    for utt in utterances:
        s0 = int(utt.start * rate)
        s1 = int(utt.end * rate)
        mfcc = _mfcc(signal[s0:s1], rate)
        if len(mfcc) == 0:
            vectors.append(np.zeros(26))
            continue
        vectors.append(np.concatenate([mfcc.mean(axis=0), mfcc.std(axis=0)]))
    features = np.array(vectors)
    # Normalisasi z-score antar ujaran agar tiap dimensi setara bobotnya.
    std = features.std(axis=0)
    std[std < 1e-8] = 1.0
    return (features - features.mean(axis=0)) / std


# --------------------------------------------------------------- k-means
def cluster_utterances(features: np.ndarray, k: int, seed: int = 0) -> np.ndarray:
    """K-means sederhana (init k-means++, beberapa restart, deterministik)."""
    n = len(features)
    if n == 0:
        return np.zeros(0, dtype=int)
    k = min(k, n)
    rng = np.random.default_rng(seed)

    best_labels = np.zeros(n, dtype=int)
    best_inertia = np.inf
    for _restart in range(5):
        # k-means++ init
        centers = [features[rng.integers(n)]]
        for _ in range(k - 1):
            dists = np.min(
                [np.sum((features - c) ** 2, axis=1) for c in centers], axis=0
            )
            probs = dists / max(dists.sum(), 1e-12)
            centers.append(features[rng.choice(n, p=probs)])
        centers = np.array(centers)

        for _iter in range(25):
            dist = ((features[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            labels = dist.argmin(axis=1)
            new_centers = np.array(
                [
                    features[labels == j].mean(axis=0)
                    if np.any(labels == j)
                    else centers[j]
                    for j in range(k)
                ]
            )
            if np.allclose(new_centers, centers):
                break
            centers = new_centers

        inertia = float(dist[np.arange(n), labels].sum())
        if inertia < best_inertia:
            best_inertia = inertia
            best_labels = labels

    # Nomori ulang cluster menurut urutan kemunculan pertama (P1 = yang
    # bicara duluan), agar label stabil dan intuitif.
    order: dict[int, int] = {}
    for label in best_labels:
        if label not in order:
            order[label] = len(order)
    return np.array([order[label] for label in best_labels])


# ------------------------------------------------------------ split/export
def build_speaker_tracks(
    audio: np.ndarray,
    utterances: list[Utterance],
    k: int,
    rate: int = SAMPLE_RATE,
) -> list[np.ndarray]:
    """Buat K track berdurasi sama: ujaran penutur pada posisi asli, sisanya hening."""
    tracks = [np.zeros(len(audio), dtype=np.int16) for _ in range(k)]
    for utt in utterances:
        s0 = max(0, int(utt.start * rate))
        s1 = min(len(audio), int(utt.end * rate))
        if 0 <= utt.cluster < k and s1 > s0:
            tracks[utt.cluster][s0:s1] = audio[s0:s1]
    return tracks


def write_wav(path: str | Path, audio: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(audio.astype(np.int16).tobytes())
