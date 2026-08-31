# Sprint 1 - Setup tooling and scaffolding

## Scope

- Python packaging (`pyproject.toml`), installable package under `src/folio/`
- CLI entry point with `--version`, `--help`, and a `doctor` command that verifies Playwright
- Dev tooling: pytest, ruff
- README and AGENTS.md updated with concrete setup/run commands
- End-to-end verification: install deps, run CLI, run tests

## Out of scope

- Crawling, link extraction, or HTML persistence
- CI pipeline (can be Sprint 2)
- Asset downloads or multi-browser support

## Tickets

- [x] `T01-project-packaging`
- [x] `T02-cli-and-playwright-smoke`
- [x] `T03-dev-tooling-and-docs`

## Sequencing

1. T01 — package layout and dependencies
2. T02 — CLI and Playwright doctor check (depends on T01)
3. T03 — tests, lint config, README updates (depends on T02)

## Done criteria

- All in-scope tickets marked complete
- `pip install -e ".[dev]"` succeeds
- `playwright install chromium` documented and doctor passes
- `folio --version` and `folio doctor` run successfully
- `pytest` and `ruff check` pass
- README documents setup and verification steps

## Verification plan

- `python -m venv .venv && source .venv/bin/activate`
- `pip install -e ".[dev]"`
- `playwright install chromium`
- `folio --version`
- `folio doctor`
- `pytest`
- `ruff check .`

## Notes

- Delivered editable install, CLI with doctor smoke check, pytest + ruff tooling
- Next sprint: crawl command, URL normalization, link discovery, HTML output

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-1.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
