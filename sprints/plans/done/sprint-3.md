# Sprint 3 - Offline asset mirroring

## Scope

- Download CSS, JS, images, and fonts referenced by crawled pages
- Rewrite HTML and CSS so saved files reference local asset paths
- Rewrite same-host navigation links for offline browsing
- Download assets from CDNs (cross-origin) while keeping page crawl same-host only

## Tickets

- [x] `T07-asset-mirror`

## Done criteria

- Saved pages render with styling when opened via `file://` or static server
- Tests pass

## Notes

- Assets saved under `output/_assets/<host>/…`
- Recommend serving output via `python -m http.server` for reliable offline preview

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-3.md`.
