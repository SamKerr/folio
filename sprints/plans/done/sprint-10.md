# Sprint 10 - Never save error pages

## Scope

- Crawls never save a page (or sidecar) whose navigation answered HTTP >= 400, whose final URL
  after redirects is an error path, or whose `<title>` / Next.js `__NEXT_DATA__.page` marks it
  as an error / challenge page; such URLs are counted (`pages_failed`) and left unsaved so a
  resumed crawl retries them
- `--error-marker PATTERN` (repeatable) extends the built-in patterns
- `--retry-failed N` (default 1) / `--retry-delay SECONDS` (default 5): failed URLs are
  re-queued after the rest of the crawl before being counted as failed
- `folio slim <dir> --drop-errors [--dry-run]`: delete saved error pages and their sidecars
- Tests (no network), README "Error pages"
- Out of scope: the GUI / `crawl_runner.py`; the saved file format; running against `output/`

## Tickets

- [x] `T17-error-pages`

## Sequencing

1. `error_pages.py` detection rules + unit tests
2. `goto_page` returns the response status / final URL; `_save_page` refuses error pages
3. Retry queue and `pages_failed` in `_crawl_pages_parallel` / `CrawlResult`
4. `slim --drop-errors`; CLI flags; CLI tests; README

## Done criteria

- T17 acceptance criteria pass
- `uv run ruff check src tests && uv run mypy && uv run pytest` pass (pre-existing
  `browser_scripts.py` E501 and `tests/test_gui_support.py` mypy errors excepted)
- README documents the detection rules, retry and `slim --drop-errors`

## Verification plan

- `uv run pytest`, `uv run ruff check src tests`, `uv run mypy`
- No crawls or slim runs against `output/` (live crawls are writing there)

## Notes

- Requested 2026-11-01: a portal answered 1,588 listing requests with its own HTTP 500 page
  (Next.js, `__NEXT_DATA__.page == "/otm-errors/500"`). Folio saved each one with a sidecar,
  and resume skips any URL whose file exists, so those listings would never be re-fetched.

## Outcome

- Done 2026-11-01. Error pages (HTTP >= 400, error final-URL paths, title / `__NEXT_DATA__`
  markers) are never saved and count as `pages_failed`; unsaved URLs are retried once at the
  end of the crawl (`--retry-failed`, `--retry-delay`); `folio slim --drop-errors` cleans up
  old ones. 194 tests pass. Not exercised on a live portal (no crawls against `output/`).

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-10.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
