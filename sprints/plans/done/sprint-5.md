# Sprint 5 - Desktop GUI polish

## Scope

- Simplify and fix the Crawl tab: grouped settings, dropdowns, capture presets
- Brand the UI with `folio.png` (header emblem, window icon, macOS app icon)
- Full-page scrolling on the Crawl tab with trackpad support
- Keep Library tab behaviour; add list scrolling and stable notebook tabs

## Out of scope

- New crawl features or CLI flags
- Automated GUI screenshot tests

## Tickets

- [x] `T10-gui-simplify`

## Done criteria

- Crawl tab readable at default window size; no clipped controls
- Capture preset and parallelism use dropdowns; Custom reveals advanced timings
- Branded theme, logo, and single scrollable Crawl page with trackpad scrolling
- Tests and lint pass; manual GUI smoke check documented in ticket

## Notes

- **Layout:** Target → Crawl → Page capture → Excludes → controls → Log on one scrollable page.
- **Presets:** Fast / Balanced / Thorough set timing values; Custom shows advanced dropdowns.
- **Theme:** Purple header, gold accents, parchment panels; `src/folio/assets/folio.png` bundled.
- **Scrolling:** App-level trackpad routing; macOS uses proportional scroll delta.
- **Tabs:** Fixed-width notebook tabs; colour change only when selected.
- 67 tests passing after sprint completion.
