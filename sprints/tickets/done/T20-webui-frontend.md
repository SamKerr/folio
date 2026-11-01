# T20-webui-frontend

## Context

- The Tk UI looks dated. Build a modern Vue 3 UI on the T19 API.

## Scope

- `src/folio/webui/static/`: `index.html`, `styles.css`, `app.js` (Vue components as ES
  modules), `vendor/vue.esm-browser.prod.js` (vendored Vue 3.5.13), `folio.png` reuse
- Screens: New crawl (form), Run (live progress), Library (cards)
- Not in scope: new crawl options beyond the Tk GUI's set

## Implementation plan (required before coding)

### Planned approach

1. Vendor Vue ESM build; `index.html` with import map, token injected by server.
2. Layout: sidebar (brand, New crawl, Library + count, status dot + output folder),
   main area. Design tokens on `:root` with dark mode via `prefers-color-scheme`.
3. New crawl: hero URL input + Start button; preset segmented control
   (Fast/Balanced/Thorough/Custom) with description; cards for "Save to" (path + Browse
   when supported) and "Speed" (parallel pages/assets, max pages, re-fetch switch);
   exclude paths textarea; collapsible Advanced timings (auto-open on Custom; editing a
   timing switches to Custom). Inline field errors from the 400 response.
4. Run view (replaces the form while a crawl is active/finished): host + status pill,
   login banner with "I've logged in — continue", stat tiles (fetched, already saved,
   errors, elapsed), current URL, Stop; collapsible log (auto-scroll); finished card with
   "Open site" and "New crawl".
5. Library: search, refresh, card grid (letter avatar, host, pages, relative time, Open,
   Re-crawl), empty state.
6. SSE client with reconnect; remember last form values in localStorage (try/catch).

### Files to touch

- `src/folio/webui/static/*` (new), `pyproject.toml` (package data)

### Data and API impact

- Schema/migration changes: none
- API/RPC/edge function changes: consumes T19 API
- State management changes: Vue reactive store in `app.js`

### Risks and mitigations

- Risk: offline use breaks with CDN assets. Mitigation: vendor Vue, system fonts only.
- Risk: WKWebView quirks. Mitigation: plain ES modules, no bleeding-edge CSS required.

### Verification plan (ticket-specific)

- Automated: test that static files exist and are packaged; server serves index with token.
- Manual: `uv run folio gui --browser` — start crawl of a local test site, see progress,
  continue after login, stop, finished card, library open; check light + dark; narrow window.

## Acceptance criteria

- [x] All three screens work end to end against the real crawler
- [x] Validation errors show inline next to the field
- [x] Light and dark themes both readable
- [x] Works fully offline

## Implementation notes (during/after execution)

- Vue 3.5.13 vendored at `static/vendor/`; components are template strings in `app.js`
  (the ESM browser build includes the template compiler).
- The logo is served from `folio/assets/folio.png` (not duplicated into `static/`).
- Start URLs without a scheme get `http://` for localhost/127.x, otherwise `https://`.
- Default URL/excludes are now empty with placeholders (Tk pre-filled example values).
- Verified headless with Playwright against a local test site: inline validation, Custom
  preset switch, login banner → continue → finished, stop, library open/update, light and
  dark, 390px width (no horizontal scroll), no console errors.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check .`
- [x] `uv run mypy`
- [x] Manual checks for crawl, run and library flows

## Status

- Owner: Claude
- State: Done
