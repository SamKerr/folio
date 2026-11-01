# T19-webui-backend

## Context

- The new Vue UI needs a local backend: start/continue/stop a crawl, stream its log and
  progress, list and open saved sites, and (in the desktop window) pick a folder.

## Scope

- `src/folio/webui/session.py`: `CrawlSession` (subprocess lifecycle, line parsing into
  state: idle/running/waiting_login/stopping/finished/failed, counters, current URL,
  log ring buffer, subscriber queues) and `settings_from_payload()` validation
- `src/folio/webui/server.py`: `WebUIServer` (ThreadingHTTPServer on 127.0.0.1, port 0)
  serving static files, `/api/*` JSON endpoints and `/api/events` SSE
- Shared presets moved to `src/folio/presets.py` (Tk GUI imports them from there)
- Not in scope: the UI itself, the native window

## Implementation plan (required before coding)

### Planned approach

1. Move `CAPTURE_PRESETS` + choice tuples to `folio/presets.py`; Tk GUI re-imports them.
2. `settings_from_payload(dict) -> CrawlSettings`, raising `SettingsError(field, msg)`.
3. `CrawlSession`: spawn `build_crawl_argv(settings)` (argv builder injectable for tests)
   with `PYTHONUNBUFFERED=1`; a reader thread reads raw stdout chunks so the newline-less
   login prompt is seen; parse `Crawling (`, `Skipping (exists)`, `Skipped (`, `Failed (`,
   `Warning: failed`, `Rate limited`, `Crawl complete: saved N`; publish events to
   subscriber queues; `continue_after_login()` writes `\n`; `stop()` terminates.
4. `WebUIServer`: routes `GET /` (index with token injected), `GET /static/*`,
   `GET /api/state`, `GET /api/config`, `GET /api/library?output=`, `POST /api/crawl`,
   `POST /api/crawl/continue`, `POST /api/crawl/stop`, `POST /api/library/open`,
   `POST /api/pick-folder`, `GET /api/events?token=` (SSE). Host check + token check.
   Callbacks `open_url` and `pick_folder` injected by the launcher.

### Files to touch

- `src/folio/presets.py` (new), `src/folio/gui.py` (import presets)
- `src/folio/webui/__init__.py`, `session.py`, `server.py` (new)
- `tests/test_webui.py` (new)

### Data and API impact

- Schema/migration changes: none
- API/RPC/edge function changes: new local-only HTTP API (documented in server docstring)
- State management changes: crawl state lives in `CrawlSession` (one crawl at a time)

### Risks and mitigations

- Risk: any web page in the user's browser could POST to the local API (spawn crawls).
  Mitigation: per-launch random token required on all `/api/*`; Host header must be
  `127.0.0.1:<port>`/`localhost:<port>`; bind 127.0.0.1 only.
- Risk: login prompt has no newline, line-based reading misses it.
  Mitigation: read chunks, check the partial buffer for the prompt text.
- Risk: path traversal in static serving. Mitigation: resolve and require under static dir.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_webui.py` — payload validation, line parsing,
  session with a fake crawl script (prompt → continue → finish, stop), API token/host
  rejection, library listing, static traversal blocked.
- Manual: none (UI in T20).

## Acceptance criteria

- [x] Invalid payloads return 400 with the offending field
- [x] A crawl can be started, continued after login, stopped via the API
- [x] SSE stream delivers log lines and state changes
- [x] Requests without the token or with a foreign Host get 403
- [x] Tk GUI still works with presets moved

## Implementation notes (during/after execution)

- `CrawlSession` reads raw stdout chunks so the newline-less login prompt is detected
  (the Tk GUI's `"press Enter" in line.lower()` check could never match).
- `ruff check .` still reports 3 pre-existing E501s in `browser_scripts.py` and `mypy`
  4 pre-existing errors in `tests/test_gui_support.py`; none from this ticket.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run mypy`

## Status

- Owner: Claude
- State: Done
