# Sprint 6 - Crawl a subset: include patterns, query-aware pages, several seeds

## Scope

- `--include PATTERN` (repeatable): restrict a crawl to matching URLs; start URLs always crawled
- `--keep-query`: query-string URLs get their own output file; rewritten anchors record the
  exact URL (`data-folio-url`) so resume follows them
- Several start URLs on one host (positional `url` takes many)
- Tests, README; CLI only (the GUI keeps its current options)

## Out of scope

- GUI controls for the new flags
- Any site-specific parsing (consumers parse the saved HTML themselves)

## Tickets

- [x] `T11-include-keep-query-seeds`

## Done criteria

- `uv run pytest && uv run ruff check . && uv run mypy` pass
- README documents the three options with a subset-crawl example

## Closure

- Done 2026-10-31 (requested by the user to mirror property search results for a sibling
  project's offline import).
