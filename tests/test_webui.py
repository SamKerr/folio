import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from folio.crawl_runner import CrawlSettings
from folio.webui.server import STATIC_DIR, WebUIServer
from folio.webui.session import (
    CrawlProgress,
    CrawlSession,
    SettingsError,
    normalize_start_url,
    parse_progress_line,
    settings_from_payload,
)

FAKE_CRAWL = """
import sys, time
print("Crawling (1): https://example.com/a", file=sys.stderr, flush=True)
input("Browser opened. Log in if needed, then press Enter here to start crawling...")
print("Crawling (2): https://example.com/b", file=sys.stderr, flush=True)
print("Skipped (HTTP 500): https://example.com/c", file=sys.stderr, flush=True)
print("Crawl complete: saved 2 new page(s), skipped 1 existing, under /tmp/x")
"""

SLOW_CRAWL = """
import time
print("Crawling (1): https://example.com/a", flush=True)
time.sleep(60)
"""


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": "https://example.com/",
        "output_dir": "/tmp/folio-out",
        "concurrency": 20,
        "asset_concurrency": 12,
        "image_wait_ms": 5000,
        "asset_quiet_ms": 750,
        "page_asset_timeout_ms": 60000,
        "settle_ms": 1000,
        "timeout_secs": 60,
        "max_pages": "",
        "force": False,
        "exclude_patterns": "/blog/*\n\n /forum/* ",
    }
    payload.update(overrides)
    return payload


def _script_builder(script: str) -> Any:
    def build(_settings: CrawlSettings) -> list[str]:
        return [sys.executable, "-c", script]

    return build


def _wait_for(predicate: Any, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


# -- settings ---------------------------------------------------------------


def test_settings_from_payload_parses_values() -> None:
    settings = settings_from_payload(_payload(max_pages="50", force=True))
    assert settings.url == "https://example.com/"
    assert settings.max_pages == 50
    assert settings.force is True
    assert settings.exclude_patterns == ["/blog/*", "/forum/*"]
    assert settings.output_dir == Path("/tmp/folio-out")


def test_normalize_start_url_adds_scheme_and_slash() -> None:
    assert normalize_start_url("example.com") == "https://example.com/"
    assert normalize_start_url("http://a.b/docs") == "http://a.b/docs"
    assert normalize_start_url("127.0.0.1:8000") == "http://127.0.0.1:8000/"
    assert normalize_start_url("localhost/x") == "http://localhost/x"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"url": ""}, "url"),
        ({"url": "ftp://example.com/"}, "url"),
        ({"output_dir": " "}, "output_dir"),
        ({"concurrency": 0}, "concurrency"),
        ({"settle_ms": "abc"}, "settle_ms"),
        ({"max_pages": "0"}, "max_pages"),
        ({"timeout_secs": -1}, "timeout_secs"),
    ],
)
def test_settings_from_payload_rejects_bad_fields(
    overrides: dict[str, Any], field: str
) -> None:
    with pytest.raises(SettingsError) as info:
        settings_from_payload(_payload(**overrides))
    assert info.value.field == field


# -- progress parsing -------------------------------------------------------


def test_parse_progress_line_counts_events() -> None:
    progress = CrawlProgress()
    lines = [
        "Crawling (1): https://example.com/a",
        "Skipping (exists): https://example.com/b",
        "Skipped (HTTP 404): https://example.com/c",
        "Rate limited (HTTP 429): pausing 30 s",
        "Some unrelated line",
        "Crawl complete: saved 7 new page(s), skipped 3 existing, under /x",
        "2 page(s) failed (error pages, timeouts or errors) and were left unsaved",
    ]
    changed = [parse_progress_line(line, progress) for line in lines]
    assert changed == [True, True, True, True, False, True, True]
    assert progress.fetched == 1
    assert progress.errors == 1
    assert progress.rate_limited == 1
    assert progress.saved == 7
    assert progress.skipped_existing == 3
    assert progress.failed == 2
    assert progress.current_url is None


# -- session ----------------------------------------------------------------


def test_session_waits_for_login_then_finishes(tmp_path: Path) -> None:
    session = CrawlSession(_script_builder(FAKE_CRAWL))
    events = session.subscribe()
    session.start(settings_from_payload(_payload(output_dir=str(tmp_path))))

    _wait_for(lambda: session.state == "waiting_login")
    assert session.progress.fetched == 1
    assert session.continue_after_login() is True
    _wait_for(lambda: session.state == "finished")

    snap = session.snapshot(include_log=True)
    assert snap["return_code"] == 0
    assert snap["host"] == "example.com"
    assert snap["progress"]["fetched"] == 2
    assert snap["progress"]["errors"] == 1
    assert snap["progress"]["saved"] == 2
    assert any("press Enter here" in line for line in snap["log"])

    states = []
    while not events.empty():
        event = events.get_nowait()
        if event["type"] == "state":
            states.append(event["session"]["state"])
    assert states == ["running", "waiting_login", "running", "finished"]


def test_session_stop_marks_stopped(tmp_path: Path) -> None:
    session = CrawlSession(_script_builder(SLOW_CRAWL))
    session.start(settings_from_payload(_payload(output_dir=str(tmp_path))))
    _wait_for(lambda: session.progress.fetched == 1)
    assert session.stop() is True
    _wait_for(lambda: session.state == "stopped")
    assert session.stop() is False


# -- server -----------------------------------------------------------------


@pytest.fixture
def server(tmp_path: Path) -> Iterator[WebUIServer]:
    site = tmp_path / "out" / "www.example.com"
    site.mkdir(parents=True)
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    opened: list[str] = []
    app = WebUIServer(
        default_output_dir=tmp_path / "out",
        session=CrawlSession(_script_builder(FAKE_CRAWL)),
        open_url=lambda url, _title: opened.append(url),
    )
    app.start()
    app.opened = opened  # type: ignore[attr-defined]
    try:
        yield app
    finally:
        app.stop()


def _request(
    app: WebUIServer,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = "",
    host: str | None = None,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Folio-Token"] = token or app.token
    if host is not None:
        headers["Host"] = host
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(app.url + path.lstrip("/"), data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, json.loads(raw) if "json" in ctype else raw.decode()
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_api_requires_token(server: WebUIServer) -> None:
    status, body = _request(server, "/api/config", token=None)
    assert status == 403
    status, _ = _request(server, "/api/config", token="wrong")
    assert status == 403
    status, body = _request(server, "/api/config")
    assert status == 200
    assert "Balanced" in body["presets"]
    assert body["can_pick_folder"] is False


def test_foreign_host_rejected(server: WebUIServer) -> None:
    status, _ = _request(server, "/api/config", host="evil.example:80")
    assert status == 403
    status, _ = _request(server, "/", token=None, host="evil.example:80")
    assert status == 403


def test_index_injects_token(server: WebUIServer) -> None:
    status, body = _request(server, "/", token=None)
    assert status == 200
    assert server.token in body
    assert "__FOLIO_TOKEN__" not in body


def test_static_traversal_blocked(server: WebUIServer) -> None:
    status, _ = _request(server, "/static/../server.py", token=None)
    assert status == 404


def test_library_lists_and_opens_sites(server: WebUIServer) -> None:
    status, body = _request(server, "/api/library")
    assert status == 200
    assert [site["host"] for site in body["sites"]] == ["www.example.com"]

    status, body = _request(
        server, "/api/library/open", body={"host": "www.example.com"}
    )
    assert status == 200
    assert body["url"].endswith("/www.example.com/")
    assert server.opened == [body["url"]]  # type: ignore[attr-defined]

    status, _ = _request(server, "/api/library/open", body={"host": "../etc"})
    assert status == 404


def test_crawl_api_validates_and_runs(server: WebUIServer, tmp_path: Path) -> None:
    status, body = _request(server, "/api/crawl", body=_payload(url=""))
    assert status == 400
    assert body["field"] == "url"

    status, body = _request(
        server, "/api/crawl", body=_payload(output_dir=str(tmp_path / "o2"))
    )
    assert status == 200
    assert body["state"] == "running"

    status, _ = _request(server, "/api/crawl", body=_payload())
    assert status == 409

    _wait_for(lambda: server.session.state == "waiting_login")
    status, body = _request(server, "/api/crawl/continue", body={})
    assert body == {"ok": True}
    _wait_for(lambda: server.session.state == "finished")

    status, body = _request(server, "/api/pick-folder", body={})
    assert status == 501


def test_static_dir_has_ui_files() -> None:
    names = ("index.html", "app.js", "styles.css", "vendor/vue.esm-browser.prod.js")
    for name in names:
        assert (STATIC_DIR / name).is_file(), name
