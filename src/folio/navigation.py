"""Resilient page navigation for slow or heavy sites."""

from __future__ import annotations

import sys
from typing import Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000


async def goto_page(
    page: Page,
    url: str,
    *,
    timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
    fallback_commit: bool = True,
) -> bool:
    """Navigate to a URL and wait for ``domcontentloaded``.

    With ``fallback_commit`` a timed-out page is retried with the lighter
    ``commit`` wait; without it (data-only crawls, where a half-loaded page is
    worse than none) the page is skipped.
    """
    waits: tuple[Literal["domcontentloaded", "commit"], ...] = (
        ("domcontentloaded", "commit") if fallback_commit else ("domcontentloaded",)
    )
    for wait_until in waits:
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            if wait_until == waits[-1]:
                print(
                    f"Warning: timed out loading {url} — skipping.",
                    file=sys.stderr,
                    flush=True,
                )
                return False
    return False
