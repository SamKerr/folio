"""Resilient page navigation for slow or heavy sites."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class NavigationResult:
    """Outcome of :func:`goto_page`; truthy when the page loaded.

    ``status`` / ``url`` are the final (post-redirect) response's HTTP status and
    URL, when Playwright returned a response.
    """

    ok: bool
    status: int | None = None
    url: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _response_url(response: Any, page: Page) -> str | None:
    for candidate in (getattr(response, "url", None), getattr(page, "url", None)):
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


async def goto_page(
    page: Page,
    url: str,
    *,
    timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
    fallback_commit: bool = True,
) -> NavigationResult:
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
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return NavigationResult(
                True,
                status=_response_status(response),
                url=_response_url(response, page),
            )
        except PlaywrightTimeoutError:
            if wait_until == waits[-1]:
                print(
                    f"Warning: timed out loading {url} — skipping.",
                    file=sys.stderr,
                    flush=True,
                )
                return NavigationResult(False)
    return NavigationResult(False)
