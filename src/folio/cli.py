import argparse
import asyncio
import sys
from pathlib import Path

from folio import __version__
from folio.crawler import run_crawl
from folio.doctor import run_doctor


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

    subparsers.add_parser(
        "gui",
        help="Open the desktop GUI to configure crawls and browse saved sites",
    )

    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Open a URL, wait for login, then crawl same-host pages to disk",
    )
    crawl_parser.add_argument(
        "url",
        help="Starting URL (e.g. https://www.example.com/)",
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
        default=1000,
        help=(
            "Milliseconds to wait after assets settle for late injections "
            "(default: 1000)"
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
        default=60,
        help="Navigation timeout in seconds per page (default: 60)",
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
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended when login is required)",
    )
    crawl_parser.add_argument(
        "--skip-login-wait",
        action="store_true",
        help="Start crawling immediately without waiting for Enter",
    )

    return parser


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
        from folio.gui import run_gui

        run_gui()
        return 0

    if command == "crawl":
        try:
            result = asyncio.run(
                run_crawl(
                    args.url,
                    args.output,
                    headed=not args.headless,
                    skip_login_wait=args.skip_login_wait,
                    delay_seconds=args.delay,
                    max_pages=args.max_pages,
                    settle_ms=args.settle_ms,
                    image_wait_ms=args.image_wait_ms,
                    asset_quiet_ms=args.asset_quiet_ms,
                    page_asset_timeout_ms=args.page_asset_timeout_ms,
                    diagram_wait_ms=args.diagram_wait_ms,
                    asset_concurrency=args.asset_concurrency,
                    page_concurrency=args.concurrency,
                    navigation_timeout_ms=args.timeout * 1000,
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
        return 0

    parser.print_help()
    return 0
