"""Local static HTTP server for browsing saved Folio output."""

from __future__ import annotations

import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PreviewServer:
    """Serve an output directory over HTTP for offline browsing."""

    def __init__(self, output_dir: Path, *, port: int = 0) -> None:
        self.output_dir = output_dir.resolve()
        self._port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._httpd is None:
            msg = "Preview server is not running"
            raise RuntimeError(msg)
        return self._httpd.server_address[1]

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    def start(self) -> int:
        """Start the server and return the bound port."""
        if self._httpd is not None:
            return self.port

        handler = partial(
            SimpleHTTPRequestHandler,
            directory=str(self.output_dir),
        )
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self._port), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None

    def site_url(self, host: str) -> str:
        return f"http://127.0.0.1:{self.port}/{host}/"


def pick_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
