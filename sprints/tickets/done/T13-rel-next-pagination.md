# T13-rel-next-pagination

## Context

- Search-result sites often paginate with `<link rel="next">` (plus JS buttons), not anchors;
  Folio discovered anchors only, so a results crawl stopped after page one.

## Scope

- Discover `link[rel~=next|prev][href]` alongside `a[href]`: in the in-page discovery script,
  the no-interaction fallback and `extract_links`, and in saved-HTML link discovery.

## Acceptance criteria

- [x] rel=next / prev links are followed (live and on resume); tests

## Status

- Owner: Claude (main session, money-maker)
- State: Done (2026-10-31)
