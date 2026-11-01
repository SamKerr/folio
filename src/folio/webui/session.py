"""Run one `folio crawl` subprocess and track its progress for the web UI."""

from __future__ import annotations

import codecs
import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from folio.crawl_runner import CrawlSettings, build_crawl_argv

# The crawler prints this (without a trailing newline) while it waits for Enter.
LOGIN_PROMPT_MARKER = "press Enter here"

Event = dict[str, Any]

_CRAWLING_RE = re.compile(r"^Crawling \([^)]*\): (?P<url>\S+)")
_COMPLETE_RE = re.compile(
    r"^Crawl complete: saved (?P<saved>\d+) new page\(s\), "
    r"skipped (?P<skipped>\d+) existing"
)
_FAILED_TOTAL_RE = re.compile(r"^(?P<failed>\d+) page\(s\) failed")


class SettingsError(ValueError):
    """A crawl setting from the UI is missing or invalid."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class CrawlBusyError(RuntimeError):
    """A crawl is already running."""


@dataclass
class CrawlProgress:
    fetched: int = 0
    skipped_existing: int = 0
    errors: int = 0
    rate_limited: int = 0
    saved: int | None = None
    failed: int | None = None
    current_url: str | None = None


def parse_progress_line(line: str, progress: CrawlProgress) -> bool:
    """Update ``progress`` from one crawler output line; return True if it changed."""
    text = line.strip()
    if match := _CRAWLING_RE.match(text):
        progress.fetched += 1
        progress.current_url = match.group("url")
        return True
    if text.startswith("Skipping (exists):"):
        progress.skipped_existing += 1
        return True
    if text.startswith(("Skipped (", "Warning: failed to process")):
        progress.errors += 1
        return True
    if text.startswith("Rate limited (HTTP"):
        progress.rate_limited += 1
        return True
    if match := _COMPLETE_RE.match(text):
        progress.saved = int(match.group("saved"))
        progress.skipped_existing = int(match.group("skipped"))
        progress.current_url = None
        return True
    if match := _FAILED_TOTAL_RE.match(text):
        progress.failed = int(match.group("failed"))
        return True
    return False


def _parse_int(
    payload: dict[str, Any],
    field: str,
    label: str,
    *,
    minimum: int = 0,
    default: int | None = None,
) -> int:
    raw = payload.get(field, default)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if default is not None:
            return default
        raise SettingsError(field, f"{label} is required.")
    if isinstance(raw, bool):
        raise SettingsError(field, f"{label} must be a whole number.")
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise SettingsError(field, f"{label} must be a whole number.") from None
    if value < minimum:
        raise SettingsError(field, f"{label} must be at least {minimum}.")
    return value


def normalize_start_url(raw: str) -> str:
    """Return an http(s) URL, adding a scheme when missing (http for localhost)."""
    url = raw.strip()
    if not url:
        raise SettingsError("url", "Enter a start URL.")
    if "://" not in url:
        host = url.split("/", 1)[0].split(":", 1)[0].lower()
        local = host == "localhost" or host.startswith("127.")
        url = f"{'http' if local else 'https'}://{url}"
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise SettingsError("url", "Enter an http:// or https:// URL.")
    if not parts.path:
        url = f"{url}/"
    return url


def settings_from_payload(payload: dict[str, Any]) -> CrawlSettings:
    """Validate a JSON payload from the UI and build crawl settings."""
    url = normalize_start_url(str(payload.get("url") or ""))

    output_raw = str(payload.get("output_dir") or "").strip()
    if not output_raw:
        raise SettingsError("output_dir", "Choose an output folder.")
    output_dir = Path(output_raw).expanduser()

    max_pages_raw = payload.get("max_pages")
    max_pages: int | None = None
    if max_pages_raw not in (None, ""):
        max_pages = _parse_int(payload, "max_pages", "Max pages", minimum=1)

    excludes_raw = payload.get("exclude_patterns") or []
    if isinstance(excludes_raw, str):
        excludes_raw = excludes_raw.splitlines()
    if not isinstance(excludes_raw, list):
        raise SettingsError("exclude_patterns", "Exclude paths must be a list.")
    excludes = [str(item).strip() for item in excludes_raw if str(item).strip()]

    return CrawlSettings(
        url=url,
        output_dir=output_dir,
        concurrency=_parse_int(payload, "concurrency", "Parallel pages", minimum=1),
        asset_concurrency=_parse_int(
            payload, "asset_concurrency", "Parallel assets", minimum=1
        ),
        image_wait_ms=_parse_int(payload, "image_wait_ms", "Image wait"),
        asset_quiet_ms=_parse_int(payload, "asset_quiet_ms", "Asset quiet"),
        page_asset_timeout_ms=_parse_int(
            payload, "page_asset_timeout_ms", "Page asset cap"
        ),
        settle_ms=_parse_int(payload, "settle_ms", "Settle"),
        timeout_secs=_parse_int(payload, "timeout_secs", "Page timeout", minimum=1),
        max_pages=max_pages,
        force=bool(payload.get("force", False)),
        exclude_patterns=excludes,
    )


class CrawlSession:
    """One crawl at a time: subprocess lifecycle, parsed progress, log fan-out.

    States: ``idle`` → ``running`` ⇄ ``waiting_login`` → (``stopping``) →
    ``finished`` | ``failed`` | ``stopped``.
    """

    def __init__(
        self,
        argv_builder: Callable[[CrawlSettings], list[str]] = build_crawl_argv,
        *,
        log_limit: int = 2000,
    ) -> None:
        self._argv_builder = argv_builder
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._subscribers: list[queue.Queue[Event]] = []
        self._log: deque[str] = deque(maxlen=log_limit)
        self.state = "idle"
        self.url: str | None = None
        self.output_dir: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.return_code: int | None = None
        self.progress = CrawlProgress()
        self._stop_requested = False

    # -- observers -----------------------------------------------------------

    def snapshot(self, *, include_log: bool = False) -> Event:
        with self._lock:
            return self._snapshot_locked(include_log=include_log)

    def _snapshot_locked(self, *, include_log: bool = False) -> Event:
        data: Event = {
            "state": self.state,
            "url": self.url,
            "host": urlsplit(self.url).netloc if self.url else None,
            "output_dir": self.output_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "progress": asdict(self.progress),
        }
        if include_log:
            data["log"] = list(self._log)
        return data

    def subscribe(self) -> queue.Queue[Event]:
        q: queue.Queue[Event] = queue.Queue(maxsize=5000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[Event]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _publish_locked(self, event: Event) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def _set_state_locked(self, state: str) -> None:
        self.state = state
        self._publish_locked({"type": "state", "session": self._snapshot_locked()})

    def _log_locked(self, line: str) -> None:
        self._log.append(line)
        changed = parse_progress_line(line, self.progress)
        event: Event = {"type": "log", "line": line}
        if changed:
            event["progress"] = asdict(self.progress)
        self._publish_locked(event)

    @property
    def is_active(self) -> bool:
        return self.state in {"running", "waiting_login", "stopping"}

    # -- control -------------------------------------------------------------

    def start(self, settings: CrawlSettings) -> None:
        with self._lock:
            if self.is_active:
                raise CrawlBusyError("A crawl is already running.")
            settings.output_dir.mkdir(parents=True, exist_ok=True)
            argv = self._argv_builder(settings)
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            self.url = settings.url
            self.output_dir = str(settings.output_dir.resolve())
            self.started_at = time.time()
            self.finished_at = None
            self.return_code = None
            self.progress = CrawlProgress()
            self._stop_requested = False
            self._log.clear()
            self._log_locked(f"$ {' '.join(argv)}")
            self._set_state_locked("running")
            proc = self._proc
        threading.Thread(target=self._read_output, args=(proc,), daemon=True).start()

    def continue_after_login(self) -> bool:
        with self._lock:
            proc = self._proc
            if proc is None or proc.stdin is None or self.state != "waiting_login":
                return False
            try:
                proc.stdin.write(b"\n")
                proc.stdin.flush()
            except OSError:
                return False
            self._log_locked("[Folio] Continuing after login.")
            self._set_state_locked("running")
            return True

    def stop(self) -> bool:
        with self._lock:
            proc = self._proc
            if proc is None or not self.is_active:
                return False
            self._stop_requested = True
            proc.terminate()
            self._log_locked("[Folio] Stop requested.")
            self._set_state_locked("stopping")
            return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop any running crawl and wait for it to exit."""
        proc = self._proc
        if self.stop() and proc is not None:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()

    # -- reader thread -------------------------------------------------------

    def _read_output(self, proc: subprocess.Popen[bytes]) -> None:
        assert proc.stdout is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        fd = proc.stdout.fileno()
        buffer = ""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buffer += decoder.decode(chunk)
            *lines, buffer = buffer.split("\n")
            with self._lock:
                for line in lines:
                    self._log_locked(line.rstrip("\r"))
                if LOGIN_PROMPT_MARKER in buffer and self.state == "running":
                    # The prompt has no trailing newline; surface it now.
                    self._log_locked(buffer.strip())
                    buffer = ""
                    self._set_state_locked("waiting_login")
        buffer += decoder.decode(b"", final=True)
        code = proc.wait()
        with self._lock:
            if buffer.strip():
                self._log_locked(buffer.strip())
            self.return_code = code
            self.finished_at = time.time()
            self._proc = None
            if self._stop_requested:
                final = "stopped"
            elif code == 0:
                final = "finished"
            else:
                final = "failed"
            self._set_state_locked(final)
