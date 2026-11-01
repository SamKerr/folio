# Sprint 11 - Back off on rate limits

## Scope

- On HTTP 429 (or 503 with a `Retry-After` header) the crawl enters a cool-down: every tab
  pauses for `Retry-After` seconds (capped at `--max-backoff`, default 300) or, without the
  header, an exponential back-off from `--backoff` (default 30 s) doubling per consecutive
  rate-limited cool-down up to the cap; the URL goes back on the queue (not the end-of-run
  retry list) up to `--retry-failed` times before counting as failed; a saved page resets the
  back-off; one log line per pause
- `--adaptive` / `--no-adaptive` (default on in `--data-only`): each cool-down adds
  `--adaptive-step` (default 1.0 s) to the per-page delay for the rest of the run; the final
  delay is printed in the `--stats` summary
- Tests (no network), README "Rate limits"
- Out of scope: the GUI / `crawl_runner.py`; cross-process coordination between separate
  crawls; running against `output/`

## Tickets

- [x] `T18-rate-limit-backoff`

## Sequencing

1. `rate_limit.py` (Retry-After parsing, pause rule) + `NavigationResult.retry_after`
2. Cool-down gate, re-queue and adaptive delay in `_crawl_pages_parallel`; `CrawlResult` fields
3. CLI flags, `--stats` line, tests, README

## Done criteria

- T18 acceptance criteria pass
- `uv run ruff check src tests && uv run mypy && uv run pytest` pass (pre-existing
  `browser_scripts.py` E501 and `tests/test_gui_support.py` mypy errors excepted)
- README documents the back-off rules and `--adaptive`

## Verification plan

- `uv run pytest`, `uv run ruff check src tests`, `uv run mypy`
- No crawls or slim runs against `output/` (live crawls are writing there)

## Notes

- Requested 2026-11-01: a portal answered 1,363 of ~3,500 requests with HTTP 429 within ten
  minutes while six crawls each ran two tabs against it. T17 skips such pages and retries once
  at the end, but a crawl that keeps going through a 429 storm wastes the run and risks a
  longer block.

## Outcome

- Done 2026-11-01. HTTP 429 / 503 + `Retry-After` pauses every tab of the crawl
  (`Retry-After` capped at `--max-backoff`, else `--backoff` doubling per consecutive pause up
  to the cap), re-queues the URL up to `--retry-failed` times, and resets on a saved page;
  `--adaptive` (default in data-only) adds `--adaptive-step` to the per-page delay per pause;
  `--stats` prints the final delay. 215 tests pass. Not exercised on a live portal; the
  cool-down does not coordinate across separate crawl processes.

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-11.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
