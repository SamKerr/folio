"""Launch the Folio web UI in a native window (pywebview) or the default browser."""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

from folio.webui.server import WebUIServer

WINDOW_SIZE = (1120, 780)
MIN_SIZE = (820, 600)
QUIT_WHILE_CRAWLING = "A crawl is still running. Stop it and quit?"


def run_webui(*, browser: bool = False, output_dir: Path | None = None) -> int:
    """Start the UI server and show it; block until the window closes or Ctrl+C."""
    default_output = output_dir or Path("output")
    if not browser:
        try:
            import webview
        except ImportError as exc:
            print(
                f"Native window unavailable ({exc}); opening in your browser.",
                file=sys.stderr,
            )
            browser = True
        else:
            return _run_window(webview, default_output)
    return _run_browser(default_output)


def _run_browser(output_dir: Path) -> int:
    server = WebUIServer(
        default_output_dir=output_dir,
        open_url=lambda url, _title: webbrowser.open(url),
    )
    url = server.start()
    print(f"Folio is running at {url} (press Ctrl+C to quit)")
    webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print()
    finally:
        server.stop()
    return 0


def _run_window(webview: Any, output_dir: Path) -> int:
    holder: dict[str, Any] = {}

    def open_url(url: str, title: str) -> None:
        webview.create_window(
            title, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1]
        )

    def pick_folder() -> str | None:
        window = holder["window"]
        current = server.default_output_dir
        chosen = window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=str(current)
        )
        return str(chosen[0]) if chosen else None

    server = WebUIServer(
        default_output_dir=output_dir,
        open_url=open_url,
        pick_folder=pick_folder,
    )
    url = server.start()
    window = webview.create_window(
        "Folio",
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_SIZE,
        background_color="#f4eedf",
        text_select=True,
        localization={"global.quitConfirmation": QUIT_WHILE_CRAWLING},
    )
    holder["window"] = window

    def on_closing() -> None:
        # Read after the closing handlers run: confirm only while crawling.
        window.confirm_close = server.session.is_active

    def on_closed() -> None:
        # Saved-site windows should not keep the app alive once Folio closes.
        for other in list(webview.windows):
            if other is not window:
                other.destroy()

    window.events.closing += on_closing
    window.events.closed += on_closed
    try:
        webview.start()
    finally:
        server.stop()
    return 0
