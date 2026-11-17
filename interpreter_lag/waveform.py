"""Editor waveform dua-tier dengan batas segmen yang bisa diseret.

Memberi pengguna pengalaman ELAN-like: kedua input ditampilkan sebagai
gelombang suara yang sejajar dalam waktu, batas tiap segmen bisa diseret
dengan mouse untuk mengoreksi timestamp, dan audio bisa diputar dengan
kursor waktu yang berjalan.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import numpy as np

from .analysis import Segment
from .i18n import t
from .ui_platform import IS_MAC, RIGHT_BUTTON, bind_wheel, ui_font, wheel_direction


SAMPLE_RATE = 16000  # rate internal untuk waveform & playback


def load_audio(path: str | Path, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Dekode file audio/video ke PCM mono int16 pada `target_rate`.

    Menggunakan PyAV (sudah ikut faster-whisper). Mengembalikan array kosong
    bila file gagal dibaca atau tidak punya track audio.
    """
    import av

    container = av.open(str(path))
    try:
        stream = next(s for s in container.streams if s.type == "audio")
    except StopIteration:
        container.close()
        return np.zeros(0, dtype=np.int16)

    resampler = av.AudioResampler(format="s16", layout="mono", rate=target_rate)
    chunks: list[np.ndarray] = []
    try:
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().flatten())
        for resampled in resampler.resample(None):
            chunks.append(resampled.to_ndarray().flatten())
    finally:
        container.close()

    if not chunks:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(chunks).astype(np.int16)


def synthesize_demo_audio(
    segments: list[Segment], total_duration: float, frequency: float = 220.0
) -> np.ndarray:
    """Audio dummy untuk demo: sinus pada rentang tiap segmen, hening di luar."""
    samples = np.zeros(int(max(total_duration, 1.0) * SAMPLE_RATE), dtype=np.int16)
    for seg in segments:
        s0 = max(0, int(seg.start * SAMPLE_RATE))
        s1 = min(len(samples), int(seg.end * SAMPLE_RATE))
        if s1 > s0:
            t = np.arange(s1 - s0) / SAMPLE_RATE
            wave = (6000 * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
            samples[s0:s1] = wave
    return samples


class WaveformEditor:
    """Editor waveform dua-tier.

    Layout canvas (atas ke bawah):
        ruler waktu | native waveform | native segment boxes | gap |
        interpreter waveform | interpreter segment boxes
    """

    HEIGHT_RULER = 22
    HEIGHT_WAVEFORM = 90
    HEIGHT_SEGMENTS = 30
    HEIGHT_GAP = 14
    TOTAL_HEIGHT = (
        HEIGHT_RULER + 2 * (HEIGHT_WAVEFORM + HEIGHT_SEGMENTS) + HEIGHT_GAP
    )

    def __init__(self, parent: ttk.Frame, app: object) -> None:
        self.parent = parent
        self.app = app
        self.colors = app.colors

        self.native_audio: np.ndarray = np.zeros(0, dtype=np.int16)
        self.interpreter_audio: np.ndarray = np.zeros(0, dtype=np.int16)

        self.t0: float = 0.0
        self.t1: float = 30.0

        self._drag: dict | None = None
        self._pan: dict | None = None

        self._play_active: bool = False
        self._play_start_wall: float = 0.0
        self._play_offset: float = 0.0
        self._play_end: float = 0.0
        self._cursor_x: float | None = None
        self._cursor_job: str | None = None

        self._build()

    # ----------------------------------------------------------- build
    def _build(self) -> None:
        c = self.colors

        controls = ttk.Frame(self.parent)
        controls.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(controls, text="Zoom −", width=8, command=self._zoom_out).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(controls, text="Zoom +", width=8, command=self._zoom_in).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(controls, text="Fit", width=6, command=self.fit).pack(
            side=tk.LEFT, padx=(0, 14)
        )

        ttk.Button(
            controls, text=t("wave.play_sl"), command=lambda: self._play("native")
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            controls,
            text=t("wave.play_tl"),
            command=lambda: self._play("interpreter"),
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            controls, text=t("wave.play_mix"), command=lambda: self._play("both")
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(controls, text=t("wave.stop"), command=self.stop).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        self.time_var = tk.StringVar(value="0.00 – 30.00 s")
        ttk.Label(
            controls, textvariable=self.time_var, style="Muted.TLabel"
        ).pack(side=tk.RIGHT)

        canvas_frame = tk.Frame(
            self.parent,
            bg=c["surface"],
            highlightthickness=1,
            highlightbackground=c["border"],
        )
        canvas_frame.pack(fill=tk.X)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg=c["surface"],
            highlightthickness=0,
            height=self.TOTAL_HEIGHT,
        )
        self.canvas.pack(fill=tk.X)

        self.canvas.bind("<Configure>", lambda _e: self._render())
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        bind_wheel(self.canvas, self._on_wheel)
        self.canvas.bind(f"<Button-{RIGHT_BUTTON}>", self._on_pan_start)
        self.canvas.bind(f"<B{RIGHT_BUTTON}-Motion>", self._on_pan_drag)
        if IS_MAC:
            # Mouse/trackpad Mac tanpa klik kanan: Control+klik-seret juga untuk pan.
            self.canvas.bind("<Control-Button-1>", self._on_pan_start)
            self.canvas.bind("<Control-B1-Motion>", self._on_pan_drag)
        self.canvas.bind("<Motion>", self._on_hover)

        ttk.Label(
            self.parent,
            text=t("wave.hint"),
            style="Muted.TLabel",
            wraplength=840,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

    # --------------------------------------------------------- public API
    def set_audio(
        self,
        native_audio: np.ndarray | None,
        interpreter_audio: np.ndarray | None,
    ) -> None:
        self.native_audio = (
            native_audio if native_audio is not None else np.zeros(0, dtype=np.int16)
        )
        self.interpreter_audio = (
            interpreter_audio
            if interpreter_audio is not None
            else np.zeros(0, dtype=np.int16)
        )
        self.fit()

    def clear(self) -> None:
        self.stop()
        self.native_audio = np.zeros(0, dtype=np.int16)
        self.interpreter_audio = np.zeros(0, dtype=np.int16)
        self.t0, self.t1 = 0.0, 30.0
        self._cursor_x = None
        self._render()

    def fit(self) -> None:
        max_t = self._max_duration()
        self.t0 = 0.0
        self.t1 = max_t
        self._render()

    def _zoom_in(self) -> None:
        center = (self.t0 + self.t1) / 2
        span = max((self.t1 - self.t0) * 0.5, 0.2)
        self._set_view(center - span / 2, center + span / 2)

    def _zoom_out(self) -> None:
        center = (self.t0 + self.t1) / 2
        span = min((self.t1 - self.t0) * 2.0, self._max_duration())
        self._set_view(center - span / 2, center + span / 2)

    def refresh(self) -> None:
        """Render ulang berdasarkan state segmen terkini (dipanggil app)."""
        self._render()

    def stop(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:  # noqa: BLE001 - playback bersifat opsional
            pass
        self._play_active = False
        if self._cursor_job is not None:
            try:
                self.parent.after_cancel(self._cursor_job)
            except (tk.TclError, ValueError):
                pass
            self._cursor_job = None
        if self._cursor_x is not None:
            self._cursor_x = None
            try:
                self.canvas.delete("cursor")
            except tk.TclError:
                pass

    # ------------------------------------------------------- geometry/audio
    def _audio_duration(self, audio: np.ndarray) -> float:
        return len(audio) / SAMPLE_RATE

    def _max_duration(self) -> float:
        candidates = [
            self._audio_duration(self.native_audio),
            self._audio_duration(self.interpreter_audio),
        ]
        for seg in list(self.app.native_segments) + list(self.app.interpreter_segments):
            candidates.append(seg.end)
        return max(candidates + [1.0])

    def _canvas_width(self) -> int:
        return max(1, self.canvas.winfo_width())

    def _time_to_x(self, t: float) -> float:
        return (t - self.t0) / max(self.t1 - self.t0, 1e-6) * self._canvas_width()

    def _x_to_time(self, x: float) -> float:
        return self.t0 + x / self._canvas_width() * (self.t1 - self.t0)

    def _set_view(self, t0: float, t1: float) -> None:
        max_t = self._max_duration()
        span = max(0.1, min(t1 - t0, max_t))
        t0 = max(0.0, t0)
        if t0 + span > max_t:
            t0 = max(0.0, max_t - span)
        self.t0, self.t1 = t0, t0 + span
        self._render()

    # ------------------------------------------------------------ rendering
    def _render(self) -> None:
        try:
            self.canvas.delete("all")
        except tk.TclError:
            return
        w = self._canvas_width()
        if w < 50:
            return
        c = self.colors

        self.time_var.set(f"{self.t0:.2f} – {self.t1:.2f} s")

        y = 0
        self._draw_ruler(y, w)
        y += self.HEIGHT_RULER

        self._draw_waveform(self.native_audio, y, w, c["primary"])
        self._draw_tier_label(t("wave.tier_sl"), y, c["primary"])
        y += self.HEIGHT_WAVEFORM
        self._draw_segments(self.app.native_segments, y, w, "native", c["primary"])
        y += self.HEIGHT_SEGMENTS

        gap_y = y + self.HEIGHT_GAP // 2
        self.canvas.create_line(0, gap_y, w, gap_y, fill=c["border"])
        y += self.HEIGHT_GAP

        self._draw_waveform(self.interpreter_audio, y, w, c["success"])
        self._draw_tier_label(t("wave.tier_tl"), y, c["success"])
        y += self.HEIGHT_WAVEFORM
        self._draw_segments(
            self.app.interpreter_segments, y, w, "interpreter", c["success"]
        )

        if self._cursor_x is not None:
            self.canvas.create_line(
                self._cursor_x,
                0,
                self._cursor_x,
                self.TOTAL_HEIGHT,
                fill="#dc2626",
                width=2,
                tags="cursor",
            )

    def _draw_tier_label(self, text: str, y: int, color: str) -> None:
        # Digambar SETELAH gelombang (dulu tertutup persegi latar gelombang),
        # dengan latar agar tetap terbaca di atas gelombang.
        label = self.canvas.create_text(
            8,
            y + 4,
            anchor="nw",
            text=text,
            font=ui_font(8, "bold"),
            fill=color,
        )
        x1, y1, x2, y2 = self.canvas.bbox(label)
        backdrop = self.canvas.create_rectangle(
            x1 - 4, y1 - 1, x2 + 4, y2 + 1,
            fill=self.colors["surface"], outline=self.colors["border"],
        )
        self.canvas.tag_lower(backdrop, label)

    def _draw_ruler(self, y: int, w: int) -> None:
        c = self.colors
        self.canvas.create_rectangle(
            0, y, w, y + self.HEIGHT_RULER, fill=c["card"], outline=""
        )
        span = self.t1 - self.t0
        if span < 5:
            step = 0.5
        elif span < 20:
            step = 1.0
        elif span < 60:
            step = 5.0
        elif span < 300:
            step = 10.0
        else:
            step = 30.0

        t = math.floor(self.t0 / step) * step
        while t <= self.t1 + step:
            if t >= self.t0:
                x = self._time_to_x(t)
                self.canvas.create_line(
                    x,
                    y + self.HEIGHT_RULER - 7,
                    x,
                    y + self.HEIGHT_RULER,
                    fill=c["muted"],
                )
                label = f"{t:.1f}s" if step < 5 else f"{int(t)}s"
                self.canvas.create_text(
                    x + 3,
                    y + 2,
                    anchor="nw",
                    text=label,
                    font=ui_font(7),
                    fill=c["muted"],
                )
            t += step

    def _draw_waveform(
        self, audio: np.ndarray, y: int, w: int, color: str
    ) -> None:
        c = self.colors
        self.canvas.create_rectangle(
            0, y, w, y + self.HEIGHT_WAVEFORM, fill=c["surface"], outline=c["border"]
        )
        if len(audio) == 0:
            self.canvas.create_text(
                w / 2,
                y + self.HEIGHT_WAVEFORM / 2,
                text=t("wave.no_audio"),
                fill=c["muted"],
                font=ui_font(9, "italic"),
            )
            return

        s0 = max(0, int(self.t0 * SAMPLE_RATE))
        s1 = min(len(audio), int(self.t1 * SAMPLE_RATE))
        if s1 <= s0:
            return

        slice_audio = audio[s0:s1]
        mins, maxs = self._downsample(slice_audio, w)
        mid = y + self.HEIGHT_WAVEFORM / 2
        scale = (self.HEIGHT_WAVEFORM / 2 - 2) / 32768.0

        self.canvas.create_line(0, mid, w, mid, fill=c["stripe"])

        for x in range(w):
            y_top = mid - maxs[x] * scale
            y_bot = mid - mins[x] * scale
            if y_top != y_bot:
                self.canvas.create_line(x, y_top, x, y_bot, fill=color)

    @staticmethod
    def _downsample(
        samples: np.ndarray, n_pixels: int
    ) -> tuple[np.ndarray, np.ndarray]:
        n = len(samples)
        if n == 0 or n_pixels <= 0:
            zero = np.zeros(max(n_pixels, 1))
            return zero, zero.copy()
        if n < n_pixels:
            idx = (np.arange(n_pixels) * n / n_pixels).astype(int)
            values = samples[idx].astype(np.float64)
            return values, values.copy()
        bin_size = n // n_pixels
        truncated = samples[: bin_size * n_pixels].reshape(n_pixels, bin_size)
        return truncated.min(axis=1), truncated.max(axis=1)

    def _draw_segments(
        self,
        segments: list[Segment],
        y: int,
        w: int,
        kind: str,
        color: str,
    ) -> None:
        c = self.colors
        self.canvas.create_rectangle(
            0, y, w, y + self.HEIGHT_SEGMENTS, fill=c["stripe"], outline=c["border"]
        )
        for seg in segments:
            x_start = self._time_to_x(seg.start)
            x_end = self._time_to_x(seg.end)
            if x_end < 0 or x_start > w:
                continue
            x_start_clip = max(0, x_start)
            x_end_clip = min(w, x_end)
            if x_end_clip - x_start_clip > 1:
                self.canvas.create_rectangle(
                    x_start_clip,
                    y + 2,
                    x_end_clip,
                    y + self.HEIGHT_SEGMENTS - 2,
                    fill=c["surface"],
                    outline=color,
                    width=1,
                )
                width_px = x_end_clip - x_start_clip
                if width_px > 30:
                    max_chars = max(3, int(width_px / 7))
                    text = (
                        seg.text
                        if len(seg.text) <= max_chars
                        else seg.text[: max_chars - 1] + "…"
                    )
                    self.canvas.create_text(
                        (x_start_clip + x_end_clip) / 2,
                        y + self.HEIGHT_SEGMENTS / 2,
                        text=text,
                        font=ui_font(8),
                        fill=c["text"],
                    )

            for edge_name, x_edge in (("start", x_start), ("end", x_end)):
                if -3 <= x_edge <= w + 3:
                    self.canvas.create_line(
                        x_edge,
                        y - self.HEIGHT_WAVEFORM,
                        x_edge,
                        y + self.HEIGHT_SEGMENTS,
                        fill=color,
                        width=2,
                        tags=("handle", f"handle-{kind}-{seg.index}-{edge_name}"),
                    )

    # -------------------------------------------------------- mouse handlers
    def _identify_handle(
        self, x: float, y: float
    ) -> tuple[Segment, str, str] | None:
        items = self.canvas.find_overlapping(x - 4, y - 4, x + 4, y + 4)
        for item in items:
            for tag in self.canvas.gettags(item):
                if tag.startswith("handle-"):
                    parts = tag.split("-")
                    if len(parts) == 4:
                        _, kind, index_str, edge = parts
                        lookup = (
                            self.app._native_by_index
                            if kind == "native"
                            else self.app._interpreter_by_index
                        )
                        try:
                            seg = lookup.get(int(index_str))
                        except ValueError:
                            return None
                        if seg is not None:
                            return seg, edge, kind
        return None

    def _on_press(self, event: tk.Event) -> None:
        hit = self._identify_handle(event.x, event.y)
        if hit:
            seg, edge, kind = hit
            self._drag = {"segment": seg, "edge": edge, "kind": kind}
            self.canvas.config(cursor="sb_h_double_arrow")
        else:
            self._drag = None

    def _on_drag(self, event: tk.Event) -> None:
        if not self._drag:
            return
        seg = self._drag["segment"]
        edge = self._drag["edge"]
        new_time = max(0.0, self._x_to_time(event.x))
        if edge == "start":
            seg.start = min(new_time, seg.end - 0.01)
        else:
            seg.end = max(new_time, seg.start + 0.01)
        self._render()

    def _on_release(self, _event: tk.Event) -> None:
        if self._drag is None:
            return
        self._drag = None
        self.canvas.config(cursor="")
        self.app.refresh_all()
        self.app.status_var.set(t("st.boundary_adjusted"))

    def _on_hover(self, event: tk.Event) -> None:
        if self._drag is not None:
            return
        if self._identify_handle(event.x, event.y) is not None:
            self.canvas.config(cursor="sb_h_double_arrow")
        else:
            self.canvas.config(cursor="")

    def _on_wheel(self, event: tk.Event) -> None:
        direction = wheel_direction(event)
        if direction == 0:
            return
        if IS_MAC:
            # Trackpad Mac mengirim banyak event kecil per gesture; batasi laju zoom.
            now = time.monotonic()
            if now - getattr(self, "_last_wheel", 0.0) < 0.06:
                return
            self._last_wheel = now
        time_at_cursor = self._x_to_time(event.x)
        factor = 0.75 if direction > 0 else 1.3333
        span = max(0.1, min((self.t1 - self.t0) * factor, self._max_duration()))
        ratio = event.x / self._canvas_width()
        self._set_view(time_at_cursor - span * ratio, time_at_cursor + span * (1 - ratio))

    def _on_pan_start(self, event: tk.Event) -> None:
        self._pan = {"x": event.x, "t0": self.t0, "t1": self.t1}

    def _on_pan_drag(self, event: tk.Event) -> None:
        if not self._pan:
            return
        span = self._pan["t1"] - self._pan["t0"]
        dt = -(event.x - self._pan["x"]) / self._canvas_width() * span
        self._set_view(self._pan["t0"] + dt, self._pan["t1"] + dt)

    # --------------------------------------------------------- playback
    def _play(self, source: str) -> None:
        self.stop()
        try:
            import sounddevice as sd
        except ImportError:
            self.app.status_var.set(t("wave.need_sounddevice"))
            return

        if source == "native":
            audio = self.native_audio
        elif source == "interpreter":
            audio = self.interpreter_audio
        else:
            audio = self._mix(self.native_audio, self.interpreter_audio)

        if len(audio) == 0:
            self.app.status_var.set(t("wave.nothing_to_play"))
            return

        start_sample = max(0, int(self.t0 * SAMPLE_RATE))
        end_sample = min(len(audio), int(self.t1 * SAMPLE_RATE))
        if end_sample <= start_sample:
            return

        try:
            sd.play(audio[start_sample:end_sample], SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001 - ditampilkan ke pengguna
            self.app.status_var.set(t("wave.play_failed", error=exc))
            return

        self._play_active = True
        self._play_start_wall = time.time()
        self._play_offset = self.t0
        self._play_end = self.t1
        self._update_cursor()

    @staticmethod
    def _mix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        if len(a) == 0:
            return b
        if len(b) == 0:
            return a
        length = max(len(a), len(b))
        a32 = a.astype(np.int32)
        b32 = b.astype(np.int32)
        if len(a32) < length:
            a32 = np.concatenate([a32, np.zeros(length - len(a32), dtype=np.int32)])
        if len(b32) < length:
            b32 = np.concatenate([b32, np.zeros(length - len(b32), dtype=np.int32)])
        return np.clip((a32 + b32) // 2, -32768, 32767).astype(np.int16)

    def _update_cursor(self) -> None:
        if not self._play_active:
            return
        elapsed = time.time() - self._play_start_wall
        t = self._play_offset + elapsed
        if t >= self._play_end:
            self.stop()
            return
        self._cursor_x = self._time_to_x(t)
        try:
            self.canvas.delete("cursor")
            self.canvas.create_line(
                self._cursor_x,
                0,
                self._cursor_x,
                self.TOTAL_HEIGHT,
                fill="#dc2626",
                width=2,
                tags="cursor",
            )
        except tk.TclError:
            self._play_active = False
            return
        self._cursor_job = self.parent.after(40, self._update_cursor)
