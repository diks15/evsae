# Panduan Penggunaan — Ear Voice Span Analysis & Editing (EVSAE)

Manual lengkap dari input rekaman sampai koreksi segmen & pasangan.
*Versi 11 Juli 2026*

---

## Daftar Isi

- [Panduan Penggunaan — Ear Voice Span Analysis \& Editing (EVSAE)](#panduan-penggunaan--ear-voice-span-analysis--editing-evsae)
  - [Daftar Isi](#daftar-isi)
  - [1. Menjalankan Aplikasi](#1-menjalankan-aplikasi)
  - [2. Menyiapkan Rekaman](#2-menyiapkan-rekaman)
  - [3. Memasukkan Input \& Memulai Analisis](#3-memasukkan-input--memulai-analisis)
  - [4. Membaca Hasil](#4-membaca-hasil)
    - [Kartu metrik (atas)](#kartu-metrik-atas)
    - [Tab-tab](#tab-tab)
    - [Arti kolom "Cek" (⚠)](#arti-kolom-cek-)
  - [5. Memverifikasi \& Mengoreksi Pasangan](#5-memverifikasi--mengoreksi-pasangan)
    - [Alur kerja yang disarankan](#alur-kerja-yang-disarankan)
    - [Tabel diagnosis: gejala → alat](#tabel-diagnosis-gejala--alat)
    - [Cara pakai tiap tombol (bagian *Koreksi Pasangan* di sidebar)](#cara-pakai-tiap-tombol-bagian-koreksi-pasangan-di-sidebar)
    - [Sifat penting koreksi](#sifat-penting-koreksi)
  - [6. Menyunting Segmen (Timestamp \& Teks)](#6-menyunting-segmen-timestamp--teks)
  - [7. Editor Waveform](#7-editor-waveform)
  - [8. Menyimpan Pekerjaan \& Export](#8-menyimpan-pekerjaan--export)
  - [9. Pertanyaan Umum](#9-pertanyaan-umum)

---

## 1. Menjalankan Aplikasi

**Versi portable (Windows, tanpa install):**
1. Ekstrak `EVSAE-portable (Windows).zip` ke sebuah folder
2. Jalankan `EVSAE.exe`

**Dari source code (Windows/macOS/Linux):**
```
pip install -r requirements.txt
python interpreter_lag_gui.py
```

**macOS (paling mudah):**
1. Pasang Python 3.12 dari python.org.
2. Ekstrak `EVSAE-source (Linux-MacOS).zip`, lalu klik dua kali `EVSAE_macOS.command`.
   Bila diblokir macOS: klik kanan file itu → **Open** → **Open**.
3. Run pertama memasang dependensi otomatis (butuh internet, beberapa menit).
   Transkripsi di Mac berjalan di CPU; di Mac Apple Silicon model *medium* masih nyaman dipakai.

Model Whisper "small" sudah terbundel di versi portable. Model lain (mis. medium — lebih akurat, lebih lambat) diunduh otomatis **sekali** saat pertama dipilih, setelah itu offline.

---

## 2. Menyiapkan Rekaman

Kualitas analisis sangat ditentukan kualitas rekaman:

- **Dua rekaman terpisah**: satu untuk sumber (pembicara asli), satu untuk sasaran — idealnya masing-masing dari mikrofon/headset sendiri agar suara tidak saling bocor
- **Mulai bersamaan**: tekan rekam kedua perangkat pada momen yang sama. Kalau tidak memungkinkan, catat selisihnya — nanti diisi di kolom **Offset**
- **Lebih dari satu penerjemah**: rekam tiap penerjemah ke file terpisah (timeline tetap sama)
- Format yang didukung: mp3, wav, mp4, m4a, mpeg, webm, dan umumnya semua format audio/video

---

## 3. Memasukkan Input & Memulai Analisis

Semua pengaturan ada di **sidebar kiri** (bisa di-scroll bila window pendek):

1. **Input 1 · Bahasa Sumber (BSu)** → klik *Pilih File BSu*, pilih rekaman pembicara asli (Inggris)
2. **Input 2 · Bahasa Sasaran (BSa)**:
   - Atur **Jumlah Penerjemah** (1–4). Slot file akan muncul sesuai jumlahnya
   - Klik *Pilih File Penerjemah* untuk tiap slot (rekaman bahasa Indonesia)
   - Tiap penerjemah otomatis diberi label **P1, P2, ...** di semua tabel
3. **Offset mulai (detik)** — isi hanya bila rekaman tidak dimulai bersamaan:
   - Contoh: perekam penerjemah ditekan 2 detik lebih lambat dari native → isi offset penerjemah `2`
   - Boleh negatif, boleh koma atau titik desimal (`1,5` = `1.5`)
   - Offset menggeser seluruh timestamp **dan** tampilan waveform file itu
4. **Model Whisper** — `small` cepat & cukup baik; `medium` lebih akurat (disarankan untuk data penelitian); `large-v3` paling akurat tapi berat
5. **Mode Interpreting** — `Simultaneous` (angka utama = EVS) atau `Consecutive` (angka utama = gap)
6. Klik **Transcribe & Analyze** — proses berjalan di latar (window tetap bisa dipakai); status tampil di kotak STATUS kiri bawah

> Hasil transkripsi **deterministik**: file yang sama selalu menghasilkan transkrip dan angka yang sama.

---

## 4. Membaca Hasil

### Kartu metrik (atas)

| Kartu | Arti |
|---|---|
| **Pasangan Lengkap** | jumlah pasangan yang punya kedua sisi (masuk statistik) |
| **Rata-rata / Tercepat / Terlama Lag** | statistik EVS (atau gap, sesuai mode) dari pasangan lengkap |
| **Keyakinan 1:1** | persen pasangan berbentuk 1 kalimat ↔ 1 kalimat — makin tinggi, makin sedikit yang perlu dicek manual |

### Tab-tab

- **Transkrip Native / Penerjemah** — semua segmen per kalimat: nomor, (Penutur), Start, End, Durasi, **Pasangan** (#n = nomor pasangan; `-` = tanpa pasangan), teks
- **Editor Waveform** — lihat bagian 7
- **Hasil Lag** — tabel pasangan: EVS, Gap, Kategori (berwarna), kolom **Cek**, teks kedua sisi. Tanda ★ di header menunjukkan metrik yang jadi acuan mode saat ini
- **Visualisasi** — donut distribusi kategori + bar chart EVS per pasangan (garis putus-putus = ambang kategori 5/10/15 s), plus baris ringkasan kualitas alignment

### Arti kolom "Cek" (⚠)

⚠ berarti **"periksa saya"** — bukan berarti salah. Muncul pada:
- **chunk gabungan** (banyak kalimat di satu sisi) — sering benar (kondensasi penerjemah), tapi perlu dipastikan
- **EVS negatif** (penerjemah tampak mendahului native) — antisipasi kecil wajar; negatif besar biasanya salah pasang
- **tanpa pasangan** (omisi/adisi)

Baris **tanpa** ⚠ dapat dipercaya tanpa diperiksa.

---

## 5. Memverifikasi & Mengoreksi Pasangan

### Alur kerja yang disarankan

1. Jalankan analisis → buka tab **Hasil Lag**
2. Telusuri hanya baris **⚠** dari atas ke bawah
3. Untuk tiap baris ⚠: **baca maknanya** — apakah teks penerjemah benar-benar terjemahan dari semua kalimat native di baris itu?
   - Cocok semua → biarkan (verifikasi selesai untuk baris itu)
   - Tidak cocok → koreksi dengan alat di bawah
4. **Simpan Sesi** setelah selesai

### Tabel diagnosis: gejala → alat

| Gejala | Diagnosis | Alat |
|---|---|---|
| Makna bergeser satu baris berurutan; EVS negatif berderet | Rantai salah-pasang | **Pasangkan Terpilih** dari atas ke bawah |
| Ada kalimat native yang tidak diterjemahkan sama sekali | Omisi | **Lepas Segmen** |
| Terjemahan satu kalimat "bocor" ke baris tetangga | Gabungan kurang lengkap | **Tambah ke Pasangan** |
| Baris berisi bukan-ujaran (tepuk tangan/batuk tertranskripsi) | Artefak transkripsi | **Hapus Pasangan** |
| EVS ekstrem (mis. >12 s) | Biasanya salah satu di atas | baca teks, urai |

### Cara pakai tiap tombol (bagian *Koreksi Pasangan* di sidebar)

**Pasangkan Terpilih** — membuat pasangan 1:1 baru.
1. Tab *Transkrip Native* → klik 1 baris
2. Tab *Transkrip Penerjemah* → klik 1 baris
3. Klik **Pasangkan Terpilih**
- Kedua segmen dilepas dari pasangan lamanya lalu disatukan. Sisa anggota pasangan lama tetap dipertahankan.

**Tambah ke Pasangan** — memasukkan segmen ke pasangan yang SUDAH ada (untuk hubungan banyak-ke-satu).
1. Tab *Hasil Lag* → klik 1 baris pasangan **tujuan**
2. Tab *Transkrip Native* **atau** *Penerjemah* → klik segmen yang mau dimasukkan
3. Klik **Tambah ke Pasangan**
- Contoh: penerjemah menggabung `n3 "Hello, Glasgow"` + `n4 "Thank you very much"` menjadi satu kalimat → pilih pasangan berisi n3 di Hasil Lag, pilih n4 di Transkrip Native, klik Tambah ke Pasangan.

**Lepas Segmen** — mengeluarkan segmen dari pasangannya menjadi *Tidak Berpasangan*.
1. Tab *Transkrip Native/Penerjemah* → klik segmen
2. Klik **Lepas Segmen**
- Gunakan untuk omisi (kalimat native tak diterjemahkan) — tetap tampil di Hasil Lag sebagai dokumentasi, tapi tidak masuk statistik EVS.

**Hapus Pasangan** — membuang satu baris seluruhnya dari analisis.
1. Tab *Hasil Lag* → klik baris
2. Klik **Hapus Pasangan**
- Hanya untuk baris sampah (bukan ujaran sungguhan). Segmen tetap ada di tab transkrip dengan pasangan `-`.

**Selaraskan (DTW)** — menghitung ulang SEMUA pasangan otomatis dari nol.
- ⚠ **Menghapus seluruh koreksi manual** — muncul dialog konfirmasi. Simpan Sesi dulu bila ragu.

### Sifat penting koreksi

- **Lokal**: koreksi hanya menyentuh pasangan yang terlibat; pasangan lain tidak berubah nilai
- **Nomor pasangan bisa bergeser** setelah koreksi (selalu diurut ulang menurut waktu) — pegang teksnya, bukan nomornya
- **Satu aksi per siklus**: setiap koreksi me-refresh semua tabel dan mengosongkan pilihan — pilih ulang sebelum aksi berikutnya
- EVS diukur dari **onset segmen pertama** tiap sisi, jadi menambahkan segmen ke belakang chunk tidak mengubah EVS chunk itu — tapi bisa membenarkan EVS chunk tetangganya
- Status bar selalu menyebutkan segmen mana yang dipindah (mis. *"Segmen native #19 dimasukkan ke pasangan"*) — periksa kalau ada yang tidak diinginkan ikut pindah

---

## 6. Menyunting Segmen (Timestamp & Teks)

Bila hasil ASR meleset (waktu mulai/selesai kurang pas, teks salah dengar):

**Lewat tabel** — di tab *Transkrip Native/Penerjemah*:
1. **Klik dua kali** sel **Start**, **End**, atau **Transkrip**
2. Ketik nilai baru → **Enter** untuk simpan, **Esc** untuk batal
3. Validasi otomatis: waktu tak boleh negatif, Start tak boleh melewati End
4. Semua EVS/gap/kategori langsung dihitung ulang

**Lewat waveform** — lihat bagian 7 (lebih presisi karena melihat bentuk gelombang).

Kolom lain (#, Penutur, Durasi, Pasangan) tidak bisa disunting langsung — Durasi mengikuti Start/End; Pasangan diubah lewat alat koreksi bagian 5.

---

## 7. Editor Waveform

Tampilan dua tier sejajar waktu: **Native** (atas, biru) dan **Penerjemah** (bawah, hijau). Tiap segmen tampil sebagai kotak berlabel teks dengan **garis batas vertikal** di awal dan akhirnya.

| Aksi | Cara |
|---|---|
| Geser batas segmen | arahkan mouse ke garis vertikal (kursor berubah ↔) → klik-seret |
| Zoom in/out | scroll mouse (zoom berpusat di posisi kursor), atau tombol *Zoom −/+/Fit* |
| Geser tampilan (pan) | klik **kanan** + seret (macOS: klik kanan/dua jari + seret, atau **Control** + klik-seret) |
| Putar audio | tombol **▶ Native / ▶ Penerjemah / ▶ Mix** — mulai dari awal tampilan saat ini; kursor merah berjalan |
| Berhenti | tombol **■ Stop** |

Melepas seretan batas segmen langsung memicu perhitungan ulang lag — perubahan di sini setara dengan menyunting Start/End di tabel.

Untuk multi-penerjemah, tier bawah menampilkan **campuran** semua track penerjemah.

---

## 8. Menyimpan Pekerjaan & Export

**Simpan Sesi** (sidebar) → file `.json` berisi:
- Seluruh transkrip kedua sisi (termasuk suntingan Anda) + label penutur
- Seluruh pasangan **termasuk semua koreksi manual**
- Pengaturan model, mode, path file, offset

**Buka Sesi** → memulihkan semuanya **persis** tanpa transkripsi ulang. Audio waveform dimuat ulang bila file rekaman masih di lokasi yang sama — karena itu **simpan file sesi berdampingan dengan file rekamannya** dalam satu folder.

Tips: simpan dua kali — `sesi_mentah.json` (sebelum koreksi, sebagai arsip hasil otomatis) dan `sesi_final.json` (setelah verifikasi).

**Export CSV** → tiga file terpisah, satu tabel per file, siap dibuka di Excel/SPSS/R:

- `<nama>_summary.csv` — metadata dan statistik (`metric`, `value`): model, mode, jumlah segmen dan pasangan, `lag_mean_s`, `lag_median_s`, `lag_sd_s`, `lag_min_s`, `lag_max_s`, `pairs_1to1`, `merged_pairs`, `omissions_source`, `additions_interpreter`, `needs_review`
- `<nama>_segments.csv` — semua segmen kedua sisi (`side` = `source`/`interpreter`, `index`, `speaker`, `start_s`, `end_s`, `duration_s`, `pair`, `text`)
- `<nama>_pairs.csv` — satu baris per pasangan (`evs_s`, `gap_s`, `primary_lag_s`, `category`, `needs_review`, teks kedua sisi)

Nama kolom, nilai kategori (`Highly Responsive`, `Moderately Responsive`, `Less Responsive`, `Unresponsive`, `Unpaired`), dan nama file **selalu berbahasa Inggris**, apa pun bahasa antarmuka yang dipilih. Dengan begitu skrip R/SPSS tidak perlu diubah saat bahasa diganti.

**Bahasa antarmuka** → *Pengaturan → Bahasa / Language*: pilih English atau Bahasa Indonesia. Tampilan langsung berganti tanpa kehilangan data yang sedang dibuka, dan pilihan tersimpan untuk pembukaan berikutnya.

---

## 9. Pertanyaan Umum

**Hasil transkripsi berubah kalau saya ulangi?**
Tidak — transkripsi deterministik. File sama = hasil sama.

**Jumlah segmen native dan penerjemah berbeda, apakah salah?**
Tidak. Penerjemah menggabung/memecah/melewatkan kalimat secara alami. Yang penting pasangannya benar, bukan jumlahnya sama.

**Angka "Keyakinan 1:1" turun setelah saya koreksi — kenapa?**
Wajar. Metrik itu mengukur berapa pasangan berbentuk 1:1, bukan kebenaran data. Koreksi yang menggabungkan segmen (banyak-ke-satu) memindahkan pasangan keluar dari kategori 1:1 padahal justru makin benar. Setelah semua baris ⚠ diverifikasi, data Anda efektif 100% terverifikasi berapa pun angkanya.

**Ujaran "Tidak Berpasangan" ikut merusak rata-rata EVS?**
Tidak — otomatis dikecualikan dari semua statistik. Ia dokumentasi omisi/adisi (temuan penelitian).

**Waveform kosong setelah Buka Sesi?**
File rekaman tidak ditemukan di path semula. Analisis tetap utuh; pindahkan file rekaman kembali ke lokasi lama lalu buka sesi lagi.

**Tidak ada suara saat menekan ▶?**
Pastikan package `sounddevice` terpasang (versi source), dan perangkat output aktif. Playback bersifat opsional — analisis tidak membutuhkannya.

**Transkripsi lama sekali?**
Model medium di CPU memang butuh beberapa menit untuk rekaman panjang. Gunakan `small` untuk uji cepat, atau GPU NVIDIA (jalur source code) yang otomatis terpakai bila tersedia.

**Kapan pakai tombol "Selaraskan (DTW)"?**
Hanya bila ingin membuang semua koreksi dan mulai dari tebakan otomatis lagi — misalnya setelah banyak menyunting timestamp sehingga tebakan awal perlu disegarkan.
