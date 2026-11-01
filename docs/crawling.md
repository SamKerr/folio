# Crawling reference

Detailed behaviour of `folio crawl`. For a quick start, see the [README](../README.md).
Run `uv run folio crawl --help` for the full list of options.

## Crawling part of a site

Crawl a **subset** of a site, e.g. one search and the listings it links to, politely:

```bash
uv run folio crawl "https://www.example.com/search?area=leeds" \
  --include "/search*" --include "/listing/*" \
  --keep-query --concurrency 2 --delay 2 --headless --skip-login-wait
```

- `--include PATTERN` (repeatable): only follow matching URLs; the start URL(s) are always
  crawled. Several start URLs on the same host can be given.
- `--keep-query`: pages that differ only by query string (page 2, filters) get their own
  file, `<name>.q<hash>.html`, instead of overwriting each other. Rewritten links carry
  `data-folio-url` so a resumed crawl follows the exact URLs again.

- `--data-sidecar`: keep non-executable JSON scripts (e.g. schema.org JSON-LD) in the snapshot
  and write each page's embedded data — JSON scripts and inline data scripts such as
  `window.PAGE_MODEL = {...}` — to `<page>.data.json`, so another program can parse the
  listing data offline while the HTML stays script-free.

## Crawl order

`--order` picks which queued page is fetched next. `section` (the default) fetches every URL
of the first path section seen before any URL of a later one (shallower paths first), so a
site's `/docs/...` mirror completes section by section. `discovered` is plain breadth-first,
in the order links were found. `interleave` round-robins across path sections: the first
queued URL of every section, then the second of every section, and so on (a URL found again
keeps its place; start URLs always go first). On a listings portal this means listing pages
(`/details/...`) start as soon as the first results page (`/for-sale/...`) has yielded links,
and results pages keep flowing alongside them, instead of every results page being fetched
first. **Data-only crawls default to `interleave`**; pass `--order section` to get the old
order back.

## Error pages

A site's own error or challenge page is never saved as if it were the page asked for, so a
resumed crawl (which skips any URL whose file exists) fetches it again. A page is an error page
when its navigation answered **HTTP >= 400** (the primary check), when the final URL after
redirects has an error path (`/otm-errors/`, `/error`, `/404`, `/500`, matched as whole path
segments, so `/details/40412` is fine), or, as a fallback for sites that answer 200, when its
`<title>` contains `Just a moment...`, `Access denied`, `Attention Required` or `captcha`
(case-insensitive) or its Next.js `__NEXT_DATA__.page` is an error path. Such pages are logged
as `Skipped (HTTP 500): <url>`, nothing is written, and they count as failed.
`--error-marker PATTERN` (repeatable) adds a pattern: one starting with `/` is a path, anything
else a title substring. Every URL left unsaved (error page, timeout, failure) is re-queued once
at the end of the crawl, after `--retry-delay` seconds (default 5), because 500s are often
transient; `--retry-failed N` sets the number of rounds (default 1, `0` disables). URLs that
still fail are reported (`N page(s) failed`) and left for the next resume. To clean up error
pages saved by an older version:

```bash
uv run folio slim output/www.example.com --drop-errors --dry-run   # list them
uv run folio slim output/www.example.com --drop-errors             # delete page + sidecar
```

`--drop-errors` only deletes (it does not slim); it checks each saved page's `<title>` and
`__NEXT_DATA__` (in the page or its sidecar, plain or `.gz`) and never touches `_assets`.

## Rate limits

When the site answers **HTTP 429** (or **503 with a `Retry-After` header**) the crawl cools
down: every tab pauses for `Retry-After` seconds when the header is present, otherwise for
`--backoff` seconds (default 30) doubling with each consecutive rate-limited pause, never
longer than `--max-backoff` (default 300, which also caps `Retry-After`). It logs
`Rate limited (HTTP 429): pausing N s` once per pause. The URL goes straight back on the queue
and is fetched again after the pause, up to `--retry-failed` times before it counts as failed;
a saved page resets the doubling. A 503 without `Retry-After` stays an ordinary error page.
With `--adaptive` (**on by default in `--data-only` crawls**; `--no-adaptive` turns it off)
each pause also adds `--adaptive-step` seconds (default 1) to the per-page `--delay` for the
rest of the run, so a crawl settles at a rate the site accepts; `--stats` prints the final
delay and the number of pauses. The cool-down covers one crawl's tabs only: separate crawls
against the same site do not see each other's pauses.

## Data-only crawls

For large crawls where another program only needs each page's embedded data and visible
text (not an offline-browsable copy), skip asset mirroring entirely:

```bash
uv run folio crawl "https://www.example.com/search?area=leeds" \
  --include "/search*" --include "/listing/*" --keep-query \
  --data-only --gzip --concurrency 2 --delay 2 --headless --skip-login-wait
```

- `--data-only`: no `_assets` downloads, no inlined CSS / fonts / images. Each page is saved
  as a **reduced snapshot**: `<title>`, `<meta>` tags, body text and structure, `<link
  rel=canonical|next|prev>` (made absolute) and same-host anchors with `data-folio-url` (so
  resume and link discovery work). Removed: executable scripts (JSON scripts stay), `<style>`,
  `<svg>`, other `<link>`s, `<img>` / `<picture>` / `<source>` / `<video>` / `<audio>`,
  `<iframe>`, `<noscript>`, `<object>` / `<embed>`, `style=` and `on*=` attributes, comments.
  A `<page>.data.json` sidecar is always written, holding JSON scripts plus only the inline
  scripts that look like page state (`__PAGE_MODEL`, `PAGE_MODEL`, `__NEXT_DATA__`,
  `__PRELOADED_STATE__`, `__INITIAL_STATE__`, `__NUXT__`, `__APOLLO_STATE__`,
  `__REDUX_STATE__`, `initialState`, `window.__data`); any single script over 2 MB is dropped.
- `--data-marker TEXT` (repeatable): add a page-state marker for a site the list misses.
- `--gzip` (with `--data-only`): write `<page>.html.gz` and `<page>.data.json.gz`. Resume
  finds a page under either name, so a crawl can switch between plain and gzip.

Data-only crawls are also **fast**: nothing visual is saved, so nothing visual is loaded.

- **Blocked** (aborted before download): `image`, `media`, `font`, `stylesheet`,
  `websocket`, `manifest`, `texttrack`, `other` (favicons, prefetches, ...) and `ping`
  requests on every host, and every request to a **third-party host** (analytics, A/B-testing
  scripts, ad / map iframes, ...). Service workers are blocked too.
- **Still loads**: the page itself (any main-frame navigation, including redirects) and the
  site's own `document`, `script`, `xhr` / `fetch` (and `eventsource`) requests, so the page's
  scripts still run and set `window.__PAGE_MODEL` / `__NEXT_DATA__` etc. "The site" is the
  start URL's host without a leading `www.`, plus its subdomains (start at
  `www.example.com` → `example.com`, `api.example.com`, `static.example.com` load).
- `--allow-host PATTERN` (repeatable): treat another host as part of the site (for listing
  data served from a CDN / API domain). A plain host also covers its subdomains; globs work
  (`--allow-host "*.cloudfront.net"`). Blocked resource types stay blocked.
- **No render waits**: no chevron / accordion clicks, scrolling, image or diagram waits or
  asset-quiet wait. Each page waits for `domcontentloaded`, then until a `<script>` contains
  a page-state marker (the sidecar markers plus `--data-marker`, or your own
  `--wait-for-marker TEXT`, repeatable) — at most `--marker-timeout-ms` (default 3000; `0`
  skips it), and no longer than the page's `load` event when it has no marker — then
  `--settle-ms` (default 300 here). Links come from `a[href]` and `link[rel=next|prev]`.
- Navigation timeout defaults to 30 s (`--timeout`), and a page that times out is skipped
  (and retried on the next resume) instead of being saved half-loaded.
- `--full-render`: load everything and use the normal waits and timeouts (the pre-T15
  behaviour), for a site whose data only appears after interaction.
- `--stats`: print pages per minute and seconds per page at the end.

On `books.toscrape.com` (20 pages, `--concurrency 2 --delay 0`, on a busy machine) a fast
data-only crawl ran at 86–94 pages/min against 25–33 with `--full-render`, writing
byte-identical files.

Convert an existing saved site in place (atomic writes, safe to re-run, never touches the
shared `_assets` folder; don't run it on a folder a crawl is writing to):

```bash
uv run folio slim output/www.example.com          # .html -> reduced, .data.json -> filtered
uv run folio slim output/www.example.com --gzip   # ... and replace each file with <name>.gz
```

On one real listing page this took the HTML from 1.1 MB to 94 KB (18.5 KB gzipped) and its
sidecar from 627 KB to 117 KB (25 KB gzipped).
