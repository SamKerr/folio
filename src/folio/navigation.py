"""Resilient page navigation for slow or heavy sites."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Literal

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from folio.rate_limit import parse_retry_after

DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class NavigationResult:
    """Outcome of :func:`goto_page`; truthy when the page loaded.

    ``status`` / ``url`` are the final (post-redirect) response's HTTP status and
    URL, when Playwright returned a response; ``retry_after`` is its ``Retry-After``
    header in seconds, when present and parseable.
    """

    ok: bool
    status: int | None = None
    url: str | None = None
    retry_after: float | None = None

    def __bool__(self) -> bool:
        return self.ok


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _response_retry_after(response: Any) -> float | None:
    headers = getattr(response, "headers", None)
    if not isinstance(headers, dict):
        return None
    for name, value in headers.items():
        if isinstance(name, str) and name.lower() == "retry-after":
            return parse_retry_after(value if isinstance(value, str) else None)
    return None


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
                retry_after=_response_retry_after(response),
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
