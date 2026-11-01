# T22-bare-folio-opens-gui

## Context

- Most use is through the desktop app, so typing `folio` alone should open it rather than
  print help. `--help` remains the way to list commands.

## Scope

- `folio` with no subcommand runs the web UI in a native window
- Not in scope: `--help`, `--version`, subcommands, `folio gui` flags

## Implementation plan (required before coding)

### Planned approach

1. In `main()` (`src/folio/cli.py`), replace the final `parser.print_help()` fallback with
   `run_webui(browser=False)`.
2. Replace `test_no_command_prints_help` with a test that bare `folio` calls `run_webui`.
3. README: say `folio` alone opens the app.

### Files to touch

- `src/folio/cli.py`: no-subcommand fallback
- `tests/test_cli.py`: update test
- `README.md`: usage and commands table

### Data and API impact

- Schema/migration changes: none
- API/RPC/edge function changes: none
- State management changes: none

### Risks and mitigations

- Risk: scripts relying on bare `folio` printing help. Mitigation: `--help` unchanged; the
  GUI only ever launches crawls with an explicit `crawl` subcommand.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_cli.py`
- Manual: `uv run folio --help` still prints help

## Acceptance criteria

- [x] `folio` with no arguments opens the desktop app
- [x] `folio --help` and `folio --version` behave as before
- [x] README updated

## Implementation notes (during/after execution)

- `main()` falls back to `run_webui(browser=False)` instead of `parser.print_help()`.
- `test_no_command_prints_help` replaced by `test_no_command_opens_gui`.
- README: `folio gui --browser` named explicitly, since bare `folio` takes no flags.
- Checks: 238 tests pass; ruff/mypy show only the pre-existing issues in
  `browser_scripts.py` and `tests/test_gui_support.py`. `folio --help` and `--version`
  unchanged.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run mypy`
- [x] Manual check of `folio --help`

## Status

- Owner: Claude
- State: Done
