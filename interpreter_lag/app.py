from __future__ import annotations

import csv
import json
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analysis import (
    CATEGORY_UNPAIRED,
    LAG_CATEGORIES,
    MODE_CONSECUTIVE,
    MODE_SIMULTANEOUS,
    SOURCE_INTERPRETER,
    SOURCE_NATIVE,
    LagRecord,
    Segment,
    align_segments,
    assign_pair,
    attach_segments,
    detach_segment,
    lag_category,
    remove_pair,
    renumber_pairs,
    summarize_lags,
)
from .diarization import (
    build_speaker_tracks,
    cluster_utterances,
    detect_utterances,
    utterance_features,
    write_wav,
)
from . import i18n
from .i18n import category_description, category_label, t
from .transcription import app_base_dir, transcribe_media
from .ui_platform import bind_wheel, ui_font, unbind_wheel, wheel_units
from .waveform import SAMPLE_RATE, WaveformEditor, load_audio, synthesize_demo_audio

try:
    from PIL import Image, ImageTk

    _PIL_AVAILABLE = True
except ImportError:  # Pillow opsional - aplikasi tetap jalan tanpa logo
    _PIL_AVAILABLE = False


MODEL_OPTIONS = ("tiny", "base", "small", "medium", "large-v3")

# Bahasa tiap input. Native = pembicara asli, Interpreter = penerjemah.
# Memberi kode bahasa yang tepat ke Whisper menaikkan akurasi transkripsi.
NATIVE_LANGUAGE = "en"
INTERPRETER_LANGUAGE = "id"

# Label mode interpreting pada combobox -> nilai internal.
MODE_LABELS = {
    "Simultaneous": MODE_SIMULTANEOUS,
    "Consecutive": MODE_CONSECUTIVE,
}

# Berkas logo institusi (diletakkan di folder root project).
LOGO_LEFT_FILE = "logo-upi-fpbs.png"
LOGO_RIGHT_FILE = "kemendiktisaintek.png"

# Warna tiap kategori jeda, mengikuti acuan peneliti (teal, biru, oranye, merah).
_CATEGORY_PALETTE = ("#2a9d8f", "#1d4e89", "#e2722e", "#c0392b")
CATEGORY_COLORS: dict[str, str] = {
    name: _CATEGORY_PALETTE[position % len(_CATEGORY_PALETTE)]
    for position, (name, _upper, _description) in enumerate(LAG_CATEGORIES)
}
CATEGORY_COLORS[CATEGORY_UNPAIRED] = "#94a3b8"

# Kolom segmen yang boleh disunting manual lewat klik dua kali.
EDITABLE_SEGMENT_COLUMNS = ("start", "end", "text")


def _demo_segments() -> tuple[list[Segment], list[Segment]]:
    """Contoh data dua input: pidato Inggris (native) + terjemahan Indonesia."""
    native = [
        Segment(1, 0.50, 4.20, "Good morning, ladies and gentlemen.", SOURCE_NATIVE),
        Segment(
            2,
            6.00,
            13.50,
            "Today I would like to talk about the importance of reading literature.",
            SOURCE_NATIVE,
        ),
        Segment(
            3,
            15.00,
            22.00,
            "Literature helps us understand culture, history, and human experience.",
            SOURCE_NATIVE,
        ),
        Segment(
            4,
            24.00,
            29.50,
            "Thank you very much for your kind attention.",
            SOURCE_NATIVE,
        ),
    ]
    interpreter = [
        Segment(1, 3.10, 7.00, "Selamat pagi, bapak ibu sekalian.", SOURCE_INTERPRETER),
        Segment(
            2,
            9.20,
            16.80,
            "Hari ini saya ingin membahas pentingnya membaca karya sastra.",
            SOURCE_INTERPRETER,
        ),
        Segment(
            3,
            18.30,
            25.50,
            "Sastra membantu kita memahami budaya, sejarah, dan pengalaman manusia.",
            SOURCE_INTERPRETER,
        ),
        Segment(
            4,
            27.40,
            32.10,
            "Terima kasih banyak atas perhatian Anda.",
            SOURCE_INTERPRETER,
        ),
    ]
    return native, interpreter


class InterpreterLagApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title(t("app.title"))
        self.master.geometry("1280x820")
        self.master.minsize(1100, 740)

        self.native_path = ""
        # Multi-penerjemah: satu file rekaman per penerjemah, timeline sama.
        self.interpreter_paths: list[str] = [""]
        self.native_segments: list[Segment] = []
        self.interpreter_segments: list[Segment] = []
        self.records: list[LagRecord] = []

        # Lookup cepat untuk koreksi pasangan manual.
        self._native_by_index: dict[int, Segment] = {}
        self._interpreter_by_index: dict[int, Segment] = {}
        self._record_by_iid: dict[str, LagRecord] = {}

        # Editor sel inline untuk penyuntingan timestamp/teks segmen.
        self._cell_editor: tk.Widget | None = None
        self._edit_context: tuple[Segment, str] | None = None

        # Referensi gambar logo harus disimpan agar tidak dibuang garbage collector.
        self.logo_left: object = None
        self.logo_right: object = None
        self._chart_canvas: tk.Canvas | None = None
        self._container: ttk.Frame | None = None
        # True selama data demo yang tampil (label berkas diisi teks demo).
        self._demo_active = False
        self._processing = False

        self.worker_queue: queue.Queue = queue.Queue()

        self.model_var = tk.StringVar(value="small")
        self.mode_var = tk.StringVar(value="Simultaneous")
        self.language_var = tk.StringVar(value=i18n.LANGUAGES[i18n.get_language()])
        self.native_file_var = tk.StringVar(value=t("file.none_sl"))
        self.native_offset_var = tk.StringVar(value="0")
        self.interp_count_var = tk.StringVar(value="1")
        self.interpreter_file_vars: list[tk.StringVar] = []
        self.interpreter_offset_vars: list[tk.StringVar] = []
        # Snapshot input untuk worker (diisi ulang setiap start_analysis).
        self._native_offset = 0.0
        self._interp_offsets: list[float] = [0.0]
        self._job_native_path = ""
        self._job_interp_paths: list[str] = []
        self.status_var = tk.StringVar(value=t("st.initial"))
        self.pair_count_var = tk.StringVar(value="-")
        self.avg_lag_var = tk.StringVar(value="-")
        self.min_lag_var = tk.StringVar(value="-")
        self.max_lag_var = tk.StringVar(value="-")
        self.confidence_var = tk.StringVar(value="-")
        self.viz_quality_var = tk.StringVar(value=t("viz.no_data"))
        # Statistik kuantitatif tab Visualisasi.
        self.viz_median_var = tk.StringVar(value="-")
        self.viz_sd_var = tk.StringVar(value="-")
        self.viz_merged_var = tk.StringVar(value="-")
        self.viz_omission_var = tk.StringVar(value="-")
        self.viz_addition_var = tk.StringVar(value="-")

        self._configure_style()
        self._load_logos()
        self._build_layout()

    # ------------------------------------------------------------------ style
    def _configure_style(self) -> None:
        style = ttk.Style(self.master)
        style.theme_use("clam")

        self.colors = {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "card": "#f8fafc",
            "border": "#dce3ec",
            "text": "#1e293b",
            "muted": "#64748b",
            "primary": "#2563eb",
            "primary_dark": "#1d4ed8",
            "success": "#0f766e",
            "green": "#15803d",
            "warning": "#b45309",
            "danger": "#b91c1c",
            "stripe": "#f4f7fb",
        }
        c = self.colors

        self.master.configure(bg=c["bg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("Surface.TFrame", background=c["surface"])
        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Surface.TLabel", background=c["surface"], foreground=c["text"])
        style.configure("Muted.TLabel", background=c["surface"], foreground=c["muted"])
        style.configure(
            "Footer.TLabel",
            background=c["bg"],
            foreground=c["muted"],
            font=ui_font(8),
        )
        style.configure(
            "SectionHead.TLabel",
            font=ui_font(9, "bold"),
            background=c["surface"],
            foreground=c["primary"],
        )

        style.configure("TButton", font=ui_font(9), padding=(10, 7))
        style.configure(
            "Primary.TButton",
            font=ui_font(10, "bold"),
            background=c["primary"],
            foreground="#ffffff",
            bordercolor=c["primary"],
        )
        style.map(
            "Primary.TButton",
            background=[("active", c["primary_dark"]), ("disabled", "#9db8f3")],
            foreground=[("disabled", "#edf2ff")],
        )

        style.configure(
            "Treeview",
            rowheight=32,
            font=ui_font(9),
            background=c["surface"],
            fieldbackground=c["surface"],
            bordercolor=c["border"],
        )
        style.configure(
            "Treeview.Heading",
            font=ui_font(9, "bold"),
            background=c["card"],
            foreground=c["muted"],
            padding=(6, 7),
        )
        style.map(
            "Treeview",
            background=[("selected", c["primary"])],
            foreground=[("selected", "#ffffff")],
        )

        style.configure("TNotebook", background=c["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            padding=(16, 9),
            font=ui_font(10),
            background=c["card"],
            foreground=c["muted"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", c["surface"])],
            foreground=[("selected", c["primary"])],
        )
        style.configure("TCombobox", padding=4)

    # ------------------------------------------------------------------- logo
    def _load_logos(self) -> None:
        self.logo_left = self._load_logo(LOGO_LEFT_FILE, 46)
        self.logo_right = self._load_logo(LOGO_RIGHT_FILE, 46)

    def _load_logo(self, filename: str, target_height: int) -> object:
        """Muat logo PNG dan skalakan ke tinggi tertentu di atas latar putih.

        Mengembalikan None bila Pillow tidak terpasang atau file gagal dibaca,
        sehingga aplikasi tetap berjalan walaupun logo tidak tampil.
        """
        if not _PIL_AVAILABLE:
            return None
        try:
            path = app_base_dir() / filename
            image = Image.open(path).convert("RGBA")
            ratio = target_height / image.height
            width = max(1, round(image.width * ratio))
            image = image.resize((width, target_height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
            canvas.alpha_composite(image)
            return ImageTk.PhotoImage(canvas.convert("RGB"))
        except Exception:  # noqa: BLE001 - logo bersifat opsional
            return None

    # ----------------------------------------------------------------- layout
    def _build_layout(self) -> None:
        container = ttk.Frame(self.master, padding=16)
        container.pack(fill=tk.BOTH, expand=True)
        self._container = container
        container.columnconfigure(0, weight=0, minsize=336)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)

        self._build_header(container)

        sidebar_outer = tk.Frame(container, bg=self.colors["surface"])
        sidebar_outer.grid(row=1, column=0, sticky="nswe", padx=(0, 14))
        sidebar_outer.rowconfigure(0, weight=1)
        sidebar_outer.columnconfigure(0, weight=1)

        sidebar_canvas = tk.Canvas(
            sidebar_outer,
            bg=self.colors["surface"],
            highlightthickness=0,
            width=318,
        )
        sidebar_scroll = ttk.Scrollbar(
            sidebar_outer, orient="vertical", command=sidebar_canvas.yview
        )
        sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)
        sidebar_canvas.grid(row=0, column=0, sticky="nswe")
        sidebar_scroll.grid(row=0, column=1, sticky="ns")

        sidebar = ttk.Frame(sidebar_canvas, style="Surface.TFrame", padding=18)
        sidebar_window = sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")

        def _on_sidebar_configure(event):
            sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))

        def _on_canvas_resize(event):
            sidebar_canvas.itemconfig(sidebar_window, width=event.width)

        def _on_mousewheel(event):
            # Hanya scroll bila kontennya memang lebih tinggi dari area tampil.
            bbox = sidebar_canvas.bbox("all")
            if bbox and bbox[3] > sidebar_canvas.winfo_height():
                units = wheel_units(event)
                if units:
                    sidebar_canvas.yview_scroll(units, "units")

        sidebar.bind("<Configure>", _on_sidebar_configure)
        sidebar_canvas.bind("<Configure>", _on_canvas_resize)
        # bind_all saat kursor masuk sidebar agar wheel tetap jalan di atas tombol/label.
        sidebar_outer.bind(
            "<Enter>", lambda _e: bind_wheel(sidebar_canvas, _on_mousewheel, all_widgets=True)
        )
        sidebar_outer.bind(
            "<Leave>", lambda _e: unbind_wheel(sidebar_canvas, all_widgets=True)
        )

        main = ttk.Frame(container)
        main.grid(row=1, column=1, sticky="nswe")

        self._build_sidebar(sidebar)
        self._build_main(main)

        footer = ttk.Frame(container)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(footer, text=t("app.footer"), style="Footer.TLabel").pack()
        self._apply_file_labels()

    # ---------------------------------------------------------------- bahasa
    def change_language(self, code: str) -> None:
        """Ganti bahasa antarmuka tanpa kehilangan data analisis yang sedang terbuka."""
        if code == i18n.get_language():
            return
        if self._processing:
            # Tampilan tidak dibangun ulang saat transkripsi berjalan.
            self.language_var.set(i18n.LANGUAGES[i18n.get_language()])
            return
        i18n.set_language(code)
        self._rebuild_ui()
        self.status_var.set(t("st.language"))

    def _on_language_selected(self, _event: object = None) -> None:
        name = self.language_var.get()
        code = next(
            (key for key, label in i18n.LANGUAGES.items() if label == name),
            i18n.get_language(),
        )
        # Ditunda ke idle: combobox ini ikut dihancurkan saat tampilan dibangun ulang.
        self.master.after_idle(lambda: self.change_language(code))

    def _rebuild_ui(self) -> None:
        """Bangun ulang seluruh widget dalam bahasa aktif.

        Data (segmen, pasangan, path, offset, pengaturan) tersimpan sebagai atribut
        dan StringVar milik aplikasi, bukan di widget, sehingga cukup dirender ulang.
        Audio dan rentang tampilan Editor Waveform dibawa ke editor yang baru.
        """
        self._cancel_cell_edit()
        editor = self.waveform_editor
        editor.stop()
        audio_state = (editor.native_audio, editor.interpreter_audio, editor.t0, editor.t1)
        try:
            tab_index = self.notebook.index(self.notebook.select())
        except tk.TclError:
            tab_index = 0

        unbind_wheel(self.master, all_widgets=True)
        self._chart_canvas = None
        if self._container is not None:
            self._container.destroy()
        self.master.title(t("app.title"))
        self.language_var.set(i18n.LANGUAGES[i18n.get_language()])
        self._build_layout()

        editor = self.waveform_editor
        editor.native_audio, editor.interpreter_audio = audio_state[0], audio_state[1]
        editor.t0, editor.t1 = audio_state[2], audio_state[3]
        self.refresh_all()
        self.notebook.select(tab_index)

    def _apply_file_labels(self) -> None:
        """Isi label nama berkas sesuai state: nama berkas, teks demo, atau placeholder."""
        if self.native_path:
            self.native_file_var.set(os.path.basename(self.native_path))
        elif self._demo_active:
            self.native_file_var.set(t("demo.sl"))
        else:
            self.native_file_var.set(t("file.none_sl"))
        if self._demo_active and self.interpreter_file_vars and not any(
            self.interpreter_paths
        ):
            self.interpreter_file_vars[0].set(t("demo.tl"))

    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Frame(
            parent,
            bg=self.colors["surface"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1, uniform="header")
        header.columnconfigure(1, weight=0)
        header.columnconfigure(2, weight=1, uniform="header")

        self._place_logo(header, self.logo_left, "UPI · FPBS", column=0, edge="w")

        title_block = tk.Frame(header, bg=self.colors["surface"])
        title_block.grid(row=0, column=1, pady=15)
        tk.Label(
            title_block,
            text=t("app.title"),
            bg=self.colors["surface"],
            fg=self.colors["text"],
            font=ui_font(19, "bold"),
        ).pack()
        tk.Label(
            title_block,
            text=t("app.subtitle"),
            bg=self.colors["surface"],
            fg=self.colors["muted"],
            font=ui_font(9),
        ).pack(pady=(3, 0))

        self._place_logo(header, self.logo_right, "Diktisaintek", column=2, edge="e")

    def _place_logo(
        self,
        parent: tk.Frame,
        image: object,
        fallback_text: str,
        column: int,
        edge: str,
    ) -> None:
        padx = (22, 12) if edge == "w" else (12, 22)
        if image is not None:
            widget = tk.Label(parent, image=image, bg=self.colors["surface"])
        else:
            widget = tk.Label(
                parent,
                text=fallback_text,
                bg=self.colors["surface"],
                fg=self.colors["muted"],
                font=ui_font(11, "bold"),
            )
        widget.grid(row=0, column=column, sticky=edge, padx=padx, pady=14)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        c = self.colors

        def section_title(text: str) -> None:
            row = ttk.Frame(parent, style="Surface.TFrame")
            row.pack(fill=tk.X, pady=(0, 7))
            bar = tk.Frame(row, bg=c["primary"], width=3)
            bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
            ttk.Label(row, text=text.upper(), style="SectionHead.TLabel").pack(side=tk.LEFT)

        def hint(text: str) -> None:
            ttk.Label(
                parent,
                text=text,
                style="Muted.TLabel",
                wraplength=288,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

        def separator() -> None:
            ttk.Separator(parent).pack(fill=tk.X, pady=12)

        section_title(t("side.input1"))
        ttk.Label(
            parent, textvariable=self.native_file_var, style="Muted.TLabel", wraplength=288
        ).pack(anchor="w", pady=(0, 5))
        ttk.Button(parent, text=t("btn.choose_sl"), command=self.select_native_file).pack(
            fill=tk.X
        )
        self._offset_row(parent, self.native_offset_var)

        ttk.Label(parent, text="", style="Surface.TLabel").pack(pady=3)

        section_title(t("side.input2"))
        count_row = ttk.Frame(parent, style="Surface.TFrame")
        count_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(count_row, text=t("side.interp_count"), style="Muted.TLabel").pack(
            side=tk.LEFT
        )
        count_box = ttk.Combobox(
            count_row,
            textvariable=self.interp_count_var,
            values=("1", "2", "3", "4"),
            state="readonly",
            width=4,
        )
        count_box.pack(side=tk.RIGHT)
        count_box.bind(
            "<<ComboboxSelected>>", lambda _e: self._rebuild_interpreter_inputs()
        )
        self._interp_files_frame = ttk.Frame(parent, style="Surface.TFrame")
        self._interp_files_frame.pack(fill=tk.X)
        self._rebuild_interpreter_inputs()
        ttk.Button(
            parent,
            text=t("btn.split"),
            command=self.open_split_dialog,
        ).pack(fill=tk.X, pady=(8, 0))
        hint(t("hint.split"))

        separator()

        section_title(t("side.settings"))
        ttk.Label(parent, text=t("side.language"), style="Muted.TLabel").pack(anchor="w")
        language_box = ttk.Combobox(
            parent,
            textvariable=self.language_var,
            values=tuple(i18n.LANGUAGES.values()),
            state="readonly",
        )
        language_box.pack(fill=tk.X, pady=(2, 8))
        language_box.bind("<<ComboboxSelected>>", self._on_language_selected)
        ttk.Label(parent, text=t("side.model"), style="Muted.TLabel").pack(anchor="w")
        ttk.Combobox(
            parent, textvariable=self.model_var, values=MODEL_OPTIONS, state="readonly"
        ).pack(fill=tk.X, pady=(2, 8))
        ttk.Label(parent, text=t("side.mode"), style="Muted.TLabel").pack(anchor="w")
        mode_box = ttk.Combobox(
            parent,
            textvariable=self.mode_var,
            values=tuple(MODE_LABELS.keys()),
            state="readonly",
        )
        mode_box.pack(fill=tk.X, pady=(2, 6))
        mode_box.bind("<<ComboboxSelected>>", self.on_mode_change)
        hint(t("hint.mode"))

        self.analyze_button = ttk.Button(
            parent,
            text=t("btn.analyze"),
            style="Primary.TButton",
            command=self.start_analysis,
        )
        self.analyze_button.pack(fill=tk.X, pady=(2, 6))

        action_row = ttk.Frame(parent, style="Surface.TFrame")
        action_row.pack(fill=tk.X)
        action_row.columnconfigure((0, 1), weight=1)
        ttk.Button(action_row, text=t("btn.demo"), command=self.load_demo_data).grid(
            row=0, column=0, sticky="ew", padx=(0, 3)
        )
        ttk.Button(action_row, text=t("btn.export"), command=self.export_csv).grid(
            row=0, column=1, sticky="ew", padx=(3, 0)
        )
        ttk.Button(action_row, text=t("btn.save_session"), command=self.save_session).grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=(6, 0)
        )
        ttk.Button(action_row, text=t("btn.open_session"), command=self.load_session).grid(
            row=1, column=1, sticky="ew", padx=(3, 0), pady=(6, 0)
        )

        separator()

        section_title(t("side.correction"))
        hint(t("hint.correction"))
        ttk.Button(parent, text=t("btn.pair"), command=self.pair_selected).pack(
            fill=tk.X
        )
        attach_row = ttk.Frame(parent, style="Surface.TFrame")
        attach_row.pack(fill=tk.X, pady=(6, 0))
        attach_row.columnconfigure((0, 1), weight=1)
        ttk.Button(
            attach_row, text=t("btn.attach"), command=self.attach_selected
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(
            attach_row, text=t("btn.detach"), command=self.detach_selected
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        pair_row = ttk.Frame(parent, style="Surface.TFrame")
        pair_row.pack(fill=tk.X, pady=(6, 0))
        pair_row.columnconfigure((0, 1), weight=1)
        ttk.Button(
            pair_row, text=t("btn.remove_pair"), command=self.remove_selected_pair
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(pair_row, text=t("btn.realign"), command=self.reauto_pair).grid(
            row=0, column=1, sticky="ew", padx=(3, 0)
        )

        separator()

        status_card = tk.Frame(
            parent,
            bg=c["card"],
            highlightthickness=1,
            highlightbackground=c["border"],
        )
        status_card.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(
            status_card,
            text=t("side.status"),
            bg=c["card"],
            fg=c["muted"],
            font=ui_font(7, "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 0))
        tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=c["card"],
            fg=c["text"],
            font=ui_font(8),
            wraplength=280,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(1, 9))
        # Bar animasi proses; hanya tampil selama transkripsi berjalan
        # (dikendalikan _set_processing).
        self.progress_bar = ttk.Progressbar(status_card, mode="indeterminate")

    def _build_main(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        self._build_metric_strip(parent)

        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=1, column=0, sticky="nswe", pady=(12, 0))

        native_tab = ttk.Frame(self.notebook, padding=8)
        interpreter_tab = ttk.Frame(self.notebook, padding=8)
        waveform_tab = ttk.Frame(self.notebook, padding=8)
        lag_tab = ttk.Frame(self.notebook, padding=8)
        viz_tab = ttk.Frame(self.notebook, padding=8)
        for tab in (native_tab, interpreter_tab, lag_tab, viz_tab):
            tab.rowconfigure(0, weight=1)
            tab.columnconfigure(0, weight=1)

        self.notebook.add(native_tab, text=t("tab.sl"))
        self.notebook.add(interpreter_tab, text=t("tab.tl"))
        self.notebook.add(waveform_tab, text=t("tab.waveform"))
        self.notebook.add(lag_tab, text=t("tab.lag"))
        self.notebook.add(viz_tab, text=t("tab.viz"))

        self.native_tree = self._create_segment_tree(native_tab)
        self.interpreter_tree = self._create_segment_tree(interpreter_tab, with_speaker=True)
        self.waveform_editor = WaveformEditor(waveform_tab, self)
        self.lag_tree = self._create_lag_tree(lag_tab)
        self._build_legend(lag_tab)
        self._build_viz_tab(viz_tab)

        self.native_tree.bind(
            "<Double-1>", lambda e: self._begin_cell_edit(e, self.native_tree, "native")
        )
        self.interpreter_tree.bind(
            "<Double-1>",
            lambda e: self._begin_cell_edit(e, self.interpreter_tree, "interpreter"),
        )

    def _build_metric_strip(self, parent: ttk.Frame) -> None:
        c = self.colors
        strip = ttk.Frame(parent)
        strip.grid(row=0, column=0, sticky="ew")

        cards = (
            (t("card.pairs"), self.pair_count_var, c["primary"]),
            (t("card.mean"), self.avg_lag_var, c["success"]),
            (t("card.min"), self.min_lag_var, c["green"]),
            (t("card.max"), self.max_lag_var, c["danger"]),
            (t("card.confidence"), self.confidence_var, c["warning"]),
        )
        for position, (label, variable, color) in enumerate(cards):
            strip.columnconfigure(position, weight=1, uniform="metric")
            card = tk.Frame(
                strip,
                bg=c["surface"],
                highlightthickness=1,
                highlightbackground=c["border"],
            )
            card.grid(
                row=0,
                column=position,
                sticky="ew",
                padx=(0 if position == 0 else 8, 0),
            )
            tk.Frame(card, bg=color, height=3).pack(fill=tk.X)
            tk.Label(
                card,
                text=label.upper(),
                bg=c["surface"],
                fg=c["muted"],
                font=ui_font(8, "bold"),
            ).pack(anchor="w", padx=14, pady=(10, 0))
            tk.Label(
                card,
                textvariable=variable,
                bg=c["surface"],
                fg=color,
                font=ui_font(21, "bold"),
            ).pack(anchor="w", padx=14, pady=(0, 12))

    def _create_segment_tree(
        self, parent: ttk.Frame, with_speaker: bool = False
    ) -> ttk.Treeview:
        columns = (
            ("index", "speaker", "start", "end", "duration", "pair", "text")
            if with_speaker
            else ("index", "start", "end", "duration", "pair", "text")
        )
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        headings = {
            "index": "#",
            "speaker": t("col.speaker"),
            "start": t("col.start"),
            "end": t("col.end"),
            "duration": t("col.duration"),
            "pair": t("col.pair"),
            "text": t("col.text"),
        }
        widths = {
            "index": 48,
            "speaker": 66,
            "start": 82,
            "end": 82,
            "duration": 88,
            "pair": 80,
            "text": 560,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(
                column, width=widths[column], minwidth=40, anchor="w", stretch=column == "text"
            )

        tree.tag_configure("oddrow", background=self.colors["stripe"])
        tree.tag_configure("evenrow", background=self.colors["surface"])
        self._attach_scrollbars(parent, tree)

        tk.Label(
            parent,
            text=t("hint.edit_cell"),
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            font=ui_font(8),
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        return tree

    def _create_lag_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("pair", "evs", "gap", "category", "check", "native", "interpreter")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        widths = {
            "pair": 48,
            "evs": 100,
            "gap": 100,
            "category": 180,
            "check": 76,
            "native": 380,
            "interpreter": 380,
        }
        headings = {
            "pair": "#",
            "evs": "EVS (s)",
            "gap": "Gap (s)",
            "category": t("col.category"),
            "check": t("col.check"),
            "native": t("col.sl"),
            "interpreter": t("col.tl"),
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(
                column,
                width=widths[column],
                minwidth=40,
                anchor="w",
                stretch=column == "interpreter",
            )

        tree.tag_configure("oddrow", background=self.colors["stripe"])
        tree.tag_configure("evenrow", background=self.colors["surface"])
        for category_name, category_color in CATEGORY_COLORS.items():
            tree.tag_configure(category_name, foreground=category_color)
        self._attach_scrollbars(parent, tree)
        return tree

    def _attach_scrollbars(self, parent: ttk.Frame, tree: ttk.Treeview) -> None:
        yscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nswe")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

    @staticmethod
    def _category_ranges() -> dict[str, str]:
        """Susun teks rentang tiap kategori dari tabel ambang LAG_CATEGORIES."""
        ranges: dict[str, str] = {}
        lower = 0.0
        for name, upper, _description in LAG_CATEGORIES:
            if upper is None:
                ranges[name] = t("legend.range_open", lower=f"{lower:g}")
            else:
                ranges[name] = t("legend.range", lower=f"{lower:g}", upper=f"{upper:g}")
                lower = upper
        return ranges

    def _build_legend(self, parent: ttk.Frame) -> None:
        c = self.colors
        legend = tk.Frame(
            parent,
            bg=c["card"],
            highlightthickness=1,
            highlightbackground=c["border"],
        )
        legend.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        tk.Label(
            legend,
            text=t("legend.title"),
            bg=c["card"],
            fg=c["muted"],
            font=ui_font(7, "bold"),
        ).pack(anchor="w", padx=12, pady=(8, 4))

        items = tk.Frame(legend, bg=c["card"])
        items.pack(fill=tk.X, padx=12, pady=(0, 9))

        ranges = self._category_ranges()
        for position, (name, _upper, _description) in enumerate(LAG_CATEGORIES):
            color = CATEGORY_COLORS.get(name, c["muted"])
            description = category_description(name)
            cell = tk.Frame(items, bg=c["card"])
            cell.grid(row=0, column=position, sticky="w", padx=(0, 20))

            swatch = tk.Frame(cell, bg=color, width=6)
            swatch.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 9))

            # Rentang di baris sendiri agar keempat kategori muat dalam satu
            # baris pada ukuran jendela bawaan (nama English lebih panjang).
            text_block = tk.Frame(cell, bg=c["card"])
            text_block.pack(side=tk.LEFT)
            tk.Label(
                text_block,
                text=ranges[name],
                bg=c["card"],
                fg=color,
                font=ui_font(8, "bold"),
            ).pack(anchor="w")
            tk.Label(
                text_block,
                text=category_label(name),
                bg=c["card"],
                fg=color,
                font=ui_font(9, "bold"),
            ).pack(anchor="w")
            tk.Label(
                text_block,
                text=description,
                bg=c["card"],
                fg=c["muted"],
                font=ui_font(8),
            ).pack(anchor="w")

        tk.Label(
            legend,
            text=t("legend.review_note"),
            bg=c["card"],
            fg=c["muted"],
            font=ui_font(8),
        ).pack(anchor="w", padx=12, pady=(0, 9))

    # ------------------------------------------------------- visualisasi chart
    def _build_viz_tab(self, parent: ttk.Frame) -> None:
        c = self.colors
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        tk.Label(
            parent,
            textvariable=self.viz_quality_var,
            bg=c["bg"],
            fg=c["muted"],
            font=ui_font(9),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Strip statistik kuantitatif tambahan (melengkapi kartu metrik utama).
        strip = ttk.Frame(parent)
        strip.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        stats = (
            (t("stat.median"), self.viz_median_var, c["success"]),
            (t("stat.sd"), self.viz_sd_var, c["primary"]),
            (t("stat.merged"), self.viz_merged_var, c["warning"]),
            (t("stat.omissions"), self.viz_omission_var, c["danger"]),
            (t("stat.additions"), self.viz_addition_var, c["muted"]),
        )
        for position, (label, variable, color) in enumerate(stats):
            strip.columnconfigure(position, weight=1, uniform="vizstat")
            card = tk.Frame(
                strip,
                bg=c["surface"],
                highlightthickness=1,
                highlightbackground=c["border"],
            )
            card.grid(
                row=0,
                column=position,
                sticky="ew",
                padx=(0 if position == 0 else 6, 0),
            )
            tk.Label(
                card,
                text=label.upper(),
                bg=c["surface"],
                fg=c["muted"],
                font=ui_font(7, "bold"),
            ).pack(anchor="w", padx=10, pady=(7, 0))
            tk.Label(
                card,
                textvariable=variable,
                bg=c["surface"],
                fg=color,
                font=ui_font(14, "bold"),
            ).pack(anchor="w", padx=10, pady=(0, 7))

        self._chart_canvas = tk.Canvas(parent, bg=c["bg"], highlightthickness=0)
        self._chart_canvas.grid(row=2, column=0, sticky="nswe")
        self._chart_canvas.bind("<Configure>", lambda _e: self._draw_charts())

    def _draw_charts(self) -> None:
        canvas = self._chart_canvas
        if canvas is None:
            return
        canvas.delete("all")
        W = canvas.winfo_width()
        H = canvas.winfo_height()
        if W < 50 or H < 50:
            return
        mode = self.current_mode()
        split = max(int(W * 0.38), 220)
        self._draw_chart_card(canvas, 2, 2, split - 5, H - 4)
        self._draw_chart_card(canvas, split + 5, 2, W - 4, H - 4)
        self._draw_category_donut(canvas, 14, 6, split - 17, H - 16, mode)
        self._draw_evs_barchart(canvas, split + 17, 6, W - 16, H - 16, mode)

    def _draw_chart_card(
        self, canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int
    ) -> None:
        canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=self.colors["surface"],
            outline=self.colors["border"],
        )

    def _draw_category_donut(
        self,
        canvas: tk.Canvas,
        x1: int, y1: int, x2: int, y2: int,
        mode: str,
    ) -> None:
        c = self.colors
        mid_x = (x1 + x2) / 2

        canvas.create_text(
            x1 + 2, y1 + 18, text=t("chart.distribution"), anchor="w",
            font=ui_font(10, "bold"), fill=c["text"],
        )

        # Hitung jumlah tiap kategori
        counts: dict[str, int] = {name: 0 for name, _, _ in LAG_CATEGORIES}
        counts[CATEGORY_UNPAIRED] = 0
        for record in self.records:
            cat = lag_category(record.lag_for(mode))
            counts[cat] = counts.get(cat, 0) + 1
        total = sum(counts.values())

        # Geometri donut
        n_legend = len(LAG_CATEGORIES) + 1
        legend_h = n_legend * 27 + 16
        area_y1 = y1 + 42
        area_y2 = y2 - legend_h
        area_h = max(area_y2 - area_y1, 1)
        area_w = x2 - x1
        r = max(min(area_w / 2 * 0.72, area_h / 2 * 0.88), 30)
        cx = mid_x
        cy = area_y1 + area_h / 2

        if total == 0:
            canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=0, extent=359.9,
                fill=c["border"], outline="", style=tk.PIESLICE,
            )
            canvas.create_oval(
                cx - r * 0.52, cy - r * 0.52, cx + r * 0.52, cy + r * 0.52,
                fill=c["surface"], outline="",
            )
            canvas.create_text(
                cx, cy, text=t("chart.empty"),
                font=ui_font(9), fill=c["muted"],
            )
        else:
            order = [name for name, _, _ in LAG_CATEGORIES] + [CATEGORY_UNPAIRED]
            angle = 90.0
            for name in order:
                count = counts.get(name, 0)
                if count == 0:
                    continue
                extent = 360.0 * count / total
                color = CATEGORY_COLORS.get(name, c["muted"])
                canvas.create_arc(
                    cx - r, cy - r, cx + r, cy + r,
                    start=angle, extent=extent,
                    fill=color, outline=c["surface"], width=2, style=tk.PIESLICE,
                )
                angle += extent

            inner_r = r * 0.52
            canvas.create_oval(
                cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                fill=c["surface"], outline="",
            )
            canvas.create_text(
                cx, cy - 9, text=str(total),
                font=ui_font(16, "bold"), fill=c["text"],
            )
            canvas.create_text(
                cx, cy + 11, text=t("chart.pairs_unit"),
                font=ui_font(8), fill=c["muted"],
            )

        # Legenda di bawah donut
        ly = y2 - legend_h + 10
        for name in ([n for n, _, _ in LAG_CATEGORIES] + [CATEGORY_UNPAIRED]):
            count = counts.get(name, 0)
            pct = f"{100 * count / total:.0f}%" if total > 0 else "–"
            color = CATEGORY_COLORS.get(name, c["muted"])
            lx = x1 + 16
            canvas.create_rectangle(lx, ly + 3, lx + 12, ly + 15, fill=color, outline="")
            canvas.create_text(
                lx + 17, ly + 9,
                text=f"{category_label(name)}  ·  {count} ({pct})",
                font=ui_font(8), fill=c["text"], anchor="w",
            )
            ly += 27

    def _draw_evs_barchart(
        self,
        canvas: tk.Canvas,
        x1: int, y1: int, x2: int, y2: int,
        mode: str,
    ) -> None:
        c = self.colors
        mid_x = (x1 + x2) / 2
        label = "EVS" if mode == MODE_SIMULTANEOUS else "Gap"

        canvas.create_text(
            x1 + 2, y1 + 18,
            text=t("chart.per_pair", label=label), anchor="w",
            font=ui_font(10, "bold"), fill=c["text"],
        )

        paired = [
            (record, record.lag_for(mode))
            for record in self.records
            if record.is_paired and record.lag_for(mode) is not None
        ]

        if not paired:
            canvas.create_text(
                mid_x, (y1 + y2) / 2,
                text=t("chart.no_pairs"),
                font=ui_font(10), fill=c["muted"],
            )
            return

        # Area chart
        p_l, p_r, p_t, p_b = 52, 16, 42, 52
        cx1 = x1 + p_l
        cx2 = x2 - p_r
        cy1 = y1 + p_t
        cy2 = y2 - p_b
        cw = cx2 - cx1
        ch = cy2 - cy1

        if cw < 20 or ch < 20:
            return

        values = [v for _, v in paired]
        max_v = max(max(values), 1.0)
        for _n, upper, _d in LAG_CATEGORIES:
            if upper is not None and max_v <= upper:
                max_v = float(upper)
                break
        else:
            max_v = max_v * 1.15

        # Garis referensi batas kategori
        for _name, upper, _desc in LAG_CATEGORIES:
            if upper is None or upper > max_v:
                continue
            ty = cy2 - (upper / max_v) * ch
            canvas.create_line(cx1, ty, cx2, ty, fill=c["border"], dash=(4, 3))
            canvas.create_text(
                cx1 - 5, ty, text=f"{upper:.0f}",
                font=ui_font(7), fill=c["muted"], anchor="e",
            )

        canvas.create_text(
            cx1 - 5, cy2, text="0",
            font=ui_font(7), fill=c["muted"], anchor="e",
        )

        # Bar tiap pasangan
        n = len(paired)
        spacing = cw / n
        bar_w = max(min(spacing * 0.72, 50.0), 4.0)

        for idx, (record, lag) in enumerate(paired):
            bx = cx1 + (idx + 0.5) * spacing
            bh = max(abs(lag) / max_v * ch, 2.0)
            by_top = cy2 - bh
            color = CATEGORY_COLORS.get(lag_category(lag), c["muted"])
            canvas.create_rectangle(
                bx - bar_w / 2, by_top, bx + bar_w / 2, cy2,
                fill=color, outline="",
            )
            canvas.create_text(
                bx, cy2 + 10, text=f"#{record.pair_index}",
                font=ui_font(7), fill=c["muted"], anchor="n",
            )
            if bar_w >= 12 and bh > 10:
                canvas.create_text(
                    bx, max(by_top - 6, cy1 + 8),
                    text=f"{lag:.1f}s",
                    font=ui_font(7), fill=c["text"], anchor="s",
                )

        # Garis rata-rata (acuan visual cepat posisi keseluruhan).
        mean_value = sum(values) / len(values)
        if 0 < mean_value <= max_v:
            mean_y = cy2 - (mean_value / max_v) * ch
            canvas.create_line(
                cx1, mean_y, cx2, mean_y,
                fill=c["success"], dash=(6, 3), width=2,
            )
            canvas.create_text(
                cx2 - 4, mean_y - 8,
                text=t("chart.mean", value=f"{mean_value:.2f}"), anchor="e",
                font=ui_font(7, "bold"), fill=c["success"],
            )

        # Sumbu
        canvas.create_line(cx1, cy1, cx1, cy2, fill=c["border"])
        canvas.create_line(cx1, cy2, cx2, cy2, fill=c["border"])

        canvas.create_text(
            mid_x, cy2 + 38, text=t("chart.x_axis"),
            font=ui_font(8), fill=c["muted"],
        )
        canvas.create_text(
            x1 + 8, (cy1 + cy2) / 2, text=t("chart.y_axis"),
            font=ui_font(8), fill=c["muted"],
        )

    # --------------------------------------------------------- edit timestamp
    def _begin_cell_edit(self, event: tk.Event, tree: ttk.Treeview, kind: str) -> None:
        """Buka editor saat sel Start/End/Transkrip diklik dua kali."""
        self._commit_cell_edit()

        if tree.identify_region(event.x, event.y) != "cell":
            return
        row_iid = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not row_iid or not column_id:
            return

        columns = tree["columns"]
        column_index = int(column_id[1:]) - 1
        if not 0 <= column_index < len(columns):
            return
        column_name = columns[column_index]
        if column_name not in EDITABLE_SEGMENT_COLUMNS:
            self.status_var.set(t("st.only_editable"))
            return

        lookup = self._native_by_index if kind == "native" else self._interpreter_by_index
        segment = lookup.get(int(row_iid[1:]))
        if segment is None:
            return

        bbox = tree.bbox(row_iid, column_id)
        if not bbox:
            return
        x, y, width, height = bbox

        if column_name == "start":
            raw_value = f"{segment.start:.2f}"
        elif column_name == "end":
            raw_value = f"{segment.end:.2f}"
        else:
            raw_value = segment.text

        entry = ttk.Entry(tree, font=ui_font(9))
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, raw_value)
        entry.select_range(0, tk.END)
        entry.focus_set()
        entry.bind("<Return>", lambda _e: self._commit_cell_edit())
        entry.bind("<Escape>", lambda _e: self._cancel_cell_edit())
        entry.bind("<FocusOut>", lambda _e: self._commit_cell_edit())

        self._cell_editor = entry
        self._edit_context = (segment, column_name)

    def _commit_cell_edit(self) -> None:
        """Simpan nilai editor ke segmen lalu hitung ulang lag."""
        if self._cell_editor is None or self._edit_context is None:
            return

        entry = self._cell_editor
        segment, column_name = self._edit_context
        # Kosongkan state dulu agar event FocusOut dari destroy() tidak rekursif.
        self._cell_editor = None
        self._edit_context = None
        value = entry.get().strip()
        entry.destroy()

        if column_name == "text":
            segment.text = value
        else:
            try:
                number = float(value.replace(",", "."))
            except ValueError:
                self.status_var.set(t("st.bad_number", value=value))
                return
            if number < 0:
                self.status_var.set(t("st.negative"))
                return
            if column_name == "start" and number > segment.end:
                self.status_var.set(t("st.start_after_end"))
                return
            if column_name == "end" and number < segment.start:
                self.status_var.set(t("st.end_before_start"))
                return
            if column_name == "start":
                segment.start = number
            else:
                segment.end = number

        self.refresh_all()
        self.status_var.set(t("st.segment_updated"))

    def _cancel_cell_edit(self) -> None:
        if self._cell_editor is None:
            return
        entry = self._cell_editor
        self._cell_editor = None
        self._edit_context = None
        entry.destroy()

    # --------------------------------------------------------------- handlers
    def current_mode(self) -> str:
        return MODE_LABELS.get(self.mode_var.get(), MODE_SIMULTANEOUS)

    def select_native_file(self) -> None:
        path = self._ask_media_file(t("dlg.choose_sl"))
        if not path:
            return
        self._end_demo()
        self.native_path = path
        self.native_file_var.set(os.path.basename(path))
        self.status_var.set(t("st.sl_ready"))

    def _end_demo(self) -> None:
        """Keluar dari mode demo: label demo pada slot berkas diganti placeholder."""
        if not self._demo_active:
            return
        self._demo_active = False
        self._apply_file_labels()
        for slot, var in enumerate(self.interpreter_file_vars):
            if not self.interpreter_paths[slot]:
                suffix = f" {slot + 1}" if len(self.interpreter_file_vars) > 1 else ""
                var.set(t("file.none_tl", suffix=suffix))

    def _offset_row(self, parent: ttk.Frame, variable: tk.StringVar) -> None:
        """Baris kecil 'Offset mulai (detik)' di bawah tombol pilih file."""
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row, text=t("side.offset"), style="Muted.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Entry(row, textvariable=variable, width=8, justify="right").pack(
            side=tk.RIGHT
        )

    def _rebuild_interpreter_inputs(self) -> None:
        """Susun ulang slot file penerjemah sesuai jumlah yang dipilih."""
        count = int(self.interp_count_var.get())
        self.interpreter_paths = (self.interpreter_paths + [""] * count)[:count]
        old_offsets = [var.get() for var in self.interpreter_offset_vars]

        for child in self._interp_files_frame.winfo_children():
            child.destroy()
        self.interpreter_file_vars = []
        self.interpreter_offset_vars = []

        for slot in range(count):
            path = self.interpreter_paths[slot]
            suffix = f" {slot + 1}" if count > 1 else ""
            var = tk.StringVar(
                value=os.path.basename(path)
                if path
                else t("file.none_tl", suffix=suffix)
            )
            self.interpreter_file_vars.append(var)
            ttk.Label(
                self._interp_files_frame,
                textvariable=var,
                style="Muted.TLabel",
                wraplength=288,
            ).pack(anchor="w", pady=(4 if slot else 0, 5))
            ttk.Button(
                self._interp_files_frame,
                text=t("btn.choose_tl", suffix=suffix),
                command=lambda s=slot: self.select_interpreter_file(s),
            ).pack(fill=tk.X)
            offset_var = tk.StringVar(
                value=old_offsets[slot] if slot < len(old_offsets) else "0"
            )
            self.interpreter_offset_vars.append(offset_var)
            self._offset_row(self._interp_files_frame, offset_var)

    def select_interpreter_file(self, slot: int = 0) -> None:
        count = len(self.interpreter_paths)
        suffix = f" {slot + 1}" if count > 1 else ""
        path = self._ask_media_file(t("dlg.choose_tl", suffix=suffix))
        if not path:
            return
        self._end_demo()
        self.interpreter_paths[slot] = path
        self.interpreter_file_vars[slot].set(os.path.basename(path))
        self.status_var.set(t("st.tl_ready", suffix=suffix))

    @staticmethod
    def _ask_media_file(title: str) -> str:
        return filedialog.askopenfilename(
            title=title,
            filetypes=[
                (t("dlg.media_files"), "*.mp3 *.wav *.mp4 *.m4a *.mpeg *.mpga *.webm"),
                (t("dlg.all_files"), "*.*"),
            ],
        )

    def load_demo_data(self) -> None:
        self.native_path = ""
        self.interp_count_var.set("1")
        self.interpreter_paths = [""]
        self._rebuild_interpreter_inputs()
        self._demo_active = True
        self._apply_file_labels()
        self.native_segments, self.interpreter_segments = _demo_segments()
        for segment in self.interpreter_segments:
            segment.speaker = "P1"
        self.records = align_segments(self.native_segments, self.interpreter_segments)
        self._rebuild_indexes()
        # Sintesis audio dummy agar Editor Waveform punya isi untuk pratinjau.
        total_duration = (
            max(
                max((s.end for s in self.native_segments), default=30.0),
                max((s.end for s in self.interpreter_segments), default=30.0),
            )
            + 2.0
        )
        self.waveform_editor.set_audio(
            synthesize_demo_audio(self.native_segments, total_duration, frequency=440.0),
            synthesize_demo_audio(self.interpreter_segments, total_duration, frequency=280.0),
        )
        self.refresh_all()
        self.status_var.set(t("st.demo_loaded"))

    def start_analysis(self) -> None:
        missing = [
            str(slot + 1)
            for slot, path in enumerate(self.interpreter_paths)
            if not path
        ]
        if not self.native_path or missing:
            detail = (
                t("msg.missing_slots", slots=", ".join(missing))
                if self.native_path and missing
                else ""
            )
            messagebox.showwarning(t("msg.warning"), t("msg.choose_all") + detail)
            return

        # Snapshot input di thread utama; worker tidak menyentuh state GUI
        # yang bisa berubah (mis. jumlah penerjemah diubah saat proses jalan).
        self._native_offset = self._parse_offset(self.native_offset_var.get())
        self._interp_offsets = [
            self._parse_offset(var.get()) for var in self.interpreter_offset_vars
        ]
        self._job_native_path = self.native_path
        self._job_interp_paths = list(self.interpreter_paths)

        self._set_processing(True)
        self.status_var.set(t("st.transcribing"))
        self.native_segments = []
        self.interpreter_segments = []
        self.records = []
        self._rebuild_indexes()
        self.waveform_editor.clear()
        self.refresh_all()

        thread = threading.Thread(target=self._analysis_worker, daemon=True)
        thread.start()
        self.master.after(120, self._poll_worker)

    def _analysis_worker(self) -> None:
        try:
            model = self.model_var.get()
            total = len(self._job_interp_paths)
            self.worker_queue.put(("status", t("st.transcribe_sl")))
            native = transcribe_media(
                self._job_native_path, model, language=NATIVE_LANGUAGE, source=SOURCE_NATIVE
            )
            self._shift_segments(native, self._native_offset)

            # Transkripsi tiap penerjemah, beri label penutur, gabung ke satu
            # timeline. Asumsi: semua rekaman dimulai pada momen yang sama.
            interpreter: list[Segment] = []
            interpreter_audios: list[object] = []
            for slot, path in enumerate(self._job_interp_paths, start=1):
                progress = f" {slot}/{total}" if total > 1 else ""
                self.worker_queue.put(
                    ("status", t("st.transcribe_tl", progress=progress))
                )
                segments = transcribe_media(
                    path,
                    model,
                    language=INTERPRETER_LANGUAGE,
                    source=SOURCE_INTERPRETER,
                )
                offset = (
                    self._interp_offsets[slot - 1]
                    if slot - 1 < len(self._interp_offsets)
                    else 0.0
                )
                self._shift_segments(segments, offset)
                label = f"P{slot}"
                for segment in segments:
                    segment.speaker = label
                interpreter.extend(segments)
                try:
                    interpreter_audios.append(
                        self._shift_audio(load_audio(path), offset)
                    )
                except Exception:  # noqa: BLE001 - editor tetap jalan tanpa audio
                    interpreter_audios.append(None)

            interpreter.sort(key=lambda seg: seg.start)
            for position, segment in enumerate(interpreter, start=1):
                segment.index = position

            records = align_segments(native, interpreter)

            self.worker_queue.put(("status", t("st.loading_audio")))
            try:
                native_audio = self._shift_audio(
                    load_audio(self._job_native_path), self._native_offset
                )
            except Exception:  # noqa: BLE001 - editor tetap jalan tanpa audio
                native_audio = None
            interpreter_audio = self._mix_audio(interpreter_audios)

            self.worker_queue.put(
                ("success", native, interpreter, records, native_audio, interpreter_audio)
            )
        except Exception as exc:  # noqa: BLE001 - ditampilkan ke pengguna
            self.worker_queue.put(("error", str(exc)))

    @staticmethod
    def _parse_offset(value: str) -> float:
        """Baca offset detik dari input teks; teks tidak sah dianggap 0."""
        try:
            return float(value.strip().replace(",", "."))
        except (ValueError, AttributeError):
            return 0.0

    @staticmethod
    def _shift_segments(segments: list[Segment], offset: float) -> None:
        """Geser seluruh timestamp segmen sebesar offset (detik, boleh negatif)."""
        if not offset:
            return
        for segment in segments:
            segment.start = max(0.0, segment.start + offset)
            segment.end = max(segment.start, segment.end + offset)

    @staticmethod
    def _shift_audio(audio: object, offset: float) -> object:
        """Geser audio agar sinkron dengan timestamp yang sudah di-offset."""
        if audio is None or not offset:
            return audio
        import numpy as np

        samples = int(round(abs(offset) * SAMPLE_RATE))
        if samples == 0:
            return audio
        if offset > 0:
            return np.concatenate(
                [np.zeros(samples, dtype=audio.dtype), audio]
            )
        return audio[samples:]

    @staticmethod
    def _mix_audio(audios: list) -> object:
        """Campur beberapa track penerjemah menjadi satu untuk Editor Waveform.

        Audio dari load_audio bertipe int16; penjumlahan dilakukan di int32
        lalu di-clip kembali ke int16 agar skala tetap cocok dengan renderer
        waveform dan playback.
        """
        arrays = [audio for audio in audios if audio is not None and len(audio)]
        if not arrays:
            return None
        if len(arrays) == 1:
            return arrays[0]
        import numpy as np

        length = max(len(array) for array in arrays)
        mixed = np.zeros(length, dtype=np.int32)
        for array in arrays:
            mixed[: len(array)] += array.astype(np.int32)
        return np.clip(mixed, -32768, 32767).astype(np.int16)

    def _poll_worker(self) -> None:
        try:
            message = self.worker_queue.get_nowait()
        except queue.Empty:
            self.master.after(120, self._poll_worker)
            return

        kind = message[0]
        if kind == "status":
            self.status_var.set(message[1])
            self.master.after(120, self._poll_worker)
            return

        if kind == "success":
            self.native_segments = message[1]
            self.interpreter_segments = message[2]
            self.records = message[3]
            self._rebuild_indexes()
            self.waveform_editor.set_audio(message[4], message[5])
            self.refresh_all()
            self.status_var.set(t("st.analysis_done"))
        else:
            self.status_var.set(t("st.analysis_failed"))
            messagebox.showerror(t("msg.error"), message[1])

        self._set_processing(False)

    def _set_processing(self, active: bool) -> None:
        """Tampilkan/sembunyikan indikator proses transkripsi."""
        self._processing = active
        if active:
            self.analyze_button.state(["disabled"])
            self.analyze_button.configure(text=t("btn.processing"))
            self.progress_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.analyze_button.configure(text=t("btn.analyze"))
            self.analyze_button.state(["!disabled"])

    def on_mode_change(self, _event: object = None) -> None:
        # Ukuran lag utama (EVS atau gap) dan kategori ikut berubah.
        self.refresh_lag_table()
        self.update_summary()
        self._draw_charts()
        self.status_var.set(t("st.mode", mode=self.mode_var.get()))

    def pair_selected(self) -> None:
        native_selection = self.native_tree.selection()
        interpreter_selection = self.interpreter_tree.selection()
        if len(native_selection) != 1 or len(interpreter_selection) != 1:
            messagebox.showinfo(t("msg.info"), t("msg.pick_pair_rows"))
            return

        native = self._native_by_index.get(int(native_selection[0][1:]))
        interpreter = self._interpreter_by_index.get(int(interpreter_selection[0][1:]))
        if native is None or interpreter is None:
            return

        self.records = assign_pair(self.records, native, interpreter)
        self.refresh_all()
        self.status_var.set(
            t("st.pair_created", source=native.index, interpreter=interpreter.index)
        )

    def _selected_transcript_segments(self) -> list[Segment]:
        """Ambil segmen yang sedang terpilih di tab Transkrip Native/Penerjemah."""
        segments: list[Segment] = []
        selections = (
            (self.native_tree.selection(), self._native_by_index),
            (self.interpreter_tree.selection(), self._interpreter_by_index),
        )
        for selection, lookup in selections:
            for iid in selection:
                segment = lookup.get(int(iid[1:]))
                if segment is not None:
                    segments.append(segment)
        return segments

    def attach_selected(self) -> None:
        """Masukkan segmen terpilih ke pasangan yang dipilih di tab Hasil Lag."""
        lag_selection = self.lag_tree.selection()
        if len(lag_selection) != 1:
            messagebox.showinfo(t("msg.info"), t("msg.pick_target_pair"))
            return
        target = self._record_by_iid.get(lag_selection[0])
        if target is None:
            return

        segments = self._selected_transcript_segments()
        existing = target.natives + target.interpreters
        segments = [
            seg for seg in segments
            if not any(seg is member for member in existing)
        ]
        if not segments:
            messagebox.showinfo(t("msg.info"), t("msg.pick_attach"))
            return

        self.records = attach_segments(self.records, target, segments)
        self.refresh_all()
        labels = ", ".join(self._segment_side_label(seg) for seg in segments)
        self.status_var.set(t("st.attached", labels=labels))

    def detach_selected(self) -> None:
        """Keluarkan segmen terpilih dari pasangannya menjadi orphan."""
        segments = self._selected_transcript_segments()
        if not segments:
            messagebox.showinfo(t("msg.info"), t("msg.pick_detach"))
            return

        for segment in segments:
            self.records = detach_segment(self.records, segment)
        self.refresh_all()
        labels = ", ".join(self._segment_side_label(seg) for seg in segments)
        self.status_var.set(t("st.detached", labels=labels))

    @staticmethod
    def _segment_side_label(segment: Segment) -> str:
        side = t("label.source" if segment.source == SOURCE_NATIVE else "label.interpreter")
        return f"{side} #{segment.index}"

    def remove_selected_pair(self) -> None:
        selection = self.lag_tree.selection()
        if len(selection) != 1:
            messagebox.showinfo(t("msg.info"), t("msg.pick_pair_row"))
            return

        record = self._record_by_iid.get(selection[0])
        if record is None:
            return

        self.records = remove_pair(self.records, record)
        self.refresh_all()
        self.status_var.set(t("st.pair_removed"))

    def reauto_pair(self) -> None:
        if not self.native_segments or not self.interpreter_segments:
            messagebox.showinfo(t("msg.info"), t("msg.no_transcripts"))
            return
        if self.records and not messagebox.askyesno(
            t("msg.confirm"), t("msg.realign_confirm")
        ):
            return
        self.records = align_segments(self.native_segments, self.interpreter_segments)
        self.refresh_all()
        self.status_var.set(t("st.realigned"))

    def open_split_dialog(self) -> None:
        """Buka dialog preprocessing pemisah rekaman multi-penerjemah."""
        SplitRecordingDialog(self)

    # ----------------------------------------------------------------- tables
    def _rebuild_indexes(self) -> None:
        self._native_by_index = {segment.index: segment for segment in self.native_segments}
        self._interpreter_by_index = {
            segment.index: segment for segment in self.interpreter_segments
        }

    def refresh_all(self) -> None:
        self.refresh_segment_tables()
        self.refresh_lag_table()
        self.update_summary()
        if getattr(self, "waveform_editor", None) is not None:
            self.waveform_editor.refresh()
        if self._chart_canvas is not None:
            self._draw_charts()

    def _segment_pair_lookup(self) -> tuple[dict[int, int], dict[int, int]]:
        native_pairs: dict[int, int] = {}
        interpreter_pairs: dict[int, int] = {}
        for record in self.records:
            for segment in record.natives:
                native_pairs[segment.index] = record.pair_index
            for segment in record.interpreters:
                interpreter_pairs[segment.index] = record.pair_index
        return native_pairs, interpreter_pairs

    @staticmethod
    def _stripe(position: int) -> str:
        return "evenrow" if position % 2 == 0 else "oddrow"

    def refresh_segment_tables(self) -> None:
        native_pairs, interpreter_pairs = self._segment_pair_lookup()

        for tree in (self.native_tree, self.interpreter_tree):
            for item in tree.get_children():
                tree.delete(item)

        for position, segment in enumerate(self.native_segments):
            pair = native_pairs.get(segment.index)
            self.native_tree.insert(
                "",
                tk.END,
                iid=f"n{segment.index}",
                values=(
                    segment.index,
                    self.format_seconds(segment.start),
                    self.format_seconds(segment.end),
                    self.format_seconds(segment.duration),
                    f"#{pair}" if pair else "-",
                    segment.text,
                ),
                tags=(self._stripe(position),),
            )

        for position, segment in enumerate(self.interpreter_segments):
            pair = interpreter_pairs.get(segment.index)
            self.interpreter_tree.insert(
                "",
                tk.END,
                iid=f"i{segment.index}",
                values=(
                    segment.index,
                    segment.speaker or "-",
                    self.format_seconds(segment.start),
                    self.format_seconds(segment.end),
                    self.format_seconds(segment.duration),
                    f"#{pair}" if pair else "-",
                    segment.text,
                ),
                tags=(self._stripe(position),),
            )

    def refresh_lag_table(self) -> None:
        mode = self.current_mode()

        # Tandai ukuran lag yang sedang menjadi acuan utama.
        self.lag_tree.heading(
            "evs", text="EVS ★ (s)" if mode == MODE_SIMULTANEOUS else "EVS (s)"
        )
        self.lag_tree.heading(
            "gap", text="Gap ★ (s)" if mode == MODE_CONSECUTIVE else "Gap (s)"
        )

        for item in self.lag_tree.get_children():
            self.lag_tree.delete(item)
        self._record_by_iid = {}

        for position, record in enumerate(self.records):
            iid = f"p{record.pair_index}"
            self._record_by_iid[iid] = record
            category = lag_category(record.lag_for(mode))
            self.lag_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    record.pair_index,
                    self.format_optional_seconds(record.evs),
                    self.format_optional_seconds(record.gap),
                    category_label(category),
                    "⚠" if self._needs_review(record) else "",
                    self._describe_chunk(record.natives),
                    self._describe_chunk(record.interpreters),
                ),
                tags=(category, self._stripe(position)),
            )

    @staticmethod
    def _needs_review(record: LagRecord) -> bool:
        """Chunk yang sebaiknya diverifikasi manual: gabungan banyak segmen,
        EVS negatif (penerjemah mendahului native), atau tanpa pasangan."""
        if not record.is_paired:
            return True
        if len(record.natives) > 1 or len(record.interpreters) > 1:
            return True
        return record.evs is not None and record.evs < 0

    def _quality_counts(self) -> dict[str, int]:
        """Hitung komposisi struktur pasangan untuk statistik & export.

        one_to_one: pasangan 1 kalimat <-> 1 kalimat (paling andal).
        merged: pasangan lengkap yang menggabung >1 segmen di salah satu sisi.
        omissions: ujaran native tanpa pasangan (tidak diterjemahkan).
        additions: ujaran penerjemah tanpa pasangan (tanpa sumber).
        needs_review: baris bertanda ⚠ pada kolom Cek.
        """
        paired = [record for record in self.records if record.is_paired]
        one_to_one = [
            record
            for record in paired
            if len(record.natives) == 1
            and len(record.interpreters) == 1
            and (record.evs is None or record.evs >= 0)
        ]
        return {
            "paired": len(paired),
            "one_to_one": len(one_to_one),
            "merged": sum(
                1
                for record in paired
                if len(record.natives) > 1 or len(record.interpreters) > 1
            ),
            "omissions": sum(
                1
                for record in self.records
                if record.natives and not record.interpreters
            ),
            "additions": sum(
                1
                for record in self.records
                if record.interpreters and not record.natives
            ),
            "needs_review": sum(
                1 for record in self.records if self._needs_review(record)
            ),
        }

    def update_summary(self) -> None:
        summary = summarize_lags(self.records, self.current_mode())
        self.pair_count_var.set(str(summary["paired"]))
        self.avg_lag_var.set(self.format_optional_seconds(summary["average"]))
        self.min_lag_var.set(self.format_optional_seconds(summary["minimum"]))
        self.max_lag_var.set(self.format_optional_seconds(summary["maximum"]))
        self._update_quality_summary(summary)

    def _update_quality_summary(self, summary: dict) -> None:
        """Perbarui indikator keyakinan + strip statistik tab Visualisasi."""
        if not self.records:
            self.confidence_var.set("-")
            self.viz_quality_var.set(t("viz.no_data"))
            for variable in (
                self.viz_median_var,
                self.viz_sd_var,
                self.viz_merged_var,
                self.viz_omission_var,
                self.viz_addition_var,
            ):
                variable.set("-")
            return

        counts = self._quality_counts()
        if counts["paired"]:
            pct = 100.0 * counts["one_to_one"] / counts["paired"]
            self.confidence_var.set(f"{pct:.0f}%")
        else:
            self.confidence_var.set("0%")

        orphans = counts["omissions"] + counts["additions"]
        self.viz_quality_var.set(
            t(
                "viz.quality",
                one=counts["one_to_one"],
                paired=counts["paired"],
                pct=self.confidence_var.get(),
                review=counts["needs_review"],
                orphans=orphans,
            )
        )

        self.viz_median_var.set(self.format_optional_seconds(summary["median"]))
        self.viz_sd_var.set(self.format_optional_seconds(summary["stdev"]))
        self.viz_merged_var.set(str(counts["merged"]))
        self.viz_omission_var.set(str(counts["omissions"]))
        self.viz_addition_var.set(str(counts["additions"]))

    # ------------------------------------------------------------------- sesi
    SESSION_MARKER = "interpreter-lag-analyzer"
    SESSION_VERSION = 1

    @staticmethod
    def _segment_to_dict(segment: Segment) -> dict:
        return {
            "index": segment.index,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text,
            "speaker": segment.speaker,
        }

    def save_session(self) -> None:
        """Simpan seluruh state analisis (transkrip, pasangan, pengaturan) ke JSON.

        Termasuk hasil koreksi manual, sehingga pekerjaan peneliti tidak hilang
        saat aplikasi ditutup dan tidak perlu transkripsi ulang.
        """
        if not self.native_segments and not self.interpreter_segments:
            messagebox.showinfo(t("msg.info"), t("msg.nothing_to_save"))
            return

        filepath = filedialog.asksaveasfilename(
            title=t("dlg.save_session"),
            defaultextension=".json",
            initialfile=t("file.session_default"),
            filetypes=[(t("dlg.session_files"), "*.json"), (t("dlg.all_files"), "*.*")],
        )
        if not filepath:
            return

        data = {
            "app": self.SESSION_MARKER,
            "version": self.SESSION_VERSION,
            "model": self.model_var.get(),
            "mode": self.mode_var.get(),
            "native_path": self.native_path,
            "native_offset": self._parse_offset(self.native_offset_var.get()),
            "interpreter_paths": self.interpreter_paths,
            "interpreter_offsets": [
                self._parse_offset(var.get()) for var in self.interpreter_offset_vars
            ],
            "native_segments": [
                self._segment_to_dict(seg) for seg in self.native_segments
            ],
            "interpreter_segments": [
                self._segment_to_dict(seg) for seg in self.interpreter_segments
            ],
            "records": [
                {
                    "natives": [seg.index for seg in record.natives],
                    "interpreters": [seg.index for seg in record.interpreters],
                }
                for record in self.records
            ],
        }
        with open(filepath, "w", encoding="utf-8") as session_file:
            json.dump(data, session_file, ensure_ascii=False, indent=2)
        self.status_var.set(t("st.session_saved", name=os.path.basename(filepath)))

    def load_session(self) -> None:
        """Muat kembali sesi analisis dari file JSON hasil Simpan Sesi."""
        filepath = filedialog.askopenfilename(
            title=t("dlg.open_session"),
            filetypes=[(t("dlg.session_files"), "*.json"), (t("dlg.all_files"), "*.*")],
        )
        if not filepath:
            return

        try:
            with open(filepath, encoding="utf-8") as session_file:
                data = json.load(session_file)
            if data.get("app") != self.SESSION_MARKER:
                raise ValueError(t("err.not_session"))

            native_segments = [
                Segment(
                    int(item["index"]),
                    float(item["start"]),
                    float(item["end"]),
                    str(item.get("text", "")),
                    SOURCE_NATIVE,
                    str(item.get("speaker", "")),
                )
                for item in data.get("native_segments", [])
            ]
            interpreter_segments = [
                Segment(
                    int(item["index"]),
                    float(item["start"]),
                    float(item["end"]),
                    str(item.get("text", "")),
                    SOURCE_INTERPRETER,
                    str(item.get("speaker", "")),
                )
                for item in data.get("interpreter_segments", [])
            ]
            native_by_index = {seg.index: seg for seg in native_segments}
            interp_by_index = {seg.index: seg for seg in interpreter_segments}
            records = []
            for item in data.get("records", []):
                natives = [
                    native_by_index[idx]
                    for idx in item.get("natives", [])
                    if idx in native_by_index
                ]
                interps = [
                    interp_by_index[idx]
                    for idx in item.get("interpreters", [])
                    if idx in interp_by_index
                ]
                if natives or interps:
                    records.append(LagRecord(0, natives, interps))
            records = renumber_pairs(records)
        except Exception as exc:  # noqa: BLE001 - file bisa rusak/salah format
            messagebox.showerror(t("msg.error"), t("msg.open_failed", error=exc))
            return

        # Terapkan state ke aplikasi.
        if data.get("model") in MODEL_OPTIONS:
            self.model_var.set(data["model"])
        if data.get("mode") in MODE_LABELS:
            self.mode_var.set(data["mode"])

        self._demo_active = False
        self.native_path = str(data.get("native_path", ""))
        self._apply_file_labels()
        self.native_offset_var.set(f"{data.get('native_offset', 0):g}")

        paths = [str(p) for p in data.get("interpreter_paths", [""])] or [""]
        self.interp_count_var.set(str(max(1, min(len(paths), 4))))
        self.interpreter_paths = paths
        self._rebuild_interpreter_inputs()
        offsets = data.get("interpreter_offsets", [])
        for slot, var in enumerate(self.interpreter_offset_vars):
            if slot < len(offsets):
                var.set(f"{offsets[slot]:g}")

        self.native_segments = native_segments
        self.interpreter_segments = interpreter_segments
        self.records = records
        self._rebuild_indexes()

        # Muat ulang audio bila file sumbernya masih ada (best-effort).
        native_offset = self._parse_offset(self.native_offset_var.get())
        native_audio = None
        if self.native_path and os.path.exists(self.native_path):
            try:
                native_audio = self._shift_audio(
                    load_audio(self.native_path), native_offset
                )
            except Exception:  # noqa: BLE001
                native_audio = None
        interpreter_audios = []
        for slot, path in enumerate(self.interpreter_paths):
            if not path or not os.path.exists(path):
                continue
            offset = (
                self._parse_offset(self.interpreter_offset_vars[slot].get())
                if slot < len(self.interpreter_offset_vars)
                else 0.0
            )
            try:
                interpreter_audios.append(self._shift_audio(load_audio(path), offset))
            except Exception:  # noqa: BLE001
                pass
        interpreter_audio = self._mix_audio(interpreter_audios)

        if native_audio is not None or interpreter_audio is not None:
            self.waveform_editor.set_audio(native_audio, interpreter_audio)
        else:
            self.waveform_editor.clear()

        self.refresh_all()
        self.status_var.set(t("st.session_loaded", name=os.path.basename(filepath)))

    # ------------------------------------------------------------------ export
    def export_csv(self) -> None:
        """Export hasil sebagai 3 file CSV rapi (tidy, satu tabel per file).

        <nama>_summary.csv  : metadata + statistik (baris metric,value)
        <nama>_segments.csv : semua segmen kedua sisi, satu baris per segmen
        <nama>_pairs.csv    : analisis lag, satu baris per pasangan

        Format satu-tabel-per-file siap diimpor langsung ke Excel/SPSS/R
        tanpa perlu memotong-motong bagian secara manual. Nama kolom, nilai
        kategori, dan nama berkas SELALU berbahasa Inggris, tidak ikut pilihan
        bahasa antarmuka, agar skrip analisis tidak rusak saat bahasa diganti.
        """
        if not self.native_segments and not self.interpreter_segments:
            messagebox.showinfo(t("msg.info"), t("msg.nothing_to_export"))
            return

        filepath = filedialog.asksaveasfilename(
            title=t("dlg.export"),
            defaultextension=".csv",
            initialfile=t("file.export_default"),
            filetypes=[(t("dlg.csv_files"), "*.csv"), (t("dlg.all_files"), "*.*")],
        )
        if not filepath:
            return

        base = filepath[:-4] if filepath.lower().endswith(".csv") else filepath
        mode = self.current_mode()
        summary = summarize_lags(self.records, mode)
        counts = self._quality_counts()

        interp_files = "; ".join(path for path in self.interpreter_paths if path)
        if not interp_files and self.interpreter_file_vars:
            interp_files = self.interpreter_file_vars[0].get()

        # --- 1. summary ---
        with open(f"{base}_summary.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            writer.writerow(["export_date", datetime.now().strftime("%Y-%m-%d %H:%M")])
            writer.writerow(["source_file", self.native_path or self.native_file_var.get()])
            writer.writerow(["interpreter_files", interp_files])
            writer.writerow(["interpreter_count", len(self.interpreter_paths)])
            writer.writerow(["whisper_model", self.model_var.get()])
            writer.writerow(["interpreting_mode", mode])
            writer.writerow(["primary_metric", "EVS" if mode == MODE_SIMULTANEOUS else "gap"])
            writer.writerow(["source_segments", len(self.native_segments)])
            writer.writerow(["interpreter_segments", len(self.interpreter_segments)])
            writer.writerow(["pairs_total", len(self.records)])
            writer.writerow(["pairs_complete", summary["paired"]])
            writer.writerow(["lag_mean_s", self._csv_seconds(summary["average"])])
            writer.writerow(["lag_median_s", self._csv_seconds(summary["median"])])
            writer.writerow(["lag_sd_s", self._csv_seconds(summary["stdev"])])
            writer.writerow(["lag_min_s", self._csv_seconds(summary["minimum"])])
            writer.writerow(["lag_max_s", self._csv_seconds(summary["maximum"])])
            writer.writerow(["pairs_1to1", counts["one_to_one"]])
            writer.writerow(["merged_pairs", counts["merged"]])
            writer.writerow(["omissions_source", counts["omissions"]])
            writer.writerow(["additions_interpreter", counts["additions"]])
            writer.writerow(["needs_review", counts["needs_review"]])

        # --- 2. segments ---
        native_pairs, interpreter_pairs = self._segment_pair_lookup()
        with open(f"{base}_segments.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["side", "index", "speaker", "start_s", "end_s",
                 "duration_s", "pair", "text"]
            )
            for segment in self.native_segments:
                writer.writerow(
                    ["source", segment.index, "",
                     f"{segment.start:.2f}", f"{segment.end:.2f}",
                     f"{segment.duration:.2f}",
                     native_pairs.get(segment.index, ""), segment.text]
                )
            for segment in self.interpreter_segments:
                writer.writerow(
                    ["interpreter", segment.index, segment.speaker,
                     f"{segment.start:.2f}", f"{segment.end:.2f}",
                     f"{segment.duration:.2f}",
                     interpreter_pairs.get(segment.index, ""), segment.text]
                )

        # --- 3. pairs ---
        with open(f"{base}_pairs.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["pair", "source_index", "source_start_s", "source_end_s",
                 "interpreter_index", "speaker", "interpreter_start_s",
                 "evs_s", "gap_s", "primary_lag_s", "category",
                 "needs_review", "source_text", "interpreter_text"]
            )
            for record in self.records:
                native = record.native
                interpreter = record.interpreter
                native_end = (
                    max(seg.end for seg in record.natives) if record.natives else None
                )
                writer.writerow(
                    [
                        record.pair_index,
                        self._segment_index_label(record.natives),
                        f"{native.start:.2f}" if native else "",
                        f"{native_end:.2f}" if native_end is not None else "",
                        self._segment_index_label(record.interpreters),
                        "/".join(
                            sorted({s.speaker for s in record.interpreters if s.speaker})
                        ),
                        f"{interpreter.start:.2f}" if interpreter else "",
                        self._csv_seconds(record.evs),
                        self._csv_seconds(record.gap),
                        self._csv_seconds(record.lag_for(mode)),
                        category_label(lag_category(record.lag_for(mode)), "en"),
                        "yes" if self._needs_review(record) else "",
                        record.native_text,
                        record.interpreter_text,
                    ]
                )

        self.status_var.set(t("st.exported", base=os.path.basename(base)))

    # ----------------------------------------------------------------- format
    @staticmethod
    def format_seconds(value: float) -> str:
        return f"{value:.2f}s"

    @classmethod
    def format_optional_seconds(cls, value: float | int | None) -> str:
        if value is None:
            return "-"
        return cls.format_seconds(float(value))

    @staticmethod
    def _csv_seconds(value: float | None) -> str:
        return "" if value is None else f"{value:.2f}"

    @staticmethod
    def _segment_index_label(segments: list[Segment]) -> str:
        if not segments:
            return ""
        if len(segments) == 1:
            return str(segments[0].index)
        return f"{segments[0].index}-{segments[-1].index}"

    def _describe_chunk(self, segments: list[Segment]) -> str:
        if not segments:
            return t("chunk.unpaired")
        first = segments[0]
        index_label = (
            f"#{first.index}"
            if len(segments) == 1
            else f"#{first.index}-{segments[-1].index}"
        )
        speakers = "/".join(
            sorted({seg.speaker for seg in segments if seg.speaker})
        )
        speaker_label = f" {speakers}" if speakers else ""
        text = " ".join(seg.text for seg in segments).strip()
        return self.shorten_text(
            f"{index_label}{speaker_label} [{first.start:.2f}] {text}", 130
        )

    @staticmethod
    def shorten_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3].rstrip()}..."


class SplitRecordingDialog:
    """Dialog preprocessing: pisahkan satu rekaman campuran menjadi file per penutur.

    Alur: pilih rekaman → tentukan jumlah penutur → Deteksi (VAD + clustering
    warna suara) → periksa/koreksi label penutur per ujaran (bisa didengarkan)
    → Simpan & Gunakan: menulis <nama>_P1.wav dst. (hening di luar ujaran
    penutur itu, timestamp asli terjaga) lalu mengisi slot input penerjemah.
    """

    def __init__(self, app: InterpreterLagApp):
        self.app = app
        self.audio = None
        self.utterances: list = []
        self.source_path = ""
        self.worker_queue: queue.Queue = queue.Queue()

        win = tk.Toplevel(app.master)
        self.win = win
        win.title(t("split.title"))
        win.geometry("900x560")
        win.transient(app.master)
        win.grab_set()
        win.columnconfigure(0, weight=1)
        win.rowconfigure(2, weight=1)

        c = app.colors
        win.configure(bg=c["bg"])

        # --- baris input ---
        top = ttk.Frame(win, padding=(12, 12, 12, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self.file_var = tk.StringVar(value=t("split.none"))
        ttk.Button(top, text=t("split.choose"), command=self._pick_file).grid(
            row=0, column=0, padx=(0, 10)
        )
        ttk.Label(top, textvariable=self.file_var).grid(row=0, column=1, sticky="w")

        ttk.Label(top, text=t("split.count")).grid(row=0, column=2, padx=(10, 4))
        self.count_var = tk.StringVar(value="2")
        ttk.Combobox(
            top, textvariable=self.count_var, values=("2", "3", "4"),
            state="readonly", width=4,
        ).grid(row=0, column=3, padx=(0, 10))

        self.detect_button = ttk.Button(
            top, text=t("split.detect"), style="Primary.TButton",
            command=self._start_detection,
        )
        self.detect_button.grid(row=0, column=4)

        status_row = ttk.Frame(win, padding=(12, 0, 12, 4))
        status_row.grid(row=1, column=0, sticky="ew")
        status_row.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value=t("split.initial"))
        ttk.Label(status_row, textvariable=self.status_var, style="TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=140)

        # --- tabel ujaran ---
        table_frame = ttk.Frame(win, padding=(12, 4))
        table_frame.grid(row=2, column=0, sticky="nswe")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("no", "start", "end", "duration", "speaker")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="extended"
        )
        for col, (text, width) in {
            "no": ("#", 50),
            "start": (t("split.col_start"), 100),
            "end": (t("split.col_end"), 100),
            "duration": (t("col.duration"), 90),
            "speaker": (t("col.speaker"), 90),
        }.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w", stretch=col == "speaker")
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nswe")
        yscroll.grid(row=0, column=1, sticky="ns")

        # --- kontrol koreksi ---
        controls = ttk.Frame(win, padding=(12, 4))
        controls.grid(row=3, column=0, sticky="ew")
        ttk.Button(controls, text=t("split.play"), command=self._play_selected).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(controls, text=t("wave.stop"), command=self._stop_play).pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Label(controls, text=t("split.move_to")).pack(side=tk.LEFT)
        self.assign_var = tk.StringVar(value="P1")
        self.assign_box = ttk.Combobox(
            controls, textvariable=self.assign_var, values=("P1", "P2"),
            state="readonly", width=5,
        )
        self.assign_box.pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text=t("split.apply"), command=self._apply_reassign).pack(
            side=tk.LEFT
        )

        # --- aksi akhir ---
        actions = ttk.Frame(win, padding=12)
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        ttk.Label(
            actions,
            text=t("split.note"),
            style="TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text=t("split.cancel"), command=self._close).grid(
            row=0, column=1, padx=(10, 6)
        )
        self.use_button = ttk.Button(
            actions, text=t("split.use"), style="Primary.TButton",
            command=self._save_and_use, state="disabled",
        )
        self.use_button.grid(row=0, column=2)

        win.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------ handlers
    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title=t("split.dlg_choose"),
            parent=self.win,
            filetypes=[
                (t("dlg.media_files"), "*.mp3 *.wav *.mp4 *.m4a *.mpeg *.mpga *.webm"),
                (t("dlg.all_files"), "*.*"),
            ],
        )
        if not path:
            return
        self.source_path = path
        self.file_var.set(os.path.basename(path))
        self.status_var.set(t("split.ready"))

    def _start_detection(self) -> None:
        if not self.source_path:
            messagebox.showinfo(t("msg.info"), t("split.pick_first"), parent=self.win)
            return
        k = int(self.count_var.get())
        self.detect_button.state(["disabled"])
        self.use_button.state(["disabled"])
        self.progress.grid(row=0, column=1, sticky="e")
        self.progress.start(12)
        self.status_var.set(t("split.detecting"))

        def worker() -> None:
            try:
                audio = load_audio(self.source_path)
                if len(audio) == 0:
                    raise RuntimeError(t("split.err_empty"))
                utterances = detect_utterances(audio)
                if len(utterances) < 2:
                    raise RuntimeError(t("split.err_few"))
                features = utterance_features(audio, utterances)
                labels = cluster_utterances(features, k)
                for utt, label in zip(utterances, labels):
                    utt.cluster = int(label)
                self.worker_queue.put(("done", audio, utterances))
            except Exception as exc:  # noqa: BLE001 - ditampilkan ke pengguna
                self.worker_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.win.after(120, self._poll)

    def _poll(self) -> None:
        try:
            message = self.worker_queue.get_nowait()
        except queue.Empty:
            self.win.after(120, self._poll)
            return

        self.progress.stop()
        self.progress.grid_forget()
        self.detect_button.state(["!disabled"])

        if message[0] == "error":
            self.status_var.set(t("split.failed"))
            messagebox.showerror(t("msg.error"), message[1], parent=self.win)
            return

        self.audio = message[1]
        self.utterances = message[2]
        k = int(self.count_var.get())
        self.assign_box.configure(values=tuple(f"P{j+1}" for j in range(k)))
        self._refresh_tree()
        self.use_button.state(["!disabled"])
        counts = [
            sum(1 for u in self.utterances if u.cluster == j) for j in range(k)
        ]
        detail = ", ".join(
            t("split.count_item", speaker=j + 1, count=n) for j, n in enumerate(counts)
        )
        self.status_var.set(
            t("split.detected", total=len(self.utterances), detail=detail)
        )

    def _refresh_tree(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, utt in enumerate(self.utterances):
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    i + 1,
                    f"{utt.start:.2f}s",
                    f"{utt.end:.2f}s",
                    f"{utt.duration:.2f}s",
                    f"P{utt.cluster + 1}",
                ),
            )

    def _selected_indices(self) -> list[int]:
        return [int(iid) for iid in self.tree.selection()]

    def _play_selected(self) -> None:
        indices = self._selected_indices()
        if not indices or self.audio is None:
            self.status_var.set(t("split.pick_play"))
            return
        utt = self.utterances[indices[0]]
        try:
            import sounddevice as sd

            s0 = int(utt.start * SAMPLE_RATE)
            s1 = int(utt.end * SAMPLE_RATE)
            sd.play(self.audio[s0:s1], SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set(t("split.play_failed", error=exc))

    def _stop_play(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:  # noqa: BLE001
            pass

    def _apply_reassign(self) -> None:
        indices = self._selected_indices()
        if not indices:
            self.status_var.set(t("split.pick_move"))
            return
        cluster = int(self.assign_var.get()[1:]) - 1
        for index in indices:
            self.utterances[index].cluster = cluster
        self._refresh_tree()
        self.status_var.set(t("split.moved", count=len(indices), speaker=cluster + 1))

    def _save_and_use(self) -> None:
        if self.audio is None or not self.utterances:
            return
        self._stop_play()
        k = int(self.count_var.get())
        tracks = build_speaker_tracks(self.audio, self.utterances, k)
        source = Path(self.source_path)
        out_paths: list[str] = []
        try:
            for j, track in enumerate(tracks):
                out = source.with_name(f"{source.stem}_P{j+1}.wav")
                write_wav(out, track)
                out_paths.append(str(out))
        except OSError as exc:
            messagebox.showerror(
                t("msg.error"), t("split.write_failed", error=exc), parent=self.win
            )
            return

        app = self.app
        app._end_demo()
        app.interp_count_var.set(str(k))
        app.interpreter_paths = out_paths
        app._rebuild_interpreter_inputs()
        app.status_var.set(t("split.done", count=k))
        self._close()

    def _close(self) -> None:
        self._stop_play()
        self.win.grab_release()
        self.win.destroy()


def main() -> None:
    root = tk.Tk()
    InterpreterLagApp(root)
    root.mainloop()
