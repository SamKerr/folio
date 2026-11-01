# Folio roadmap

| Sprint | Goal | Tickets | Plan |
|--------|------|---------|------|
| **1** | Installable project with CLI and Playwright smoke test | T01–T03 | [sprint-1.md](sprints/plans/done/sprint-1.md) |
| **2** | Login once, crawl same-domain pages to HTML | T04–T06 | [sprint-2.md](sprints/plans/done/sprint-2.md) |
| **3** | Download and rewrite CSS, images, fonts for local paths | T07 | [sprint-3.md](sprints/plans/done/sprint-3.md) |
| **4** | Lazy-load capture, script stripping, auth-free offline browse | T08–T09 | [sprint-4.md](sprints/plans/done/sprint-4.md) |
| **5** | Desktop GUI: usable crawl settings, branding, and scrolling | T10 | [sprint-5.md](sprints/plans/done/sprint-5.md) |
| **6** | Crawl a subset: include patterns, query-aware pages, several start URLs | T11–T13 | [sprint-6.md](sprints/plans/sprint-6.md) |
| **7** | Data-only crawls: reduced snapshots, data sidecars, gzip, `folio slim` | T14 | [sprint-7.md](sprints/plans/done/sprint-7.md) |
| **8** | Fast data-only crawls: block non-data requests, skip render waits | T15 | [sprint-8.md](sprints/plans/done/sprint-8.md) |
| **9** | Crawl order: section, discovered, and interleave | T16 | [sprint-9.md](sprints/plans/done/sprint-9.md) |
| **10** | Never save error pages; retry failed URLs | T17 | [sprint-10.md](sprints/plans/done/sprint-10.md) |
| **11** | Back off on rate limits; adaptive per-page delay | T18 | [sprint-11.md](sprints/plans/done/sprint-11.md) |
| **12** | Modern desktop app: Vue UI in a native window *(in progress)* | T19–T21 | [sprint-12.md](sprints/plans/sprint-12.md) |

---

## Sprint 1 — Setup tooling and scaffolding

**Goal:** `uv sync`, `folio doctor`, and the test/lint toolchain all work.

- Python package under `src/folio/`
- CLI: `folio --version`, `folio doctor`
- pytest, ruff, mypy; README and AGENTS.md

**Done when:** Playwright/Chromium verified; no crawling yet.

---

## Sprint 2 — Interactive login and same-domain crawl

**Goal:** `folio crawl <url>` opens a browser for login, then saves same-host pages as HTML.

- Headed Chromium; user confirms login with Enter
- BFS link discovery; output under `output/<host>/`
- Resume, excludes, parallelism, rate limiting

**Done when:** Same-domain pages persist as HTML after a manual login.

---

## Sprint 3 — Offline asset mirroring

**Goal:** Saved pages pull in styling assets and link to local copies.

- Download CSS, images, fonts (including CDN)
- Rewrite HTML/CSS URLs; rewrite same-host navigation links
- Assets under `output/_assets/`

**Done when:** Offline pages render with basic styling via a static server.

---

## Sprint 4 — Full offline fidelity

**Goal:** Offline copy matches the live site visually; no re-login when browsing locally.

- Scroll and wait for lazy images and diagrams before capture
- Network + DOM asset discovery; richer HTML/CSS rewrite
- Strip scripts and media hooks so pages stay static offline

**Done when:** CSS, images, and fonts survive offline; no auth redirect on saved pages.

---

## Sprint 5 — Desktop GUI polish

**Goal:** A usable, branded desktop UI for configuring crawls and browsing saved output.

- Reorganize crawl settings into clear groups: Target, Crawl, Page capture, Excludes
- Replace clipped macOS spinboxes with dropdowns; capture presets (Fast / Balanced / Thorough / Custom)
- Branded header and window icon from `folio.png`; purple, gold, and parchment theme
- One scrollable Crawl page (options, controls, and log together); trackpad scrolling on macOS
- Library tab with scrollable site list; tab bar keeps fixed size and changes colour only

**Done when:** `uv run folio gui` is readable at default window size, every control maps to the correct CLI flags, and the app feels intentionally designed rather than a debug form.

---

## Sprint 6 — Crawl a subset of a site

**Goal:** Crawl one part of a site, such as a search and the listings it links to.

- `--include PATTERN` restricts the crawl; start URLs are always crawled
- `--keep-query` saves query-string pages separately and resumes them exactly (`data-folio-url`)
- Several start URLs on one host; follow `<link rel=next|prev>` pagination
- `--data-sidecar` writes each page's embedded data to `<page>.data.json`

**Done when:** A filtered, paginated crawl saves every matching page and resumes cleanly.

---

## Sprint 7 — Data-only crawls

**Goal:** Save only what another program needs: page text, structure, and embedded data.

- `--data-only`: no asset mirroring; reduced HTML snapshot plus a filtered data sidecar
- `--data-marker` for page-state scripts the built-in list misses
- `--gzip` output; resume reads plain or gzipped files
- `folio slim <dir>` converts an existing saved site in place

**Done when:** Data-only output is a fraction of the full size and keeps all page data.

---

## Sprint 8 — Fast data-only crawls

**Goal:** Make data-only crawls several times faster.

- Block images, media, fonts, stylesheets, and third-party hosts; keep the site's own scripts
- Skip render waits; wait briefly for a page-state marker instead
- `--allow-host`, `--wait-for-marker`, `--marker-timeout-ms`, `--full-render`, `--stats`

**Done when:** Data-only crawls run roughly 3× faster with byte-identical output.

---

## Sprint 9 — Crawl order

**Goal:** Let listing pages start downloading as soon as results pages reveal them.

- `--order section | discovered | interleave`
- Data-only crawls default to `interleave`

**Done when:** Results and listing pages are fetched side by side instead of in sequence.

---

## Sprint 10 — Never save error pages

**Goal:** A site's error or challenge page is never saved as if it were real content.

- Detect errors by HTTP status, error paths, page titles, and Next.js error pages
- `--error-marker` adds custom patterns
- `--retry-failed` / `--retry-delay` retry failed URLs at the end of the crawl
- `folio slim --drop-errors` removes error pages saved by older versions

**Done when:** Error pages are skipped, counted as failed, and retried on the next resume.

---

## Sprint 11 — Rate-limit back-off

**Goal:** Slow down automatically when a site says it is being asked too often.

- On HTTP 429 (or 503 with `Retry-After`) every tab pauses, then the URL is retried
- Exponential back-off via `--backoff` / `--max-backoff`
- `--adaptive` raises the per-page delay after each pause (on by default for data-only crawls)

**Done when:** Rate-limited crawls recover without losing pages.

---

## Sprint 12 — Modern desktop app *(in progress)*

**Goal:** Replace the dated Tk interface with a modern app that matches the Folio brand.

- Vue 3 interface (vendored, no build step) served by a local, token-protected server
- Native window via pywebview; `folio gui --browser` and `--classic` (Tk) alternatives
- Crawl form with quality presets, live progress with a login prompt, searchable library
- Light and dark themes in the colours of the Folio icon

**Done when:** `uv run folio gui` opens the new app in a native window and every flow works.

---
