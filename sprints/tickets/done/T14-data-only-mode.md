# T14-data-only-mode

## Context

- Mirroring property-listing portals costs ~1.8 MB per listing (1.15 MB HTML, mostly inlined
  `<style>` and SVG; a 634 KB sidecar padded with A/B-testing and tracking scripts; shared
  images in `_assets`). The consumer only needs the embedded data and the visible text / meta.

## Scope

- `--data-only` crawl mode, `--data-marker`, `--gzip`, `folio slim`, tests, README
- Not: the GUI, the normal full-mirror crawl behaviour, page wait / request blocking changes

## Implementation plan (required before coding)

### Planned approach

1. `offline.py`: `DATA_MARKERS` constant, `MAX_DATA_SCRIPT_BYTES = 2 MB`,
   `prepare_data_snapshot(html, *, base_url=None)` (reduced snapshot; makes canonical / next /
   prev hrefs absolute when the page URL is known), `extract_data_scripts(html, markers=...)`
   (marker-filtered when markers are given), `filter_sidecar(data, markers)` for slim.
2. `storage.py`: gzip-aware helpers — `gz_path` / `plain_path`, `sidecar_path(html_path)`,
   `find_saved_page(path)` (either name), `read_text(path)` (gzip by suffix),
   `write_text_atomic(path, text)` (temp + rename, gzip by suffix).
3. `urls.py`: `url_to_output_path(..., gzip=False)` → `.html.gz`; `output_path_to_url`
   accepts `.html.gz`.
4. `assets.py`: `AssetMirror.rewrite_anchors(html, ...)` (anchors only, no cache); `gzip`
   attribute so rewritten hrefs point at the `.gz` names.
5. `crawler.py`: `run_crawl(data_only=, data_markers=, gzip_output=)`; data-only `_save_page`
   writes the filtered sidecar and the reduced snapshot (no `mirror_page`); resume via
   `find_saved_page` + `read_text`; `extract_links_from_saved_html` accepts `.html.gz` hrefs.
6. `slim.py` + `folio slim <dir> [--gzip] [--data-marker M]`: walk `*.html`, `*.html.gz`,
   `*.data.json`, `*.data.json.gz` outside `_assets`; rewrite only when the content changes.
7. `cli.py`: `--data-only`, `--data-marker` (repeatable), `--gzip` (requires `--data-only`).
8. Tests + README.

### Files to touch

- `src/folio/offline.py`, `src/folio/storage.py` (new), `src/folio/slim.py` (new),
  `src/folio/urls.py`, `src/folio/assets.py`, `src/folio/crawler.py`, `src/folio/cli.py`
- `tests/test_data_only.py` (new), `tests/test_cli.py`
- `README.md`, sprint records

### Data and API impact

- Schema/migration changes: none. Sidecar keys unchanged (`url`, `json_scripts`,
  `inline_scripts`); data-only sidecars just hold fewer inline scripts.
- API changes: new keyword args with defaults; existing callers unaffected.
- State management changes: none.

### Risks and mitigations

- Risk: a site's page state uses a marker not in the list and is dropped.
  Mitigation: `--data-marker` extends the list; JSON scripts are always kept.
- Risk: a > 2 MB page-state script is dropped (truncating would corrupt it).
  Mitigation: documented; cap is a module constant.
- Risk: `slim` racing a live crawl on the same folder.
  Mitigation: atomic temp + rename writes; never touches `_assets`; documented to run on
  folders not being crawled. Not run on the user's real `output/` in this ticket.

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_data_only.py tests/test_cli.py`, then the full gate.
- Manual: `folio slim` on a temp copy of one saved listing page (html + sidecar, with and
  without `--gzip`), then delete the copy.

## Acceptance criteria

- [x] Data-only crawl writes a reduced snapshot + filtered sidecar and no `_assets` files
- [x] Reduced snapshot drops scripts (except JSON), styles, SVG, non-canonical/next/prev links,
      media, iframes, noscript, object/embed, `style=` / `on*=` attributes, comments; keeps
      title, meta, text, canonical, `data-folio-url` anchors
- [x] Sidecar keeps JSON scripts and marker scripts only; 2 MB cap; `--data-marker` extends
- [x] `--gzip` writes `.html.gz` / `.data.json.gz`; resume and link extraction read them
- [x] `folio slim` shrinks an existing site in place, is idempotent, skips `_assets`
- [x] README "Data-only crawls" section

## Implementation notes (during/after execution)

- New: `src/folio/storage.py` (gzip twins, `sidecar_path`, `find_saved_page`, `read_text`,
  atomic `write_text_atomic` keeping file permissions), `src/folio/slim.py` (`slim_site`).
- `offline.py`: `prepare_data_snapshot`, `DATA_MARKERS`, `MAX_DATA_SCRIPT_BYTES`,
  `extract_data_scripts(markers=)`, `filter_sidecar`. Whitespace-only text nodes left by
  removals are collapsed so the snapshot is compact and idempotent.
- `crawler.py`: data-only `_save_page` writes sidecar then page (page file last, both atomic)
  and never calls `mirror_page`; resume uses `find_saved_page` + `read_text`;
  `run_crawl(gzip_output=True)` without `data_only` raises. `--data-only` implies the sidecar.
- Oversized scripts are dropped, not truncated (truncated JSON / JS is unparseable).
- Measured with `folio slim` on a temp copy of one saved Rightmove listing (copy deleted
  after): HTML 1,170,817 B -> 96,592 B (18,947 B gzipped); sidecar 641,546 B -> 120,172 B
  (25,406 B gzipped); the sidecar's remaining bulk is the 105 KB `window.__PAGE_MODEL`
  script. Of the reduced HTML, `class` attributes are ~27 KB and `data-folio-url` ~14 KB;
  classes were kept (consumers may select on them). Second `slim` run rewrote 0 files.
- Not run on the real `output/` folders (live crawls).
- Gate: ruff shows only the 3 pre-existing E501 in `browser_scripts.py`; mypy only the 4
  pre-existing errors in `tests/test_gui_support.py`; pytest 100 passed.
- Follow-ups (not done): in data-only mode, skip the image / asset-quiet waits and block
  image / font / stylesheet requests to speed crawls; GUI controls.

## Verification

- [x] `uv run pytest`
- [x] `uv run ruff check src tests`
- [x] `uv run mypy`
- [x] Manual: slim on a temp copy of one real page

## Status

- Owner: Claude (subagent, money-maker session)
- State: Done (2026-10-31)

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T14-data-only-mode.md`.
