# Folio - Clone static content locally

**Save a website you can browse offline — after one login.**

Folio is a Python CLI tool that crawls a site with headless/headed Chromium (via [Playwright](https://playwright.dev/python/)), lets you log in manually in a real browser, then walks same-domain pages and writes a **static offline copy**: HTML, CSS, images, fonts, and SVGs. Saved pages have JavaScript stripped so they do not re-hit auth or call live APIs.

Use it for personal archives, documentation mirrors, study material, or any site you are allowed to access.

---

## What you get

| Live site | Folio output |
|-----------|--------------|
| Requires login session / cookies | Browse locally without logging in again |
| JS-rendered content | Captured after render, saved as static HTML |
| CDN assets | Downloaded to `output/_assets/` and rewritten in place |
| Same-host navigation | Relative links between saved `.html` files |

Folio is **not** a general-purpose website copier for the whole internet. It stays on the **same hostname** as your start URL, skips paths you exclude, and does not store credentials.

---

## Requirements

- [uv](https://docs.astral.sh/uv/) (recommended) or pip + Python **3.11+**
- Chromium via Playwright (~150 MB one-time install)

---

## Quick start

```bash
git clone <your-repo-url> folio && cd folio

uv sync --group dev
uv run playwright install chromium
uv run folio doctor
```

Crawl a site (opens a browser window for login):

```bash
uv run folio crawl https://www.example.com/
```

1. Log in in the Chromium window if needed.
2. Press **Enter** in the terminal (or click **Continue after login** in the GUI).
3. Wait while Folio crawls. Output lands in `output/`.

Preview locally (recommended — works better than `file://`):

```bash
cd output && python -m http.server 8765
# open http://127.0.0.1:8765/www.example.com/
```

Resume after interruption: run the same command again — existing pages are skipped, links from them are still followed. Use `--force` to re-fetch everything.

---

## GUI

```bash
uv run folio gui
```

- **Crawl** — URL, output dir, concurrency, wait timings, exclude patterns, live log
- **Library** — list sites under `output/`, double-click to open in your browser

### macOS app (optional)

Build a double-clickable **Folio.app** (no Terminal window):

```bash
uv sync --group dev
uv run playwright install chromium
bash scripts/build-macos-app.sh
cp -R dist/Folio.app /Applications/
```

The app bundle points at this project directory. If you move the repo, run `build-macos-app.sh` again. Playwright Chromium must already be installed in the project venv.

---

## CLI reference

```bash
uv run folio crawl <url> [options]
```

### Common flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--output DIR` | `output` | Where to write HTML and assets |
| `--concurrency N` | `20` | Parallel browser tabs for pages |
| `--asset-concurrency N` | `12` | Parallel asset downloads per page |
| `--exclude PATTERN` | — | Skip path globs, e.g. `/forum/*` (repeatable) |
| `--max-pages N` | unlimited | Stop after N new pages (testing) |
| `--force` | off | Re-fetch pages even if HTML already exists |
| `--skip-login-wait` | off | Start crawl immediately (automation/tests) |
| `--headless` | off | Headless browser (not ideal when login is required) |
| `--quiet` | off | Less progress output |

### Capture tuning

Folio prepares each page before snapshotting: expand collapsed chevrons, scroll, wait for images and lazy diagrams, then wait for the asset network to go quiet.

| Flag | Default | Purpose |
|------|---------|---------|
| `--asset-quiet-ms` | `750` | Idle time with no image/CSS/font requests before moving on |
| `--page-asset-timeout-ms` | `60000` | Hard cap per page for asset waiting |
| `--diagram-wait-ms` | `30000` | Wait for lazy diagram placeholders (e.g. Excalidraw) to render |
| `--image-wait-ms` | `5000` | Per-`<img>` fallback timeout during DOM wait |
| `--settle-ms` | `1000` | Extra buffer after waits for late injections |
| `--timeout SECS` | `60` | Navigation timeout per page |
| `--delay SECS` | `0` | Pause between page fetches |

Example — large site, patient asset capture:

```bash
uv run folio crawl https://docs.example.com/ \
  --output output \
  --exclude "/search/*" \
  --asset-quiet-ms 1500 \
  --diagram-wait-ms 45000 \
  --force
```

Other commands:

```bash
uv run folio doctor    # verify Playwright + Chromium
uv run folio gui       # desktop UI
uv run folio --version
```

---

## Output layout

```
output/
├── www.example.com/
│   ├── index.html
│   ├── docs/
│   │   └── guide.html
│   └── ...
└── _assets/
    └── www.example.com/    # CSS, fonts, images, SVGs
        └── ...
```

- **Pages:** `output/<host>/<path>.html` mirrors URL paths (`/` → `index.html`).
- **Assets:** `output/_assets/<host>/…` with URLs rewritten to relative paths in HTML/CSS.
- **Cross-origin CDN assets** (fonts, CSS on another host) are downloaded too; only the **page crawl queue** is same-host.

Crawl order is **section-first**: URLs group by top-level path prefix (`/docs/` before `/blog/`), then by depth within each section.

---

## How it works

High-level pipeline for each page:

```
navigate → discover links (expand chevrons) → prepare page → save HTML + assets
```

### 1. Browser session

- Playwright launches Chromium (headed by default so you can log in).
- One browser context; multiple worker tabs (`--concurrency`) process the queue in parallel.
- Video/audio requests are blocked during crawl to save bandwidth; static images/CSS/fonts are kept.

### 2. Link discovery

- Same-host links from `<a href>` after optional interaction.
- Collapsed sections are expanded by clicking **chevron icons only** (SVG/caret elements), not arbitrary buttons.
- URLs are normalized (lowercase host, trailing slashes trimmed, fragments dropped for dedup).

### 3. Page preparation (`capture.py`)

Before `page.content()`:

1. Scroll the page to trigger lazy-loaded content.
2. Expand chevrons again (content revealed by scroll).
3. Wait for lazy **diagram** placeholders (`role="img"` pulse skeletons) to be replaced by inline SVG.
4. Wait for `<img>` elements (including lazy `data-src` promotion).
5. Wait until image/CSS/font network activity is quiet (`AssetQuietTracker`).
6. Short settle delay.

### 4. Asset mirroring (`assets.py`)

- Collect asset URLs from the DOM (including `srcset`, inline styles, CSS rules, SVG `<use href>`, etc.) plus network responses seen while the tab was open.
- Download each asset once into `_assets/` with concurrent fetches.
- Rewrite HTML and CSS to point at relative local paths; rewrite same-host anchors to other saved `.html` files.

### 5. Offline sanitization (`offline.py`)

- Remove `<script>` tags and `on*` event handlers.
- Strip video/audio sources.
- Result: static snapshot that does not execute JS or redirect to login.

### Package map

```
src/folio/
├── cli.py              # argparse entrypoint
├── crawler.py          # queue, workers, resume, parallel crawl
├── capture.py          # page prep, network capture, asset-quiet wait
├── browser_scripts.py  # in-browser JS (scroll, chevrons, images, diagrams)
├── assets.py           # download + rewrite HTML/CSS/assets
├── offline.py          # strip scripts for safe offline viewing
├── urls.py             # normalize, same-host, output paths, excludes
├── navigation.py       # goto with domcontentloaded fallback
├── gui.py              # Tkinter desktop UI
├── preview_server.py   # local library preview helper
└── doctor.py           # Playwright smoke test
```

Browser-side scripts are validated with Node (`tests/test_browser_scripts.py`) before they run in Playwright.

---

## Limitations

- **No JavaScript in saved pages** — by design. SPAs, live search, WebSockets, and client-only routing will not work offline.
- **Same hostname only** for page discovery (CDN assets are still fetched).
- **No automated login** — you log in once in the browser; Folio does not store passwords or cookies in the output.
- **No `robots.txt`** enforcement yet — crawl only sites you are permitted to access; use `--delay` if you need to be polite.
- **Not a forensic archiver** — dynamic content that never appears in the DOM (or loads after all waits time out) may be missing.
- **Diagrams / lazy media** — Folio waits for common patterns (Excalidraw placeholders, lazy images), but exotic loaders may need tuning via wait flags.

---

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy
```

Tests use mocked Playwright for the crawler; no live network required in CI. Browser script syntax is checked with Node when available.

Project conventions and sprint workflow: [`AGENTS.md`](AGENTS.md). Roadmap: [`ROADMAP.md`](ROADMAP.md).

---

## License

MIT — see [LICENSE](LICENSE).
