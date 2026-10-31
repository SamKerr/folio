"""Page load preparation and network asset capture."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from playwright.async_api import Page, Request, Response, Route

from folio.assets import is_downloadable_asset_url, is_media_content_type
from folio.browser_scripts import (
    DISCOVER_LINKS_WITH_INTERACTION,
    INTERACT_WITH_PAGE,
    SCROLL_PAGE,
    WAIT_FOR_DIAGRAMS,
    WAIT_FOR_IMAGES,
)

PAGE_LINK_SELECTOR = 'a[href], link[rel~="next"][href], link[rel~="prev"][href]'
"""Anchors plus non-anchor pagination links (``<link rel="next">``)."""
DEFAULT_CLICK_DELAY_MS = 250
DEFAULT_ASSET_QUIET_MS = 750
DEFAULT_PAGE_ASSET_TIMEOUT_MS = 60_000
DEFAULT_DIAGRAM_WAIT_MS = 30_000

QUIET_RESOURCE_TYPES = frozenset({"image", "stylesheet", "font"})

STATIC_CONTENT_PREFIXES = (
    "text/css",
    "image/",
    "font/",
    "application/font",
)

STATIC_EXTENSIONS = (
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".avif",
)


def _is_quiet_asset_request(request: Request) -> bool:
    if request.method.upper() != "GET":
        return False
    if request.resource_type in QUIET_RESOURCE_TYPES:
        return True
    url = request.url
    if not url.startswith(("http://", "https://")):
        return False
    if not is_downloadable_asset_url(url):
        return False
    path = urlparse(url).path.lower()
    return path.endswith(STATIC_EXTENSIONS) or path.endswith(".css")


class NetworkCapture:
    """Collect static resource URLs loaded while a page is open."""

    def __init__(self) -> None:
        self.urls: set[str] = set()

    def attach(self, page: Page) -> None:
        page.on("response", self._on_response)

    def clear(self) -> None:
        self.urls.clear()

    def _on_response(self, response: Response) -> None:
        if response.status >= 400:
            return
        if response.request.resource_type == "media":
            return
        if response.request.method.upper() != "GET":
            return
        url = response.url
        if not url.startswith(("http://", "https://")):
            return
        if not is_downloadable_asset_url(url):
            return
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if is_media_content_type(content_type):
            return
        if _is_static_asset(url, content_type):
            self.urls.add(url)


class AssetQuietTracker:
    """Track in-flight image/css/font requests until the network goes quiet."""

    def __init__(self) -> None:
        self._pending = 0
        self._attached = False

    @property
    def pending(self) -> int:
        return self._pending

    def attach(self, page: Page) -> None:
        if self._attached:
            return
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_finished)
        page.on("requestfailed", self._on_request_finished)
        self._attached = True

    def reset(self) -> None:
        self._pending = 0

    def _on_request(self, request: Request) -> None:
        if _is_quiet_asset_request(request):
            self._pending += 1

    def _on_request_finished(self, request: Request) -> None:
        if _is_quiet_asset_request(request):
            self._pending = max(0, self._pending - 1)

    async def wait_for_quiet(
        self,
        *,
        quiet_ms: int,
        timeout_ms: int,
    ) -> None:
        if quiet_ms <= 0:
            return
        deadline = time.monotonic() + max(timeout_ms, quiet_ms) / 1000
        quiet_seconds = quiet_ms / 1000
        quiet_since: float | None = None

        while time.monotonic() < deadline:
            if self._pending > 0:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= quiet_seconds:
                return
            await asyncio.sleep(0.05)


def _is_static_asset(url: str, content_type: str) -> bool:
    if content_type.startswith(("text/javascript", "application/javascript")):
        return False
    if is_media_content_type(content_type):
        return False
    if content_type.startswith(STATIC_CONTENT_PREFIXES):
        return True
    if content_type in {"application/octet-stream", ""}:
        path = urlparse(url).path.lower()
        return path.endswith(STATIC_EXTENSIONS)
    return False


async def block_media_requests(page: Page) -> None:
    """Stop the browser from downloading video/audio during crawl."""

    async def handle(route: Route) -> None:
        if route.request.resource_type == "media":
            await route.abort()
            return
        await route.continue_()

    await page.route("**/*", handle)


async def interact_with_page(
    page: Page,
    *,
    click_delay_ms: int = DEFAULT_CLICK_DELAY_MS,
) -> None:
    """Expand collapsed chevrons and accordions so hidden links and content load."""
    if click_delay_ms <= 0:
        return
    await page.evaluate(INTERACT_WITH_PAGE, click_delay_ms)


async def discover_links_with_interaction(
    page: Page,
    *,
    click_delay_ms: int = DEFAULT_CLICK_DELAY_MS,
) -> list[str]:
    """Return hrefs found after expanding chevrons and accordion sections."""
    if click_delay_ms <= 0:
        fallback_links: list[str] = await page.eval_on_selector_all(
            PAGE_LINK_SELECTOR,
            "elements => elements.map(element => element.href)",
        )
        return [link for link in fallback_links if link]
    raw_links: list[str] = await page.evaluate(
        DISCOVER_LINKS_WITH_INTERACTION,
        click_delay_ms,
    )
    return [link for link in raw_links if link]


async def prepare_page(
    page: Page,
    *,
    settle_ms: int = 1000,
    image_wait_ms: int = 5000,
    asset_quiet_ms: int = DEFAULT_ASSET_QUIET_MS,
    page_asset_timeout_ms: int = DEFAULT_PAGE_ASSET_TIMEOUT_MS,
    diagram_wait_ms: int = DEFAULT_DIAGRAM_WAIT_MS,
    click_delay_ms: int = DEFAULT_CLICK_DELAY_MS,
    skip_interact: bool = False,
    asset_tracker: AssetQuietTracker | None = None,
) -> None:
    """Expand chevrons, scroll, wait for diagrams/images and quiet asset network."""
    if not skip_interact:
        await interact_with_page(page, click_delay_ms=click_delay_ms)
    await page.evaluate(SCROLL_PAGE)
    await interact_with_page(page, click_delay_ms=click_delay_ms)
    await page.evaluate(SCROLL_PAGE)

    tracker = asset_tracker
    if tracker is None:
        tracker = AssetQuietTracker()
        tracker.attach(page)

    if diagram_wait_ms > 0:
        await page.evaluate(WAIT_FOR_DIAGRAMS, diagram_wait_ms)

    if image_wait_ms > 0:
        await page.evaluate(WAIT_FOR_IMAGES, image_wait_ms)

    if asset_quiet_ms > 0:
        tracker.reset()
        await tracker.wait_for_quiet(
            quiet_ms=asset_quiet_ms,
            timeout_ms=page_asset_timeout_ms,
        )
        if diagram_wait_ms > 0:
            await page.evaluate(WAIT_FOR_DIAGRAMS, diagram_wait_ms)
        if image_wait_ms > 0:
            await page.evaluate(WAIT_FOR_IMAGES, image_wait_ms)

    if settle_ms > 0:
        await asyncio.sleep(settle_ms / 1000)
