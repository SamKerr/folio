# T02-cli-and-playwright-smoke

## Context

Developers need a quick way to confirm the tool is installed and Playwright browsers work before building the crawler.

## Scope

- CLI with `--version`, `--help`, and `doctor` subcommand
- `doctor` launches Chromium, loads a blank page, reports success or actionable error
- `python -m folio` entry via `__main__.py`

## Implementation plan (required before coding)

### Planned approach

1. Implement argparse CLI in `cli.py` with `doctor` command
2. Add `doctor.py` with async Playwright smoke check
3. Add `__main__.py` delegating to CLI main

### Files to touch

- `src/folio/cli.py`: argument parsing and dispatch
- `src/folio/doctor.py`: Playwright browser launch smoke test
- `src/folio/__main__.py`: module entry point

### Data and API impact

- None

### Risks and mitigations

- Risk: Playwright browsers not installed
  Mitigation: doctor prints clear message to run `playwright install chromium`

### Verification plan (ticket-specific)

- Automated: CLI unit tests with mocked doctor
- Manual: `folio doctor` after `playwright install chromium`

## Acceptance criteria

- [x] `folio --version` prints version and exits 0
- [x] `folio --help` shows usage including `doctor`
- [x] `folio doctor` launches Chromium and exits 0 when browsers are installed
- [x] `python -m folio --version` works

## Implementation notes (during/after execution)

- `doctor.py` uses async Playwright to launch headless Chromium and load `about:blank`
- CLI catches errors and prints install hint for missing browsers

## Verification

- [x] Manual `folio doctor` passes with browsers installed
- [x] CLI tests pass (mocked)

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T02-cli-and-playwright-smoke.md`.
