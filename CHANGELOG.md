# Changelog

## [1.0.0] — 2026-11-17

First public release, accompanying the SoftwareX article.

- Transcription of source and interpreter recordings with faster-whisper
  (deterministic decoding, VAD filtering, word timestamps) and sentence-level
  re-segmentation.
- Causal DTW alignment with anticipation tolerance; many-to-one chunks.
- EVS and gap measures, simultaneous / consecutive modes, lag categories.
- 1:1 confidence score and *Review* flags for confidence-based triage.
- Pair correction tools (pair, add to pair, detach, delete, re-align).
- Two-tier waveform editor with boundary dragging, zoom, pan and playback.
- Multiple interpreters (up to four), start offsets, mixed-recording split.
- JSON sessions and three-file CSV export with English column names.
- English / Bahasa Indonesia interface.
- Windows portable build; source distribution for macOS and Linux with a
  double-click macOS launcher.
- Automatic CPU fallback when an NVIDIA GPU is present but the CUDA libraries
  cannot be loaded.
