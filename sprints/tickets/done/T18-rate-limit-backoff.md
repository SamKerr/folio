# T18-rate-limit-backoff

## Context

- A portal answered 1,363 of ~3,500 requests with HTTP 429 within ten minutes (six crawls, two
  tabs each). T17 treats a 429 like any error page (skip, retry once at the end), so the crawl
  keeps hammering through the storm. Folio should slow down when told to.

## Scope

- Cool-down on 429 / 503 + `Retry-After`, re-queue, exponential back-off, reset on success,
  adaptive per-page delay, CLI flags, `--stats` final delay, tests, README
- Not: the GUI, `crawl_runner.py`, error-page detection rules, coordination across processes

## Implementation plan (required before coding)

### Planned approach

1. New `src/folio/rate_limit.py`: `DEFAULT_BACKOFF_SECONDS = 30.0`,
   `DEFAULT_MAX_BACKOFF_SECONDS = 300.0`, `DEFAULT_ADAPTIVE_STEP_SECONDS = 1.0`;
   `parse_retry_after(value)` (delta-seconds or HTTP-date, `None` if unparseable);
   `is_rate_limited(status, retry_after)` (429, or 503 with a header);
   `backoff_seconds(consecutive, retry_after, base, cap)`; `RateLimitedError(url, status,
   retry_after)`.
2. `navigation.py`: `NavigationResult.retry_after` from the final response's `Retry-After`
   header (Playwright's lower-cased `response.headers`).
3. `crawler.py` `_save_page`: right after navigation, a rate-limited response raises
   `RateLimitedError` (nothing written) before the error-page checks.
4. `_crawl_pages_parallel`: an `asyncio.Event` gate (set = open). Every tab waits on the gate
   before fetching a page. On `RateLimitedError` the URL is removed from `visited` and put back
   on the queue (up to `retry_failed` re-queues for that URL, else counted failed). If no
   cool-down is running, that tab starts one: consecutive += 1, pause =
   `backoff_seconds(...)`, log `Rate limited (HTTP 429): pausing N s`, clear the gate,
   `asyncio.sleep(pause)`, set the gate; with adaptive on, the per-page delay grows by
   `adaptive_step`. A 429 arriving while a cool-down runs (a request already in flight) only
   re-queues. A saved page resets consecutive to 0. The pausing tab counts itself in flight
   so other tabs do not exit.
5. `run_crawl(backoff=, max_backoff=, adaptive=None, adaptive_step=)`: `adaptive=None` means
   on for data-only; `CrawlResult.final_delay`, `CrawlResult.rate_limit_pauses`.
6. `cli.py`: `--backoff`, `--max-backoff`, `--adaptive/--no-adaptive`, `--adaptive-step`;
   negative values rejected; `format_crawl_stats` appends the final delay and pause count.
7. Tests (no network) in `tests/test_rate_limit.py`; README "Rate limits".

### Files to touch

- `src/folio/rate_limit.py` (new), `src/folio/navigation.py`, `src/folio/crawler.py`,
  `src/folio/cli.py`
- `tests/test_rate_limit.py` (new); `tests/test_fast_data_only.py` if the stats line changes
- `README.md`, sprint records

### Data and API impact

- Schema/migration changes: none (saved file format unchanged).
- API changes: `NavigationResult.retry_after` (defaulted); `run_crawl(backoff=,
  max_backoff=, adaptive=, adaptive_step=)`; `CrawlResult.final_delay`,
  `CrawlResult.rate_limit_pauses` (defaulted, last fields).
- State management changes: none.

### Risks and mitigations

- Risk: tabs exit while one tab sleeps through a cool-down with an empty queue.
  Mitigation: the URL is re-queued before the pause and the pausing tab is in flight; tested.
- Risk: patched `asyncio.sleep` in tests makes a time-based cool-down spin.
  Mitigation: the gate is an `asyncio.Event`, not a deadline.
- Risk: a huge `Retry-After` stalls the crawl. Mitigation: capped at `--max-backoff`.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_rate_limit.py tests/test_error_pages.py
  tests/test_cli.py tests/test_fast_data_only.py`, then the full gate.
- Manual: none against live sites (live crawls are writing to `output/`).

## Acceptance criteria

- [x] A 429 with `Retry-After: 7` pauses 7 s (one log line), re-queues the URL, and the
      second attempt saves it; it is not on the end-of-run retry list
- [x] Consecutive 429s without the header pause `backoff`, `2 x backoff`, ... up to the cap;
      `Retry-After` is capped at `--max-backoff`
- [x] A saved page resets the back-off
- [x] A 503 with `Retry-After` is a rate limit; a 503 without one stays an error page
- [x] A URL rate-limited more than `--retry-failed` times counts as failed
- [x] Adaptive (default in data-only) raises the per-page delay by `--adaptive-step` per
      cool-down; `--no-adaptive` keeps it; `--stats` prints the final delay
- [x] CLI plumbing for `--backoff`, `--max-backoff`, `--adaptive/--no-adaptive`,
      `--adaptive-step`
- [x] README "Rate limits" paragraph

## Implementation notes (during/after execution)

- `src/folio/rate_limit.py`: `parse_retry_after` (delta-seconds or HTTP-date, never
  negative, `None` if unparseable / non-finite), `is_rate_limited` (429, or 503 with a
  header), `backoff_seconds(consecutive, retry_after, base, cap)`, `RateLimitedError`.
- `navigation.py`: `NavigationResult.retry_after` from the final response's `headers` dict.
- `crawler.py`: `_save_page` raises `RateLimitedError` right after navigation (before the
  error-page checks; nothing written). `_crawl_pages_parallel` keeps an `asyncio.Event` gate;
  every tab waits on it before fetching a page (resume skips do not wait). On a rate limit the
  URL leaves `visited` and goes back on the queue via `ordering.key` (counted per URL against
  `retry_failed`, separately from the T17 end-of-run attempts; beyond it the URL is counted in
  `pages_failed`). If the gate is open the tab starts the cool-down (consecutive += 1, pause
  from `backoff_seconds`, one `Rate limited (HTTP N): pausing N s` line, adaptive step added,
  gate closed for `asyncio.sleep(pause)`); a 429 that lands while the gate is closed only
  re-queues. The pausing tab is still in flight, so other tabs do not exit. A saved page
  resets consecutive to 0. The per-page delay after a saved page is now the adaptive
  `page_delay` (starts at `--delay`).
- `run_crawl(backoff=30, max_backoff=300, adaptive=None, adaptive_step=1.0)`; `adaptive=None`
  means on for data-only; negatives raise `ValueError`. `CrawlResult.final_delay`,
  `CrawlResult.rate_limit_pauses`.
- CLI: `--backoff`, `--max-backoff`, `--adaptive/--no-adaptive` (argparse
  `BooleanOptionalAction`, default `None`), `--adaptive-step`; negatives rejected;
  `format_crawl_stats` appends `; final delay N s/page, N rate-limit pause(s)`.
- Tests: `tests/test_rate_limit.py` (21 tests; `asyncio.sleep` patched to record pauses >=
  0.1 s and yield). Gate: ruff only the 3 pre-existing E501 in `browser_scripts.py`; mypy only
  the 4 pre-existing errors in `tests/test_gui_support.py`; `ruff format --check` only the 4
  pre-existing unformatted test files; pytest 215 passed. No live crawl.
- Limit: the cool-down is per crawl process; parallel crawls against one site do not share it.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check src tests`
- [x] `uv run mypy`

## Status

- Owner: Claude (subagent, money-maker session)
- State: Done (2026-11-01)

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T18-rate-limit-backoff.md`.
