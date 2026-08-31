"""Build argv for launching `folio crawl` as a subprocess."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CrawlSettings:
    url: str
    output_dir: Path = field(default_factory=lambda: Path("output"))
    concurrency: int = 20
    image_wait_ms: int = 5000
    asset_quiet_ms: int = 750
    page_asset_timeout_ms: int = 60_000
    settle_ms: int = 1000
    timeout_secs: int = 60
    asset_concurrency: int = 12
    max_pages: int | None = None
    force: bool = False
    exclude_patterns: list[str] = field(default_factory=list)


def build_crawl_argv(settings: CrawlSettings) -> list[str]:
    """Return argv for `python -m folio crawl ...`."""
    argv = [
        sys.executable,
        "-m",
        "folio",
        "crawl",
        settings.url.strip(),
        "--output",
        str(settings.output_dir),
        "--concurrency",
        str(settings.concurrency),
        "--image-wait-ms",
        str(settings.image_wait_ms),
        "--asset-quiet-ms",
        str(settings.asset_quiet_ms),
        "--page-asset-timeout-ms",
        str(settings.page_asset_timeout_ms),
        "--settle-ms",
        str(settings.settle_ms),
        "--timeout",
        str(settings.timeout_secs),
        "--asset-concurrency",
        str(settings.asset_concurrency),
    ]
    if settings.max_pages is not None:
        argv.extend(["--max-pages", str(settings.max_pages)])
    if settings.force:
        argv.append("--force")
    for pattern in settings.exclude_patterns:
        cleaned = pattern.strip()
        if cleaned:
            argv.extend(["--exclude", cleaned])
    return argv
