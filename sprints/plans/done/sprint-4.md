# Sprint 4 - Full offline fidelity

## Scope

- Capture every static asset the browser loads (network + DOM), including lazy-loaded media
- Rewrite HTML/CSS comprehensively (srcset, data-src, inline styles, preload links)
- Scroll pages to trigger lazy-loaded images before capture
- Sanitize saved HTML so offline viewing does not redirect to login
- Login required once during crawl only; offline copy browsable without auth

## Tickets

- [x] `T08-page-capture`
- [x] `T09-offline-rewrite-and-guard`

## Done criteria

- Saved pages retain CSS, JS, images, and fonts when served locally
- Offline pages do not bounce to login
- Tests pass

## Notes

- Builds on Sprint 3 basic asset mirroring (T07)
- Serve output via `python -m http.server` for best results

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-4.md`.
