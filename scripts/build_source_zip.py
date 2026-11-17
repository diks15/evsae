"""Buat release/EVSAE-source (Linux-MacOS).zip dari source code terkini.

Dipakai sebagai pengganti Compress-Archive (PowerShell 5.1), yang menulis
pemisah folder "\\" sehingga di macOS file bisa terekstrak sebagai
"interpreter_lag\\app.py" alih-alih masuk ke folder interpreter_lag/.

Script ini:
- memakai pemisah "/" sesuai spesifikasi ZIP,
- menyimpan izin eksekusi (755) untuk peluncur .command/.sh,
- memastikan peluncur memakai akhir baris LF (CRLF membuat bash gagal).

Pemakaian (dari folder project):
    python scripts/build_source_zip.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "release" / "EVSAE-source (Linux-MacOS).zip"
TOP = "EVSAE"  # folder induk di dalam zip

FILES = [
    "interpreter_lag_gui.py",
    "requirements.txt",
    "README.md",
    "PANDUAN_PENGGUNAAN.md",
    "docs/USER_GUIDE.md",
    "Licence.txt",
    "CHANGELOG.md",
    "EVSAE_macOS.command",
    "logo-upi-fpbs.png",
    "kemendiktisaintek.png",
]
PACKAGE = "interpreter_lag"
EXECUTABLE_SUFFIXES = {".command", ".sh"}


def collect() -> list[Path]:
    paths = [ROOT / name for name in FILES]
    paths += sorted((ROOT / PACKAGE).glob("*.py"))
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise SystemExit("File tidak ditemukan: " + ", ".join(str(p) for p in missing))
    return paths


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    tmp = OUTPUT.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in collect():
            arcname = f"{TOP}/{path.relative_to(ROOT).as_posix()}"
            data = path.read_bytes()
            executable = path.suffix in EXECUTABLE_SUFFIXES
            if executable:
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(arcname, date_time=_mtime(path))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, agar atribut izin dibaca macOS/Linux
            mode = 0o100755 if executable else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, data)
            print("  +", arcname)
    tmp.replace(OUTPUT)
    print("Selesai:", OUTPUT)


def _mtime(path: Path) -> tuple[int, int, int, int, int, int]:
    import time

    t = time.localtime(max(path.stat().st_mtime, 315532800))  # ZIP minimal 1980
    return t[:6]


if __name__ == "__main__":
    main()
