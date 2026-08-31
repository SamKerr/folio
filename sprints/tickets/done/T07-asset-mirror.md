# T07-asset-mirror

## Context

Sprint 2 saved HTML only; stylesheet and asset URLs still point remote, so offline pages are unstyled.

## Scope

- Download linked assets via Playwright request context (session cookies preserved)
- Rewrite HTML/CSS to use relative local paths
- Rewrite same-host anchor hrefs to local `.html` files

## Acceptance criteria

- [x] CSS/JS/image URLs in saved HTML point to local files under `_assets/`
- [x] Nested `url(...)` references inside CSS are downloaded and rewritten
- [x] Same-host page links use relative `.html` paths
- [x] Tests cover path mapping and HTML/CSS rewriting

## Status

- Owner: agent
- State: Done
