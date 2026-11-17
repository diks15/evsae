# EVSAE User Guide

Complete manual for Ear-Voice Span Analysis and Editing (EVSAE) v1.0, from
input recordings to verified, exported results. Labels below are those of the
English interface (*Settings → Language / Bahasa*). An Indonesian version of
this guide is available in [PANDUAN_PENGGUNAAN.md](../PANDUAN_PENGGUNAAN.md).

## Contents

1. [Starting the application](#1-starting-the-application)
2. [Preparing recordings](#2-preparing-recordings)
3. [Entering inputs and starting the analysis](#3-entering-inputs-and-starting-the-analysis)
4. [Reading the results](#4-reading-the-results)
5. [Verifying and correcting pairs](#5-verifying-and-correcting-pairs)
6. [Editing segments (timestamps and text)](#6-editing-segments-timestamps-and-text)
7. [Waveform Editor](#7-waveform-editor)
8. [Saving work and exporting](#8-saving-work-and-exporting)
9. [Frequently asked questions](#9-frequently-asked-questions)

---

## 1. Starting the application

**Windows portable build (no installation):** extract
`EVSAE-portable (Windows).zip` to a folder and run `EVSAE.exe`.

**From source (Windows, macOS, Linux):**

```bash
pip install -r requirements.txt
python interpreter_lag_gui.py
```

**macOS (easiest):** install Python 3.12 from python.org, extract the source
archive and double-click `EVSAE_macOS.command`. If macOS blocks it,
right-click → **Open** → **Open**. The first run installs the dependencies
automatically (internet required, a few minutes).

The `small` Whisper model is bundled with the portable build. Other models
(e.g. `medium`, more accurate but slower) are downloaded **once** the first
time they are selected and work offline afterwards.

To explore the interface without your own data, click **Load Demo**.

---

## 2. Preparing recordings

The quality of the analysis depends largely on the recordings:

- **Two separate recordings**: one for the source speaker and one for the
  interpreter, ideally each from its own microphone or headset so the voices
  do not bleed into each other.
- **Start them together**: press record on both devices at the same moment.
  If that is not possible, note the difference; it goes into the **Start
  offset** field.
- **More than one interpreter**: record each interpreter to a separate file
  (on the same timeline). If several interpreters ended up in one file, use
  **Split Mixed Recording…** to split it into one file per speaker first.
- Supported formats: mp3, wav, mp4, m4a, mpeg, webm and most other audio or
  video formats.

---

## 3. Entering inputs and starting the analysis

All settings are in the **left sidebar** (scrollable when the window is
short):

1. **Input 1 · Source Language (SL)** → *Choose SL File* and select the
   original speaker's recording (English).
2. **Input 2 · Target Language (TL)**:
   - set **Number of Interpreters** (1–4); one file slot appears per
     interpreter;
   - *Choose TL File* for each slot (Indonesian recordings);
   - each interpreter is labelled **P1, P2, …** in all tables.
3. **Start offset (s)**: only when the recordings did not start together.
   - Example: the interpreter's recorder was started 2 s after the source
     recorder → enter `2` for that interpreter.
   - Negative values and either decimal separator are accepted
     (`1,5` = `1.5`).
   - The offset shifts every timestamp **and** the waveform of that file.
4. **Whisper Model**: `small` is fast and reasonably good; `medium` is more
   accurate (recommended for research data); `large-v3` is the heaviest.
5. **Interpreting Mode**: *Simultaneous* (primary measure = EVS) or
   *Consecutive* (primary measure = gap).
6. Click **Transcribe & Analyze**. Processing runs in the background (the
   window stays usable); progress is shown in the STATUS box.

> Transcription is **deterministic**: the same file always yields the same
> transcript and the same numbers.

---

## 4. Reading the results

### Metric cards (top)

| Card | Meaning |
|:--|:--|
| **Complete Pairs** | number of pairs with both sides (included in statistics) |
| **Mean / Shortest / Longest Lag** | EVS statistics (or gap, depending on the mode) over complete pairs |
| **1:1 Confidence** | percentage of pairs that are one sentence ↔ one sentence; the higher, the fewer rows need manual checking |

### Tabs

- **SL Transcript / TL Transcript**: every sentence segment: number,
  (Speaker), Start, End, Duration, **Pair** (#n = pair number; `-` = unpaired)
  and text.
- **Waveform Editor**: see section 7.
- **Lag Results**: one row per pair: EVS, Gap, Category (colour-coded), the
  **Review** column and the text of both sides. The ★ in a column header marks
  the primary measure of the current mode.
- **Visualization**: category distribution (donut) and EVS per pair (bars;
  dashed lines = category thresholds at 5/10/15 s), plus an alignment-quality
  summary.

### The "Review" column (⚠)

⚠ means **"check me"**, not "wrong". It appears on:

- **merged chunks** (several sentences on one side): often correct
  (interpreter condensation), but worth confirming;
- **negative EVS** (the interpreter appears to start before the source):
  small anticipation is normal, a large negative value usually indicates a
  mismatch;
- **unpaired** utterances (omissions / additions).

Rows **without** ⚠ can be trusted without checking.

---

## 5. Verifying and correcting pairs

### Recommended workflow

1. Run the analysis and open **Lag Results**.
2. Go through the **⚠ rows only**, from top to bottom.
3. For each ⚠ row, **read the meaning**: is the interpreter's text really the
   rendition of all source sentences in that row?
   - Everything matches → leave it (that row is verified).
   - It does not match → correct it with the tools below.
4. **Save Session** when done.

### Diagnosis table: symptom → tool

| Symptom | Diagnosis | Tool |
|:--|:--|:--|
| Meaning is shifted by one row over several consecutive rows; a run of negative EVS | Chain of mismatches | **Pair Selected**, from top to bottom |
| A source sentence was not interpreted at all | Omission | **Detach Segment** |
| The rendition of one sentence "leaks" into the neighbouring row | Incomplete merge | **Add to Pair** |
| A row contains a non-utterance (applause or a cough transcribed as text) | Transcription artefact | **Delete Pair** |
| Extreme EVS (e.g. > 12 s) | Usually one of the above | read the text and resolve |

### Using each button (*Pair Correction* section of the sidebar)

**Pair Selected**: creates a new 1:1 pair.

1. *SL Transcript* tab → click one row.
2. *TL Transcript* tab → click one row.
3. Click **Pair Selected**.

Both segments leave their previous pairs and are joined; the remaining members
of the old pairs are kept.

**Add to Pair**: adds a segment to an EXISTING pair (many-to-one).

1. *Lag Results* tab → click the **target** pair.
2. *SL Transcript* **or** *TL Transcript* tab → click the segment to add.
3. Click **Add to Pair**.

Example: the interpreter merged `n3 "Hello, Glasgow"` and
`n4 "Thank you very much"` into one sentence → select the pair containing n3
in Lag Results, select n4 in SL Transcript, click Add to Pair.

**Detach Segment**: removes a segment from its pair, making it *Unpaired*.

1. *SL/TL Transcript* tab → click the segment.
2. Click **Detach Segment**.

Use it for omissions (a source sentence that was not interpreted). The segment
stays visible in Lag Results as documentation but is excluded from EVS
statistics.

**Delete Pair**: removes one row from the analysis entirely.

1. *Lag Results* tab → click the row.
2. Click **Delete Pair**.

Only for junk rows (not real utterances). The segments stay in the transcript
tabs with pair `-`.

**Re-align (DTW)**: recomputes ALL pairs automatically from scratch.

⚠ This **discards every manual correction**; a confirmation dialog appears.
Save the session first if in doubt.

### Properties of corrections

- **Local**: a correction only touches the pairs involved; other pairs keep
  their values.
- **Pair numbers may shift** after a correction (pairs are always re-sorted by
  time). Track the text, not the number.
- **One action per cycle**: each correction refreshes all tables and clears
  the selection; select again before the next action.
- EVS is measured from the **first onset** on each side, so appending a
  segment to the end of a chunk does not change that chunk's EVS, but it can
  correct the EVS of the neighbouring chunk.
- The status bar always states which segment was moved (e.g. *"Segment source #19 added to
  pair…"*); check it if something unintended moved.

---

## 6. Editing segments (timestamps and text)

When the ASR output is off (start or end slightly wrong, misheard text):

**In the tables**: in the *SL/TL Transcript* tab:

1. **Double-click** a **Start**, **End** or **Transcript** cell.
2. Type the new value → **Enter** to save, **Esc** to cancel.
3. Automatic validation: times cannot be negative, Start cannot pass End.
4. All EVS, gap and category values are recomputed immediately.

**In the waveform**: see section 7 (more precise because you see the signal).

Other columns (#, Speaker, Duration, Pair) cannot be edited directly:
Duration follows Start/End, and Pair is changed with the correction tools of
section 5.

---

## 7. Waveform Editor

Two tiers on a shared timeline: **Source** (top, blue) and **Interpreter**
(bottom, green). Each segment is drawn as a labelled box with **vertical
boundary lines** at its start and end.

| Action | How |
|:--|:--|
| Move a segment boundary | hover over a vertical line (cursor becomes ↔) → click and drag |
| Zoom in / out | mouse wheel (centred on the cursor) or the *Zoom − / Zoom + / Fit* buttons |
| Pan | **right**-click and drag (macOS: right-click / two-finger click and drag, or **Control** + click and drag) |
| Play audio | **▶ Source / ▶ Interpreter / ▶ Mix**, starting at the left edge of the current view; a red cursor follows playback |
| Stop | **■ Stop** |

Releasing a boundary drag recomputes the lags immediately; it is equivalent to
editing Start/End in the table.

With several interpreters, the bottom tier shows a **mix** of all interpreter
tracks.

---

## 8. Saving work and exporting

**Save Session** (sidebar) writes a `.json` file containing:

- the full transcripts of both sides (including your edits) and speaker labels;
- all pairs, **including every manual correction**;
- the model, mode, file paths and offsets.

**Open Session** restores everything **exactly**, without re-transcribing. The
waveforms are reloaded if the recordings are still at the same location, so
**keep the session file in the same folder as its recordings**.

Tip: save twice: `session_raw.json` (before correction, as an archive of the
automatic result) and `session_final.json` (after verification).

**Export CSV** writes three files, one table each, ready for Excel, SPSS or R:

- `<name>_summary.csv`: metadata and statistics (`metric`, `value`): model,
  mode, segment and pair counts, `lag_mean_s`, `lag_median_s`, `lag_sd_s`,
  `lag_min_s`, `lag_max_s`, `pairs_1to1`, `merged_pairs`, `omissions_source`,
  `additions_interpreter`, `needs_review`;
- `<name>_segments.csv`: every segment of both sides (`side` =
  `source`/`interpreter`, `index`, `speaker`, `start_s`, `end_s`,
  `duration_s`, `pair`, `text`);
- `<name>_pairs.csv`: one row per pair (`evs_s`, `gap_s`, `primary_lag_s`,
  `category`, `needs_review`, texts of both sides).

Column names, category values (`Highly Responsive`, `Moderately Responsive`,
`Less Responsive`, `Unresponsive`, `Unpaired`) and file names are **always in
English**, whatever the interface language, so R/SPSS scripts do not need to
change when the language is switched.

**Interface language**: *Settings → Language / Bahasa*: English or Bahasa
Indonesia. The interface switches immediately without losing the open data,
and the choice is remembered.

---

## 9. Frequently asked questions

**Does the transcription change if I run it again?**
No. Transcription is deterministic: same file, same result.

**The source and interpreter have different numbers of segments. Is that
wrong?**
No. Interpreters naturally merge, split or skip sentences. What matters is
that the pairs are correct, not that the counts match.

**"1:1 Confidence" dropped after my corrections. Why?**
That is expected. The metric measures how many pairs are 1:1, not whether the
data are correct. Corrections that merge segments (many-to-one) move pairs out
of the 1:1 group even though they make the data more accurate. Once every ⚠ row
has been verified, your data are effectively 100 % verified, whatever the
number.

**Do unpaired utterances distort the mean EVS?**
No. They are automatically excluded from all statistics. They document
omissions and additions (a research finding in themselves).

**The waveform is empty after Open Session.**
The recordings were not found at their original path. The analysis is intact;
move the recordings back to their original location and open the session again.

**No sound when I press ▶.**
Make sure the `sounddevice` package is installed (source version) and that an
output device is active. Playback is optional; the analysis does not need it.

**Transcription takes very long.**
The `medium` model on a CPU needs several minutes for long recordings. Use
`small` for quick tests, or an NVIDIA GPU (source installation), which is used
automatically when available.

**When should I use "Re-align (DTW)"?**
Only when you want to discard all corrections and start again from the
automatic alignment, for example after extensive timestamp editing.
