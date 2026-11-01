"""Same-domain web crawler with interactive login support."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from folio.assets import AssetMirror
from folio.capture import (
    PAGE_LINK_SELECTOR,
    AssetQuietTracker,
    NetworkCapture,
    block_media_requests,
    discover_links_with_interaction,
    install_data_request_filter,
    prepare_data_page,
    prepare_page,
)
from folio.error_pages import (
    DEFAULT_ERROR_RULES,
    ErrorRules,
    html_reason,
    status_reason,
    url_reason,
)
from folio.navigation import DEFAULT_NAVIGATION_TIMEOUT_MS, NavigationResult, goto_page
from folio.offline import DATA_MARKERS, extract_data_scripts, prepare_data_snapshot
from folio.ordering import DEFAULT_CRAWL_ORDER, QueueKey, QueueOrdering
from folio.rate_limit import (
    DEFAULT_ADAPTIVE_STEP_SECONDS,
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    RateLimitedError,
    backoff_seconds,
    is_rate_limited,
)
from folio.storage import find_saved_page, read_text, sidecar_path, write_text_atomic
from folio.urls import (
    is_excluded_url,
    is_included_url,
    normalize_url,
    output_path_to_url,
    same_host,
    url_to_output_path,
)

DEFAULT_LOGIN_MESSAGE = (
    "Browser opened. Log in if needed, then press Enter here to start crawling..."
)
DEFAULT_ASSET_CONCURRENCY = 12
DEFAULT_PAGE_CONCURRENCY = 20
DEFAULT_RETRY_FAILED = 1
DEFAULT_RETRY_DELAY_SECONDS = 5.0


@dataclass(frozen=True)
class CrawlResult:
    start_url: str
    pages_saved: int
    pages_skipped: int
    output_dir: Path
    crawl_seconds: float = 0.0
    """Wall time of the crawl phase (after the browser and login page are up)."""
    page_seconds: float = 0.0
    """Summed time spent fetching and saving new pages, across all tabs."""
    pages_failed: int = 0
    """URLs left unsaved after their last attempt (error pages, timeouts, failures);
    a resumed crawl fetches them again."""
    final_delay: float = 0.0
    """Per-page delay at the end of the crawl (``delay_seconds`` plus any adaptive
    increases after rate-limit cool-downs)."""
    rate_limit_pauses: int = 0
    """Cool-downs started because the site answered HTTP 429 / 503 + Retry-After."""


@dataclass(frozen=True)
class _CrawlCounts:
    pages_saved: int
    pages_skipped: int
    crawl_seconds: float
    page_seconds: float
    pages_failed: int = 0
    final_delay: float = 0.0
    rate_limit_pauses: int = 0


@dataclass(frozen=True)
class RateLimitOptions:
    """Cool-down settings for HTTP 429 / 503 + Retry-After (:mod:`folio.rate_limit`)."""

    backoff: float = DEFAULT_BACKOFF_SECONDS
    max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS
    adaptive: bool = False
    adaptive_step: float = DEFAULT_ADAPTIVE_STEP_SECONDS


@dataclass(frozen=True)
class FastDataOptions:
    """Settings for fast data-only crawls (``data_only`` without ``full_render``)."""

    allow_hosts: tuple[str, ...] = ()
    markers: tuple[str, ...] = DATA_MARKERS
    marker_timeout_ms: int = 3000


async def extract_links(page: Page) -> list[str]:
    """Return absolute href values from anchor tags on the current page."""
    raw_links: list[str] = await page.eval_on_selector_all(
        PAGE_LINK_SELECTOR,
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
    candidates = list(soup.find_all("a", href=True))
    for link in soup.find_all("link", href=True):
        rels = link.get("rel")
        if isinstance(rels, str):
            rel_values = {rels.lower()}
        else:
            rel_values = {str(value).lower() for value in (rels or [])}
        if rel_values & {"next", "prev"}:
            candidates.append(link)
    for anchor in candidates:
        href = anchor.get("href")
        if not isinstance(href, str) or href.startswith("#"):
            continue
        original = anchor.get("data-folio-url")
        if isinstance(original, str) and original:
            href = original  # written by the asset mirror; keeps the query string
        try:
            if href.startswith(("http://", "https://")):
                normalized = normalize_url(href)
            elif href.endswith((".html", ".html.gz")):
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
    data_sidecar: bool = False,
    data_only: bool = False,
    data_markers: tuple[str, ...] = (),
    gzip_output: bool = False,
    full_render: bool = False,
    allow_hosts: tuple[str, ...] = (),
    wait_markers: tuple[str, ...] = (),
    marker_timeout_ms: int = 3000,
    order: str = DEFAULT_CRAWL_ORDER,
    error_markers: tuple[str, ...] = (),
    retry_failed: int = DEFAULT_RETRY_FAILED,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS,
    adaptive: bool | None = None,
    adaptive_step: float = DEFAULT_ADAPTIVE_STEP_SECONDS,
    verbose: bool = True,
) -> CrawlResult:
    """Open start_url, wait for optional login confirmation, then crawl.

    ``include_patterns`` restrict the crawl to matching URLs (start URLs always
    allowed); ``keep_query`` gives query-string URLs their own files;
    ``extra_start_urls`` are additional same-host seeds. ``data_sidecar`` keeps
    JSON scripts in the snapshot and writes each page's embedded data (JSON and
    inline data scripts) to ``<page>.data.json`` for offline parsing.

    ``data_only`` mirrors no assets: each page is saved as a reduced snapshot
    (:func:`folio.offline.prepare_data_snapshot`) plus a sidecar holding only JSON
    scripts and inline scripts containing a page-state marker
    (:data:`folio.offline.DATA_MARKERS` plus ``data_markers``). ``gzip_output``
    (data-only only) writes ``<page>.html.gz`` / ``<page>.data.json.gz``.

    Data-only crawls are *fast* unless ``full_render``: requests that carry no
    data are aborted (:func:`folio.capture.request_allowed`; ``allow_hosts`` adds
    hosts to the site), service workers are blocked, and instead of the render
    waits each page waits for ``domcontentloaded`` (no ``commit`` fallback), a
    page-state marker in a ``<script>`` (``wait_markers``, default the sidecar
    markers; at most ``marker_timeout_ms``) and ``settle_ms``.

    ``order`` picks the crawl queue order (:class:`folio.ordering.QueueOrdering`):
    ``section`` (default), ``discovered`` or ``interleave``.

    Error pages are never saved (:mod:`folio.error_pages`): a navigation answered
    with HTTP >= 400, a final URL on an error path, or a page whose ``<title>`` /
    ``__NEXT_DATA__.page`` marks an error (``error_markers`` extend the built-in
    patterns). Any URL left unsaved is re-queued after the rest of the crawl, after
    ``retry_delay`` seconds, up to ``retry_failed`` times, then counted in
    ``CrawlResult.pages_failed``.

    Rate limits: a page answered HTTP 429 (or 503 with ``Retry-After``) pauses every
    tab for ``Retry-After`` seconds, else ``backoff`` doubling per consecutive
    cool-down, at most ``max_backoff``; a saved page resets the doubling. The URL is
    put back on the queue (up to ``retry_failed`` times, then counted failed). With
    ``adaptive`` (default: on for ``data_only``) each cool-down adds
    ``adaptive_step`` seconds to the per-page delay for the rest of the run.
    """
    QueueOrdering(order)  # validate before launching a browser
    if retry_failed < 0:
        msg = "retry_failed must be >= 0"
        raise ValueError(msg)
    for name, value in (
        ("backoff", backoff),
        ("max_backoff", max_backoff),
        ("adaptive_step", adaptive_step),
    ):
        if value < 0:
            msg = f"{name} must be >= 0"
            raise ValueError(msg)
    rate_limit = RateLimitOptions(
        backoff=backoff,
        max_backoff=max_backoff,
        adaptive=data_only if adaptive is None else adaptive,
        adaptive_step=adaptive_step,
    )
    error_rules = ErrorRules.build(error_markers)
    if gzip_output and not data_only:
        msg = "gzip output is only supported for data-only crawls"
        raise ValueError(msg)
    markers = tuple(dict.fromkeys(DATA_MARKERS + tuple(data_markers)))
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
    fast = (
        FastDataOptions(
            allow_hosts=tuple(allow_hosts),
            markers=tuple(wait_markers) or markers,
            marker_timeout_ms=marker_timeout_ms,
        )
        if data_only and not full_render
        else None
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed)
        try:
            counts = await _crawl_with_browser(
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
                data_sidecar=data_sidecar or data_only,
                data_only=data_only,
                data_markers=markers,
                gzip_output=gzip_output,
                fast=fast,
                order=order,
                error_rules=error_rules,
                retry_failed=retry_failed,
                retry_delay=retry_delay,
                rate_limit=rate_limit,
                verbose=verbose,
            )
        finally:
            await browser.close()

    return CrawlResult(
        start_url=root_url,
        pages_saved=counts.pages_saved,
        pages_skipped=counts.pages_skipped,
        output_dir=output_dir,
        crawl_seconds=counts.crawl_seconds,
        page_seconds=counts.page_seconds,
        pages_failed=counts.pages_failed,
        final_delay=counts.final_delay,
        rate_limit_pauses=counts.rate_limit_pauses,
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
    data_sidecar: bool = False,
    data_only: bool = False,
    data_markers: tuple[str, ...] = DATA_MARKERS,
    gzip_output: bool = False,
    fast: FastDataOptions | None = None,
    order: str = DEFAULT_CRAWL_ORDER,
    error_rules: ErrorRules = DEFAULT_ERROR_RULES,
    retry_failed: int = DEFAULT_RETRY_FAILED,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    rate_limit: RateLimitOptions | None = None,
    verbose: bool,
) -> _CrawlCounts:
    context = await browser.new_context(
        service_workers="block" if fast is not None else "allow"
    )
    context.set_default_navigation_timeout(navigation_timeout_ms)
    context.set_default_timeout(navigation_timeout_ms)
    asset_mirror = AssetMirror(
        context.request,
        output_dir,
        concurrency=asset_concurrency,
        keep_query=keep_query,
    )
    asset_mirror.keep_data_scripts = data_sidecar
    asset_mirror.gzip = gzip_output

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
            data_sidecar=data_sidecar,
            data_only=data_only,
            data_markers=data_markers,
            gzip_output=gzip_output,
            fast=fast,
            order=order,
            error_rules=error_rules,
            retry_failed=retry_failed,
            retry_delay=retry_delay,
            rate_limit=rate_limit,
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
    data_sidecar: bool = False,
    data_only: bool = False,
    data_markers: tuple[str, ...] = DATA_MARKERS,
    gzip_output: bool = False,
    fast: FastDataOptions | None = None,
    order: str = DEFAULT_CRAWL_ORDER,
    error_rules: ErrorRules = DEFAULT_ERROR_RULES,
    retry_failed: int = DEFAULT_RETRY_FAILED,
    retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    rate_limit: RateLimitOptions | None = None,
    verbose: bool,
) -> _CrawlCounts:
    queue: asyncio.PriorityQueue[tuple[QueueKey, str]] = asyncio.PriorityQueue()
    ordering = QueueOrdering(order)

    async def enqueue_url(url: str, *, seed: bool = False) -> None:
        if is_excluded_url(url, exclude_patterns):
            return
        if not seed and not is_included_url(url, include_patterns):
            return
        # Synchronous, so atomic within the event loop.
        key = ordering.key(url, seed=seed)
        await queue.put((key, url))

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
    page_seconds = 0.0
    pages_failed = 0
    attempts: dict[str, int] = {}
    pending_retries: list[str] = []
    crawl_started = time.monotonic()
    limits = rate_limit or RateLimitOptions()
    page_delay = max(0.0, delay_seconds)
    gate = asyncio.Event()  # set = open; cleared during a rate-limit cool-down
    gate.set()
    consecutive_limits = 0
    rate_limit_pauses = 0
    rate_attempts: dict[str, int] = {}

    async def should_stop() -> bool:
        async with stop_lock:
            return stop

    async def set_stop() -> None:
        nonlocal stop
        async with stop_lock:
            stop = True

    async def worker_done() -> bool:
        async with flight_lock:
            return in_flight == 0 and queue.empty() and (stop or not pending_retries)

    async def record_failure(url: str) -> None:
        """Hold a URL back for a retry round, or count it failed."""
        nonlocal pages_failed
        async with flight_lock:
            attempts[url] = attempts.get(url, 0) + 1
            if attempts[url] <= retry_failed:
                pending_retries.append(url)
                return
            pages_failed += 1
        if verbose:
            print(
                f"Failed (after {attempts[url]} attempt(s), left unsaved): {url}",
                file=sys.stderr,
                flush=True,
            )

    async def requeue_retries() -> bool:
        """Once the queue has drained and no tab is busy, re-queue the held-back
        failed URLs (after ``retry_delay``). True when it re-queued something."""
        nonlocal in_flight
        if await should_stop():
            return False
        async with flight_lock:
            if in_flight or not queue.empty() or not pending_retries:
                return False
            batch = list(dict.fromkeys(pending_retries))
            pending_retries.clear()
            in_flight += 1  # keeps the other tabs from exiting while we wait
        try:
            if verbose:
                print(
                    f"Retrying {len(batch)} failed URL(s) in {retry_delay:g} s...",
                    file=sys.stderr,
                    flush=True,
                )
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)
            async with visited_lock:
                visited.difference_update(batch)
            for url in batch:
                # Already passed the include / exclude filters on the first try.
                await queue.put((ordering.key(url), url))
        finally:
            async with flight_lock:
                in_flight -= 1
        return True

    async def handle_rate_limit(exc: RateLimitedError) -> None:
        """Put the URL back on the queue and, unless a cool-down is already running
        (a request that was in flight when it began), pause every tab."""
        nonlocal pages_failed, consecutive_limits, rate_limit_pauses, page_delay
        url = exc.url
        async with flight_lock:
            rate_attempts[url] = rate_attempts.get(url, 0) + 1
            requeue = rate_attempts[url] <= retry_failed
            if not requeue:
                pages_failed += 1
        if requeue:
            async with visited_lock:
                visited.discard(url)
            await queue.put((ordering.key(url), url))
        elif verbose:
            print(
                f"Failed (rate limited {rate_attempts[url]} time(s), left unsaved): "
                f"{url}",
                file=sys.stderr,
                flush=True,
            )
        if not gate.is_set():
            return
        consecutive_limits += 1
        rate_limit_pauses += 1
        pause = backoff_seconds(
            consecutive_limits,
            exc.retry_after,
            base=limits.backoff,
            cap=limits.max_backoff,
        )
        if limits.adaptive:
            page_delay += limits.adaptive_step
        print(
            f"Rate limited (HTTP {exc.status}): pausing {pause:g} s",
            file=sys.stderr,
            flush=True,
        )
        gate.clear()
        try:
            await asyncio.sleep(pause)
        finally:
            gate.set()
        if limits.adaptive and verbose:
            print(
                f"Resuming with {page_delay:g} s between pages",
                file=sys.stderr,
                flush=True,
            )

    async def worker() -> None:
        nonlocal pages_saved, pages_skipped, in_flight, page_seconds
        nonlocal consecutive_limits
        page = await context.new_page()
        capture = NetworkCapture()
        asset_tracker = AssetQuietTracker()
        if fast is not None:
            # No asset capture or quiet tracking: nothing visual is saved.
            await install_data_request_filter(
                page, root_url, allow_hosts=fast.allow_hosts
            )
        else:
            await block_media_requests(page)
            capture.attach(page)
            asset_tracker.attach(page)
        try:
            while True:
                if await should_stop() and await worker_done():
                    break

                try:
                    _, url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    if await requeue_retries():
                        continue
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
                        url, output_dir, keep_query=keep_query, gzip=gzip_output
                    )
                    discovered: list[str] | None
                    saved_path = find_saved_page(out_path) if resume else None
                    if saved_path is not None:
                        if verbose:
                            print(
                                f"Skipping (exists): {url}",
                                file=sys.stderr,
                                flush=True,
                            )
                        html = read_text(saved_path)
                        discovered = extract_links_from_saved_html(
                            html,
                            html_path=saved_path,
                            output_dir=output_dir,
                            root_url=root_url,
                            exclude_patterns=exclude_patterns,
                            include_patterns=include_patterns,
                        )
                        async with pages_lock:
                            pages_skipped += 1
                    else:
                        await gate.wait()  # hold during a rate-limit cool-down
                        if verbose:
                            async with pages_lock:
                                label_num = pages_saved + 1
                            print(
                                f"Crawling ({label_num}): {url}",
                                file=sys.stderr,
                                flush=True,
                            )
                        page_started = time.monotonic()
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
                            data_sidecar=data_sidecar,
                            data_only=data_only,
                            data_markers=data_markers,
                            gzip_output=gzip_output,
                            asset_tracker=asset_tracker,
                            fast=fast,
                            error_rules=error_rules,
                        )
                        if discovered is None:
                            await record_failure(url)
                            continue
                        async with pages_lock:
                            pages_saved += 1
                            page_seconds += time.monotonic() - page_started
                            consecutive_limits = 0  # the site accepts us again
                            if max_pages is not None and pages_saved >= max_pages:
                                await set_stop()

                        if page_delay > 0:
                            await asyncio.sleep(page_delay)

                    if await should_stop():
                        continue

                    for link in discovered:
                        async with visited_lock:
                            if link in visited or await should_stop():
                                continue
                        await enqueue_url(link)
                except RateLimitedError as exc:
                    await handle_rate_limit(exc)
                except Exception as exc:
                    print(
                        f"Warning: failed to process {url}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    await record_failure(url)
                finally:
                    async with flight_lock:
                        in_flight -= 1
        finally:
            await page.close()

    workers = [asyncio.create_task(worker()) for _ in range(page_concurrency)]
    await asyncio.gather(*workers)
    # Held back for a retry that a --max-pages stop never ran.
    pages_failed += len(set(pending_retries))
    return _CrawlCounts(
        pages_saved=pages_saved,
        pages_skipped=pages_skipped,
        crawl_seconds=time.monotonic() - crawl_started,
        page_seconds=page_seconds,
        pages_failed=pages_failed,
        final_delay=page_delay,
        rate_limit_pauses=rate_limit_pauses,
    )


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
    data_sidecar: bool = False,
    data_only: bool = False,
    data_markers: tuple[str, ...] = DATA_MARKERS,
    gzip_output: bool = False,
    fast: FastDataOptions | None = None,
    error_rules: ErrorRules = DEFAULT_ERROR_RULES,
) -> list[str] | None:
    """Fetch one page and return same-host links discovered on it.

    Returns ``None`` (and writes nothing) when the page did not load or is an error
    page (see :mod:`folio.error_pages`), so a later run fetches it again. Raises
    :class:`folio.rate_limit.RateLimitedError` (writing nothing) on HTTP 429, or 503
    with ``Retry-After``.
    """
    if fast is not None:
        nav = await goto_page(
            page, url, timeout_ms=navigation_timeout_ms, fallback_commit=False
        )
        if not nav:
            return None
        _raise_if_rate_limited(url, nav)
        if _skip_error(url, _navigation_reason(nav, error_rules)):
            return None
        await prepare_data_page(
            page,
            settle_ms=settle_ms,
            markers=fast.markers,
            marker_timeout_ms=fast.marker_timeout_ms,
        )
        raw_links = await extract_links(page)
    else:
        nav = await goto_page(page, url, timeout_ms=navigation_timeout_ms)
        if not nav:
            return None
        _raise_if_rate_limited(url, nav)
        if _skip_error(url, _navigation_reason(nav, error_rules)):
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
    out_path = url_to_output_path(
        url, output_dir, keep_query=keep_query, gzip=gzip_output
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if data_only:
        raw_html = await page.content()
        if _skip_error(url, html_reason(raw_html, error_rules)):
            return None
        sidecar = {"url": url, **extract_data_scripts(raw_html, markers=data_markers)}
        write_text_atomic(
            sidecar_path(out_path), json.dumps(sidecar, ensure_ascii=False)
        )
        reduced = prepare_data_snapshot(raw_html, base_url=url)
        html = asset_mirror.rewrite_anchors(
            reduced, page_url=url, html_path=out_path, root_url=root_url
        )
        write_text_atomic(out_path, html)  # page file last: it marks the page done
        capture.clear()
    else:
        if data_sidecar:
            raw_html = await page.content()
            if _skip_error(url, html_reason(raw_html, error_rules)):
                return None
            sidecar = {"url": url, **extract_data_scripts(raw_html)}
            sidecar_path(out_path).write_text(
                json.dumps(sidecar, ensure_ascii=False), encoding="utf-8"
            )
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

        if _skip_error(url, html_reason(html, error_rules)):
            sidecar_path(out_path).unlink(missing_ok=True)
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


def _navigation_reason(nav: object, rules: ErrorRules) -> str | None:
    """Why a loaded navigation is an error page: its HTTP status (primary) or a
    final URL on an error path."""
    if not isinstance(nav, NavigationResult):
        return None  # a bare ``True`` (e.g. a stubbed navigation) carries no response
    return status_reason(nav.status) or url_reason(nav.url, rules)


def _raise_if_rate_limited(url: str, nav: object) -> None:
    if isinstance(nav, NavigationResult) and is_rate_limited(
        nav.status, nav.retry_after
    ):
        assert nav.status is not None
        raise RateLimitedError(url, nav.status, nav.retry_after)


def _skip_error(url: str, reason: str | None) -> bool:
    """Log and report an error page; it is never saved."""
    if reason is None:
        return False
    print(f"Skipped ({reason}): {url}", file=sys.stderr, flush=True)
    return True


def _default_login_prompt(message: str) -> None:
    input(message)
