# Folio

**Log in once, save the content, browse it offline.**

Folio crawls a website with Chromium ([Playwright](https://playwright.dev/python/)), waits while you sign in if needed, then saves same-domain pages as static HTML — with CSS, images, fonts, and SVGs pulled down locally. JS is not downloaded.

Only crawl sites you're allowed to access.

![Folio desktop GUI](assets/example-gui.png)

## Install

```bash
git clone https://github.com/SamKerr/Folio.git
cd Folio
uv sync --group dev
uv run playwright install chromium
uv run folio doctor
```

## Crawl

```bash
uv run folio crawl https://www.example.com/
```

1. Log in in the browser window if you need to.
2. Press **Enter** in the terminal (or **Continue after login** in the GUI).
3. Pages land in `output/<host>/`.

Preview with a local server (works better than `file://`):

```bash
cd output && python -m http.server 8765
# http://127.0.0.1:8765/www.example.com/
```

Run the same command again to resume — existing pages are skipped. Add `--force` to re-fetch everything.

## GUI

```bash
uv run folio gui
```

Pick a URL, choose a capture preset (Fast / Balanced / Thorough), start the crawl, then open saved sites from the **Library** tab.

macOS app (optional): `bash scripts/build-macos-app.sh` → open `dist/Folio.app`

## Useful flags

```bash
uv run folio crawl https://www.example.com/ \
  --exclude "/forum/*" \
  --concurrency 20 \
  --force
```

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

`uv run folio crawl --help` for waits, limits, headless mode, and the rest.

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

Convert an existing saved site in place (atomic writes, safe to re-run, never touches the
shared `_assets` folder; don't run it on a folder a crawl is writing to):

```bash
uv run folio slim output/www.example.com          # .html -> reduced, .data.json -> filtered
uv run folio slim output/www.example.com --gzip   # ... and replace each file with <name>.gz
```

On one real listing page this took the HTML from 1.1 MB to 94 KB (18.5 KB gzipped) and its
sidecar from 627 KB to 117 KB (25 KB gzipped).

## Caveats

- Same hostname only (CDN assets are still downloaded).
- Saved pages are static — no JavaScript, so SPAs and live widgets won't work offline.
- Folio doesn't store your password; it uses your browser session during the crawl.

## Dev

```bash
uv run pytest && uv run ruff check . && uv run mypy
```

Project history: [ROADMAP.md](ROADMAP.md)

## License

MIT — see [LICENSE](LICENSE).
