"""Same-domain web crawler with interactive login support."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from folio.assets import AssetMirror
from folio.capture import (
    AssetQuietTracker,
    NetworkCapture,
    block_media_requests,
    discover_links_with_interaction,
    prepare_page,
)
from folio.navigation import DEFAULT_NAVIGATION_TIMEOUT_MS, goto_page
from folio.urls import (
    is_excluded_url,
    is_included_url,
    normalize_url,
    output_path_to_url,
    same_host,
    url_path_depth,
    url_path_section,
    url_to_output_path,
)

DEFAULT_LOGIN_MESSAGE = (
    "Browser opened. Log in if needed, then press Enter here to start crawling..."
)
DEFAULT_ASSET_CONCURRENCY = 12
DEFAULT_PAGE_CONCURRENCY = 20


@dataclass(frozen=True)
class CrawlResult:
    start_url: str
    pages_saved: int
    pages_skipped: int
    output_dir: Path


async def extract_links(page: Page) -> list[str]:
    """Return absolute href values from anchor tags on the current page."""
    raw_links: list[str] = await page.eval_on_selector_all(
        "a[href]",
        "elements => elements.map(element => element.href)",
    )
    return [link for link in raw_links if link]


def extract_links_from_saved_html(
    html: str,
    *,
    html_path: Path,
    output_dir: Path,
    root_url: str,
    exclude_patterns: tuple[str, ...] = (),
    include_patterns: tuple[str, ...] = (),
) -> list[str]:
    """Discover crawl URLs from an already-saved offline HTML file."""
    soup = BeautifulSoup(html, "html.parser")
    discovered: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str) or href.startswith("#"):
            continue
        original = anchor.get("data-folio-url")
        if isinstance(original, str) and original:
            href = original  # written by the asset mirror; keeps the query string
        try:
            if href.startswith(("http://", "https://")):
                normalized = normalize_url(href)
            elif href.endswith(".html"):
                target_path = (html_path.parent / href).resolve()
                url = output_path_to_url(target_path, output_dir, root_url)
                if url is None:
                    continue
                normalized = normalize_url(url)
            else:
                continue
        except ValueError:
            continue
        if (
            same_host(normalized, root_url)
            and not is_excluded_url(normalized, exclude_patterns)
            and is_included_url(normalized, include_patterns)
        ):
            discovered.append(normalized)
    return discovered


async def run_crawl(
    start_url: str,
    output_dir: Path,
    *,
    headed: bool = True,
    skip_login_wait: bool = False,
    login_prompt: Callable[[str], None] | None = None,
    delay_seconds: float = 0.0,
    max_pages: int | None = None,
    settle_ms: int = 1000,
    image_wait_ms: int = 5000,
    asset_quiet_ms: int = 750,
    page_asset_timeout_ms: int = 60_000,
    diagram_wait_ms: int = 30_000,
    click_delay_ms: int = 250,
    asset_concurrency: int = DEFAULT_ASSET_CONCURRENCY,
    page_concurrency: int = DEFAULT_PAGE_CONCURRENCY,
    navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
    resume: bool = True,
    exclude_patterns: tuple[str, ...] = (),
    include_patterns: tuple[str, ...] = (),
    keep_query: bool = False,
    extra_start_urls: tuple[str, ...] = (),
    verbose: bool = True,
) -> CrawlResult:
    """Open start_url, wait for optional login confirmation, then crawl.

    ``include_patterns`` restrict the crawl to matching URLs (start URLs always
    allowed); ``keep_query`` gives query-string URLs their own files;
    ``extra_start_urls`` are additional same-host seeds.
    """
    root_url = normalize_url(start_url)
    if is_excluded_url(root_url, exclude_patterns):
        msg = f"Start URL is excluded by pattern: {root_url}"
        raise ValueError(msg)
    seeds: list[str] = []
    for extra in extra_start_urls:
        normalized = normalize_url(extra)
        if not same_host(normalized, root_url):
            msg = f"Extra start URL is on another host: {extra}"
            raise ValueError(msg)
        seeds.append(normalized)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed)
        try:
            pages_saved, pages_skipped = await _crawl_with_browser(
                browser,
                root_url,
                output_dir,
                skip_login_wait=skip_login_wait,
                login_prompt=login_prompt,
                delay_seconds=delay_seconds,
                max_pages=max_pages,
                settle_ms=settle_ms,
                image_wait_ms=image_wait_ms,
                asset_quiet_ms=asset_quiet_ms,
                page_asset_timeout_ms=page_asset_timeout_ms,
                diagram_wait_ms=diagram_wait_ms,
                click_delay_ms=click_delay_ms,
                asset_concurrency=asset_concurrency,
                page_concurrency=page_concurrency,
                navigation_timeout_ms=navigation_timeout_ms,
                resume=resume,
                exclude_patterns=exclude_patterns,
                include_patterns=include_patterns,
                keep_query=keep_query,
                extra_start_urls=tuple(seeds),
                verbose=verbose,
            )
        finally:
            await browser.close()

    return CrawlResult(
        start_url=root_url,
        pages_saved=pages_saved,
        pages_skipped=pages_skipped,
        output_dir=output_dir,
    )


async def _crawl_with_browser(
    browser: Browser,
    root_url: str,
    output_dir: Path,
    *,
    skip_login_wait: bool,
    login_prompt: Callable[[str], None] | None,
    delay_seconds: float,
    max_pages: int | None,
    settle_ms: int,
    image_wait_ms: int,
    asset_quiet_ms: int,
    page_asset_timeout_ms: int,
    diagram_wait_ms: int,
    click_delay_ms: int,
    asset_concurrency: int,
    page_concurrency: int,
    navigation_timeout_ms: int,
    resume: bool,
    exclude_patterns: tuple[str, ...],
    include_patterns: tuple[str, ...] = (),
    keep_query: bool = False,
    extra_start_urls: tuple[str, ...] = (),
    verbose: bool,
) -> tuple[int, int]:
    context = await browser.new_context()
    context.set_default_navigation_timeout(navigation_timeout_ms)
    context.set_default_timeout(navigation_timeout_ms)
    asset_mirror = AssetMirror(
        context.request,
        output_dir,
        concurrency=asset_concurrency,
        keep_query=keep_query,
    )

    login_page = await context.new_page()
    try:
        if not await goto_page(
            login_page,
            root_url,
            timeout_ms=navigation_timeout_ms,
        ):
            msg = f"Could not load login page: {root_url}"
            raise RuntimeError(msg)
        if not skip_login_wait:
            prompt = login_prompt or _default_login_prompt
            prompt(DEFAULT_LOGIN_MESSAGE)
    finally:
        await login_page.close()

    try:
        return await _crawl_pages_parallel(
            context,
            asset_mirror,
            root_url,
            output_dir,
            max_pages=max_pages,
            settle_ms=settle_ms,
            image_wait_ms=image_wait_ms,
            asset_quiet_ms=asset_quiet_ms,
            page_asset_timeout_ms=page_asset_timeout_ms,
            diagram_wait_ms=diagram_wait_ms,
            click_delay_ms=click_delay_ms,
            page_concurrency=max(1, page_concurrency),
            navigation_timeout_ms=navigation_timeout_ms,
            delay_seconds=delay_seconds,
            resume=resume,
            exclude_patterns=exclude_patterns,
            include_patterns=include_patterns,
            keep_query=keep_query,
            extra_start_urls=extra_start_urls,
            verbose=verbose,
        )
    finally:
        await context.close()


async def _crawl_pages_parallel(
    context: BrowserContext,
    asset_mirror: AssetMirror,
    root_url: str,
    output_dir: Path,
    *,
    max_pages: int | None,
    settle_ms: int,
    image_wait_ms: int,
    asset_quiet_ms: int,
    page_asset_timeout_ms: int,
    diagram_wait_ms: int,
    click_delay_ms: int,
    page_concurrency: int,
    navigation_timeout_ms: int,
    delay_seconds: float,
    resume: bool,
    exclude_patterns: tuple[str, ...],
    include_patterns: tuple[str, ...] = (),
    keep_query: bool = False,
    extra_start_urls: tuple[str, ...] = (),
    verbose: bool,
) -> tuple[int, int]:
    queue: asyncio.PriorityQueue[tuple[int, int, int, str]] = asyncio.PriorityQueue()
    section_ranks: dict[str, int] = {"": 0}
    section_lock = asyncio.Lock()
    enqueue_counter = 0
    enqueue_lock = asyncio.Lock()

    async def enqueue_url(url: str, *, seed: bool = False) -> None:
        nonlocal enqueue_counter
        if is_excluded_url(url, exclude_patterns):
            return
        if not seed and not is_included_url(url, include_patterns):
            return
        section = url_path_section(url)
        async with section_lock:
            if section not in section_ranks:
                section_ranks[section] = len(section_ranks)
            section_rank = section_ranks[section]
        depth = url_path_depth(url)
        async with enqueue_lock:
            enqueue_counter += 1
            order = enqueue_counter
        await queue.put((section_rank, depth, order, url))

    await enqueue_url(root_url, seed=True)
    for seed_url in extra_start_urls:
        await enqueue_url(seed_url, seed=True)

    visited: set[str] = set()
    visited_lock = asyncio.Lock()
    pages_saved = 0
    pages_skipped = 0
    pages_lock = asyncio.Lock()
    stop = False
    stop_lock = asyncio.Lock()
    in_flight = 0
    flight_lock = asyncio.Lock()

    async def should_stop() -> bool:
        async with stop_lock:
            return stop

    async def set_stop() -> None:
        nonlocal stop
        async with stop_lock:
            stop = True

    async def worker_done() -> bool:
        async with flight_lock:
            return in_flight == 0 and queue.empty()

    async def worker() -> None:
        nonlocal pages_saved, pages_skipped, in_flight
        page = await context.new_page()
        await block_media_requests(page)
        capture = NetworkCapture()
        capture.attach(page)
        asset_tracker = AssetQuietTracker()
        asset_tracker.attach(page)
        try:
            while True:
                if await should_stop() and await worker_done():
                    break

                try:
                    _, _, _, url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    if await worker_done():
                        break
                    await asyncio.sleep(0.05)
                    continue

                async with flight_lock:
                    in_flight += 1

                try:
                    async with visited_lock:
                        if url in visited:
                            continue
                        async with pages_lock:
                            if max_pages is not None and pages_saved >= max_pages:
                                await set_stop()
                                continue
                        visited.add(url)

                    out_path = url_to_output_path(
                        url, output_dir, keep_query=keep_query
                    )
                    discovered: list[str] | None
                    if resume and out_path.is_file():
                        if verbose:
                            print(
                                f"Skipping (exists): {url}",
                                file=sys.stderr,
                                flush=True,
                            )
                        html = out_path.read_text(encoding="utf-8")
                        discovered = extract_links_from_saved_html(
                            html,
                            html_path=out_path,
                            output_dir=output_dir,
                            root_url=root_url,
                            exclude_patterns=exclude_patterns,
                            include_patterns=include_patterns,
                        )
                        async with pages_lock:
                            pages_skipped += 1
                    else:
                        if verbose:
                            async with pages_lock:
                                label_num = pages_saved + 1
                            print(
                                f"Crawling ({label_num}): {url}",
                                file=sys.stderr,
                                flush=True,
                            )
                        discovered = await _save_page(
                            page,
                            capture,
                            asset_mirror,
                            url=url,
                            root_url=root_url,
                            output_dir=output_dir,
                            settle_ms=settle_ms,
                            image_wait_ms=image_wait_ms,
                            asset_quiet_ms=asset_quiet_ms,
                            page_asset_timeout_ms=page_asset_timeout_ms,
                            diagram_wait_ms=diagram_wait_ms,
                            click_delay_ms=click_delay_ms,
                            navigation_timeout_ms=navigation_timeout_ms,
                            exclude_patterns=exclude_patterns,
                            include_patterns=include_patterns,
                            keep_query=keep_query,
                            asset_tracker=asset_tracker,
                        )
                        if discovered is None:
                            continue
                        async with pages_lock:
                            pages_saved += 1
                            if max_pages is not None and pages_saved >= max_pages:
                                await set_stop()

                        if delay_seconds > 0:
                            await asyncio.sleep(delay_seconds)

                    if await should_stop():
                        continue

                    for link in discovered:
                        async with visited_lock:
                            if link in visited or await should_stop():
                                continue
                        await enqueue_url(link)
                except Exception as exc:
                    print(
                        f"Warning: failed to process {url}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                finally:
                    async with flight_lock:
                        in_flight -= 1
        finally:
            await page.close()

    workers = [asyncio.create_task(worker()) for _ in range(page_concurrency)]
    await asyncio.gather(*workers)
    return pages_saved, pages_skipped


async def _save_page(
    page: Page,
    capture: NetworkCapture,
    asset_mirror: AssetMirror,
    *,
    url: str,
    root_url: str,
    output_dir: Path,
    settle_ms: int,
    image_wait_ms: int,
    asset_quiet_ms: int,
    page_asset_timeout_ms: int,
    diagram_wait_ms: int,
    click_delay_ms: int,
    navigation_timeout_ms: int,
    exclude_patterns: tuple[str, ...],
    asset_tracker: AssetQuietTracker,
    include_patterns: tuple[str, ...] = (),
    keep_query: bool = False,
) -> list[str] | None:
    """Fetch one page and return same-host links discovered on it."""
    if not await goto_page(page, url, timeout_ms=navigation_timeout_ms):
        return None

    raw_links = await discover_links_with_interaction(
        page,
        click_delay_ms=click_delay_ms,
    )
    await prepare_page(
        page,
        settle_ms=settle_ms,
        image_wait_ms=image_wait_ms,
        asset_quiet_ms=asset_quiet_ms,
        page_asset_timeout_ms=page_asset_timeout_ms,
        diagram_wait_ms=diagram_wait_ms,
        click_delay_ms=click_delay_ms,
        skip_interact=True,
        asset_tracker=asset_tracker,
    )
    out_path = url_to_output_path(url, output_dir, keep_query=keep_query)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    network_urls = set(capture.urls)
    try:
        html = await asset_mirror.mirror_page(
            page,
            page_url=url,
            html_path=out_path,
            root_url=root_url,
            extra_urls=network_urls,
        )
    except Exception as exc:
        print(
            f"Warning: asset mirroring failed for {url}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return None

    out_path.write_text(html, encoding="utf-8")
    capture.clear()

    discovered: list[str] = []
    for link in raw_links:
        try:
            normalized = normalize_url(link, base=url)
        except ValueError:
            continue
        if (
            same_host(normalized, root_url)
            and not is_excluded_url(normalized, exclude_patterns)
            and is_included_url(normalized, include_patterns)
        ):
            discovered.append(normalized)
    return discovered


def _default_login_prompt(message: str) -> None:
    input(message)
