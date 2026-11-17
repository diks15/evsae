"""Teks antarmuka EVSAE dalam dua bahasa (English / Bahasa Indonesia).

Semua teks yang tampil ke pengguna diambil lewat ``t(kunci, **nilai)``. Bahasa
aktif disimpan di berkas pengaturan per pengguna sehingga pilihan tetap berlaku
saat aplikasi dibuka kembali. Istilah English mengikuti glosarium yang disepakati
tim (BSu/BSa -> SL/TL, pasangan -> pair, Lepas Segmen -> Detach Segment, dst.).

Nama kategori jeda di ``analysis.py`` tetap menjadi kunci internal (dipakai juga
untuk warna dan tag tabel); terjemahannya diambil lewat ``category_label``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LANGUAGES: dict[str, str] = {"en": "English", "id": "Bahasa Indonesia"}
DEFAULT_LANGUAGE = "en"

# kunci -> (English, Bahasa Indonesia)
STRINGS: dict[str, tuple[str, str]] = {
    # ---------------------------------------------------------------- kepala
    "app.title": (
        "Ear-Voice Span Analysis and Editing (EVSAE) v1.0",
        "Ear-Voice Span Analysis and Editing (EVSAE) v1.0",
    ),
    "app.subtitle": (
        "Interpreter lag analysis from source- and target-language recordings",
        "Analisis jeda juru bahasa dari rekaman Bahasa Sumber dan Bahasa Sasaran",
    ),
    "app.footer": (
        "Faculty of Language and Literature Education  ·  Universitas Pendidikan Indonesia"
        "  ·  Funded by BIMA Kemdiktisaintek",
        "Fakultas Pendidikan Bahasa dan Sastra  ·  Universitas Pendidikan Indonesia"
        "  ·  Didanai oleh BIMA Kemdiktisaintek",
    ),
    # ------------------------------------------------------------ panel kiri
    "side.input1": ("Input 1 · Source Language (SL)", "Input 1 · Bahasa Sumber (BSu)"),
    "side.input2": ("Input 2 · Target Language (TL)", "Input 2 · Bahasa Sasaran (BSa)"),
    "file.none_sl": ("No SL file selected", "Belum ada file BSu"),
    "file.none_tl": ("No TL file selected{suffix}", "Belum ada file BSa{suffix}"),
    "btn.choose_sl": ("Choose SL File", "Pilih File BSu"),
    "btn.choose_tl": ("Choose TL File{suffix}", "Pilih File BSa{suffix}"),
    "side.offset": ("Start offset (s)", "Offset mulai (detik)"),
    "side.interp_count": ("Number of Interpreters", "Jumlah Penerjemah"),
    "btn.split": ("Split Mixed Recording…", "Pisahkan Rekaman Campuran…"),
    "hint.split": (
        "Split Recording: if 2+ interpreters are in ONE recording, detect and split it "
        "into one file per speaker first. Offset shifts every timestamp of a recording "
        "(seconds, may be negative) when the recordings do not start together.",
        "Pisahkan Rekaman: bila 2+ penerjemah ada dalam SATU rekaman, deteksi & pisahkan "
        "dulu menjadi file per penutur. Offset menggeser seluruh timestamp rekaman "
        "(detik, boleh negatif) bila rekaman tidak dimulai bersamaan.",
    ),
    "side.settings": ("Settings", "Pengaturan"),
    "side.language": ("Language / Bahasa", "Bahasa / Language"),
    "side.model": ("Whisper Model", "Model Whisper"),
    "side.mode": ("Interpreting Mode", "Mode Interpreting"),
    "hint.mode": (
        "Simultaneous → EVS (onset to onset). "
        "Consecutive → gap (end of source to interpreter onset).",
        "Simultaneous → acuan EVS (awal ke awal). "
        "Consecutive → acuan gap (akhir native ke awal penerjemah).",
    ),
    "btn.analyze": ("Transcribe & Analyze", "Transcribe & Analyze"),
    "btn.processing": ("Processing...", "Memproses..."),
    "btn.demo": ("Load Demo", "Load Demo"),
    "btn.export": ("Export CSV", "Export CSV"),
    "btn.save_session": ("Save Session", "Simpan Sesi"),
    "btn.open_session": ("Open Session", "Buka Sesi"),
    "side.correction": ("Pair Correction", "Koreksi Pasangan"),
    "hint.correction": (
        "Pair Selected: select 1 source utterance + 1 target utterance. "
        "Add to Pair: select the destination pair in Lag Results + segments in the "
        "transcript tabs. Detach Segment: remove a segment from its pair "
        "(e.g. an utterance that was not interpreted).",
        "Pasangkan: pilih 1 ujaran sumber + 1 ujaran sasaran. "
        "Tambah ke Pasangan: pilih pasangan tujuan di Hasil Lag + segmen "
        "di tab transkrip. Lepas Segmen: keluarkan segmen dari pasangannya "
        "(mis. ujaran yang tidak diterjemahkan).",
    ),
    "btn.pair": ("Pair Selected", "Pasangkan Terpilih"),
    "btn.attach": ("Add to Pair", "Tambah ke Pasangan"),
    "btn.detach": ("Detach Segment", "Lepas Segmen"),
    "btn.remove_pair": ("Delete Pair", "Hapus Pasangan"),
    "btn.realign": ("Re-align (DTW)", "Selaraskan (DTW)"),
    "side.status": ("STATUS", "STATUS"),
    # ------------------------------------------------------- tab dan tabel
    "tab.sl": ("  SL Transcript (Input 1)  ", "  Transkrip BSu (Input 1)  "),
    "tab.tl": ("  TL Transcript (Input 2)  ", "  Transkrip BSa (Input 2)  "),
    "tab.waveform": ("  Waveform Editor  ", "  Editor Waveform  "),
    "tab.lag": ("  Lag Results  ", "  Hasil Lag  "),
    "tab.viz": ("  Visualization  ", "  Visualisasi  "),
    "card.pairs": ("Complete Pairs", "Pasangan Lengkap"),
    "card.mean": ("Mean Lag", "Rata-rata Lag"),
    "card.min": ("Shortest Lag", "Lag Tercepat"),
    "card.max": ("Longest Lag", "Lag Terlama"),
    "card.confidence": ("1:1 Confidence", "Keyakinan 1:1"),
    "col.speaker": ("Speaker", "Penutur"),
    "col.start": ("Start", "Start"),
    "col.end": ("End", "End"),
    "col.duration": ("Duration", "Durasi"),
    "col.pair": ("Pair", "Pasangan"),
    "col.text": ("Transcript", "Transkrip"),
    "col.category": ("Category", "Kategori"),
    "col.check": ("Review", "Cek"),
    "col.sl": ("Input 1 — SL", "Input 1 — BSu"),
    "col.tl": ("Input 2 — TL", "Input 2 — BSa"),
    "hint.edit_cell": (
        "Double-click a Start, End, or Transcript cell to edit it.",
        "Klik dua kali sel Start, End, atau Transkrip untuk menyuntingnya.",
    ),
    "chunk.unpaired": ("— (unpaired)", "— (tidak berpasangan)"),
    # --------------------------------------------------------------- legenda
    "legend.title": ("LAG CATEGORY REFERENCE", "ACUAN KATEGORI JEDA"),
    "legend.range": ("{lower} – {upper} s", "{lower} – {upper} detik"),
    "legend.range_open": ("> {lower} s", "> {lower} detik"),
    "legend.review_note": (
        "⚠ in the Review column = merged pair (many-to-one), negative EVS, "
        "or unpaired — manual verification recommended.",
        "⚠ pada kolom Cek = chunk gabungan (banyak-ke-satu), EVS negatif, "
        "atau tanpa pasangan — disarankan verifikasi manual.",
    ),
    # ----------------------------------------------------------- visualisasi
    "viz.no_data": ("No analysis data yet.", "Belum ada data analisis."),
    "viz.quality": (
        "Automatic alignment confidence: {one} of {paired} pairs are 1:1 ({pct})"
        "  ·  needs manual review (⚠): {review}  ·  unpaired: {orphans}",
        "Keyakinan alignment otomatis: {one} dari {paired} pasangan bersifat 1:1 ({pct})"
        "  ·  perlu verifikasi manual (⚠): {review}  ·  tanpa pasangan: {orphans}",
    ),
    "stat.median": ("Median Lag", "Median Lag"),
    "stat.sd": ("Standard Deviation", "Simpangan Baku"),
    "stat.merged": ("Merged Pairs", "Chunk Gabungan"),
    "stat.omissions": ("Omissions (SL)", "Omisi (Native)"),
    "stat.additions": ("Additions (TL)", "Adisi (Penerjemah)"),
    "chart.distribution": ("Lag Category Distribution", "Distribusi Kategori Jeda"),
    "chart.empty": ("No data yet", "Belum ada data"),
    "chart.pairs_unit": ("pairs", "pasangan"),
    "chart.per_pair": ("{label} per Pair (s)", "Nilai {label} per Pasangan (detik)"),
    "chart.no_pairs": ("No pairs with lag values yet", "Belum ada pasangan dengan nilai lag"),
    "chart.mean": ("mean {value}s", "rata-rata {value}s"),
    "chart.x_axis": ("Pair Number", "Nomor Pasangan"),
    "chart.y_axis": ("s", "detik"),
    # ------------------------------------------------------- pesan status
    "st.initial": (
        "Choose two files: Input 1 (SL) and Input 2 (TL).",
        "Pilih dua file: Input 1 (BSu) dan Input 2 (BSa).",
    ),
    "st.language": ("Language: English.", "Bahasa: Bahasa Indonesia."),
    "st.only_editable": (
        "Only the Start, End, and Transcript columns can be edited.",
        "Hanya kolom Start, End, dan Transkrip yang bisa disunting.",
    ),
    "st.bad_number": (
        "'{value}' is not a valid number of seconds - change discarded.",
        "'{value}' bukan angka detik yang sah - perubahan dibatalkan.",
    ),
    "st.negative": (
        "Time cannot be negative - change discarded.",
        "Waktu tidak boleh negatif - perubahan dibatalkan.",
    ),
    "st.start_after_end": (
        "Start cannot be later than End - change discarded.",
        "Start tidak boleh melewati End - perubahan dibatalkan.",
    ),
    "st.end_before_start": (
        "End cannot be earlier than Start - change discarded.",
        "End tidak boleh mendahului Start - perubahan dibatalkan.",
    ),
    "st.segment_updated": (
        "Segment updated. Lag recomputed from the new timestamps.",
        "Segmen diperbarui. Lag dihitung ulang dari timestamp baru.",
    ),
    "st.sl_ready": (
        "Source file ready. Choose the target file too, then click Transcribe & Analyze.",
        "File sumber siap. Pilih juga file sasaran lalu klik Transcribe & Analyze.",
    ),
    "st.tl_ready": (
        "Interpreter file{suffix} ready. Make sure the other files are selected too.",
        "File penerjemah{suffix} siap. Pastikan file lainnya sudah dipilih juga.",
    ),
    "demo.sl": ("Demo: English speech", "Demo: pidato Inggris"),
    "demo.tl": ("Demo: Indonesian interpretation", "Demo: terjemahan Indonesia"),
    "st.demo_loaded": (
        "Demo loaded. Open the Waveform Editor or Lag Results tab to review.",
        "Demo dimuat. Buka tab Editor Waveform atau Hasil Lag untuk meninjau.",
    ),
    "st.transcribing": (
        "Transcribing... the window remains usable.",
        "Memproses transkripsi. Window tetap bisa digunakan.",
    ),
    "st.transcribe_sl": (
        "Transcribing Input 1 - Source Language (SL)...",
        "Transkripsi Input 1 - Bahasa Sumber (BSu)...",
    ),
    "st.transcribe_tl": (
        "Transcribing Input 2 - Target Language (TL){progress} (Indonesian)...",
        "Transkripsi Input 2 - Bahasa Sasaran (BSa){progress} (Indonesia)...",
    ),
    "st.loading_audio": (
        "Loading audio for the Waveform Editor...",
        "Memuat audio untuk Editor Waveform...",
    ),
    "st.analysis_done": (
        "Analysis complete. Open the Waveform Editor to correct timestamps, "
        "or Lag Results to view the results.",
        "Analisis selesai. Buka Editor Waveform untuk mengoreksi timestamp, "
        "atau Hasil Lag untuk melihat hasil.",
    ),
    "st.analysis_failed": ("Analysis failed.", "Analisis gagal."),
    "st.mode": ("Interpreting mode: {mode}.", "Mode interpreting: {mode}."),
    "st.pair_created": (
        "Pair created: source #{source} <-> interpreter #{interpreter}.",
        "Pasangan dibuat: native #{source} <-> penerjemah #{interpreter}.",
    ),
    "st.attached": (
        "Segment {labels} added to pair. EVS recomputed from the first segment "
        "onset on each side.",
        "Segmen {labels} dimasukkan ke pasangan. EVS dihitung ulang dari onset "
        "segmen pertama tiap sisi.",
    ),
    "st.detached": (
        "Segment {labels} detached and left unpaired (excluded from statistics).",
        "Segmen {labels} dilepas menjadi tanpa pasangan (tidak masuk statistik).",
    ),
    "label.source": ("source", "native"),
    "label.interpreter": ("interpreter", "penerjemah"),
    "st.pair_removed": (
        "Pair removed from the analysis. Its segments remain in the transcript tabs.",
        "Pasangan dihapus dari analisis. Segmen tetap ada di tab transkrip.",
    ),
    "st.realigned": (
        "Pairs re-aligned with DTW (sentence alignment).",
        "Pasangan diselaraskan ulang dengan DTW (alignment kalimat).",
    ),
    "st.session_saved": ("Session saved: {name}", "Sesi tersimpan: {name}"),
    "st.session_loaded": (
        "Session loaded: {name}. All pairs and manual corrections restored.",
        "Sesi dimuat: {name}. Semua pasangan dan koreksi manual dipulihkan.",
    ),
    "st.exported": (
        "3 CSV files saved: {base}_summary / _segments / _pairs.csv",
        "3 file CSV tersimpan: {base}_summary / _segments / _pairs.csv",
    ),
    "st.boundary_adjusted": (
        "Segment boundary adjusted. Lag recomputed.",
        "Batas segmen disesuaikan. Lag dihitung ulang.",
    ),
    # ---------------------------------------------------- kotak dialog
    "msg.info": ("Info", "Info"),
    "msg.warning": ("Warning", "Peringatan"),
    "msg.error": ("Error", "Error"),
    "msg.confirm": ("Confirm", "Konfirmasi"),
    "msg.choose_all": (
        "Choose all files first: Input 1 (SL) and Input 2 (TL).",
        "Pilih semua file dulu: Input 1 (BSu) dan Input 2 (BSa).",
    ),
    "msg.missing_slots": (
        " Interpreter files incomplete (slot {slots}).",
        " File penerjemah belum lengkap (slot {slots}).",
    ),
    "msg.pick_pair_rows": (
        "Select exactly 1 row in the SL Transcript tab AND 1 row in the TL Transcript tab.",
        "Pilih tepat 1 baris di tab Transkrip BSu DAN 1 baris di tab Transkrip BSa.",
    ),
    "msg.pick_target_pair": (
        "Select 1 destination pair row in the Lag Results tab first.",
        "Pilih 1 baris pasangan tujuan di tab Hasil Lag dulu.",
    ),
    "msg.pick_attach": (
        "Select the segments in the SL/TL Transcript tabs to add to that pair.",
        "Pilih segmen di tab Transkrip BSu/BSa yang akan dimasukkan ke pasangan tersebut.",
    ),
    "msg.pick_detach": (
        "Select the segments in the SL/TL Transcript tabs to detach from their pairs.",
        "Pilih segmen di tab Transkrip BSu/BSa yang akan dilepas dari pasangannya.",
    ),
    "msg.pick_pair_row": (
        "Select 1 pair row in the Lag Results tab.",
        "Pilih 1 baris pasangan di tab Hasil Lag.",
    ),
    "msg.no_transcripts": (
        "There are no transcripts for both inputs yet.",
        "Belum ada transkrip untuk kedua input.",
    ),
    "msg.realign_confirm": (
        "Re-aligning with DTW recomputes all pairs from scratch and DISCARDS every "
        "manual correction (Add to Pair, Detach Segment, etc.).\n\nSave the session "
        "first to keep your corrections. Continue?",
        "Selaraskan ulang dengan DTW akan menghitung semua pasangan dari nol dan "
        "MENGHAPUS seluruh koreksi manual (Tambah ke Pasangan, Lepas Segmen, dll.)."
        "\n\nSimpan Sesi dulu bila koreksi ingin dipertahankan. Lanjutkan?",
    ),
    "msg.nothing_to_save": (
        "There is no analysis data to save yet.",
        "Belum ada data analisis untuk disimpan.",
    ),
    "msg.open_failed": ("Could not open the session: {error}", "Gagal membuka sesi: {error}"),
    "msg.nothing_to_export": (
        "There are no transcripts to export yet.",
        "Belum ada transkrip untuk diexport.",
    ),
    "err.not_session": ("Not an EVSAE session file", "Bukan file sesi EVSAE"),
    "err.file_not_found": ("File not found: {path}", "File tidak ditemukan: {path}"),
    "err.no_whisper": (
        "The faster-whisper package is not installed. "
        "Run: pip install -r requirements.txt",
        "Package faster-whisper belum terpasang. "
        "Jalankan: pip install -r requirements.txt",
    ),
    # ------------------------------------------------- jendela pilih berkas
    "dlg.choose_sl": (
        "Choose the SL audio/video file (Input 1)",
        "Pilih file audio/video BSu (Input 1)",
    ),
    "dlg.choose_tl": (
        "Choose the TL audio/video file{suffix} (Input 2)",
        "Pilih file audio/video BSa{suffix} (Input 2)",
    ),
    "dlg.media_files": ("Media Files", "File Media"),
    "dlg.all_files": ("All Files", "Semua File"),
    "dlg.session_files": ("Session Files", "File Sesi"),
    "dlg.csv_files": ("CSV Files", "File CSV"),
    "dlg.save_session": ("Save analysis session", "Simpan sesi analisis"),
    "dlg.open_session": ("Open analysis session", "Buka sesi analisis"),
    "dlg.export": ("Save results (as 3 CSV files)", "Simpan hasil analisis (menjadi 3 file CSV)"),
    "file.session_default": ("evsae_session.json", "sesi_evsae.json"),
    "file.export_default": ("lag_analysis.csv", "analisis_lag.csv"),
    # ----------------------------------------------------- editor waveform
    "wave.play_sl": ("▶  Source", "▶  Native"),
    "wave.play_tl": ("▶  Interpreter", "▶  Penerjemah"),
    "wave.play_mix": ("▶  Mix", "▶  Mix"),
    "wave.stop": ("■  Stop", "■  Stop"),
    "wave.tier_sl": ("Source (English)", "Native (Inggris)"),
    "wave.tier_tl": ("Interpreter (Indonesian)", "Penerjemah (Indonesia)"),
    "wave.no_audio": ("(audio not loaded)", "(audio belum dimuat)"),
    "wave.hint": (
        "Drag a vertical line to move a segment boundary. Mouse wheel = zoom, "
        "right-drag (Mac: Ctrl+drag) = pan. Playback starts at the left edge of the view.",
        "Seret garis vertikal untuk mengatur batas segmen. Scroll mouse = zoom, "
        "klik-kanan-seret (Mac: Ctrl+seret) = geser horizontal. Pemutaran dimulai dari awal tampilan saat ini.",
    ),
    "wave.need_sounddevice": (
        "Playback needs the 'sounddevice' package. Run: pip install sounddevice",
        "Pemutaran butuh package 'sounddevice'. Jalankan: pip install sounddevice",
    ),
    "wave.nothing_to_play": ("Audio is not loaded for playback.", "Audio belum dimuat untuk diputar."),
    "wave.play_failed": ("Could not play audio: {error}", "Gagal memutar audio: {error}"),
    # ------------------------------------------- dialog pisahkan rekaman
    "split.title": ("Split Multi-Interpreter Recording", "Pisahkan Rekaman Multi-Penerjemah"),
    "split.none": ("No file selected", "Belum ada rekaman campuran"),
    "split.choose": ("Choose Mixed Recording", "Pilih Rekaman Campuran"),
    "split.count": ("Number of Speakers", "Jumlah Penutur"),
    "split.detect": ("Detect Speakers", "Deteksi Penutur"),
    "split.initial": (
        "Choose a recording that contains several interpreters, then click Detect Speakers.",
        "Pilih rekaman berisi beberapa penerjemah, lalu klik Deteksi Penutur.",
    ),
    "split.col_start": ("Start", "Mulai"),
    "split.col_end": ("End", "Selesai"),
    "split.play": ("▶  Play Utterance", "▶  Putar Ujaran"),
    "split.move_to": ("Move selected utterances to:", "Pindahkan ujaran terpilih ke:"),
    "split.apply": ("Apply", "Terapkan"),
    "split.note": (
        "Save & Use writes <name>_P1.wav etc. to the recording's folder (original timing "
        "preserved) and fills the Input 2 slots directly.",
        "Simpan & Gunakan menulis file <nama>_P1.wav dst. di folder rekaman "
        "(posisi waktu asli dipertahankan) dan langsung mengisi slot Input 2.",
    ),
    "split.cancel": ("Cancel", "Batal"),
    "split.use": ("Save & Use", "Simpan & Gunakan Hasil"),
    "split.dlg_choose": (
        "Choose a recording that contains several interpreters",
        "Pilih rekaman berisi beberapa penerjemah",
    ),
    "split.ready": ("Recording ready. Click Detect Speakers.", "Rekaman siap. Klik Deteksi Penutur."),
    "split.pick_first": ("Choose the mixed recording first.", "Pilih rekaman campurannya dulu."),
    "split.detecting": (
        "Detecting utterances and grouping speakers...",
        "Mendeteksi ujaran dan mengelompokkan penutur...",
    ),
    "split.err_empty": ("The audio is empty or could not be read.", "Audio kosong atau gagal dibaca."),
    "split.err_few": (
        "Too few utterances were detected to split.",
        "Ujaran terdeteksi terlalu sedikit untuk dipisahkan.",
    ),
    "split.failed": ("Detection failed.", "Deteksi gagal."),
    "split.count_item": ("P{speaker}: {count} utterances", "P{speaker}: {count} ujaran"),
    "split.detected": (
        "{total} utterances detected ({detail}). Listen to a sample of each speaker "
        "and correct if needed.",
        "{total} ujaran terdeteksi ({detail}). Dengarkan sampel tiap penutur dan "
        "koreksi bila perlu.",
    ),
    "split.pick_play": (
        "Select one utterance in the table to listen to it.",
        "Pilih satu ujaran di tabel untuk didengarkan.",
    ),
    "split.play_failed": ("Could not play: {error}", "Gagal memutar: {error}"),
    "split.pick_move": ("Select the utterances to move first.", "Pilih ujaran yang mau dipindahkan dulu."),
    "split.moved": ("{count} utterances moved to P{speaker}.", "{count} ujaran dipindahkan ke P{speaker}."),
    "split.write_failed": ("Could not write the file: {error}", "Gagal menulis file: {error}"),
    "split.done": (
        "Recording split into {count} speaker files and loaded into the Input 2 slots. "
        "Choose the SL file, then Transcribe & Analyze.",
        "Rekaman dipisah menjadi {count} file penutur dan mengisi slot Input 2. "
        "Pilih file BSu lalu Transcribe & Analyze.",
    ),
}

# Kategori jeda: kunci internal (nama di analysis.py) -> (nama, keterangan) per bahasa.
CATEGORIES: dict[str, dict[str, tuple[str, str]]] = {
    "Sangat Responsif": {
        "en": ("Highly Responsive", "Ideal interpreter response"),
        "id": ("Sangat Responsif", "Reaksi ideal interpreter"),
    },
    "Cukup Responsif": {
        "en": ("Moderately Responsive", "Within the normal range"),
        "id": ("Cukup Responsif", "Masih dalam batas wajar"),
    },
    "Kurang Responsif": {
        "en": ("Less Responsive", "Noticeable hesitation"),
        "id": ("Kurang Responsif", "Mulai terasa hesitasi"),
    },
    "Tidak Responsif": {
        "en": ("Unresponsive", "Excessive delay"),
        "id": ("Tidak Responsif", "Jeda berlebihan"),
    },
    "Tidak Berpasangan": {
        "en": ("Unpaired", "Utterance has no pair"),
        "id": ("Tidak Berpasangan", "Ujaran tidak memiliki pasangan"),
    },
}

_LANG_INDEX = {"en": 0, "id": 1}
_current: str | None = None


def settings_path() -> Path:
    """Berkas pengaturan per pengguna (bisa dialihkan lewat EVSAE_SETTINGS_DIR)."""
    override = os.environ.get("EVSAE_SETTINGS_DIR")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home()) / "EVSAE"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "evsae"
    return base / "settings.json"


def _read_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_language() -> str:
    global _current
    if _current is None:
        stored = _read_settings().get("language")
        _current = stored if stored in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def set_language(code: str, persist: bool = True) -> None:
    """Ganti bahasa aktif; simpan pilihan bila memungkinkan (gagal simpan diabaikan)."""
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"Unknown language: {code}")
    _current = code
    if not persist:
        return
    data = _read_settings()
    data["language"] = code
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass  # pilihan tetap berlaku untuk sesi ini


def t(key: str, **values: object) -> str:
    """Teks untuk kunci pada bahasa aktif; kunci tak dikenal dikembalikan apa adanya."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry[_LANG_INDEX[get_language()]]
    return text.format(**values) if values else text


def category_label(name: str, lang: str | None = None) -> str:
    entry = CATEGORIES.get(name)
    return entry[lang or get_language()][0] if entry else name


def category_description(name: str, lang: str | None = None) -> str:
    entry = CATEGORIES.get(name)
    return entry[lang or get_language()][1] if entry else ""
