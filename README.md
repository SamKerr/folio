```text
 ________            __  __
|        \          |  \|  \
| $$$$$$$$  ______  | $$ \$$  ______
| $$__     /      \ | $$|  \ /      \
| $$  \   |  $$$$$$\| $$| $$|  $$$$$$\
| $$$$$   | $$  | $$| $$| $$| $$  | $$
| $$      | $$__/ $$| $$| $$| $$__/ $$
| $$       \$$    $$| $$| $$ \$$    $$
 \$$        \$$$$$$  \$$ \$$  \$$$$$$
```

**Log in once, save the content, browse it offline.**

Folio crawls a website in Chromium (via [Playwright](https://playwright.dev/python/)), lets
you sign in first if the site needs it, and saves same-site pages as static HTML with their
CSS, images, fonts and SVGs stored locally. JavaScript is not saved.

![Folio desktop app](assets/example-gui.png)

## Features

- **Authenticated crawls**: sign in once in the browser window, then let Folio crawl.
- **Offline copies**: pages and assets are rewritten to work from disk.
- **Resumable**: re-running a crawl skips pages already saved.
- **Polite by default**: retries transient errors, backs off on HTTP 429 and skips error pages.
- **Data-only mode**: compact snapshots plus embedded page data (JSON) for downstream processing.
- **Desktop app**: start crawls, follow progress and browse your library, in light or dark mode.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone https://github.com/SamKerr/folio.git
cd folio
uv sync --group dev
uv run playwright install chromium
uv run folio doctor   # verify the setup
```

## Usage

### Desktop app

```bash
uv run folio
```

Running `folio` on its own opens the app (`folio gui` does the same). Enter a URL, choose
a capture quality and press **Start crawl**. If the site needs a login, sign in in the
browser window, then click **I'm logged in, continue**. Saved sites appear under
**Library**.

Run `folio gui --browser` to open the app in your default browser instead of a native
window. To build a macOS app bundle, run `bash scripts/build-macos-app.sh` and open
`dist/Folio.app`.

### Command line

```bash
uv run folio crawl https://www.example.com/
```

Sign in if needed, then press **Enter** in the terminal. Pages are written to
`output/<host>/`. Run the same command again to resume.

To browse a saved site, serve it locally:

```bash
cd output && python -m http.server 8765   # http://127.0.0.1:8765/www.example.com/
```

## Commands

| Command | Description |
|---|---|
| `folio` or `folio gui` | Open the desktop app |
| `folio crawl <url>` | Crawl a site from the terminal |
| `folio slim <dir>` | Convert a saved site to the compact data-only form |
| `folio doctor` | Check that Playwright and Chromium work |

Prefix each command with `uv run`. Add `--help` to any command for its options.

## Common options

| Option | Description |
|---|---|
| `--include PATTERN` | Only follow matching URLs (repeatable) |
| `--exclude PATTERN` | Skip matching URLs (repeatable) |
| `--max-pages N` | Stop after N pages |
| `--concurrency N` | Pages fetched in parallel |
| `--delay SECONDS` | Pause between pages |
| `--force` | Re-fetch pages that are already saved |
| `--headless` | Run without a visible browser |
| `--skip-login-wait` | Start crawling immediately |
| `--data-only` | Save compact snapshots and page data instead of full pages |

See [docs/crawling.md](docs/crawling.md) for crawl order, error handling, rate limiting and
data-only crawls.

## Limitations

- Only pages on the starting host are crawled. Assets from CDNs are still downloaded.
- Saved pages contain no JavaScript, so single-page apps and live widgets will not work offline.
- Folio never stores your password. It uses the browser session from your sign-in.
- Only crawl sites you are permitted to access.

## Development

```bash
uv run pytest && uv run ruff check . && uv run mypy
```

Project history is in [ROADMAP.md](ROADMAP.md).

## License

MIT. See [LICENSE](LICENSE).
