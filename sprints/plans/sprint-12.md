# Sprint 12 - Modern desktop UI (Vue)

## Scope

- Replace the Tkinter GUI as the default `folio gui` with a local web UI built with Vue 3
  (vendored ESM build, no Node/build step), shown in a native window via pywebview
- Local Python HTTP server (stdlib) serving the UI, a token-protected JSON API and a
  server-sent-events log stream; it reuses `CrawlSettings`, `build_crawl_argv`,
  `list_saved_sites` and `PreviewServer`
- New layout: sidebar (New crawl / Library), hero URL field, capture-quality segmented
  control, speed + folder cards, collapsible advanced timings; a live run view (status,
  login banner, stat tiles, current URL, collapsible log); a library card grid with search
- Light and dark theme (follows the system), purple/gold brand accent
- `folio gui --browser` opens the same UI in the default browser; `folio gui --classic`
  keeps the Tk GUI for now
- Out of scope: new crawl options in the GUI beyond what the Tk GUI offers; removing the
  Tk GUI; Node/Vite tooling

## Tickets

- [x] `T19-webui-backend`
- [x] `T20-webui-frontend`
- [ ] `T21-desktop-window`

## Sequencing

1. T19: crawl session + API server (testable without a UI)
2. T20: Vue UI against the T19 API (verified in the browser)
3. T21: pywebview window, CLI flags, macOS app, README

## Done criteria

- All in-scope tickets marked complete
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` pass
- `folio gui` opens the new UI; a crawl can be started, continued after login, stopped;
  the library lists and opens saved sites
- README updated (GUI section, screenshot note)

## Verification plan

- `uv run pytest && uv run ruff check . && uv run mypy`
- Manual: `uv run folio gui --browser` and `uv run folio gui` flows on macOS

## Notes

- Vue is vendored (not CDN) so the UI works offline.
- The API spawns processes, so it binds 127.0.0.1 only, checks the Host header and
  requires a per-launch token on every API call (blocks other web pages / DNS rebinding).

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-12.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
