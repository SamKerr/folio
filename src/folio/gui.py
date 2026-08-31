"""Desktop GUI for configuring crawls and browsing saved output."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from folio.crawl_runner import CrawlSettings, build_crawl_argv
from folio.output_catalog import SavedSite, list_saved_sites
from folio.preview_server import PreviewServer


@dataclass(frozen=True)
class FolioTheme:
    bg: str = "#f4ecdc"
    panel: str = "#faf6ee"
    fg: str = "#2c1f3a"
    muted: str = "#6b5a7a"
    header_bg: str = "#2a1847"
    header_gold: str = "#e8c86a"
    header_subtitle: str = "#c9b8df"
    accent: str = "#c9a84c"
    accent_active: str = "#dbbf6a"
    accent_fg: str = "#2a1847"
    border: str = "#d4c4a8"
    log_bg: str = "#1e1429"
    log_fg: str = "#e8dcc8"
    status_bg: str = "#3d2463"
    status_fg: str = "#f0e6d2"
    title_font: tuple[str, int, str] = ("Palatino", 26, "bold")
    subtitle_font: tuple[str, int] = ("Helvetica Neue", 12)
    body_font: tuple[str, int] = ("Helvetica Neue", 13)
    mono_font: tuple[str, int] = ("Menlo", 11)


THEME = FolioTheme()


def find_logo_path() -> Path | None:
    """Return bundled logo path from the folio package assets."""
    path = Path(__file__).resolve().parent / "assets" / "folio.png"
    return path if path.is_file() else None


def load_scaled_photo(path: Path, *, target_height: int) -> tk.PhotoImage:
    """Load a PNG and downscale with subsampling for crisp Tk display."""
    image = tk.PhotoImage(file=str(path))
    factor = max(image.height() // target_height, 1)
    if factor > 1:
        return image.subsample(factor, factor)
    return image


def _tk_patchlevel_at_least(tk_root: tk.Misc, major: int, minor: int) -> bool:
    patchlevel = str(tk_root.tk.call("info", "patchlevel"))
    parts = patchlevel.split(".")
    try:
        return (int(parts[0]), int(parts[1])) >= (major, minor)
    except (IndexError, ValueError):
        return False


def _has_touchpad_scroll(tk_root: tk.Misc) -> bool:
    try:
        tk_root.tk.call("info", "commands", "::tk::PreciseScrollDeltas")
        return True
    except tk.TclError:
        return False


def _mousewheel_steps(event: tk.Event, tk_root: tk.Misc) -> int:
    if not event.delta:
        return 0
    if _tk_patchlevel_at_least(tk_root, 9, 0):
        step = int(-event.delta / 120)
        return step if step else (-1 if event.delta > 0 else 1)
    if sys.platform == "darwin":
        return -round(event.delta)
    step = int(-event.delta / 120)
    return step if step else (-1 if event.delta > 0 else 1)


def _touchpad_vertical_step(event: tk.Event, tk_root: tk.Misc) -> int:
    """Return vertical scroll step from a Tk 9 TouchpadScroll event."""
    try:
        delta_x, delta_y = tk_root.tk.call(
            "::tk::PreciseScrollDeltas",
            event.keycode,
        )
    except tk.TclError:
        return 0
    dx = int(delta_x)
    dy = int(delta_y)
    if dy == 0 or abs(dx) > abs(dy):
        return 0
    return dy


def _widget_is_descendant(widget: tk.Misc, ancestor: tk.Misc) -> bool:
    current: tk.Misc | None = widget
    while current is not None:
        if current == ancestor:
            return True
        current = current.master
    return False


def create_scrollable_frame(parent: ttk.Frame) -> tuple[tk.Canvas, ttk.Frame]:
    """Return a vertical scroll canvas and inner frame that expands to content width."""
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)

    canvas = tk.Canvas(
        parent,
        highlightthickness=0,
        borderwidth=0,
        bg=THEME.bg,
    )
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)

    scroll_frame = ttk.Frame(canvas, style="Main.TFrame")
    window_id = canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)

    def _on_canvas_configure(event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    def _on_frame_configure(_event: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", _on_canvas_configure)
    scroll_frame.bind("<Configure>", _on_frame_configure)

    return canvas, scroll_frame


CAPTURE_PRESETS: dict[str, dict[str, int]] = {
    "Fast": {
        "image_wait_ms": 2_000,
        "asset_quiet_ms": 500,
        "page_asset_timeout_ms": 30_000,
        "settle_ms": 500,
        "timeout_secs": 45,
    },
    "Balanced": {
        "image_wait_ms": 5_000,
        "asset_quiet_ms": 750,
        "page_asset_timeout_ms": 60_000,
        "settle_ms": 1_000,
        "timeout_secs": 60,
    },
    "Thorough": {
        "image_wait_ms": 15_000,
        "asset_quiet_ms": 1_500,
        "page_asset_timeout_ms": 120_000,
        "settle_ms": 2_000,
        "timeout_secs": 90,
    },
}

PAGE_CONCURRENCY_CHOICES = ("4", "8", "12", "20", "32")
ASSET_CONCURRENCY_CHOICES = ("4", "8", "12", "20", "32")
IMAGE_WAIT_CHOICES = ("0", "2000", "5000", "10000", "15000", "30000")
ASSET_QUIET_CHOICES = ("0", "500", "750", "1000", "1500", "3000")
PAGE_ASSET_CAP_CHOICES = ("30000", "60000", "90000", "120000")
SETTLE_CHOICES = ("0", "500", "1000", "2000", "5000")
TIMEOUT_CHOICES = ("30", "45", "60", "90", "120")
FOLIO_SCROLL_TAG = "FolioScroll"


class FolioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Folio")
        self.geometry("920x760")
        self.minsize(760, 640)

        self._output_dir = tk.StringVar(value=str(Path("output").resolve()))
        self._crawl_url = tk.StringVar(value="https://www.example.com/")
        self._capture_preset = tk.StringVar(value="Balanced")
        self._concurrency = tk.StringVar(value="20")
        self._asset_concurrency = tk.StringVar(value="12")
        self._image_wait_ms = tk.StringVar(value="5000")
        self._asset_quiet_ms = tk.StringVar(value="750")
        self._page_asset_timeout_ms = tk.StringVar(value="60000")
        self._settle_ms = tk.StringVar(value="1000")
        self._timeout_secs = tk.StringVar(value="60")
        self._max_pages = tk.StringVar(value="")
        self._force = tk.BooleanVar(value=False)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._crawl_proc: subprocess.Popen[str] | None = None
        self._crawl_thread: threading.Thread | None = None
        self._preview = PreviewServer(Path("output"))
        self._sites: list[SavedSite] = []
        self._advanced_frame: ttk.LabelFrame | None = None
        self._crawl_scroll_canvas: tk.Canvas | None = None
        self._crawl_scroll_frame: ttk.Frame | None = None
        self._crawl_scroll_outer: ttk.Frame | None = None
        self._crawl_tab: ttk.Frame | None = None
        self._library_tab: ttk.Frame | None = None
        self._touchpad_bind_cmd: str | None = None
        self._library_scroll_root: ttk.Frame | None = None
        self._logo_photo: tk.PhotoImage | None = None
        self._icon_photo: tk.PhotoImage | None = None

        self._setup_theme()
        self._setup_window_icon()
        self._build_ui()
        self._setup_trackpad_scrolling()
        self._poll_log_queue()
        self.refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_theme(self) -> None:
        self.configure(bg=THEME.bg)
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=THEME.bg, foreground=THEME.fg)
        style.configure("Main.TFrame", background=THEME.bg)
        style.configure("Card.TFrame", background=THEME.panel)
        style.configure(
            "TLabelframe",
            background=THEME.panel,
            foreground=THEME.fg,
            bordercolor=THEME.border,
        )
        style.configure(
            "TLabelframe.Label",
            background=THEME.panel,
            foreground=THEME.muted,
            font=("Helvetica Neue", 12, "bold"),
        )
        style.configure("TLabel", background=THEME.panel, foreground=THEME.fg)
        style.configure(
            "Hint.TLabel",
            background=THEME.panel,
            foreground=THEME.muted,
            font=("Helvetica Neue", 11),
        )
        style.configure(
            "TEntry",
            fieldbackground="#fffdf8",
            foreground=THEME.fg,
            bordercolor=THEME.border,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#fffdf8",
            foreground=THEME.fg,
            bordercolor=THEME.border,
        )
        style.configure(
            "TNotebook",
            background=THEME.bg,
            bordercolor=THEME.border,
            tabmargins=(2, 4, 2, 0),
        )
        tab_padding = (22, 10)
        style.configure(
            "TNotebook.Tab",
            background=THEME.panel,
            foreground=THEME.muted,
            padding=tab_padding,
            width=10,
            font=("Helvetica Neue", 12, "bold"),
            borderwidth=1,
            focuscolor=THEME.panel,
            lightcolor=THEME.border,
            darkcolor=THEME.border,
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", THEME.header_bg),
                ("active", THEME.panel),
                ("!selected", THEME.panel),
            ],
            foreground=[
                ("selected", THEME.header_gold),
                ("active", THEME.muted),
                ("!selected", THEME.muted),
            ],
            padding=[
                ("selected", tab_padding),
                ("!selected", tab_padding),
            ],
            expand=[("selected", [0, 0, 0, 0]), ("!selected", [0, 0, 0, 0])],
            lightcolor=[
                ("selected", THEME.header_bg),
                ("!selected", THEME.border),
            ],
            darkcolor=[
                ("selected", THEME.header_bg),
                ("!selected", THEME.border),
            ],
        )
        style.configure(
            "Treeview",
            background="#fffdf8",
            fieldbackground="#fffdf8",
            foreground=THEME.fg,
            bordercolor=THEME.border,
            rowheight=28,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME.header_bg,
            foreground=THEME.header_gold,
            font=("Helvetica Neue", 11, "bold"),
        )
        style.configure(
            "TButton",
            background=THEME.panel,
            foreground=THEME.fg,
            bordercolor=THEME.border,
            padding=(12, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#efe5d3")],
        )
        style.configure(
            "Accent.TButton",
            background=THEME.accent,
            foreground=THEME.accent_fg,
            bordercolor=THEME.accent,
            font=("Helvetica Neue", 12, "bold"),
            padding=(16, 8),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", THEME.accent_active),
                ("disabled", "#b9a888"),
            ],
            foreground=[("disabled", "#5c5348")],
        )
        style.configure(
            "Danger.TButton",
            background="#8b3a3a",
            foreground="#fceeee",
            bordercolor="#8b3a3a",
            padding=(12, 6),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#a44a4a"), ("disabled", "#b9a888")],
        )

    def _setup_window_icon(self) -> None:
        logo_path = find_logo_path()
        if logo_path is None:
            return
        self._icon_photo = load_scaled_photo(logo_path, target_height=64)
        self.iconphoto(True, self._icon_photo)

    def _widget_in_crawl_area(self, widget: tk.Misc) -> bool:
        anchors: list[tk.Misc] = []
        if self._crawl_scroll_canvas is not None:
            anchors.append(self._crawl_scroll_canvas)
        if self._crawl_scroll_frame is not None:
            anchors.append(self._crawl_scroll_frame)
        if self._crawl_scroll_outer is not None:
            anchors.append(self._crawl_scroll_outer)
        return any(_widget_is_descendant(widget, anchor) for anchor in anchors)

    def _widget_in_library_area(self, widget: tk.Misc) -> bool:
        if self._library_scroll_root is None:
            return False
        return _widget_is_descendant(widget, self._library_scroll_root)

    def _install_scroll_tag(self, widget: tk.Misc) -> None:
        """Run our scroll handler before Tk's default wheel/touchpad bindings."""
        tags = widget.bindtags()
        if FOLIO_SCROLL_TAG not in tags:
            widget.bindtags((FOLIO_SCROLL_TAG, *tags))
        for child in widget.winfo_children():
            self._install_scroll_tag(child)

    def _scroll_target_widget(self, event: tk.Event) -> tk.Misc:
        px, py = self.winfo_pointerxy()
        target = self.winfo_containing(px, py)
        return target if target is not None else event.widget

    def _scroll_crawl_by(self, step: int) -> str:
        if step and self._crawl_scroll_canvas is not None:
            self._crawl_scroll_canvas.yview_scroll(-step, "units")
            return "break"
        return ""

    def _scroll_library_by(self, step: int) -> str:
        if step:
            self._site_tree.yview_scroll(-step, "units")
            return "break"
        return ""

    def _route_mousewheel(self, event: tk.Event) -> str:
        if event.num == 4:
            step = 1
        elif event.num == 5:
            step = -1
        else:
            step = _mousewheel_steps(event, self)
        if step == 0:
            return ""
        target = self._scroll_target_widget(event)
        if self._widget_in_crawl_area(target):
            return self._scroll_crawl_by(step)
        if self._widget_in_library_area(target):
            return self._scroll_library_by(step)
        return ""

    def _route_touchpad(self, event: tk.Event) -> str:
        step = _touchpad_vertical_step(event, self)
        if step == 0:
            return ""
        target = self._scroll_target_widget(event)
        if self._widget_in_crawl_area(target):
            return self._scroll_crawl_by(step)
        if self._widget_in_library_area(target):
            return self._scroll_library_by(step)
        return ""

    def _setup_trackpad_scrolling(self) -> None:
        if self._crawl_scroll_canvas is None:
            return

        has_touchpad = _has_touchpad_scroll(self)
        wheel_sequences = ["<MouseWheel>", "<Button-4>", "<Button-5>"]
        if has_touchpad:
            wheel_sequences.append("<TouchpadScroll>")

        for sequence in wheel_sequences:
            if sequence == "<TouchpadScroll>":
                handler = self._route_touchpad
            else:
                handler = self._route_mousewheel
            self.bind_class(FOLIO_SCROLL_TAG, sequence, handler, add="+")

        for tab in (self._crawl_tab, self._library_tab):
            if tab is not None:
                self._install_scroll_tag(tab)

        # Fallback: prepend a global TouchpadScroll handler (runs even without focus).
        if has_touchpad:
            self._touchpad_bind_cmd = self.register(self._route_touchpad)
            self.tk.call(
                "bind",
                "all",
                "<TouchpadScroll>",
                f"+ {self._touchpad_bind_cmd}",
            )

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._route_mousewheel, add="+")

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=THEME.header_bg)
        header.pack(fill=tk.X)
        header.columnconfigure(1, weight=1)

        logo_path = find_logo_path()
        text_column = 0
        if logo_path is not None:
            self._logo_photo = load_scaled_photo(logo_path, target_height=72)
            tk.Label(
                header,
                image=self._logo_photo,
                bg=THEME.header_bg,
                borderwidth=0,
            ).grid(row=0, column=0, padx=(18, 10), pady=12, sticky=tk.NS)
            text_column = 1

        text_block = tk.Frame(header, bg=THEME.header_bg)
        text_block.grid(row=0, column=text_column, sticky=tk.W, pady=12, padx=(0, 18))
        tk.Label(
            text_block,
            text="Folio",
            font=THEME.title_font,
            fg=THEME.header_gold,
            bg=THEME.header_bg,
        ).pack(anchor=tk.W)
        tk.Label(
            text_block,
            text="Save the web for offline reading",
            font=THEME.subtitle_font,
            fg=THEME.header_subtitle,
            bg=THEME.header_bg,
        ).pack(anchor=tk.W, pady=(4, 0))

        accent = tk.Frame(self, bg=THEME.accent, height=3)
        accent.pack(fill=tk.X)

    def _build_ui(self) -> None:
        self._build_header()

        main = ttk.Frame(self, style="Main.TFrame", padding=(12, 10, 12, 0))
        main.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(main)
        notebook.pack(fill=tk.BOTH, expand=True)

        crawl_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        library_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self._crawl_tab = crawl_tab
        self._library_tab = library_tab
        notebook.add(crawl_tab, text="Crawl")
        notebook.add(library_tab, text="Library")

        self._build_crawl_tab(crawl_tab)
        self._build_library_tab(library_tab)

        status_bar = tk.Frame(self, bg=THEME.status_bg, height=30)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)
        self._status = tk.StringVar(value="Ready")
        tk.Label(
            status_bar,
            textvariable=self._status,
            anchor=tk.W,
            bg=THEME.status_bg,
            fg=THEME.status_fg,
            font=("Helvetica Neue", 11),
            padx=14,
        ).pack(fill=tk.BOTH, expand=True)

    def _build_crawl_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        scroll_outer = ttk.Frame(parent, style="Main.TFrame")
        scroll_outer.grid(row=0, column=0, sticky=tk.NSEW)
        self._crawl_scroll_outer = scroll_outer
        self._crawl_scroll_canvas, body = create_scrollable_frame(scroll_outer)
        self._crawl_scroll_frame = body
        body.columnconfigure(0, weight=1)

        target = ttk.LabelFrame(body, text="Target", padding=8)
        target.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))
        target.columnconfigure(1, weight=1)
        self._add_labeled_entry(target, 0, "Start URL", self._crawl_url, width=60)
        self._add_output_picker(target, 1)

        crawl = ttk.LabelFrame(body, text="Crawl", padding=8)
        crawl.grid(row=1, column=0, sticky=tk.EW, pady=(0, 8))
        crawl.columnconfigure(1, weight=1)
        self._add_combobox(
            crawl,
            0,
            "Parallel pages",
            self._concurrency,
            PAGE_CONCURRENCY_CHOICES,
        )
        self._add_combobox(
            crawl,
            1,
            "Parallel assets",
            self._asset_concurrency,
            ASSET_CONCURRENCY_CHOICES,
        )
        self._add_labeled_entry(crawl, 2, "Max pages", self._max_pages, width=12)
        ttk.Checkbutton(
            crawl,
            text="Force re-fetch existing pages",
            variable=self._force,
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky=tk.W,
            pady=(4, 0),
        )

        capture = ttk.LabelFrame(body, text="Page capture", padding=8)
        capture.grid(row=2, column=0, sticky=tk.EW, pady=(0, 8))
        capture.columnconfigure(1, weight=1)
        preset_values = (*CAPTURE_PRESETS.keys(), "Custom")
        self._add_combobox(
            capture,
            0,
            "Quality preset",
            self._capture_preset,
            preset_values,
        )
        self._capture_preset.trace_add("write", self._on_capture_preset_changed)
        ttk.Label(
            capture,
            text="Fast skips waits; Thorough waits longer for images and downloads.",
            wraplength=680,
            style="Hint.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        self._advanced_frame = ttk.LabelFrame(body, text="Advanced timings", padding=8)
        self._advanced_frame.grid(row=3, column=0, sticky=tk.EW, pady=(0, 8))
        self._advanced_frame.columnconfigure(1, weight=1)
        self._add_combobox(
            self._advanced_frame,
            0,
            "Image wait (ms)",
            self._image_wait_ms,
            IMAGE_WAIT_CHOICES,
        )
        self._add_combobox(
            self._advanced_frame,
            1,
            "Asset quiet (ms)",
            self._asset_quiet_ms,
            ASSET_QUIET_CHOICES,
        )
        self._add_combobox(
            self._advanced_frame,
            2,
            "Page asset cap (ms)",
            self._page_asset_timeout_ms,
            PAGE_ASSET_CAP_CHOICES,
        )
        self._add_combobox(
            self._advanced_frame,
            3,
            "Settle (ms)",
            self._settle_ms,
            SETTLE_CHOICES,
        )
        self._add_combobox(
            self._advanced_frame,
            4,
            "Page timeout (s)",
            self._timeout_secs,
            TIMEOUT_CHOICES,
        )
        self._on_capture_preset_changed()

        exclude_frame = ttk.LabelFrame(
            body,
            text="Exclude paths (one pattern per line)",
            padding=8,
        )
        exclude_frame.grid(row=4, column=0, sticky=tk.EW, pady=(0, 8))
        exclude_frame.columnconfigure(0, weight=1)
        self._exclude_text = tk.Text(
            exclude_frame,
            height=3,
            wrap=tk.NONE,
            bg="#fffdf8",
            fg=THEME.fg,
            insertbackground=THEME.accent,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=THEME.border,
            highlightcolor=THEME.accent,
            font=THEME.mono_font,
        )
        self._exclude_text.grid(row=0, column=0, sticky=tk.EW)
        self._exclude_text.insert("1.0", "/community/*\n/blog/*")

        controls = ttk.Frame(body)
        controls.grid(row=5, column=0, sticky=tk.EW, pady=(0, 8))
        self._start_button = ttk.Button(
            controls,
            text="Start crawl",
            command=self.start_crawl,
            style="Accent.TButton",
        )
        self._start_button.pack(side=tk.LEFT)
        self._continue_button = ttk.Button(
            controls,
            text="Continue after login",
            command=self.continue_after_login,
            state=tk.DISABLED,
        )
        self._continue_button.pack(side=tk.LEFT, padx=(8, 0))
        self._stop_button = ttk.Button(
            controls,
            text="Stop",
            command=self.stop_crawl,
            state=tk.DISABLED,
            style="Danger.TButton",
        )
        self._stop_button.pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(body, text="Log", padding=8)
        log_frame.grid(row=6, column=0, sticky=tk.EW, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        self._log = tk.Text(
            log_frame,
            height=14,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=THEME.log_bg,
            fg=THEME.log_fg,
            insertbackground=THEME.header_gold,
            relief=tk.FLAT,
            highlightthickness=0,
            font=THEME.mono_font,
        )
        self._log.grid(row=0, column=0, sticky=tk.EW)

    def _build_library_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_library).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Open site", command=self.open_selected_site).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(
            toolbar, text="Choose output folder", command=self._pick_output_dir
        ).pack(
            side=tk.RIGHT,
        )

        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=(8, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self._library_scroll_root = tree_frame

        columns = ("host", "pages", "modified")
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self._site_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode=tk.BROWSE,
            yscrollcommand=tree_scroll.set,
        )
        tree_scroll.configure(command=self._site_tree.yview)
        self._site_tree.heading("host", text="Site")
        self._site_tree.heading("pages", text="Pages")
        self._site_tree.heading("modified", text="Last saved")
        self._site_tree.column("host", width=360, anchor=tk.W)
        self._site_tree.column("pages", width=80, anchor=tk.E)
        self._site_tree.column("modified", width=180, anchor=tk.W)
        self._site_tree.grid(row=0, column=0, sticky=tk.NSEW)
        tree_scroll.grid(row=0, column=1, sticky=tk.NS)
        self._site_tree.bind("<Double-1>", lambda _event: self.open_selected_site())

        hint = ttk.Label(
            parent,
            text=(
                "Double-click a site to open it in your browser "
                "via a local preview server."
            ),
            style="Hint.TLabel",
        )
        hint.grid(row=2, column=0, sticky=tk.W, pady=(8, 0))

    def _add_labeled_entry(
        self,
        parent: Any,
        row: int,
        label: str,
        variable: tk.Variable,
        *,
        width: int = 40,
        column: int = 0,
    ) -> None:
        ttk.Label(parent, text=label, style="Hint.TLabel").grid(
            row=row, column=column, sticky=tk.W, pady=4, padx=(0, 8)
        )
        ttk.Entry(parent, textvariable=variable, width=width).grid(
            row=row,
            column=column + 1,
            sticky=tk.EW,
            pady=4,
        )

    def _add_combobox(
        self,
        parent: Any,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label, style="Hint.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=4, padx=(0, 8)
        )
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=24,
        )
        combo.grid(row=row, column=1, sticky=tk.W, pady=4)
        if variable.get() not in values:
            variable.set(values[0])
        return combo

    def _add_output_picker(self, parent: Any, row: int) -> None:
        ttk.Label(parent, text="Output folder", style="Hint.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=4, padx=(0, 8)
        )
        entry = ttk.Entry(parent, textvariable=self._output_dir)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        ttk.Button(parent, text="Browse…", command=self._pick_output_dir).grid(
            row=row,
            column=2,
            padx=(8, 0),
            pady=4,
        )

    def _on_capture_preset_changed(self, *_args: str) -> None:
        preset = self._capture_preset.get()
        if preset in CAPTURE_PRESETS:
            values = CAPTURE_PRESETS[preset]
            self._image_wait_ms.set(str(values["image_wait_ms"]))
            self._asset_quiet_ms.set(str(values["asset_quiet_ms"]))
            self._page_asset_timeout_ms.set(str(values["page_asset_timeout_ms"]))
            self._settle_ms.set(str(values["settle_ms"]))
            self._timeout_secs.set(str(values["timeout_secs"]))
        if self._advanced_frame is not None:
            if preset == "Custom":
                self._advanced_frame.grid()
            else:
                self._advanced_frame.grid_remove()
        if self._crawl_scroll_canvas is not None:
            self._crawl_scroll_canvas.update_idletasks()
            self._crawl_scroll_canvas.configure(
                scrollregion=self._crawl_scroll_canvas.bbox("all"),
            )

    def _pick_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Choose Folio output folder")
        if chosen:
            self._output_dir.set(chosen)
            self.refresh_library()

    def _append_log(self, message: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, message)
        if not message.endswith("\n"):
            self._log.insert(tk.END, "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                line = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line.rstrip())
            if "press Enter" in line.lower() or "login" in line.lower():
                self._continue_button.configure(state=tk.NORMAL)
                self._status.set(
                    "Waiting for login — finish in browser, then click Continue"
                )
        self.after(100, self._poll_log_queue)

    @staticmethod
    def _parse_positive_int(raw: str, *, field: str) -> int | None:
        cleaned = raw.strip()
        if not cleaned:
            messagebox.showerror("Invalid value", f"{field} is required.")
            return None
        try:
            value = int(cleaned)
        except ValueError:
            messagebox.showerror("Invalid value", f"{field} must be a whole number.")
            return None
        if value < 0:
            messagebox.showerror("Invalid value", f"{field} cannot be negative.")
            return None
        return value

    def _parse_settings(self) -> CrawlSettings | None:
        url = self._crawl_url.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Enter a start URL for the crawl.")
            return None

        concurrency = self._parse_positive_int(
            self._concurrency.get(),
            field="Parallel pages",
        )
        asset_concurrency = self._parse_positive_int(
            self._asset_concurrency.get(),
            field="Parallel assets",
        )
        image_wait_ms = self._parse_positive_int(
            self._image_wait_ms.get(),
            field="Image wait",
        )
        asset_quiet_ms = self._parse_positive_int(
            self._asset_quiet_ms.get(),
            field="Asset quiet",
        )
        page_asset_timeout_ms = self._parse_positive_int(
            self._page_asset_timeout_ms.get(),
            field="Page asset cap",
        )
        settle_ms = self._parse_positive_int(self._settle_ms.get(), field="Settle")
        timeout_secs = self._parse_positive_int(
            self._timeout_secs.get(),
            field="Page timeout",
        )
        if None in {
            concurrency,
            asset_concurrency,
            image_wait_ms,
            asset_quiet_ms,
            page_asset_timeout_ms,
            settle_ms,
            timeout_secs,
        }:
            return None

        max_pages_raw = self._max_pages.get().strip()
        max_pages: int | None
        if max_pages_raw:
            max_pages = self._parse_positive_int(max_pages_raw, field="Max pages")
            if max_pages is None or max_pages == 0:
                if max_pages == 0:
                    messagebox.showerror("Invalid max pages", "Max pages must be > 0.")
                return None
        else:
            max_pages = None

        excludes = [
            line.strip()
            for line in self._exclude_text.get("1.0", tk.END).splitlines()
            if line.strip()
        ]
        return CrawlSettings(
            url=url,
            output_dir=Path(self._output_dir.get()).expanduser(),
            concurrency=concurrency or 20,
            image_wait_ms=image_wait_ms or 0,
            asset_quiet_ms=asset_quiet_ms or 0,
            page_asset_timeout_ms=page_asset_timeout_ms or 0,
            settle_ms=settle_ms or 0,
            timeout_secs=timeout_secs or 60,
            asset_concurrency=asset_concurrency or 12,
            max_pages=max_pages,
            force=self._force.get(),
            exclude_patterns=excludes,
        )

    def start_crawl(self) -> None:
        if self._crawl_proc is not None:
            messagebox.showinfo("Crawl running", "A crawl is already in progress.")
            return

        settings = self._parse_settings()
        if settings is None:
            return

        settings.output_dir.mkdir(parents=True, exist_ok=True)
        argv = build_crawl_argv(settings)
        self._append_log(f"$ {' '.join(argv)}")

        try:
            self._crawl_proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            messagebox.showerror("Could not start crawl", str(exc))
            self._crawl_proc = None
            return

        self._start_button.configure(state=tk.DISABLED)
        self._stop_button.configure(state=tk.NORMAL)
        self._continue_button.configure(state=tk.DISABLED)
        self._status.set("Crawl running…")

        self._crawl_thread = threading.Thread(
            target=self._read_crawl_output,
            daemon=True,
        )
        self._crawl_thread.start()

    def _read_crawl_output(self) -> None:
        proc = self._crawl_proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self._log_queue.put(line)
        code = proc.wait()
        self.after(0, lambda: self._crawl_finished(code))

    def _crawl_finished(self, return_code: int) -> None:
        self._crawl_proc = None
        self._crawl_thread = None
        self._start_button.configure(state=tk.NORMAL)
        self._stop_button.configure(state=tk.DISABLED)
        self._continue_button.configure(state=tk.DISABLED)
        if return_code == 0:
            self._status.set("Crawl finished")
            self.refresh_library()
        else:
            self._status.set(f"Crawl exited with code {return_code}")

    def continue_after_login(self) -> None:
        proc = self._crawl_proc
        if proc is None or proc.stdin is None:
            return
        proc.stdin.write("\n")
        proc.stdin.flush()
        self._continue_button.configure(state=tk.DISABLED)
        self._status.set("Crawl running…")
        self._append_log("[GUI] Sent continue after login.")

    def stop_crawl(self) -> None:
        proc = self._crawl_proc
        if proc is None:
            return
        proc.terminate()
        self._append_log("[GUI] Stop requested.")
        self._status.set("Stopping crawl…")

    def refresh_library(self) -> None:
        output_dir = Path(self._output_dir.get()).expanduser()
        self._sites = list_saved_sites(output_dir)
        for item in self._site_tree.get_children():
            self._site_tree.delete(item)
        for site in self._sites:
            modified = datetime.fromtimestamp(site.modified_at).strftime(
                "%Y-%m-%d %H:%M",
            )
            self._site_tree.insert(
                "",
                tk.END,
                iid=site.host,
                values=(site.host, site.page_count, modified),
            )
        self._status.set(f"{len(self._sites)} saved site(s) in {output_dir}")

    def open_selected_site(self) -> None:
        selection = self._site_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Choose a site from the list first.")
            return
        host = selection[0]
        output_dir = Path(self._output_dir.get()).expanduser()
        if self._preview.output_dir != output_dir.resolve():
            self._preview.stop()
            self._preview = PreviewServer(output_dir)
        if not self._preview.is_running:
            port = self._preview.start()
            self._append_log(
                f"[GUI] Preview server started on http://127.0.0.1:{port}/"
            )
        url = self._preview.site_url(host)
        webbrowser.open(url)
        self._status.set(f"Opened {url}")

    def _on_close(self) -> None:
        if self._crawl_proc is not None:
            if not messagebox.askyesno(
                "Crawl in progress",
                "A crawl is still running. Stop it and quit?",
            ):
                return
            self.stop_crawl()
        self._preview.stop()
        self.destroy()


def apply_capture_preset(preset: str) -> dict[str, int]:
    """Return timing values for a named capture preset."""
    return dict(CAPTURE_PRESETS[preset])


def run_gui() -> None:
    app = FolioApp()
    app.mainloop()
