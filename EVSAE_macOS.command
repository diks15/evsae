#!/bin/bash
# EVSAE - peluncur macOS (klik dua kali di Finder).
# Run pertama: membuat virtual environment .venv dan memasang dependensi
# (butuh internet, beberapa menit). Run berikutnya langsung membuka aplikasi.

cd "$(dirname "$0")" || exit 1

pause_exit() {
    echo
    read -r -p "Tekan Enter untuk menutup jendela ini..." _
    exit "${1:-1}"
}

find_python() {
    # Utamakan Python dari python.org (Tk 8.6 sudah terbundel), lalu Homebrew,
    # lalu python3 di PATH. /usr/bin/python3 bawaan Apple dihindari bila ada
    # pilihan lain karena Tk-nya versi lama.
    for candidate in \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        "$(command -v python3 2>/dev/null)"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

if [ ! -x ".venv/bin/python" ]; then
    PYTHON="$(find_python)" || {
        echo "Python 3 tidak ditemukan."
        echo "Pasang Python 3.12 dari https://www.python.org/downloads/macos/ lalu jalankan lagi."
        pause_exit 1
    }
    echo "Memakai Python: $PYTHON"

    if ! "$PYTHON" -c "import sys, tkinter; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)" 2>/dev/null; then
        echo "Python ini tidak punya Tkinter 8.6 (dibutuhkan untuk tampilan aplikasi)."
        echo "- Python dari python.org: pasang ulang installer resminya."
        echo "- Python dari Homebrew : jalankan  brew install python-tk"
        pause_exit 1
    fi

    echo "Run pertama: membuat virtual environment dan memasang dependensi..."
    "$PYTHON" -m venv .venv || pause_exit 1
    .venv/bin/python -m pip install --upgrade pip || pause_exit 1
    .venv/bin/python -m pip install -r requirements.txt || {
        rm -rf .venv
        echo "Pemasangan dependensi gagal. Periksa koneksi internet lalu coba lagi."
        pause_exit 1
    }
fi

.venv/bin/python interpreter_lag_gui.py || pause_exit 1
