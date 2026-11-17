"""Penyesuaian antarmuka per sistem operasi (Windows, macOS, Linux).

Tk berperilaku berbeda di tiap platform:
- Font "Segoe UI" hanya ada di Windows. macOS memakai skala 72 dpi sehingga
  ukuran poin yang sama tampak lebih kecil dibanding Windows (96 dpi).
- Event <MouseWheel> di Windows memberi delta kelipatan 120; di macOS delta
  bernilai kecil (±1..±10, trackpad bahkan per piksel); di Linux/X11 wheel
  dikirim sebagai <Button-4>/<Button-5> dengan delta 0.
- Klik kanan di macOS (Tk Aqua) adalah <Button-2>, bukan <Button-3>.
"""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Callable

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    UI_FAMILY = "Segoe UI"
    _SIZE_SCALE = 1.0
elif IS_MAC:
    UI_FAMILY = "Helvetica Neue"
    _SIZE_SCALE = 4 / 3  # setara ukuran tampak di Windows
else:
    UI_FAMILY = "DejaVu Sans"
    _SIZE_SCALE = 1.0

# Tombol mouse untuk klik kanan (dipakai untuk pan di Editor Waveform).
RIGHT_BUTTON = 2 if IS_MAC else 3


def ui_font(size: int, *styles: str) -> tuple:
    """Tuple font Tk dengan keluarga & ukuran yang sesuai platform."""
    return (UI_FAMILY, max(1, round(size * _SIZE_SCALE)), *styles)


def wheel_direction(event: tk.Event) -> int:
    """Arah scroll: +1 = ke atas/menjauh, -1 = ke bawah/mendekat, 0 = tidak ada."""
    num = getattr(event, "num", None)
    if num == 4:
        return 1
    if num == 5:
        return -1
    delta = getattr(event, "delta", 0) or 0
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def wheel_units(event: tk.Event) -> int:
    """Jumlah baris scroll (positif = turun) untuk Canvas.yview_scroll."""
    num = getattr(event, "num", None)
    if num in (4, 5):
        return -1 if num == 4 else 1
    delta = getattr(event, "delta", 0) or 0
    if IS_MAC:
        # Delta macOS sudah dalam satuan "langkah"; trackpad bisa sangat kecil.
        return -int(delta) if delta else 0
    return int(-1 * (delta / 120)) or (-1 if delta > 0 else 1 if delta < 0 else 0)


WHEEL_SEQUENCES = ("<MouseWheel>",) if (IS_WINDOWS or IS_MAC) else (
    "<MouseWheel>",
    "<Button-4>",
    "<Button-5>",
)


def bind_wheel(widget: tk.Misc, handler: Callable, *, all_widgets: bool = False) -> None:
    """Pasang handler wheel untuk semua varian event platform ini."""
    for sequence in WHEEL_SEQUENCES:
        if all_widgets:
            widget.bind_all(sequence, handler)
        else:
            widget.bind(sequence, handler)


def unbind_wheel(widget: tk.Misc, *, all_widgets: bool = False) -> None:
    for sequence in WHEEL_SEQUENCES:
        if all_widgets:
            widget.unbind_all(sequence)
        else:
            widget.unbind(sequence)
