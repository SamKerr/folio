# T16-crawl-order

## Context

- `_crawl_pages_parallel` keys its single `asyncio.PriorityQueue` by
  `(section_rank, depth, order, url)`: every URL of the first-seen path section is fetched
  before any URL of a later section. On a listings portal the results pages (`/for-sale/...`)
  all come before the listing pages (`/details/<id>`), so listings never arrive until the
  results are exhausted (20,708 results pages vs 2 listings after five hours on one portal).

## Scope

- `--order section|discovered|interleave`; default `section` (unchanged); `interleave` by
  default with `--data-only` unless `--order` is given
- Not: the GUI, link discovery, resume / visited handling, file format

## Implementation plan (required before coding)

### Planned approach

1. New `src/folio/ordering.py`: `CRAWL_ORDERS`, `CrawlOrder` (literal type) and
   `QueueOrdering(order)` with `key(url, *, seed=False) -> tuple[int, int, int, int]`
   (a monotonically increasing discovery counter is the last element, so keys are unique):
   - `section`: `(0, section_rank, depth, order)` - exactly today's order.
   - `discovered`: `(0 if seed else 1, 0, 0, order)` - plain FIFO by discovery.
   - `interleave`: `(0 if seed else 1, n, 0, order)` where `n` is the number of URLs already
     queued in that URL's section (first URL of a section gets 0, the next 1, ...). With a
     static priority this is the round-robin: the queue serves round 0 of every section,
     then round 1, ..., ties by discovery order; a newly seen section (listings) starts at
     round 0, so it is served ahead of the deeper rounds of a section that has queued many
     URLs (results), and the two then alternate.
   Key computation is synchronous (no await), so it is atomic within the event loop.
2. `crawler.py`: `run_crawl(order="section")` -> `_crawl_with_browser` ->
   `_crawl_pages_parallel(order=...)`; `enqueue_url` uses `QueueOrdering.key`; queue items
   become `(key, url)`. Unknown order raises `ValueError`.
3. `cli.py`: `--order {section,discovered,interleave}` default None; resolves to
   `interleave` when `--data-only`, else `section`; help text says so.
4. Tests: `tests/test_ordering.py` (scripted discovery sequence through `QueueOrdering` +
   `heapq`/`PriorityQueue`, asserted dequeue order per mode; seeds first; unknown order);
   `tests/test_cli.py` plumbing (default section, data-only -> interleave, explicit wins).
5. README "Crawl order" paragraph.

### Files to touch

- `src/folio/ordering.py` (new), `src/folio/crawler.py`, `src/folio/cli.py`
- `tests/test_ordering.py` (new), `tests/test_cli.py`
- `README.md`, sprint records

### Data and API impact

- Schema/migration changes: none.
- API changes: `run_crawl(order=...)` keyword with default `"section"`.
- State management changes: none.

### Risks and mitigations

- Risk: changing the default order for normal crawls surprises existing users.
  Mitigation: default stays `section`; only data-only changes default (documented).
- Risk: interleave uses queued-per-section rounds rather than live fetched counts (a static
  PriorityQueue key cannot change after enqueue). Mitigation: documented; for a portal the
  effect is the same - listings start right after the first results page and then alternate
  with results pages.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_ordering.py tests/test_cli.py tests/test_crawler.py`,
  then the full gate.
- Manual: none against live sites (live crawls are writing to `output/`).

## Acceptance criteria

- [x] `--order section` (default) keeps today's dequeue order; existing crawl tests pass
- [x] `--order discovered` dequeues in plain discovery order
- [x] `--order interleave` round-robins sections, seeds first
- [x] `--data-only` without `--order` uses `interleave`; an explicit `--order` wins
- [x] README "Crawl order" paragraph; `--help` mentions the data-only default

## Implementation notes (during/after execution)

- `src/folio/ordering.py`: `CrawlOrder`, `CRAWL_ORDERS`, `DEFAULT_CRAWL_ORDER` (`section`),
  `DEFAULT_DATA_ONLY_CRAWL_ORDER` (`interleave`), `QueueOrdering.key(url, seed=)` returning
  `(seed_tier, a, b, discovery_counter)`. Section mode returns `(0, section_rank, depth,
  order)`, i.e. the old key with a constant 0 in front, so the old order is unchanged.
- Interleave: `round` = number of distinct URLs already queued in the URL's path section; a URL
  queued again (found on another page) keeps its first round (so duplicate links do not push a
  section back). This is a static stand-in for "fewest fetched so far": a PriorityQueue key
  cannot change after enqueue, and queued-per-section gives the same round-robin.
- `crawler.py`: queue items are `(key, url)`; `run_crawl(order=)` validates the order before
  launching a browser; threaded through `_crawl_with_browser` / `_crawl_pages_parallel`. The
  old `section_lock` / `enqueue_lock` went: the key computation has no await, so it is atomic.
- `cli.py`: `--order {section,discovered,interleave}`, default None -> `interleave` with
  `--data-only`, else `section`.
- Tests: `tests/test_ordering.py` (scripted portal through the crawler's dequeue / visit /
  enqueue loop per mode; distinct-URL rounds; seeds first; unknown order),
  `tests/test_crawler.py` section-order crawl test parametrised over the default and the three
  orders, `tests/test_cli.py` order plumbing (default, data-only default, explicit wins, bad
  choice).
- Gate: ruff only the 3 pre-existing E501 in `browser_scripts.py`; mypy only the 4
  pre-existing errors in `tests/test_gui_support.py`; `ruff format --check` only the 4
  pre-existing unformatted test files (`test_assets.py`, `test_capture.py`, `test_resume.py`,
  `test_static_assets.py`); pytest 158 passed. No live crawl was run.

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
4. Move this file to `sprints/tickets/done/T16-crawl-order.md`.
