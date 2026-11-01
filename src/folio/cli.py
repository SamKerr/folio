import argparse
import asyncio
import sys
from pathlib import Path

from folio import __version__
from folio.capture import (
    DEFAULT_DATA_NAVIGATION_TIMEOUT_MS,
    DEFAULT_DATA_SETTLE_MS,
    DEFAULT_MARKER_TIMEOUT_MS,
)
from folio.crawler import (
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_RETRY_FAILED,
    CrawlResult,
    run_crawl,
)
from folio.doctor import run_doctor
from folio.error_pages import DEFAULT_ERROR_PATHS, DEFAULT_ERROR_TITLES
from folio.offline import DATA_MARKERS
from folio.ordering import (
    CRAWL_ORDERS,
    DEFAULT_CRAWL_ORDER,
    DEFAULT_DATA_ONLY_CRAWL_ORDER,
)
from folio.rate_limit import (
    DEFAULT_ADAPTIVE_STEP_SECONDS,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="folio",
        description="Crawl a website and save same-domain pages as local HTML.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "doctor",
        help="Verify Playwright and Chromium are installed and working",
    )

    gui_parser = subparsers.add_parser(
        "gui",
        help="Open the desktop GUI to configure crawls and browse saved sites",
    )
    gui_mode = gui_parser.add_mutually_exclusive_group()
    gui_mode.add_argument(
        "--browser",
        action="store_true",
        help="Open the GUI in your default browser instead of a native window",
    )
    gui_mode.add_argument(
        "--classic",
        action="store_true",
        help="Use the previous Tkinter GUI",
    )

    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Open a URL, wait for login, then crawl same-host pages to disk",
    )
    crawl_parser.add_argument(
        "url",
        nargs="+",
        help="Starting URL(s) on one host (e.g. https://www.example.com/)",
    )
    crawl_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Directory for saved HTML (default: output)",
    )
    crawl_parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait between page fetches (default: 0)",
    )
    crawl_parser.add_argument(
        "--settle-ms",
        type=int,
        default=None,
        help=(
            "Milliseconds to wait after assets settle for late injections "
            f"(default: 1000; {DEFAULT_DATA_SETTLE_MS} in fast --data-only mode)"
        ),
    )
    crawl_parser.add_argument(
        "--image-wait-ms",
        type=int,
        default=5000,
        help="Per-image fallback timeout during DOM wait (default: 5000)",
    )
    crawl_parser.add_argument(
        "--asset-quiet-ms",
        type=int,
        default=750,
        help="Stop after this many ms with no image/css/font traffic (default: 750)",
    )
    crawl_parser.add_argument(
        "--page-asset-timeout-ms",
        type=int,
        default=60_000,
        help="Hard cap for asset quiet wait per page in ms (default: 60000)",
    )
    crawl_parser.add_argument(
        "--diagram-wait-ms",
        type=int,
        default=30_000,
        help="Max milliseconds to wait for lazy diagrams to render (default: 30000)",
    )
    crawl_parser.add_argument(
        "--asset-concurrency",
        type=int,
        default=12,
        help="Parallel asset downloads per page (default: 12)",
    )
    crawl_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=(
            "Navigation timeout in seconds per page (default: 60; "
            f"{DEFAULT_DATA_NAVIGATION_TIMEOUT_MS // 1000} in fast --data-only mode)"
        ),
    )
    crawl_parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Parallel browser tabs for crawling pages (default: 20)",
    )
    crawl_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch pages even when HTML already exists in output",
    )
    crawl_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide per-page crawl progress output",
    )
    crawl_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Stop after saving this many pages (default: unlimited)",
    )
    crawl_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Skip URLs matching path glob (repeatable), e.g. /community/*",
    )
    crawl_parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Only follow URLs matching path glob (repeatable), e.g. /properties/*; "
            "start URLs are always crawled"
        ),
    )
    crawl_parser.add_argument(
        "--keep-query",
        action="store_true",
        help=(
            "Save URLs with a query string to their own file (<name>.q<hash>.html) "
            "instead of collapsing them onto the path"
        ),
    )
    crawl_parser.add_argument(
        "--data-sidecar",
        action="store_true",
        help=(
            "Keep JSON scripts in the snapshot and write each page's embedded data "
            "(JSON-LD, inline data scripts) to <page>.data.json for offline parsing"
        ),
    )
    crawl_parser.add_argument(
        "--data-only",
        action="store_true",
        help=(
            "Mirror no assets: save a reduced snapshot (text, meta, links) plus a "
            "<page>.data.json holding only JSON and page-state scripts. Fast: blocks "
            "images, fonts, CSS, media and third-party hosts and skips render waits"
        ),
    )
    crawl_parser.add_argument(
        "--full-render",
        action="store_true",
        help=(
            "With --data-only: load every resource and keep the normal render waits "
            "(chevron clicks, scrolling, image / asset waits) and timeouts"
        ),
    )
    crawl_parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Fast --data-only: also load scripts / XHR / fetch from this host "
            "(repeatable; a host covers its subdomains, globs like *.cloudfront.net)"
        ),
    )
    crawl_parser.add_argument(
        "--wait-for-marker",
        action="append",
        default=[],
        metavar="TEXT",
        help=(
            "Fast --data-only: wait for a <script> containing this text (repeatable; "
            "default: the page-state markers, including --data-marker)"
        ),
    )
    crawl_parser.add_argument(
        "--marker-timeout-ms",
        type=int,
        default=DEFAULT_MARKER_TIMEOUT_MS,
        help=(
            "Fast --data-only: max ms to wait for a marker; stops early once the page "
            f"has loaded (default: {DEFAULT_MARKER_TIMEOUT_MS}; 0 skips the wait)"
        ),
    )
    crawl_parser.add_argument(
        "--order",
        choices=CRAWL_ORDERS,
        default=None,
        help=(
            "Crawl queue order: 'section' fetches every URL of the first path section "
            "seen before the next section; 'discovered' is plain breadth-first; "
            "'interleave' round-robins across sections so e.g. listing pages arrive "
            "while results pages are still being fetched (default: section; "
            "interleave with --data-only)"
        ),
    )
    crawl_parser.add_argument(
        "--stats",
        action="store_true",
        help="Print pages per minute and seconds per page at the end",
    )
    crawl_parser.add_argument(
        "--data-marker",
        action="append",
        default=[],
        metavar="TEXT",
        help=(
            "Extra substring marking an inline script as page state (repeatable; "
            f"built in: {', '.join(DATA_MARKERS)})"
        ),
    )
    crawl_parser.add_argument(
        "--gzip",
        action="store_true",
        help="With --data-only: write <page>.html.gz and <page>.data.json.gz",
    )
    _add_error_marker_argument(crawl_parser)
    crawl_parser.add_argument(
        "--retry-failed",
        type=int,
        default=DEFAULT_RETRY_FAILED,
        metavar="N",
        help=(
            "Re-queue each URL that was not saved (error page, timeout, failure) up "
            "to N times at the end of the crawl before counting it failed "
            f"(default: {DEFAULT_RETRY_FAILED}; 0 disables)"
        ),
    )
    crawl_parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        metavar="SECONDS",
        help=(
            "Seconds to wait before each retry round "
            f"(default: {DEFAULT_RETRY_DELAY_SECONDS:g})"
        ),
    )
    crawl_parser.add_argument(
        "--backoff",
        type=float,
        default=DEFAULT_BACKOFF_SECONDS,
        metavar="SECONDS",
        help=(
            "On HTTP 429 (or 503 with Retry-After) without a Retry-After header, pause "
            "all tabs this long, doubling per consecutive rate-limited pause "
            f"(default: {DEFAULT_BACKOFF_SECONDS:g})"
        ),
    )
    crawl_parser.add_argument(
        "--max-backoff",
        type=float,
        default=DEFAULT_MAX_BACKOFF_SECONDS,
        metavar="SECONDS",
        help=(
            "Longest rate-limit pause, also capping Retry-After "
            f"(default: {DEFAULT_MAX_BACKOFF_SECONDS:g})"
        ),
    )
    crawl_parser.add_argument(
        "--adaptive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "After each rate-limit pause, add --adaptive-step seconds to the per-page "
            "delay for the rest of the run (default: on with --data-only)"
        ),
    )
    crawl_parser.add_argument(
        "--adaptive-step",
        type=float,
        default=DEFAULT_ADAPTIVE_STEP_SECONDS,
        metavar="SECONDS",
        help=(
            "Seconds added to the per-page delay per rate-limit pause with --adaptive "
            f"(default: {DEFAULT_ADAPTIVE_STEP_SECONDS:g})"
        ),
    )
    crawl_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended when login is required)",
    )
    crawl_parser.add_argument(
        "--skip-login-wait",
        action="store_true",
        help="Start crawling immediately without waiting for Enter",
    )

    slim_parser = subparsers.add_parser(
        "slim",
        help="Convert an existing saved site in place to the --data-only form",
    )
    slim_parser.add_argument(
        "directory",
        type=Path,
        help="Saved site folder (e.g. output/www.example.com); _assets is left alone",
    )
    slim_parser.add_argument(
        "--gzip",
        action="store_true",
        help="Rewrite each file as <name>.gz and remove the plain file",
    )
    slim_parser.add_argument(
        "--data-marker",
        action="append",
        default=[],
        metavar="TEXT",
        help="Extra page-state marker for sidecar filtering (repeatable)",
    )
    slim_parser.add_argument(
        "--drop-errors",
        action="store_true",
        help=(
            "Instead of slimming: delete saved error pages (title / __NEXT_DATA__ page "
            "matching the error patterns) together with their sidecars"
        ),
    )
    slim_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --drop-errors: list what would be deleted, delete nothing",
    )
    _add_error_marker_argument(slim_parser)

    return parser


def _add_error_marker_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--error-marker",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Extra error-page pattern (repeatable): one starting with / is a URL path "
            f"(whole segments; built in: {', '.join(DEFAULT_ERROR_PATHS)}), anything "
            "else a <title> substring (case-insensitive; built in: "
            f"{', '.join(DEFAULT_ERROR_TITLES)})"
        ),
    )


def _format_bytes(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{count} B"


def format_crawl_stats(result: CrawlResult, concurrency: int) -> str:
    """One line of crawl throughput: pages / minute and seconds per page."""
    pages = result.pages_saved
    seconds = result.crawl_seconds
    pacing = (
        f"; final delay {result.final_delay:g} s/page, "
        f"{result.rate_limit_pauses} rate-limit pause(s)"
    )
    if pages <= 0 or seconds <= 0:
        return f"Stats: {pages} new page(s) in {seconds:.1f} s{pacing}"
    return (
        f"Stats: {pages} new page(s) in {seconds:.1f} s: "
        f"{pages * 60 / seconds:.1f} pages/min, {seconds / pages:.2f} s/page wall, "
        f"{result.page_seconds / pages:.2f} s/page per tab "
        f"(concurrency {concurrency}){pacing}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command: str | None = args.command

    if command == "doctor":
        try:
            asyncio.run(run_doctor())
        except Exception as exc:
            print(f"Doctor check failed: {exc}", file=sys.stderr)
            print(
                "Install browser binaries with: playwright install chromium",
                file=sys.stderr,
            )
            return 1

        print("Doctor check passed: Playwright and Chromium are working.")
        return 0

    if command == "gui":
        if args.classic:
            from folio.gui import run_gui

            run_gui()
            return 0

        from folio.webui.app import run_webui

        return run_webui(browser=args.browser)

    if command == "slim":
        from folio.error_pages import ErrorRules
        from folio.slim import drop_error_pages, slim_site

        directory: Path = args.directory
        if not directory.is_dir():
            print(f"Not a directory: {directory}", file=sys.stderr)
            return 1
        if args.dry_run and not args.drop_errors:
            print("--dry-run requires --drop-errors", file=sys.stderr)
            return 1
        if args.drop_errors:
            drop = drop_error_pages(
                directory,
                rules=ErrorRules.build(args.error_marker),
                dry_run=args.dry_run,
            )
            verb = "Would delete" if args.dry_run else "Deleted"
            print(
                f"{verb} {drop.error_pages} error page(s) of {drop.pages_checked} "
                f"and {drop.orphan_sidecars} orphan error sidecar(s): "
                f"{drop.files_deleted} file(s); {drop.failed} unreadable"
            )
            return 1 if drop.failed else 0
        stats = slim_site(
            directory, gzip_output=args.gzip, extra_markers=tuple(args.data_marker)
        )
        print(
            f"Slimmed {stats.html_files} page(s): "
            f"{_format_bytes(stats.html_before)} -> {_format_bytes(stats.html_after)}; "
            f"{stats.sidecar_files} sidecar(s): "
            f"{_format_bytes(stats.sidecar_before)} -> "
            f"{_format_bytes(stats.sidecar_after)}; "
            f"{stats.changed} file(s) rewritten, {stats.failed} failed"
        )
        return 1 if stats.failed else 0

    if command == "crawl":
        if args.gzip and not args.data_only:
            print("--gzip requires --data-only", file=sys.stderr)
            return 1
        if args.retry_failed < 0:
            print("--retry-failed must be >= 0", file=sys.stderr)
            return 1
        for flag, value in (
            ("--backoff", args.backoff),
            ("--max-backoff", args.max_backoff),
            ("--adaptive-step", args.adaptive_step),
        ):
            if value < 0:
                print(f"{flag} must be >= 0", file=sys.stderr)
                return 1
        fast = args.data_only and not args.full_render
        order = args.order or (
            DEFAULT_DATA_ONLY_CRAWL_ORDER if args.data_only else DEFAULT_CRAWL_ORDER
        )
        settle_ms = args.settle_ms
        if settle_ms is None:
            settle_ms = DEFAULT_DATA_SETTLE_MS if fast else 1000
        timeout_ms = (
            args.timeout * 1000
            if args.timeout is not None
            else (DEFAULT_DATA_NAVIGATION_TIMEOUT_MS if fast else 60_000)
        )
        try:
            result = asyncio.run(
                run_crawl(
                    args.url[0],
                    args.output,
                    extra_start_urls=tuple(args.url[1:]),
                    include_patterns=tuple(args.include),
                    keep_query=args.keep_query,
                    data_sidecar=args.data_sidecar,
                    data_only=args.data_only,
                    data_markers=tuple(args.data_marker),
                    gzip_output=args.gzip,
                    full_render=args.full_render,
                    allow_hosts=tuple(args.allow_host),
                    wait_markers=tuple(args.wait_for_marker),
                    marker_timeout_ms=args.marker_timeout_ms,
                    order=order,
                    error_markers=tuple(args.error_marker),
                    retry_failed=args.retry_failed,
                    retry_delay=args.retry_delay,
                    backoff=args.backoff,
                    max_backoff=args.max_backoff,
                    adaptive=args.adaptive,
                    adaptive_step=args.adaptive_step,
                    headed=not args.headless,
                    skip_login_wait=args.skip_login_wait,
                    delay_seconds=args.delay,
                    max_pages=args.max_pages,
                    settle_ms=settle_ms,
                    image_wait_ms=args.image_wait_ms,
                    asset_quiet_ms=args.asset_quiet_ms,
                    page_asset_timeout_ms=args.page_asset_timeout_ms,
                    diagram_wait_ms=args.diagram_wait_ms,
                    asset_concurrency=args.asset_concurrency,
                    page_concurrency=args.concurrency,
                    navigation_timeout_ms=timeout_ms,
                    resume=not args.force,
                    exclude_patterns=tuple(args.exclude),
                    verbose=not args.quiet,
                )
            )
        except Exception as exc:
            print(f"Crawl failed: {exc}", file=sys.stderr)
            return 1

        print(
            f"Crawl complete: saved {result.pages_saved} new page(s), "
            f"skipped {result.pages_skipped} existing, under "
            f"{result.output_dir.resolve()}"
        )
        failed = result.pages_failed
        if isinstance(failed, int) and failed > 0:
            print(
                f"{failed} page(s) failed (error pages, timeouts or errors) and were "
                "left unsaved; a resumed crawl fetches them again"
            )
        if args.stats:
            print(format_crawl_stats(result, args.concurrency))
        return 0

    parser.print_help()
    return 0
