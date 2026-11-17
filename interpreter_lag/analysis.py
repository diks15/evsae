from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median, stdev


# Dua sumber input yang dianalisis.
#   SOURCE_NATIVE      -> Input 1, ujaran pembicara asli (mis. bahasa Inggris).
#   SOURCE_INTERPRETER -> Input 2, ujaran penerjemah/juru bahasa (mis. Indonesia).
SOURCE_NATIVE = "NATIVE"
SOURCE_INTERPRETER = "INTERPRETER"

# Mode interpreting menentukan ukuran lag mana yang dipakai sebagai angka utama.
#   simultaneous -> native & penerjemah bicara bersamaan, ukuran utama = EVS.
#   consecutive  -> penerjemah bicara setelah native berhenti, ukuran utama = gap.
MODE_SIMULTANEOUS = "simultaneous"
MODE_CONSECUTIVE = "consecutive"

# Parameter penjodohan DTW (lihat align_segments).
#   ANTICIPATION_TOLERANCE: seberapa jauh penerjemah boleh "mendahului" native
#     (detik) sebelum dianggap mustahil. Antisipasi kecil wajar dalam interpreting.
#   ANTICIPATION_WEIGHT: pengali biaya untuk lag negatif DI DALAM toleransi.
#     Tanpa bobot ini DTW justru menyukai lag senegatif mungkin (biaya = lag),
#     sehingga memperlebar toleransi malah menambah salah-pasang. Dengan bobot,
#     pasangan lag positif kecil selalu lebih murah daripada antisipasi.
#   CAUSALITY_PENALTY: bobot penalti untuk lag yang lebih negatif dari toleransi.
ANTICIPATION_TOLERANCE = 3.0
ANTICIPATION_WEIGHT = 8.0
CAUSALITY_PENALTY = 100.0


@dataclass
class Segment:
    """Satu ujaran hasil transkripsi salah satu input, beserta timestamp-nya.

    speaker: label penutur untuk mode multi-penerjemah (mis. "P1", "P2").
    Kosong untuk native atau bila hanya ada satu penerjemah tanpa label.
    """

    index: int
    start: float
    end: float
    text: str
    source: str = SOURCE_NATIVE
    speaker: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class LagRecord:
    """Satu chunk: kelompok ujaran native yang berpasangan dengan kelompok
    ujaran penerjemah yang menerjemahkannya.

    Karena Whisper memotong kedua rekaman dengan granularitas berbeda, satu
    chunk bisa berisi beberapa segmen di salah satu/kedua sisi (hubungan
    banyak-ke-satu). Salah satu sisi boleh kosong (orphan) - ujaran tetap
    disimpan agar tidak hilang dari laporan, tetapi tidak masuk statistik.

    EVS/gap diukur dari segmen PERTAMA tiap sisi (onset chunk).
    """

    pair_index: int
    natives: list[Segment] = field(default_factory=list)
    interpreters: list[Segment] = field(default_factory=list)

    @property
    def native(self) -> Segment | None:
        """Segmen native pertama dalam chunk (representatif onset)."""
        return self.natives[0] if self.natives else None

    @property
    def interpreter(self) -> Segment | None:
        """Segmen penerjemah pertama dalam chunk (representatif onset)."""
        return self.interpreters[0] if self.interpreters else None

    @property
    def is_paired(self) -> bool:
        return bool(self.natives) and bool(self.interpreters)

    @property
    def native_text(self) -> str:
        return " ".join(seg.text for seg in self.natives).strip()

    @property
    def interpreter_text(self) -> str:
        return " ".join(seg.text for seg in self.interpreters).strip()

    @property
    def evs(self) -> float | None:
        """Ear-Voice Span: jeda dari ONSET native ke ONSET penerjemah.

            evs = waktu mulai penerjemah pertama - waktu mulai native pertama

        Ini ukuran baku jeda interpreter (decalage) dan menjadi angka utama
        untuk simultaneous interpreting.
        """
        if not self.is_paired:
            return None
        return self.interpreters[0].start - self.natives[0].start

    @property
    def gap(self) -> float | None:
        """Jeda antar-giliran: dari AKHIR native ke ONSET penerjemah.

            gap = waktu mulai penerjemah pertama - waktu selesai native terakhir

        Cocok sebagai angka utama untuk consecutive interpreting (penerjemah
        baru bicara setelah native selesai). Bisa negatif bila tumpang tindih.
        """
        if not self.is_paired:
            return None
        native_end = max(seg.end for seg in self.natives)
        return self.interpreters[0].start - native_end

    def lag_for(self, mode: str) -> float | None:
        """Ambil ukuran lag yang relevan dengan mode interpreting terpilih."""
        if mode == MODE_CONSECUTIVE:
            return self.gap
        return self.evs


# Kategori jeda interpreter berdasarkan acuan peneliti (satuan detik).
CATEGORY_VERY_RESPONSIVE = "Sangat Responsif"
CATEGORY_FAIRLY_RESPONSIVE = "Cukup Responsif"
CATEGORY_LESS_RESPONSIVE = "Kurang Responsif"
CATEGORY_NOT_RESPONSIVE = "Tidak Responsif"
CATEGORY_UNPAIRED = "Tidak Berpasangan"

# Tiap entri: (nama_kategori, batas_atas_detik, deskripsi). Diurutkan dari
# paling responsif. Batas atas None berarti tak terhingga. Untuk mengubah
# kalibrasi ambang, cukup sunting tabel ini.
LAG_CATEGORIES: tuple[tuple[str, float | None, str], ...] = (
    (CATEGORY_VERY_RESPONSIVE, 5.0, "Reaksi ideal interpreter"),
    (CATEGORY_FAIRLY_RESPONSIVE, 10.0, "Masih dalam batas wajar"),
    (CATEGORY_LESS_RESPONSIVE, 15.0, "Mulai terasa hesitasi"),
    (CATEGORY_NOT_RESPONSIVE, None, "Jeda berlebihan"),
)

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    name: description for name, _upper, description in LAG_CATEGORIES
}
CATEGORY_DESCRIPTIONS[CATEGORY_UNPAIRED] = "Ujaran tidak memiliki pasangan"


def lag_category(lag_seconds: float | None) -> str:
    """Klasifikasikan nilai lag (detik) ke kategori acuan peneliti.

    Ambang: <=5 Sangat Responsif (termasuk nilai negatif/tumpang tindih),
    >5..<=10 Cukup Responsif, >10..<=15 Kurang Responsif, >15 Tidak Responsif.
    """
    if lag_seconds is None:
        return CATEGORY_UNPAIRED
    for name, upper, _description in LAG_CATEGORIES:
        if upper is None or lag_seconds <= upper:
            return name
    return CATEGORY_NOT_RESPONSIVE


def _sort_key(record: LagRecord) -> float:
    if record.natives:
        return record.natives[0].start
    if record.interpreters:
        return record.interpreters[0].start
    return 0.0


def renumber_pairs(records: list[LagRecord]) -> list[LagRecord]:
    """Urutkan chunk menurut waktu dan beri ulang nomor pair_index."""
    ordered = sorted(records, key=_sort_key)
    for number, record in enumerate(ordered, start=1):
        record.pair_index = number
    return ordered


def _dtw_align(
    natives: list[Segment],
    interpreters: list[Segment],
) -> list[tuple[int, int]]:
    """Selaraskan dua urutan segmen dengan DTW (dynamic time warping).

    Mengembalikan jalur monotonik berisi pasangan indeks (i, j). Membolehkan
    banyak-ke-satu/satu-ke-banyak sehingga beda granularitas segmen antara
    kedua rekaman tidak menyebabkan drift seperti penjodohan greedy.

    Biaya bersifat KAUSAL: penerjemah yang mulai jauh sebelum native (lag <
    -ANTICIPATION_TOLERANCE) diberi penalti berat, karena penerjemah tidak
    mungkin menerjemahkan sebelum mendengar. Lag negatif di dalam toleransi
    dikenai bobot ANTICIPATION_WEIGHT agar lag positif kecil selalu lebih
    disukai daripada antisipasi.
    """
    a, b = len(natives), len(interpreters)
    if a == 0 or b == 0:
        return []

    inf = float("inf")
    cost_matrix = [[0.0] * b for _ in range(a)]
    for i in range(a):
        ni = natives[i].start
        for j in range(b):
            lag = interpreters[j].start - ni
            if lag < -ANTICIPATION_TOLERANCE:
                cost_matrix[i][j] = (
                    1000.0 + (-ANTICIPATION_TOLERANCE - lag) * CAUSALITY_PENALTY
                )
            elif lag < 0:
                cost_matrix[i][j] = -lag * ANTICIPATION_WEIGHT
            else:
                cost_matrix[i][j] = lag

    # Akumulasi DTW.
    acc = [[inf] * (b + 1) for _ in range(a + 1)]
    acc[0][0] = 0.0
    for i in range(1, a + 1):
        for j in range(1, b + 1):
            acc[i][j] = cost_matrix[i - 1][j - 1] + min(
                acc[i - 1][j - 1], acc[i - 1][j], acc[i][j - 1]
            )

    # Backtrack (utamakan langkah diagonal saat seri).
    i, j = a, b
    path: list[tuple[int, int]] = []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        diag, up, left = acc[i - 1][j - 1], acc[i - 1][j], acc[i][j - 1]
        best = min(diag, up, left)
        if best == diag:
            i, j = i - 1, j - 1
        elif best == up:
            i -= 1
        else:
            j -= 1
    path.reverse()
    return path


def align_segments(
    native_segments: list[Segment],
    interpreter_segments: list[Segment],
) -> list[LagRecord]:
    """Bentuk chunk pasangan native<->penerjemah memakai DTW kausal.

    Jalur DTW dikelompokkan menjadi chunk (komponen terhubung): bila beberapa
    segmen native dipetakan ke satu segmen penerjemah (atau sebaliknya), mereka
    menjadi satu chunk. EVS tiap chunk diukur dari onset segmen pertama.
    """
    natives = sorted(native_segments, key=lambda seg: seg.start)
    interpreters = sorted(interpreter_segments, key=lambda seg: seg.start)

    if not natives and not interpreters:
        return []
    if not natives:
        return renumber_pairs([LagRecord(0, [], [seg]) for seg in interpreters])
    if not interpreters:
        return renumber_pairs([LagRecord(0, [seg], []) for seg in natives])

    path = _dtw_align(natives, interpreters)

    records: list[LagRecord] = []
    current_natives: list[int] = []
    current_interps: list[int] = []
    last: tuple[int, int] | None = None

    for (i, j) in path:
        # Langkah diagonal (i dan j sama-sama maju) -> mulai chunk baru.
        if last is not None and i != last[0] and j != last[1]:
            records.append(
                LagRecord(
                    0,
                    [natives[k] for k in current_natives],
                    [interpreters[k] for k in current_interps],
                )
            )
            current_natives = []
            current_interps = []
        if not current_natives or current_natives[-1] != i:
            current_natives.append(i)
        if not current_interps or current_interps[-1] != j:
            current_interps.append(j)
        last = (i, j)

    if current_natives or current_interps:
        records.append(
            LagRecord(
                0,
                [natives[k] for k in current_natives],
                [interpreters[k] for k in current_interps],
            )
        )

    return renumber_pairs(records)


# Nama lama dipertahankan sebagai alias agar pemanggil lama tetap berfungsi.
auto_pair_segments = align_segments


def _segment_in(record: LagRecord, segment: Segment) -> bool:
    return segment in record.natives or segment in record.interpreters


def assign_pair(
    records: list[LagRecord],
    native: Segment,
    interpreter: Segment,
) -> list[LagRecord]:
    """Pasangkan manual satu ujaran native dengan satu ujaran penerjemah.

    Keduanya dilepas dari chunk lamanya (sisa segmen pada chunk lama tetap
    dipertahankan), lalu disatukan menjadi chunk baru 1-1.
    """
    detached: list[LagRecord] = []
    for record in records:
        kept_natives = [seg for seg in record.natives if seg is not native]
        kept_interps = [seg for seg in record.interpreters if seg is not interpreter]
        if not kept_natives and not kept_interps:
            continue
        detached.append(LagRecord(0, kept_natives, kept_interps))

    detached.append(LagRecord(0, [native], [interpreter]))
    return renumber_pairs(detached)


def attach_segments(
    records: list[LagRecord],
    target: LagRecord,
    segments: list[Segment],
) -> list[LagRecord]:
    """Pindahkan segmen ke chunk target (dilepas dulu dari chunk lamanya).

    Dipakai untuk koreksi banyak-ke-satu: mis. dua kalimat native yang
    diterjemahkan menjadi satu kalimat digabungkan ke chunk yang sama.
    Segmen di dalam chunk selalu diurut ulang menurut waktu mulai.
    """
    result: list[LagRecord] = []
    for record in records:
        kept_natives = [
            seg for seg in record.natives
            if not any(seg is moved for moved in segments)
        ]
        kept_interps = [
            seg for seg in record.interpreters
            if not any(seg is moved for moved in segments)
        ]
        if record is target:
            kept_natives += [s for s in segments if s.source == SOURCE_NATIVE]
            kept_interps += [s for s in segments if s.source == SOURCE_INTERPRETER]
            kept_natives.sort(key=lambda seg: seg.start)
            kept_interps.sort(key=lambda seg: seg.start)
        if kept_natives or kept_interps:
            result.append(LagRecord(0, kept_natives, kept_interps))
    return renumber_pairs(result)


def detach_segment(
    records: list[LagRecord],
    segment: Segment,
) -> list[LagRecord]:
    """Lepas satu segmen dari chunk-nya menjadi chunk orphan tersendiri.

    Berguna untuk menandai omission: ujaran native yang tidak diterjemahkan
    dikeluarkan dari pasangan agar tidak mencemari pengukuran EVS.
    """
    result: list[LagRecord] = []
    for record in records:
        kept_natives = [seg for seg in record.natives if seg is not segment]
        kept_interps = [seg for seg in record.interpreters if seg is not segment]
        if kept_natives or kept_interps:
            result.append(LagRecord(0, kept_natives, kept_interps))

    if segment.source == SOURCE_NATIVE:
        result.append(LagRecord(0, [segment], []))
    else:
        result.append(LagRecord(0, [], [segment]))
    return renumber_pairs(result)


def remove_pair(
    records: list[LagRecord],
    target: LagRecord,
) -> list[LagRecord]:
    """Keluarkan satu chunk dari analisis (segmen tetap ada di tab transkrip)."""
    remaining = [record for record in records if record is not target]
    return renumber_pairs(remaining)


def summarize_lags(
    records: list[LagRecord],
    mode: str,
) -> dict[str, float | int | None]:
    """Ringkas statistik lag dari chunk yang lengkap (orphan diabaikan)."""
    values = [
        record.lag_for(mode)
        for record in records
        if record.is_paired and record.lag_for(mode) is not None
    ]

    if not values:
        return {
            "pairs": len(records),
            "paired": 0,
            "average": None,
            "median": None,
            "stdev": None,
            "minimum": None,
            "maximum": None,
        }

    return {
        "pairs": len(records),
        "paired": len(values),
        "average": mean(values),
        "median": median(values),
        "stdev": stdev(values) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "maximum": max(values),
    }
