# Sprint 7 - Data-only crawls

## Scope

- `--data-only` crawl mode: no asset mirroring; a reduced HTML snapshot (title, meta, text,
  structure, canonical / next / prev links, same-host anchors with `data-folio-url`); a sidecar
  filtered to JSON scripts and page-state inline scripts (marker list, `--data-marker`, 2 MB cap)
- `--gzip` (data-only crawls): `<page>.html.gz` / `<page>.data.json.gz`; path mapping, resume
  and saved-link extraction read either name
- `folio slim <dir> [--gzip]`: convert an existing saved site in place (atomic, idempotent,
  never touches `_assets`), printing bytes before / after
- Tests (synthetic HTML only), README section
- Out of scope: GUI controls; changes to normal (full mirror) crawls; skipping page waits or
  blocking image requests in data-only mode (possible follow-up)

## Tickets

- [x] `T14-data-only-mode`

## Sequencing

1. `offline.py`: reduced snapshot + filtered sidecar
2. Storage helpers (gzip-aware paths, atomic writes, read either name); crawler wiring
3. `folio slim`; CLI flags; tests; README

## Done criteria

- T14 acceptance criteria pass
- `uv run ruff check src tests && uv run mypy && uv run pytest` pass (pre-existing
  `browser_scripts.py` E501 and `tests/test_gui_support.py` mypy errors excepted)
- README documents `--data-only`, `--data-marker`, `--gzip`, `folio slim`

## Verification plan

- `uv run pytest`
- `uv run ruff check src tests`
- `uv run mypy`
- `folio slim` on a temp copy of one real saved listing page (never on the live `output/`)

## Notes

- Requested 2026-10-31: property-portal mirrors were ~1.8 MB per listing (inlined CSS, SVG,
  tracking scripts in the sidecar, shared images), too big for a UK-wide crawl.

## Outcome

- Done 2026-10-31. One real listing page: HTML 1.1 MB -> 94 KB (18.5 KB gzipped), sidecar
  627 KB -> 117 KB (25 KB gzipped). 100 tests pass.

## Closure (required when sprint finishes)

1. Check off all completed tickets above (`- [x]`).
2. Confirm every finished ticket is in `sprints/tickets/done/` with `State: Done`.
3. Move this file to `sprints/plans/done/sprint-7.md`.
4. Leave only the next active sprint plan in `sprints/plans/`.
