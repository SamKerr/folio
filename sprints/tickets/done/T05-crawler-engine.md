# T05-crawler-engine

## Context

After Sprint 1's Playwright smoke check, we need the core crawl loop: open a session, pause for login, then traverse same-domain links and save HTML.

## Scope

- Headed browser session on start URL
- Callable login prompt (default: stdin Enter) before crawling
- BFS crawl using shared browser context (cookies preserved)
- Extract links from `<a href>`, rate limit between requests
- Write HTML files via T04 path mapping

## Implementation plan (required before coding)

### Planned approach

1. Add `folio/crawler.py` with `CrawlResult` and `run_crawl`
2. Login phase: launch browser, `goto` start URL, await prompt
3. Crawl phase: deque BFS, new page per URL, save content, enqueue links
4. Add `tests/test_crawler.py` with mocked Playwright

### Files to touch

- `src/folio/crawler.py`: crawl orchestration
- `tests/test_crawler.py`: mocked crawl tests

### Data and API impact

- None

### Risks and mitigations

- Risk: Infinite crawl on large sites
  Mitigation: optional `--max-pages` limit
- Risk: Playwright hangs on slow pages
  Mitigation: 30s navigation timeout

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_crawler.py`

## Acceptance criteria

- [x] Crawl preserves session after login pause
- [x] Same-host links discovered and visited once
- [x] HTML written to expected output paths
- [x] `skip_login_wait` bypasses prompt for tests

## Verification

- [x] `uv run pytest tests/test_crawler.py`

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T05-crawler-engine.md`.
