"""Local HTTP server for the Folio web UI.

Binds 127.0.0.1 only. Every ``/api/*`` request must carry the per-launch token
(``X-Folio-Token`` header, or ``?token=`` for the event stream) and a Host header
naming this server, so other web pages cannot drive it.

Endpoints:

- ``GET  /api/config``          defaults, presets, choices, window capabilities
- ``GET  /api/state``           crawl session snapshot including the log
- ``GET  /api/events``          server-sent events: ``state`` and ``log``
- ``GET  /api/library?output=`` saved sites in an output folder
- ``POST /api/crawl``           start a crawl (400 with ``field`` on bad input)
- ``POST /api/crawl/continue``  send Enter after login
- ``POST /api/crawl/stop``      terminate the crawl
- ``POST /api/library/open``    serve a saved site and open it
- ``POST /api/pick-folder``     native folder dialog (501 when unavailable)
"""

from __future__ import annotations

import json
import mimetypes
import queue
import secrets
import sys
import threading
from collections.abc import Callable
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from folio.output_catalog import list_saved_sites
from folio.presets import (
    ASSET_CONCURRENCY_CHOICES,
    CAPTURE_PRESETS,
    PAGE_CONCURRENCY_CHOICES,
)
from folio.preview_server import PreviewServer
from folio.webui.session import (
    CrawlBusyError,
    CrawlSession,
    SettingsError,
    settings_from_payload,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "folio.png"
TOKEN_PLACEHOLDER = "__FOLIO_TOKEN__"
SSE_HEARTBEAT_SECS = 15.0

PRESET_DESCRIPTIONS = {
    "Fast": "Skips most waits. Quickest, may miss lazy images.",
    "Balanced": "Waits briefly for images and downloads. Good default.",
    "Thorough": "Waits longer for images and assets. Slowest, most complete.",
}

OpenUrl = Callable[[str, str], object]
PickFolder = Callable[[], str | None]


class WebUIServer:
    """Serve the UI, its JSON API and the event stream."""

    def __init__(
        self,
        *,
        default_output_dir: Path,
        session: CrawlSession | None = None,
        open_url: OpenUrl | None = None,
        pick_folder: PickFolder | None = None,
        static_dir: Path = STATIC_DIR,
        port: int = 0,
    ) -> None:
        self.default_output_dir = default_output_dir.expanduser().resolve()
        self.session = session or CrawlSession()
        self.open_url = open_url
        self.pick_folder = pick_folder
        self.static_dir = static_dir.resolve()
        self.token = secrets.token_urlsafe(24)
        self._port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._preview: PreviewServer | None = None
        self._preview_lock = threading.Lock()
        self.closing = threading.Event()

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("Web UI server is not running")
        return int(self._httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> str:
        if self._httpd is None:
            handler = partial(_Handler, self)
            self._httpd = _QuietServer(("127.0.0.1", self._port), handler)
            self._thread = threading.Thread(
                target=self._httpd.serve_forever, daemon=True
            )
            self._thread.start()
        return self.url

    def stop(self) -> None:
        self.closing.set()
        self.session.shutdown()
        with self._preview_lock:
            if self._preview is not None:
                self._preview.stop()
                self._preview = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None

    # -- helpers used by the handler -----------------------------------------

    def allowed_host(self, host: str | None) -> bool:
        if self._httpd is None or host is None:
            return False
        return host in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def config(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.default_output_dir),
            "presets": CAPTURE_PRESETS,
            "preset_descriptions": PRESET_DESCRIPTIONS,
            "page_concurrency_choices": [int(v) for v in PAGE_CONCURRENCY_CHOICES],
            "asset_concurrency_choices": [int(v) for v in ASSET_CONCURRENCY_CHOICES],
            "can_pick_folder": self.pick_folder is not None,
        }

    def library(self, output: str | None) -> dict[str, Any]:
        output_dir = Path(output).expanduser() if output else self.default_output_dir
        sites = list_saved_sites(output_dir)
        return {
            "output_dir": str(output_dir.resolve()),
            "sites": [
                {
                    "host": site.host,
                    "page_count": site.page_count,
                    "modified_at": site.modified_at,
                    "path": str(site.root.resolve()),
                }
                for site in sites
            ],
        }

    def open_site(self, output: str | None, host: str) -> str:
        output_dir = (
            Path(output).expanduser() if output else self.default_output_dir
        ).resolve()
        hosts = {site.host for site in list_saved_sites(output_dir)}
        if host not in hosts:
            raise KeyError(host)
        with self._preview_lock:
            if self._preview is None or self._preview.output_dir != output_dir:
                if self._preview is not None:
                    self._preview.stop()
                self._preview = PreviewServer(output_dir)
            self._preview.start()
            url = self._preview.site_url(host)
        if self.open_url is not None:
            self.open_url(url, host)
        return url


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Closed tabs and reloads reset connections; that is not an error.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    server_version = "FolioUI/1"

    def __init__(self, app: WebUIServer, *args: Any, **kwargs: Any) -> None:
        self.app = app
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep the terminal quiet

    # -- plumbing ------------------------------------------------------------

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _guard(self, *, query: dict[str, list[str]], api: bool) -> bool:
        if not self.app.allowed_host(self.headers.get("Host")):
            self._send_json(403, {"error": "Forbidden host"})
            return False
        if api:
            token = self.headers.get("X-Folio-Token") or (
                query.get("token") or [""]
            )[0]
            if not secrets.compare_digest(token, self.app.token):
                self._send_json(403, {"error": "Missing or invalid token"})
                return False
        return True

    # -- GET -----------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        path = parts.path
        api = path.startswith("/api/")
        if not self._guard(query=query, api=api):
            return
        if path in {"/", "/index.html"}:
            self._serve_index()
        elif path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
        elif path == "/api/config":
            self._send_json(200, self.app.config())
        elif path == "/api/state":
            self._send_json(200, self.app.session.snapshot(include_log=True))
        elif path == "/api/library":
            output = query.get("output")
            self._send_json(200, self.app.library(output[0] if output else None))
        elif path == "/api/events":
            self._stream_events()
        else:
            self._send_json(404, {"error": "Not found"})

    def _serve_index(self) -> None:
        html = (self.app.static_dir / "index.html").read_text(encoding="utf-8")
        body = html.replace(TOKEN_PLACEHOLDER, self.app.token).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, relative: str) -> None:
        target = (self.app.static_dir / relative).resolve()
        if relative == "folio.png":
            target = LOGO_PATH
        elif not target.is_relative_to(self.app.static_dir):
            target = self.app.static_dir / "missing"
        if not target.is_file():
            self._send_json(404, {"error": "Not found"})
            return
        if target.suffix in {".js", ".mjs"}:
            content_type = "text/javascript; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        else:
            content_type = (
                mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream_events(self) -> None:
        session = self.app.session
        subscription = session.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self._write_event({"type": "state", "session": session.snapshot()})
            while not self.app.closing.is_set():
                try:
                    event = subscription.get(timeout=SSE_HEARTBEAT_SECS)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._write_event(event)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            session.unsubscribe(subscription)

    def _write_event(self, event: dict[str, Any]) -> None:
        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.flush()

    # -- POST ----------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if not self._guard(query={}, api=True):
            return
        try:
            payload = self._read_json()
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "Invalid JSON"})
            return

        session = self.app.session
        path = parts.path
        if path == "/api/crawl":
            try:
                settings = settings_from_payload(payload)
                session.start(settings)
            except SettingsError as exc:
                self._send_json(400, {"error": exc.message, "field": exc.field})
                return
            except CrawlBusyError as exc:
                self._send_json(409, {"error": str(exc)})
                return
            except OSError as exc:
                self._send_json(500, {"error": f"Could not start crawl: {exc}"})
                return
            self._send_json(200, session.snapshot())
        elif path == "/api/crawl/continue":
            self._send_json(200, {"ok": session.continue_after_login()})
        elif path == "/api/crawl/stop":
            self._send_json(200, {"ok": session.stop()})
        elif path == "/api/library/open":
            try:
                url = self.app.open_site(
                    payload.get("output_dir"), str(payload.get("host") or "")
                )
            except KeyError:
                self._send_json(404, {"error": "No saved site with that name"})
                return
            self._send_json(200, {"url": url})
        elif path == "/api/pick-folder":
            if self.app.pick_folder is None:
                self._send_json(501, {"error": "Folder picker unavailable"})
                return
            self._send_json(200, {"path": self.app.pick_folder()})
        else:
            self._send_json(404, {"error": "Not found"})
