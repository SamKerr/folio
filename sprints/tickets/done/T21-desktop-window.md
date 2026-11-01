# T21-desktop-window

## Context

- The web UI should feel like an app: a native window, not a browser tab.

## Scope

- Add `pywebview` dependency; `folio gui` starts `WebUIServer` and opens it in a pywebview
  window (folder picker via native dialog, saved sites open in a new app window)
- `folio gui --browser`: open in the default browser instead (no pywebview needed at runtime)
- `folio gui --classic`: the existing Tk GUI
- Closing the window with a crawl running asks to confirm, then stops it
- macOS `.app` launcher unchanged in shape (still runs `folio gui`)
- README GUI section updated

## Implementation plan (required before coding)

### Planned approach

1. `src/folio/webui/app.py`: `run_webui(browser: bool)` — start server, wire callbacks,
   create window (1120x780, min 820x600), confirm-close hook, stop session + preview on exit.
2. CLI: `gui` subparser gets `--browser` / `--classic`.
3. README + AGENTS verify notes.

### Files to touch

- `pyproject.toml`, `uv.lock` (pywebview), `src/folio/webui/app.py` (new),
  `src/folio/cli.py`, `README.md`, `tests/test_cli.py`

### Data and API impact

- Schema/migration changes: none
- API/RPC/edge function changes: none beyond T19
- State management changes: none

### Risks and mitigations

- Risk: pywebview import fails on some platforms. Mitigation: fall back to `--browser`
  behaviour with a message.
- Risk: `--browser` mode server must keep running. Mitigation: block until Ctrl+C.

### Verification plan (ticket-specific)

- Automated: CLI parses `gui --browser/--classic`; mypy/ruff clean.
- Manual: `uv run folio gui` opens the native window; Browse picks a folder; Open site
  opens a window; close-with-crawl confirmation.

## Acceptance criteria

- [x] `folio gui` opens the Vue UI in a native window
- [x] `--browser` and `--classic` work
- [x] README documents the new GUI

## Implementation notes (during/after execution)

- `src/folio/webui/app.py`: pywebview 6.2 window; `closing` handler sets
  `window.confirm_close` only while a crawl is active (custom quit message via
  localization); closing the main window closes saved-site windows.
- Falls back to browser mode if `import webview` fails.
- README screenshot (`assets/example-gui.png`) replaced with the new UI.
- Retheme (user request): palette taken from the Folio icon. Violet card sidebar with a
  gold edge, parchment page, gold accents, serif wordmark/headings, site avatars in icon
  colours; dark mode is a deep-violet "night card". Window background matches.
- Native window verified by the user: window opens, Browse… folder picker, opening a
  saved site, and the quit-while-crawling confirmation all work.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .` (only 3 pre-existing E501s in `browser_scripts.py`)
- [x] `uv run mypy` (only 4 pre-existing errors in `tests/test_gui_support.py`)
- [x] Manual check of window flows

## Status

- Owner: Claude
- State: Done
