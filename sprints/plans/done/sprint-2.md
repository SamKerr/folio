# Sprint 2 - Interactive login and same-domain crawl

## Scope

- `folio crawl <url>` opens a headed Chromium window on the target URL
- User logs in manually, then confirms via Enter in the terminal to start crawling
- BFS crawl of all discoverable same-host pages via `<a href>` links
- Save rendered HTML under `output/<host>/…` mirroring URL paths
- Rate limiting between page fetches
- Unit tests with mocked Playwright (no live network in CI)

## Out of scope

- Automated login / credential storage
- Cross-domain or subdomain expansion (e.g. `www` vs apex treated as different hosts)
- Binary asset downloads (images, PDFs)
- `robots.txt` enforcement
- CI against live example.com (manual verification only)

## Tickets

- [x] `T04-url-utils`
- [x] `T05-crawler-engine`
- [x] `T06-crawl-cli-and-docs`

## Sequencing

1. T04 — URL normalization, same-domain check, output path mapping
2. T05 — Playwright session, login pause, link discovery, HTML persistence (depends on T04)
3. T06 — `crawl` subcommand, README, `.gitignore` (depends on T05)

## Done criteria

- All in-scope tickets marked complete
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` pass
- Manual: `folio crawl https://www.example.com/` opens browser, waits for Enter, crawls same-domain pages to `output/`

## Verification plan

- `uv run pytest`
- `uv run ruff check .`
- `uv run mypy`
- Manual crawl against https://www.example.com/ after login

## Notes

- Delivered `folio crawl` with headed login pause, BFS same-host crawl, HTML output under `output/<host>/`
- Manual example.com verification left to user (requires real login)
- Default delay 0.5s; use `--max-pages` while testing

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-2.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
