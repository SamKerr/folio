# Sprint 13 - Plain `folio` opens the app

## Scope

- Running `folio` with no subcommand opens the desktop app (same as `folio gui`)
- `folio --help`, `folio --version` and every subcommand are unchanged
- Out of scope: any other CLI or GUI behaviour

## Tickets

- [x] `T22-bare-folio-opens-gui`

## Sequencing

1. T22 (single ticket)

## Done criteria

- All in-scope tickets marked complete
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` pass (pre-existing issues aside)
- README documents the behaviour

## Verification plan

- `uv run pytest tests/test_cli.py`
- Manual: `uv run folio` opens the app; `uv run folio --help` prints help

## Notes

- Requested by the user after Sprint 12. Outcome: bare `folio` opens the app.

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-13.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
