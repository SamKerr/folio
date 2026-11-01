# T15-fast-data-only

## Context

- Data-only crawls (T14) still render every page as if for an offline mirror: images, fonts,
  stylesheets, third-party analytics / A/B scripts (one portal injects a 400 KB VWO script
  per page) and maps load, and `prepare_page` clicks chevrons, scrolls, waits for images,
  diagrams and a quiet asset network. With 8 crawls in parallel each Chromium sat at
  60-120% CPU and the machine managed ~30 pages a minute. T14 listed this as the follow-up.

## Scope

- Data-only crawls: request blocking, no render waits, short marker wait, lower timeouts;
  `--full-render`, `--allow-host`, `--wait-for-marker`, `--marker-timeout-ms`, `--stats`
- Not: the GUI, full-mirror crawls (unchanged), the saved snapshot / sidecar format

## Implementation plan (required before coding)

### Planned approach

1. `capture.py`:
   - `site_domain(host)` (host without a leading `www.`) and
     `request_allowed(resource_type, url, *, site_host, allow_hosts, main_frame_navigation)`:
     `data:` / `blob:` allowed; a main-frame navigation is always allowed (redirects);
     `image`, `media`, `font`, `stylesheet`, `websocket`, `manifest`, `texttrack`, `other`,
     `ping` are aborted on every host; a host is "same site" when it equals the site domain or
     is a subdomain of it, or matches an `--allow-host` pattern (glob, or the host / a
     subdomain of it); same-site requests of the remaining types (`document`, `script`, `xhr`,
     `fetch`, `eventsource`, ...) continue, everything third-party is aborted.
   - `install_data_request_filter(page, root_url, allow_hosts)` routes `**/*` through it.
   - `wait_for_data_marker(page, markers, timeout_ms, poll_ms=100)`: polls an in-page check
     (any `<script>` text containing a marker; also reports `document.readyState`) and
     returns as soon as a marker is present, or the document is `complete` with none (a page
     without page state should not pay the full timeout), or the timeout passes.
   - `prepare_data_page(page, settle_ms, markers, marker_timeout_ms)`: marker wait + settle.
2. `navigation.py`: `goto_page(..., fallback_commit=True)`; data-only passes `False` so a
   timed-out page is skipped (and retried on resume) rather than saved half-loaded.
3. `crawler.py`: `run_crawl(full_render=False, allow_hosts=(), marker_patterns=(),
   marker_timeout_ms=3000)`; fast mode = `data_only and not full_render`: block service
   workers in the context, install the request filter instead of `block_media_requests`,
   don't attach `NetworkCapture` / `AssetQuietTracker` listeners, `_save_page` does
   `goto_page` (no commit fallback) -> `prepare_data_page` -> `extract_links`. Time the crawl
   phase and each fetched page; `CrawlResult` gains `crawl_seconds` and `page_seconds`
   (defaults 0.0).
4. `cli.py`: `--full-render`, `--allow-host` (repeatable), `--wait-for-marker` (repeatable;
   default the built-in markers plus `--data-marker`), `--marker-timeout-ms` (3000; 0 skips),
   `--stats`. `--settle-ms` and `--timeout` default to None and resolve to 300 ms / 30 s in
   fast data-only mode, 1000 ms / 60 s otherwise.
5. Tests, README, measurement.

### Files to touch

- `src/folio/capture.py`, `src/folio/browser_scripts.py` (marker check script),
  `src/folio/navigation.py`, `src/folio/crawler.py`, `src/folio/cli.py`
- `tests/test_fast_data_only.py` (new), `tests/test_cli.py`, `tests/test_navigation.py`
- `README.md`, sprint records

### Data and API impact

- Schema/migration changes: none; saved files are unchanged.
- API changes: new keyword args with defaults; `CrawlResult` gets two defaulted fields.
- State management changes: none.

### Risks and mitigations

- Risk: a site loads its listing data from a CDN / API host on another domain.
  Mitigation: `--allow-host`; `--full-render` as the escape hatch; documented.
- Risk: a page injects its state late and the snapshot misses it.
  Mitigation: marker wait (3 s cap, configurable); same-site scripts still run.
- Risk: blocking stylesheets changes layout-dependent scripts.
  Mitigation: only data is kept; the reduced snapshot drops styles anyway.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_fast_data_only.py tests/test_cli.py
  tests/test_navigation.py tests/test_data_only.py`, then the full gate.
- Manual: `folio crawl https://books.toscrape.com/ --data-only --headless --skip-login-wait
  --max-pages 20 --concurrency 2 --delay 0` to a temp folder, before and after, sampling
  Chromium CPU with `ps`.

## Acceptance criteria

- [x] Data-only aborts image / media / font / stylesheet / websocket / manifest / texttrack /
      other / ping requests and all third-party hosts; same-site document / script / xhr /
      fetch load; `--allow-host` extends the site
- [x] Data-only skips chevron clicks, scrolling, image / diagram / asset-quiet waits; waits for
      `domcontentloaded` + settle + marker (capped); still writes snapshot + sidecar
- [x] Data-only defaults: 30 s timeout, 300 ms settle, no commit fallback; `--full-render`
      restores the previous behaviour
- [x] `--stats` prints pages per minute and seconds per page
- [x] Before / after measurement recorded below
- [x] README updated

## Implementation notes (during/after execution)

- `capture.py`: `BLOCKED_DATA_RESOURCE_TYPES`, `site_domain`, `request_allowed`,
  `install_data_request_filter`, `wait_for_data_marker`, `prepare_data_page`, data-only
  default constants. `browser_scripts.py`: `CHECK_DATA_MARKERS` (registered for the Node
  syntax check). `navigation.py`: `goto_page(fallback_commit=)`.
- `crawler.py`: `FastDataOptions`; fast mode blocks service workers, installs the request
  filter instead of `block_media_requests`, attaches no `NetworkCapture` /
  `AssetQuietTracker` listeners, and `_save_page` does `goto_page` (no commit fallback) ->
  `prepare_data_page` -> `extract_links`. `CrawlResult.crawl_seconds` / `page_seconds`.
- `cli.py`: `--full-render`, `--allow-host`, `--wait-for-marker`, `--marker-timeout-ms`,
  `--stats`; `--settle-ms` / `--timeout` default to None and resolve to 300 ms / 30 s in fast
  data-only mode, 1000 ms / 60 s otherwise (normal crawls unchanged).
- Choices beyond the brief: "same site" is the start host minus a leading `www.` plus
  subdomains (so `api.` / `static.` hosts of the portal load); main-frame navigations always
  load (redirects); `ping` is blocked too; the marker wait also ends when the page reaches
  `readyState == "complete"` without a marker, so marker-less pages don't pay 3 s each;
  `--allow-host` does not unblock image / font / CSS types.
- The T14 data-only crawl test now patches `prepare_data_page` / `extract_links` and asserts
  `prepare_page` is not called.
- Measurement (books.toscrape.com, `--data-only --headless --skip-login-wait --max-pages 20
  --concurrency 2 --delay 0`, temp folder; machine load average 36-48 from the live crawls,
  so absolute numbers are noisy). Each run saved 21 pages (one over the cap: concurrency).
  "Process wall" is the whole `folio crawl` process incl. uv / browser start; "CPU time" is
  the summed `ps` CPU time of the crawl's child processes (Python, driver, Chromium), max
  seen before exit.

  | Run | Crawl phase | pages/min | s/page wall | s/page per tab | process wall | CPU time | peak RSS |
  |---|---|---|---|---|---|---|---|
  | before (pre-T15 code) #1 | n/a | n/a | n/a | n/a | 39.9 s | n/a | 784 MB |
  | before (pre-T15 code) #2 | n/a | n/a | n/a | n/a | 47.5 s | n/a | 746 MB |
  | `--full-render` #1 | 50.0 s | 25.2 | 2.38 | 4.34 | 53.3 s | 8.1 s | 732 MB |
  | `--full-render` #2 | 38.4 s | 32.8 | 1.83 | 3.45 | 41.3 s | 7.5 s | 767 MB |
  | fast #1 | 16.3 s | 77.4 | 0.78 | 1.48 | 21.9 s | n/a | 702 MB |
  | fast #2 | 15.9 s | 79.3 | 0.76 | 1.40 | 21.4 s | n/a | 714 MB |
  | fast #3 | 14.6 s | 86.5 | 0.69 | 1.25 | 19.8 s | 4.8 s | 712 MB |
  | fast #4 | 13.4 s | 93.8 | 0.64 | 1.16 | 19.3 s | 4.9 s | 714 MB |

  `--full-render` is the pre-T15 code path (its process wall matches the two pre-T15 runs).
  Fast data-only: ~3x the pages per minute, ~40% less CPU time for the run; RSS barely moves
  (browser baseline). The 40 files both modes saved were byte-identical. books.toscrape.com
  is a light static site (no third-party scripts, small images); the saving on the property
  portals (VWO, analytics, maps, many images) should be larger, but was not measured here
  (no crawl against them or the live `output/` folders).
- Gate: ruff only the 3 pre-existing E501 in `browser_scripts.py`; mypy only the 4
  pre-existing errors in `tests/test_gui_support.py`; pytest 141 passed.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check src tests`
- [x] `uv run mypy`
- [x] Manual: before / after crawl of books.toscrape.com to a temp folder

## Status

- Owner: Claude (subagent, money-maker session)
- State: Done (2026-11-01)

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T15-fast-data-only.md`.
