EVSAE - EAR-VOICE SPAN ANALYSIS AND EDITING - VERSI PORTABLE (WINDOWS)
=======================================================================
Fakultas Pendidikan Bahasa dan Sastra - Universitas Pendidikan Indonesia

CARA MENJALANKAN
----------------
1. Ekstrak seluruh isi zip ini ke satu folder (jangan jalankan dari dalam zip).
2. Buka folder hasil ekstrak, jalankan: EVSAE.exe
3. Tidak perlu install Python atau program lain.

BAHASA / LANGUAGE
-----------------
Tampilan tersedia dalam English dan Bahasa Indonesia. Ganti lewat
Pengaturan -> "Bahasa / Language" (Settings -> "Language / Bahasa").
Pilihan tersimpan untuk pembukaan berikutnya.

PEMAKAIAN SINGKAT
-----------------
1. Pilih File BSu (rekaman sumber, Inggris).
2. Pilih File BSa (rekaman juru bahasa, Indonesia).
   - Bila penerjemah lebih dari satu orang, ubah "Jumlah Penerjemah"
     lalu pilih satu file rekaman per penerjemah.
   - Bila rekaman tidak dimulai bersamaan, isi "Offset mulai (detik)".
3. Klik "Transcribe & Analyze" dan tunggu (model medium butuh beberapa menit).
4. Periksa tab Hasil Lag: baris bertanda peringatan pada kolom "Cek"
   perlu diverifikasi manual (gunakan tombol di bagian Koreksi Pasangan).
5. Simpan pekerjaan dengan "Simpan Sesi" (bisa dilanjutkan kapan saja
   lewat "Buka Sesi" tanpa transkripsi ulang).
6. "Export CSV" menghasilkan 3 file (_summary, _segments, _pairs.csv)
   untuk Excel/SPSS/R. Nama kolom selalu berbahasa Inggris.

MODEL WHISPER
-------------
- Folder "models" berisi model transkripsi. Bila model yang dipilih belum
  ada di folder itu, aplikasi mengunduhnya sekali dari internet
  (model "small" +-500 MB, "medium" +-1,5 GB), setelah itu bisa offline.
- Simpan file sesi (.json) berdampingan dengan file rekamannya agar
  waveform tetap muncul saat sesi dibuka kembali.

CATATAN
-------
- Versi portable ini berjalan di CPU. Untuk GPU NVIDIA, jalankan aplikasi
  dari source code Python (lihat README.md di repository).
- Antivirus kadang memindai exe baru cukup lama pada run pertama - normal.
