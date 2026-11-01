# Sprint 8 - Fast data-only crawls

## Scope

- Make `--data-only` crawls cheap: block requests that carry no data (images, media, fonts,
  stylesheets, websockets, manifests, text tracks, `other`, pings, and every third-party host),
  keeping same-site `document` / `script` / `xhr` / `fetch` so page-state scripts still run
- Skip the render waits in data-only mode (chevron clicks, scrolling, image / diagram waits,
  asset-quiet wait); wait for `domcontentloaded`, a short settle and, briefly, a page-state
  marker instead; plain `a[href]` + `link[rel=next|prev]` link discovery
- Data-only defaults: 30 s navigation timeout, 300 ms settle; `--full-render` restores today's
  waits; `--allow-host`, `--wait-for-marker`, `--marker-timeout-ms`, `--stats`
- Tests (synthetic, no network), README, a before / after measurement on books.toscrape.com
- Out of scope: the GUI; normal (full mirror) crawls; the saved file format

## Tickets

- [x] `T15-fast-data-only`

## Sequencing

1. Request-routing decision + route installer; marker wait helper (`capture.py`)
2. Crawler wiring (fast path in `_save_page`, timing stats); `goto_page` option
3. CLI flags + data-only defaults; tests; README; measurement

## Done criteria

- T15 acceptance criteria pass
- `uv run ruff check src tests && uv run mypy && uv run pytest` pass (pre-existing
  `browser_scripts.py` E501 and `tests/test_gui_support.py` mypy errors excepted)
- README "Data-only crawls" documents what is blocked, `--full-render`, `--allow-host`, the
  marker wait and `--stats`

## Verification plan

- `uv run pytest`, `uv run ruff check src tests`, `uv run mypy`
- 20-page crawl of https://books.toscrape.com/ before and after, to a temp folder (never
  `output/`, where live crawls are writing)

## Notes

- Requested 2026-10-31: 8 parallel data-only portal crawls on one Mac ran each Chromium at
  60-120% CPU / ~700 MB, load average ~50, ~30 pages a minute in total.

## Outcome

- Done 2026-11-01. books.toscrape.com, 20 pages, concurrency 2: fast data-only 77-94
  pages/min (0.64-0.78 s/page wall) vs 25-33 pages/min (1.83-2.38 s/page) with
  `--full-render` (= the old path); ~40% less CPU time; identical saved files. 141 tests pass.

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-8.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
