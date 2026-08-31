# Folio roadmap

| Sprint | Goal | Tickets | Plan |
|--------|------|---------|------|
| **1** | Installable project with CLI and Playwright smoke test | T01–T03 | [sprint-1.md](sprints/plans/done/sprint-1.md) |
| **2** | Login once, crawl same-domain pages to HTML | T04–T06 | [sprint-2.md](sprints/plans/done/sprint-2.md) |
| **3** | Download and rewrite CSS, images, fonts for local paths | T07 | [sprint-3.md](sprints/plans/done/sprint-3.md) |
| **4** | Lazy-load capture, script stripping, auth-free offline browse | T08–T09 | [sprint-4.md](sprints/plans/done/sprint-4.md) |
| **5** | Desktop GUI: usable crawl settings, branding, and scrolling | T10 | [sprint-5.md](sprints/plans/done/sprint-5.md) |

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

