# T12-data-sidecar

## Context

- Static snapshots drop every `<script>`, which also drops the embedded listing data
  (JSON-LD, `window.PAGE_MODEL`, `__NEXT_DATA__`) a consumer needs to parse a page offline.

## Scope

- `offline.py`: `prepare_static_snapshot(keep_data_scripts=)` keeps `application/json` and
  `application/ld+json` scripts (never executed by browsers); `extract_data_scripts(html)`
  returns those plus inline executable scripts that look like data (≥ 200 chars, contain `{`).
- `crawler.py` / `assets.py` / `cli.py`: `--data-sidecar` writes `<page>.data.json`
  (`url`, `json_scripts`, `inline_scripts`) beside each saved page.

## Acceptance criteria

- [x] Snapshot stays free of executable scripts; JSON scripts kept only with the flag
- [x] Sidecar written per page with the flag; tests; README

## Status

- Owner: Claude (main session, money-maker)
- State: Done (2026-10-31)
