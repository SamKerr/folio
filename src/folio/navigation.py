"""Resilient page navigation for slow or heavy sites."""

from __future__ import annotations

import sys

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000


async def goto_page(
    page: Page,
    url: str,
    *,
    timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
) -> bool:
    """Navigate to a URL, falling back to a lighter wait if the page is slow."""
    for wait_until in ("domcontentloaded", "commit"):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            if wait_until == "commit":
                print(
                    f"Warning: timed out loading {url} — skipping.",
                    file=sys.stderr,
                    flush=True,
                )
                return False
    return False
