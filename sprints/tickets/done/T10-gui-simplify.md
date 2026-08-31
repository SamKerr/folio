# T10-gui-simplify

## Context

- Crawl tab options are cramped in a 4-column spinbox grid; labels clip and spinboxes behave poorly on macOS.

## Scope

- Reorganize crawl tab into Target / Crawl / Page capture / Excludes groups
- Capture quality preset dropdown (Fast, Balanced, Thorough, Custom)
- Parallelism via dropdowns; advanced timings only when Custom
- Wire values through `_parse_settings` unchanged semantically

## Acceptance criteria

- [x] Options grouped in labeled sections; no 4-column spinbox grid
- [x] Capture quality and parallelism use dropdowns
- [x] Custom preset reveals advanced timing dropdowns
- [x] Crawl start passes correct flags to subprocess

## Verification

- [x] `uv run pytest tests/test_gui_support.py -q`
- [x] `uv run ruff check src/folio/gui.py`
- [x] Manual: open GUI, select Thorough preset, confirm log argv on start

## Status

- Owner: Sam
- State: Done

## Implementation notes

- Replaced macOS-unfriendly `ttk.Spinbox` grid with readonly `ttk.Combobox` rows.
- Capture presets (`Fast`, `Balanced`, `Thorough`) set timing vars; `Custom` shows advanced frame.
- Groups: Target, Crawl, Page capture, Advanced timings (conditional), Excludes, Log.
