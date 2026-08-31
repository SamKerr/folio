"""Desktop GUI for configuring crawls and browsing saved output."""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from folio.crawl_runner import CrawlSettings, build_crawl_argv
from folio.output_catalog import SavedSite, list_saved_sites
from folio.preview_server import PreviewServer


class FolioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Folio")
        self.geometry("960x720")
        self.minsize(820, 620)

        self._output_dir = tk.StringVar(value=str(Path("output").resolve()))
        self._crawl_url = tk.StringVar(value="https://www.example.com/")
        self._concurrency = tk.IntVar(value=20)
        self._image_wait_ms = tk.IntVar(value=5000)
        self._asset_quiet_ms = tk.IntVar(value=750)
        self._page_asset_timeout_ms = tk.IntVar(value=60_000)
        self._settle_ms = tk.IntVar(value=1000)
        self._timeout_secs = tk.IntVar(value=60)
        self._asset_concurrency = tk.IntVar(value=12)
        self._max_pages = tk.StringVar(value="")
        self._force = tk.BooleanVar(value=False)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._crawl_proc: subprocess.Popen[str] | None = None
        self._crawl_thread: threading.Thread | None = None
        self._preview = PreviewServer(Path("output"))
        self._sites: list[SavedSite] = []

        self._build_ui()
        self._poll_log_queue()
        self.refresh_library()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        crawl_tab = ttk.Frame(notebook, padding=8)
        library_tab = ttk.Frame(notebook, padding=8)
        notebook.add(crawl_tab, text="Crawl")
        notebook.add(library_tab, text="Library")

        self._build_crawl_tab(crawl_tab)
        self._build_library_tab(library_tab)

        self._status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self._status, anchor=tk.W).pack(
            fill=tk.X,
            padx=10,
            pady=(0, 8),
        )

    def _build_crawl_tab(self, parent: ttk.Frame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill=tk.X)

        self._add_labeled_entry(form, 0, "Start URL", self._crawl_url, width=70)
        self._add_output_picker(form, 1)

        options = ttk.LabelFrame(form, text="Options", padding=8)
        options.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        for col in range(4):
            options.columnconfigure(col, weight=1)

        self._add_spin(options, 0, 0, "Parallel pages", self._concurrency, 1, 64)
        self._add_spin(
            options, 0, 1, "Image wait (ms)", self._image_wait_ms, 0, 120_000
        )
        self._add_spin(
            options, 0, 2, "Asset quiet (ms)", self._asset_quiet_ms, 0, 10_000
        )
        self._add_spin(options, 0, 3, "Settle (ms)", self._settle_ms, 0, 60_000)
        self._add_spin(options, 1, 0, "Timeout (s)", self._timeout_secs, 10, 600)
        self._add_spin(
            options,
            1,
            1,
            "Page asset cap (ms)",
            self._page_asset_timeout_ms,
            1000,
            300_000,
        )
        self._add_spin(
            options,
            1,
            2,
            "Asset parallel",
            self._asset_concurrency,
            1,
            64,
        )
        self._add_labeled_entry(
            options,
            1,
            "Max pages",
            self._max_pages,
            width=10,
            column=3,
        )
        ttk.Checkbutton(options, text="Force re-fetch", variable=self._force).grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=4,
            pady=4,
        )

        exclude_frame = ttk.LabelFrame(
            parent, text="Exclude path patterns (one per line)"
        )
        exclude_frame.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self._exclude_text = tk.Text(exclude_frame, height=4, wrap=tk.NONE)
        self._exclude_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._exclude_text.insert("1.0", "/community/*\n/blog/*")

        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(8, 0))
        self._start_button = ttk.Button(
            controls, text="Start crawl", command=self.start_crawl
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
        )
        self._stop_button.pack(side=tk.LEFT, padx=(8, 0))

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._log = tk.Text(log_frame, height=16, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.configure(yscrollcommand=scroll.set)
        self._log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_library_tab(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X)
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

        columns = ("host", "pages", "modified")
        self._site_tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode=tk.BROWSE,
        )
        self._site_tree.heading("host", text="Site")
        self._site_tree.heading("pages", text="Pages")
        self._site_tree.heading("modified", text="Last saved")
        self._site_tree.column("host", width=360, anchor=tk.W)
        self._site_tree.column("pages", width=80, anchor=tk.E)
        self._site_tree.column("modified", width=180, anchor=tk.W)
        self._site_tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._site_tree.bind("<Double-1>", lambda _event: self.open_selected_site())

        hint = ttk.Label(
            parent,
            text=(
                "Double-click a site to open it in your browser "
                "via a local preview server."
            ),
        )
        hint.pack(anchor=tk.W, pady=(8, 0))

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
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, pady=2)
        ttk.Entry(parent, textvariable=variable, width=width).grid(
            row=row,
            column=column + 1,
            sticky=tk.EW,
            padx=(8, 0),
            pady=2,
        )
        parent.columnconfigure(column + 1, weight=1)

    def _add_output_picker(self, parent: Any, row: int) -> None:
        ttk.Label(parent, text="Output folder").grid(
            row=row, column=0, sticky=tk.W, pady=2
        )
        ttk.Entry(parent, textvariable=self._output_dir, width=70).grid(
            row=row,
            column=1,
            sticky=tk.EW,
            padx=(8, 0),
            pady=2,
        )
        ttk.Button(parent, text="Browse…", command=self._pick_output_dir).grid(
            row=row,
            column=2,
            padx=(8, 0),
            pady=2,
        )
        parent.columnconfigure(1, weight=1)

    def _add_spin(
        self,
        parent: Any,
        row: int,
        column: int,
        label: str,
        variable: tk.IntVar,
        from_: int,
        to: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=column, sticky=tk.W, padx=4, pady=4
        )
        ttk.Spinbox(
            parent,
            from_=from_,
            to=to,
            textvariable=variable,
            width=8,
        ).grid(row=row + 1, column=column, sticky=tk.W, padx=4, pady=(0, 4))

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

    def _parse_settings(self) -> CrawlSettings | None:
        url = self._crawl_url.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Enter a start URL for the crawl.")
            return None

        max_pages_raw = self._max_pages.get().strip()
        max_pages: int | None
        if max_pages_raw:
            try:
                max_pages = int(max_pages_raw)
            except ValueError:
                messagebox.showerror("Invalid max pages", "Max pages must be a number.")
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
            concurrency=self._concurrency.get(),
            image_wait_ms=self._image_wait_ms.get(),
            asset_quiet_ms=self._asset_quiet_ms.get(),
            page_asset_timeout_ms=self._page_asset_timeout_ms.get(),
            settle_ms=self._settle_ms.get(),
            timeout_secs=self._timeout_secs.get(),
            asset_concurrency=self._asset_concurrency.get(),
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


def run_gui() -> None:
    app = FolioApp()
    app.mainloop()
