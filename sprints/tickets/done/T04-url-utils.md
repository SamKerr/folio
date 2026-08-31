# T04-url-utils

## Context

The crawler needs consistent URL handling for deduplication, same-domain filtering, and mapping saved HTML to disk paths.

## Scope

- Normalize URLs (resolve relative links, lowercase host, strip fragments)
- Same-host check against crawl root
- Map URL to output file path under `output/<host>/…`

## Implementation plan (required before coding)

### Planned approach

1. Add `folio/urls.py` with `normalize_url`, `same_host`, `url_to_output_path`
2. Add `tests/test_urls.py` with pure unit tests

### Files to touch

- `src/folio/urls.py`: URL helpers
- `tests/test_urls.py`: unit tests

### Data and API impact

- None

### Risks and mitigations

- Risk: Trailing-slash vs no-slash duplicates
  Mitigation: normalize path for dedup in crawler (strip trailing slash except root)

### Verification plan (ticket-specific)

- Automated: `uv run pytest tests/test_urls.py`

## Acceptance criteria

- [x] Relative and absolute URLs normalize to a stable form
- [x] `same_host` rejects external domains
- [x] Output paths mirror URL structure under host directory

## Verification

- [x] `uv run pytest tests/test_urls.py`

## Status

- Owner: agent
- State: Done

## Closure (required when ticket finishes)

1. Check off acceptance criteria and verification items above.
2. Set `State: Done` in the Status section.
3. Check off this ticket in the sprint plan (`- [x]`).
4. Move this file to `sprints/tickets/done/T04-url-utils.md`.
