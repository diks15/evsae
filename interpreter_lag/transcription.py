from __future__ import annotations

import os
from pathlib import Path
import sys

from .analysis import SOURCE_NATIVE, Segment
from .i18n import t


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def models_dir() -> Path:
    """Folder penyimpanan model. Model faster-whisper diunduh sekali ke sini."""
    directory = app_base_dir() / "models"
    directory.mkdir(exist_ok=True)
    return directory


# Cache model agar tidak dimuat ulang setiap transkripsi (pemuatan model mahal).
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}

_cuda_libraries_ready = False
# True setelah GPU terbukti tidak bisa dipakai (mis. DLL CUDA tidak ada di
# versi portable); sejak itu semua transkripsi langsung memakai CPU.
_force_cpu = False


def _ensure_cuda_libraries() -> None:
    """Daftarkan folder DLL CUDA dari paket pip nvidia-* (khusus Windows).

    Di Windows, ctranslate2 tidak otomatis menemukan DLL CUDA yang dipasang
    lewat pip (nvidia-cublas-cu12, nvidia-cudnn-cu12). Folder `bin`-nya perlu
    ditambahkan ke `PATH` agar inferensi GPU bisa berjalan.
    """
    global _cuda_libraries_ready
    if _cuda_libraries_ready:
        return
    _cuda_libraries_ready = True

    if sys.platform != "win32":
        return
    try:
        import nvidia
    except ImportError:
        return

    bin_dirs: list[str] = []
    for root in getattr(nvidia, "__path__", []):
        base = Path(root)
        if not base.is_dir():
            continue
        for package_dir in base.iterdir():
            bin_dir = package_dir / "bin"
            if bin_dir.is_dir():
                bin_dirs.append(str(bin_dir))

    if not bin_dirs:
        return

    if hasattr(os, "add_dll_directory"):
        for bin_dir in bin_dirs:
            try:
                os.add_dll_directory(bin_dir)
            except OSError:
                pass
    os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ.get("PATH", "")


def _select_device() -> tuple[str, str]:
    """Pilih perangkat & tipe komputasi.

    GPU NVIDIA dipakai bila tersedia. `int8_float16` hemat VRAM sehingga aman
    untuk GPU laptop dengan memori terbatas (mis. 4 GB), dengan akurasi yang
    praktis sama. Bila tidak ada GPU, jatuh ke CPU dengan kuantisasi int8.
    """
    if _force_cpu:
        return "cpu", "int8"
    _ensure_cuda_libraries()
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0 and _cuda_runtime_loadable():
            return "cuda", "int8_float16"
    except Exception:  # noqa: BLE001 - deteksi GPU bersifat best-effort
        pass
    return "cpu", "int8"


# DLL yang dibutuhkan ctranslate2 4.x untuk inferensi GPU di Windows.
_WINDOWS_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")


def _cuda_runtime_loadable() -> bool:
    """Cek apakah DLL CUDA benar-benar bisa dimuat.

    Driver NVIDIA saja membuat get_cuda_device_count() > 0, tetapi cuBLAS/cuDNN
    belum tentu terpasang (mis. versi portable sengaja tidak membawanya).
    Tanpa cek ini model dimuat di GPU lalu transkripsi gagal di tengah jalan.
    """
    if sys.platform != "win32":
        return True
    import ctypes

    for dll in _WINDOWS_CUDA_DLLS:
        try:
            ctypes.WinDLL(dll)
        except OSError:
            return False
    return True


def _is_cuda_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(key in message for key in ("cuda", "cublas", "cudnn", "gpu"))


def _load_model(model_name: str) -> object:
    """Muat (atau ambil dari cache) model faster-whisper.

    Bila pemuatan di GPU gagal (mis. VRAM tidak cukup), otomatis jatuh ke CPU.
    """
    from faster_whisper import WhisperModel

    device, compute_type = _select_device()
    key = (model_name, device, compute_type)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    try:
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(models_dir()),
        )
    except Exception:  # noqa: BLE001 - fallback ke CPU bila GPU bermasalah
        if device == "cpu":
            raise
        cpu_key = (model_name, "cpu", "int8")
        if cpu_key not in _MODEL_CACHE:
            _MODEL_CACHE[cpu_key] = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(models_dir()),
            )
        return _MODEL_CACHE[cpu_key]

    _MODEL_CACHE[key] = model
    return model


_SENTENCE_END_CHARS = frozenset(".!?。！？")

# Ambang deteksi "tanda baca gagal": satu segmen yang menutupi sebagian besar
# rekaman berarti Whisper mengembalikan tuturan tanpa tanda baca kalimat sama
# sekali. Lazim terjadi pada tuturan spontan bahasa Indonesia.
_UNPUNCTUATED_SHARE = 0.5
_UNPUNCTUATED_MIN_DURATION = 20.0

# Parameter pemotongan cadangan berbasis jeda antarkata.
_GAP_SPLIT_TARGET = 12.0
_GAP_SPLIT_MIN = 0.35


def _build_segment(words: list, idx: int, source: str) -> Segment | None:
    text = "".join(w.word for w in words).strip()
    if not text:
        return None
    return Segment(
        index=idx,
        start=float(words[0].start),
        end=float(words[-1].end),
        text=text,
        source=source,
    )


def _split_on_gaps(words: list) -> list[list]:
    """Pecah daftar kata di jeda terpanjang sampai tiap bagian cukup pendek.

    Dipakai hanya bila pemotongan per tanda baca gagal. Pemotongan dilakukan
    rekursif di jeda antarkata terlebar, sehingga batas segmen jatuh di tempat
    penutur benar-benar berhenti, bukan di titik waktu yang sembarang.
    """
    if len(words) < 2:
        return [words]
    start = float(words[0].start)
    duration = float(words[-1].end) - start
    if duration <= _GAP_SPLIT_TARGET:
        return [words]

    def _widest(lo: float, hi: float) -> tuple[int, float]:
        """Jeda terlebar di antara kata yang jatuh pada rentang waktu tertentu."""
        idx, widest = -1, -1.0
        for i in range(1, len(words)):
            if not lo <= float(words[i].start) - start <= hi:
                continue
            gap = float(words[i].start) - float(words[i - 1].end)
            if gap > widest:
                idx, widest = i, gap
        return idx, widest

    best_idx, best_gap = _widest(0.0, duration)
    if best_idx < 0:
        return [words]

    if best_gap < _GAP_SPLIT_MIN:
        # Tuturan mengalir tanpa jeda yang jelas. Blok yang masih sangat panjang
        # tetap dipotong, tetapi hanya di sekitar tengahnya, agar setiap potongan
        # berkurang separuh alih-alih mengelupas satu kata per pemotongan.
        if duration <= 2 * _GAP_SPLIT_TARGET:
            return [words]
        best_idx, _ = _widest(0.25 * duration, 0.75 * duration)
        if best_idx < 0:
            return [words]

    return _split_on_gaps(words[:best_idx]) + _split_on_gaps(words[best_idx:])


def _punctuation_failed(segments: list[Segment], all_words: list) -> bool:
    if not segments or not all_words:
        return False
    if len(segments) <= 1:
        return True
    span = float(all_words[-1].end) - float(all_words[0].start)
    if span <= 0:
        return False
    longest = max(seg.end - seg.start for seg in segments)
    return longest >= _UNPUNCTUATED_MIN_DURATION and longest / span >= _UNPUNCTUATED_SHARE


def _words_to_sentence_segments(
    all_words: list,
    source: str,
) -> list[Segment]:
    """Kelompokkan daftar kata (Word dari faster-whisper) menjadi segmen per kalimat.

    Pemisahan utama dilakukan di setiap kata yang diakhiri tanda baca kalimat
    (. ! ?). Pendekatan ini menyamakan granularitas antara rekaman native
    dan penerjemah sehingga DTW bisa mencocokkan kalimat-ke-kalimat,
    bukan blok-ke-blok.

    Bila ASR mengembalikan tuturan tanpa tanda baca — sehingga seluruh rekaman
    jatuh menjadi satu blok — pemotongan diulang berdasarkan jeda antarkata.
    Tanpa cadangan ini, rekaman semacam itu hanya menghasilkan satu pasangan
    dan nilai EVS-nya menjadi artefak, bukan pengukuran.
    """
    segments: list[Segment] = []
    current: list = []

    def _flush(idx: int) -> int:
        nonlocal current
        if not current:
            return idx
        segment = _build_segment(current, idx, source)
        if segment is not None:
            segments.append(segment)
            idx += 1
        current = []
        return idx

    seg_index = 1
    for word in all_words:
        current.append(word)
        # Potong di akhir kalimat (tanda baca terakhir pada kata ini).
        stripped = word.word.rstrip()
        if stripped and stripped[-1] in _SENTENCE_END_CHARS:
            seg_index = _flush(seg_index)

    # Sisa kata yang belum membentuk kalimat lengkap.
    _flush(seg_index)

    if not _punctuation_failed(segments, all_words):
        return segments

    rebuilt: list[Segment] = []
    for chunk in _split_on_gaps(list(all_words)):
        segment = _build_segment(chunk, len(rebuilt) + 1, source)
        if segment is not None:
            rebuilt.append(segment)
    return rebuilt or segments


def transcribe_media(
    file_path: str,
    model_name: str = "small",
    language: str | None = None,
    source: str = SOURCE_NATIVE,
) -> list[Segment]:
    """Transkripsi satu file audio/video menjadi daftar Segment per kalimat.

    Menggunakan word_timestamps dari faster-whisper lalu memecah hasilnya
    di batas tanda baca kalimat. Dengan cara ini granularitas segmen native
    dan penerjemah setara (per kalimat), sehingga DTW bisa mencocokkan
    kalimat-ke-kalimat dan nilai EVS menjadi akurat.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(t("err.file_not_found", path=file_path))

    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(t("err.no_whisper")) from exc

    global _force_cpu
    model = _load_model(model_name)
    try:
        return _transcribe_with(model, path, language, source)
    except RuntimeError as exc:
        # Pengaman terakhir: GPU terdeteksi tetapi gagal saat inferensi.
        if _force_cpu or not _is_cuda_error(exc):
            raise
        _force_cpu = True
        model = _load_model(model_name)
        return _transcribe_with(model, path, language, source)


def _transcribe_with(
    model: object, path: Path, language: str | None, source: str
) -> list[Segment]:
    segments_iter, _info = model.transcribe(
        str(path),
        language=language,
        word_timestamps=True,
        temperature=0.0,
        beam_size=5,
        # Buang bagian senyap sebelum inferensi. Tanpa ini, Whisper kerap
        # mengarang teks pada keheningan panjang (mis. "Terima kasih telah
        # menonton"), yang menggeser penanda waktu awal ujaran dan merusak EVS.
        vad_filter=True,
    )

    # Kumpulkan semua kata dari seluruh segmen Whisper.
    all_words: list = []
    for item in segments_iter:
        if item.words:
            all_words.extend(item.words)

    # Bila tidak ada word_timestamps (model sangat kecil), fallback ke segmen Whisper.
    if not all_words:
        segments_iter2, _info2 = model.transcribe(
            str(path),
            language=language,
            word_timestamps=False,
            temperature=0.0,
            beam_size=5,
            vad_filter=True,
        )
        return [
            Segment(
                index=i,
                start=float(item.start),
                end=float(item.end),
                text=str(item.text).strip(),
                source=source,
            )
            for i, item in enumerate(segments_iter2, start=1)
        ]

    return _words_to_sentence_segments(all_words, source)
