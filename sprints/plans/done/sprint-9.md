# Sprint 9 - Crawl order: progressive listings

## Scope

- `folio crawl --order section|discovered|interleave` (default `section`, today's order)
- Data-only crawls default to `interleave` unless `--order` is given
- Tests (no network), README "Crawl order"
- Out of scope: the GUI; changing the saved file format; resume / visited logic

## Tickets

- [x] `T16-crawl-order`

## Sequencing

1. Ordering module (queue keys per mode) + unit tests
2. Crawler wiring (`run_crawl(order=...)`, `_crawl_pages_parallel`)
3. CLI flag + data-only default; CLI test; README

## Done criteria

- T16 acceptance criteria pass
- `uv run ruff check src tests && uv run mypy && uv run pytest` pass (pre-existing
  `browser_scripts.py` E501 and `tests/test_gui_support.py` mypy errors excepted)
- README documents the three orders and the data-only default

## Verification plan

- `uv run pytest`, `uv run ruff check src tests`, `uv run mypy`
- No crawls against `output/` (live crawls and a slim pass are writing there)

## Notes

- Requested 2026-11-01: section-first ordering fetches every `/for-sale/...` results page
  before any `/details/<id>` listing page; one portal had 20,708 results pages saved and 2
  listing pages after five hours. The consumer wants listings to arrive progressively.

## Outcome

- Done 2026-11-01. `--order section|discovered|interleave`; section stays the default,
  data-only crawls default to interleave. 158 tests pass. Not measured on a live portal
  (no crawls against `output/`).

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-9.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
