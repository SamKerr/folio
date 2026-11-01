# T17-error-pages

## Context

- A portal answered 1,588 listing requests with its own HTTP 500 page (a Next.js page whose
  `__NEXT_DATA__` has `"page": "/otm-errors/500"`). `_save_page` saved each one (page and
  sidecar) as if it were the listing; resume skips any URL whose file exists, so those
  listings would never be fetched again. The consumer had to find and delete them by hand.

## Scope

- Detect error pages during the crawl and never save them; count them; retry them once at the
  end of the crawl; a `slim --drop-errors` clean-up for already-saved ones
- Not: the GUI, `crawl_runner.py`, the saved file format, link discovery or ordering

## Implementation plan (required before coding)

### Planned approach

1. New `src/folio/error_pages.py`:
   - `DEFAULT_ERROR_PATHS = ("/otm-errors/", "/error", "/404", "/500")`,
     `DEFAULT_ERROR_TITLES = ("Just a moment...", "Access denied", "Attention Required",
     "captcha")`, `ErrorRules(paths, titles)` with `ErrorRules.build(extra)`: an extra pattern
     starting with `/` is a path pattern, anything else a title marker.
   - Path patterns match whole path segments (case-insensitive; a segment's extension is
     ignored), so `/404` matches `/404` or `/404.html` but not `/properties/40412`, and
     `/error` does not match `/otm-errors/...`.
   - `status_reason(status)` (`HTTP 500` when >= 400), `url_reason(url)` (final URL path),
     `html_reason(html)` (`<title>` substring, case-insensitive; `__NEXT_DATA__.page` against
     the path patterns), `sidecar_reason(text)` (`__NEXT_DATA__` in `json_scripts` /
     `inline_scripts`).
2. `navigation.py`: `goto_page` returns `NavigationResult(ok, status, url)` (truthy when the
   page loaded) carrying the final response's status and URL; callers using it as a bool keep
   working.
3. `crawler.py` `_save_page(error_rules=...)`: after `goto_page`, a status >= 400 or an error
   final URL returns `None` before anything is written; the HTML checks run on the raw HTML
   before the sidecar is written (data-only / data-sidecar) or on the mirrored HTML before the
   page is written (full render). Logs `Skipped (<reason>): <url>`.
4. `_crawl_pages_parallel(retry_failed=1, retry_delay=5.0)`: any URL that is not saved
   (error page, timeout, mirror failure, exception) is held back; when the queue is empty and
   no tab is busy the held-back URLs are re-queued (after `retry_delay`), up to `retry_failed`
   rounds; a URL that still fails is counted in `CrawlResult.pages_failed`. A `--max-pages`
   stop counts held-back URLs as failed without retrying.
5. `slim.py` `drop_error_pages(root, rules, dry_run)`: pages (plain / `.gz`) whose HTML or
   sidecar is an error page lose both files; an orphan error sidecar is removed too; `_assets`
   is never visited.
6. `cli.py`: `crawl --error-marker / --retry-failed / --retry-delay`; the completion line
   reports failed pages; `slim --drop-errors [--dry-run] [--error-marker]`.
7. Tests (no network), README "Error pages".

### Files to touch

- `src/folio/error_pages.py` (new), `src/folio/navigation.py`, `src/folio/crawler.py`,
  `src/folio/slim.py`, `src/folio/cli.py`
- `tests/test_error_pages.py` (new), `tests/test_navigation.py`
- `README.md`, sprint records

### Data and API impact

- Schema/migration changes: none (saved file format unchanged).
- API changes: `goto_page` returns `NavigationResult` (truthy / falsy like the old bool);
  `run_crawl(error_markers=, retry_failed=, retry_delay=)`; `CrawlResult.pages_failed`
  (defaulted, last field).
- State management changes: none.

### Risks and mitigations

- Risk: a path pattern drops a real page (e.g. a listing id starting `404`).
  Mitigation: whole-segment matching, tested.
- Risk: a body marker drops a real page (a title mentioning "captcha").
  Mitigation: title only (not the body), status stays primary; documented.
- Risk: the retry loop never ends or exits early. Mitigation: bounded rounds; the re-queuing
  tab counts itself in flight while it sleeps so other tabs do not exit; tested.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_error_pages.py tests/test_navigation.py
  tests/test_cli.py tests/test_crawler.py`, then the full gate.
- Manual: none against live sites (live crawls are writing to `output/`).

## Acceptance criteria

- [x] A navigation answered with HTTP 500 saves no page or sidecar, logs
      `Skipped (HTTP 500): <url>` and counts in `pages_failed`
- [x] A redirect to `/otm-errors/500` is not saved
- [x] A 200 page whose `<title>` is a challenge / error marker is not saved
- [x] A failed URL is re-queued once at the end, then counted as failed; a URL that succeeds on
      retry is saved and not counted
- [x] `slim --drop-errors` removes saved error pages (plain and `.gz`) with their sidecars,
      keeps normal pages and `_assets`; `--dry-run` deletes nothing
- [x] CLI plumbing for `--error-marker`, `--retry-failed`, `--retry-delay`, `slim --drop-errors`
- [x] README "Error pages" paragraph

## Implementation notes (during/after execution)

- `src/folio/error_pages.py`: `ErrorRules` (paths, titles; `build(extra)` sorts `--error-marker`
  patterns by a leading `/`), `path_matches` (whole segments, case-insensitive, extension
  ignored), `status_reason`, `url_reason`, `title_reason`, `html_reason` (title + Next.js
  `__NEXT_DATA__.page`), `sidecar_reason`.
- `navigation.py`: `goto_page` returns `NavigationResult(ok, status, url)` (truthy like the old
  bool); status / URL come from the final response (`page.url` as a fallback for the URL).
- `crawler.py` `_save_page`: status / final-URL check right after navigation; HTML check on the
  raw HTML before the sidecar is written (data-only and `--data-sidecar`), or on the mirrored
  HTML before the page is written (full render; asset files mirrored before that check stay in
  `_assets`). `_navigation_reason` ignores a bare `True` from stubbed navigations (existing
  tests patch `goto_page` with `return_value=True`).
- Retry: any URL not saved (error page, timeout, mirror failure, exception) is recorded; up to
  `retry_failed` times it is held back, otherwise counted in `pages_failed`. When the queue is
  empty and no tab is busy, one tab takes the held-back batch, counts itself in flight, sleeps
  `retry_delay`, removes the URLs from `visited` and re-queues them (bypassing include/exclude,
  which they passed already). `worker_done` waits while retries are pending (unless a
  `--max-pages` stop, after which held-back URLs are counted failed).
- `slim.py` `drop_error_pages`: pages whose HTML or sidecar is an error page lose both files;
  orphan error sidecars are removed too; `--dry-run` only reports. `--drop-errors` does not slim.
- CLI: `crawl --error-marker / --retry-failed / --retry-delay`; the completion line is followed
  by `N page(s) failed ...` when any failed; `slim --drop-errors [--dry-run] [--error-marker]`.
- Tests: `tests/test_error_pages.py` (36 tests). Gate: ruff only the 3 pre-existing E501 in
  `browser_scripts.py`; mypy only the 4 pre-existing errors in `tests/test_gui_support.py`;
  `ruff format --check` only the 4 pre-existing unformatted test files; pytest 194 passed.
  No live crawl or slim run.

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
4. Move this file to `sprints/tickets/done/T17-error-pages.md`.
