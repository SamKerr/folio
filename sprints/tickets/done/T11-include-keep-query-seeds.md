# T11-include-keep-query-seeds

## Context

- The user wants to mirror a site subset (a property search and the listings it links to) for
  another project to parse offline. Folio only had `--exclude`, collapsed query URLs onto one
  file, and took a single start URL.

## Scope

- `urls.py`: `is_included_url` (shared matcher with `is_excluded_url`), `url_to_output_path(...,
  keep_query)` → `<name>.q<sha1[:10]>.html`, `output_path_to_url` strips the tag.
- `crawler.py`: `include_patterns`, `keep_query`, `extra_start_urls` threaded through
  `run_crawl` → `_crawl_with_browser` → `_crawl_pages_parallel` → `_save_page`; seeds bypass
  the include filter; saved-HTML link discovery prefers `data-folio-url`.
- `assets.py`: `AssetMirror(keep_query=...)`; rewritten anchors get `data-folio-url`.
- `cli.py`: `url` nargs="+", `--include`, `--keep-query`.

## Implementation plan (required before coding)

### Planned approach

1. URL helpers + tests. 2. Crawler threading + tests with the mocked Playwright. 3. CLI + README.

### Files to touch

- `src/folio/{urls,crawler,assets,cli}.py`, `tests/test_{urls,crawler,cli}.py`, `README.md`.

### Data and API impact

- `run_crawl` gains three keyword arguments with defaults; `AssetMirror` one. Existing
  behaviour unchanged when they are not set.

### Risks and mitigations

- Risk: a query page's exact URL is not recoverable from its file name on resume.
  Mitigation: the mirror writes `data-folio-url` on rewritten anchors; discovery reads it.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_urls.py tests/test_crawler.py tests/test_cli.py`.
- Manual: a bounded crawl of a search page with `--include` / `--keep-query` saves one file per
  results page and only the included listing pages.

## Acceptance criteria

- [x] Include-only crawling with seeds always allowed
- [x] Query-aware file names and exact resume
- [x] Several start URLs; CLI flags; README

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run mypy`
- [x] Manual bounded crawl (see the money-maker Sprint 210 record)

## Status

- Owner: Claude (main session, money-maker)
- State: Done
