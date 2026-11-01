"""Fast data-only crawls (T15): request blocking, no render waits, marker wait.

No network: pages, routes and the browser are fakes.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _pytest.capture import CaptureFixture
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from folio.browser_scripts import CHECK_DATA_MARKERS
from folio.capture import (
    BLOCKED_DATA_RESOURCE_TYPES,
    install_data_request_filter,
    prepare_data_page,
    request_allowed,
    site_domain,
    wait_for_data_marker,
)
from folio.cli import main
from folio.crawler import CrawlResult, FastDataOptions, _save_page, run_crawl
from folio.navigation import goto_page
from folio.storage import read_text, sidecar_path

SITE = "www.example.com"


@pytest.mark.parametrize(
    ("resource_type", "url", "allowed"),
    [
        ("document", "https://www.example.com/listing/1", True),
        ("script", "https://www.example.com/app.js", True),
        ("script", "https://static.example.com/app.js", True),  # subdomain
        ("script", "https://example.com/app.js", True),  # bare site domain
        ("xhr", "https://api.example.com/listings?page=2", True),
        ("fetch", "https://www.example.com/api/1", True),
        ("eventsource", "https://www.example.com/stream", True),
        ("script", "https://dev.visualwebsiteoptimizer.com/j.php", False),
        ("xhr", "https://www.google-analytics.com/collect", False),
        ("document", "https://maps.google.com/embed", False),  # third-party iframe
        ("script", "https://notexample.com/x.js", False),  # suffix, not a subdomain
        ("image", "https://www.example.com/photo.jpg", False),
        ("stylesheet", "https://www.example.com/site.css", False),
        ("font", "https://www.example.com/f.woff2", False),
        ("media", "https://www.example.com/v.mp4", False),
        ("websocket", "wss://www.example.com/live", False),
        ("manifest", "https://www.example.com/site.webmanifest", False),
        ("texttrack", "https://www.example.com/subs.vtt", False),
        ("other", "https://www.example.com/favicon.ico", False),
        ("ping", "https://www.example.com/beacon", False),
        ("image", "data:image/png;base64,AAAA", True),
        ("script", "blob:https://www.example.com/abc", True),
    ],
)
def test_request_allowed_by_type_and_host(
    resource_type: str, url: str, allowed: bool
) -> None:
    assert request_allowed(resource_type, url, site_host=SITE) is allowed


def test_blocked_types_are_the_non_data_ones() -> None:
    assert {"image", "media", "font", "stylesheet", "websocket"} <= (
        BLOCKED_DATA_RESOURCE_TYPES
    )
    assert not {"document", "script", "xhr", "fetch"} & BLOCKED_DATA_RESOURCE_TYPES


def test_main_frame_navigation_always_loads() -> None:
    # e.g. the start URL redirects to another host
    assert request_allowed(
        "document",
        "https://login.other.com/",
        site_host=SITE,
        main_frame_navigation=True,
    )


def test_allow_host_patterns() -> None:
    allow = ("cdn.example.net", "*.cloudfront.net")
    assert request_allowed(
        "script", "https://cdn.example.net/x.js", site_host=SITE, allow_hosts=allow
    )
    assert request_allowed(
        "xhr", "https://eu.cdn.example.net/d", site_host=SITE, allow_hosts=allow
    )
    assert request_allowed(
        "fetch", "https://d1.cloudfront.net/d.json", site_host=SITE, allow_hosts=allow
    )
    assert not request_allowed(
        "script", "https://example.net/x.js", site_host=SITE, allow_hosts=allow
    )
    # allow-host does not unblock non-data resource types
    assert not request_allowed(
        "image", "https://d1.cloudfront.net/p.jpg", site_host=SITE, allow_hosts=allow
    )


def test_site_domain_drops_www() -> None:
    assert site_domain("WWW.Rightmove.co.uk") == "rightmove.co.uk"
    assert site_domain("shop.example.com") == "shop.example.com"


def _route(resource_type: str, url: str, *, navigation: bool = False) -> Any:
    route = MagicMock()
    route.request.resource_type = resource_type
    route.request.url = url
    route.request.is_navigation_request.return_value = navigation
    route.continue_ = AsyncMock()
    route.abort = AsyncMock()
    return route


@pytest.mark.asyncio
async def test_install_data_request_filter_routes_through_decision() -> None:
    page = MagicMock()
    page.route = AsyncMock()
    await install_data_request_filter(
        page, "https://www.example.com/search", allow_hosts=("api.other.com",)
    )
    pattern, handler = page.route.await_args.args
    assert pattern == "**/*"

    cases = [
        (_route("script", "https://www.example.com/a.js"), True),
        (_route("image", "https://www.example.com/a.jpg"), False),
        (_route("script", "https://tracker.com/t.js"), False),
        (_route("xhr", "https://api.other.com/data"), True),
    ]
    nav = _route("document", "https://elsewhere.com/", navigation=True)
    nav.request.frame = page.main_frame
    cases.append((nav, True))
    for route, allowed in cases:
        await handler(route)
        assert route.continue_.await_count == (1 if allowed else 0), route.request.url
        assert route.abort.await_count == (0 if allowed else 1), route.request.url


def _marker_page(states: list[Any]) -> Any:
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=states)
    return page


@pytest.mark.asyncio
async def test_marker_wait_returns_when_marker_appears() -> None:
    page = _marker_page(
        [
            {"found": False, "complete": False},
            {"found": False, "complete": False},
            {"found": True, "complete": False},
        ]
    )
    assert await wait_for_data_marker(
        page, ["__PAGE_MODEL"], timeout_ms=2000, poll_ms=1
    )
    assert page.evaluate.await_count == 3
    script, markers = page.evaluate.await_args.args
    assert script == CHECK_DATA_MARKERS
    assert markers == ["__PAGE_MODEL"]


@pytest.mark.asyncio
async def test_marker_wait_stops_once_loaded_without_marker() -> None:
    page = _marker_page(
        [{"found": False, "complete": False}, {"found": False, "complete": True}]
    )
    assert not await wait_for_data_marker(page, ["X"], timeout_ms=5000, poll_ms=1)
    assert page.evaluate.await_count == 2


@pytest.mark.asyncio
async def test_marker_wait_times_out_and_survives_errors() -> None:
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=RuntimeError("context destroyed"))
    assert not await wait_for_data_marker(page, ["X"], timeout_ms=30, poll_ms=5)
    assert page.evaluate.await_count >= 2


@pytest.mark.asyncio
async def test_marker_wait_disabled() -> None:
    page = _marker_page([])
    assert not await wait_for_data_marker(page, ["X"], timeout_ms=0)
    assert not await wait_for_data_marker(page, [], timeout_ms=1000)
    page.evaluate.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_data_page_only_checks_markers() -> None:
    page = _marker_page([{"found": True, "complete": True}])
    await prepare_data_page(page, settle_ms=0, markers=["__NEXT_DATA__"])
    # one marker check, no scrolling / chevrons / image or diagram waits
    assert [call.args[0] for call in page.evaluate.await_args_list] == [
        CHECK_DATA_MARKERS
    ]


@pytest.mark.asyncio
async def test_goto_page_without_commit_fallback_skips_slow_page() -> None:
    page = AsyncMock()
    page.goto.side_effect = PlaywrightTimeoutError("timeout")
    assert not await goto_page(
        page, "https://example.com/", timeout_ms=5000, fallback_commit=False
    )
    page.goto.assert_awaited_once_with(
        "https://example.com/", wait_until="domcontentloaded", timeout=5000
    )


PAGE_MODEL = 'window.__PAGE_MODEL = {"id": 7, "pad": "' + "x" * 300 + '"}'
PAGE_HTML = f"""<html><head><title>Flat</title>
<script>{PAGE_MODEL}</script>
<script>(function(){{var tracking=1}})()</script>
</head><body><h1>Two bedroom flat</h1>
<a href="/properties/2">2</a></body></html>"""


def _fake_page() -> Any:
    page = MagicMock()
    page.content = AsyncMock(return_value=PAGE_HTML)
    page.eval_on_selector_all = AsyncMock(
        return_value=[
            "https://www.example.com/properties/2",
            "https://tracker.com/x",
        ]
    )
    page.evaluate = AsyncMock(return_value={"found": True, "complete": True})
    return page


@pytest.mark.asyncio
async def test_fast_save_page_skips_render_waits_and_writes_sidecar(
    tmp_path: Path,
) -> None:
    page = _fake_page()
    mirror = MagicMock()
    mirror.rewrite_anchors = MagicMock(side_effect=lambda html, **_: html)
    goto = AsyncMock(return_value=True)
    with (
        patch("folio.crawler.goto_page", goto),
        patch("folio.crawler.prepare_page", new_callable=AsyncMock) as prepare,
        patch(
            "folio.crawler.discover_links_with_interaction", new_callable=AsyncMock
        ) as discover,
    ):
        links = await _save_page(
            page,
            MagicMock(),
            mirror,
            url="https://www.example.com/properties/1",
            root_url="https://www.example.com/properties/1",
            output_dir=tmp_path,
            settle_ms=0,
            image_wait_ms=5000,
            asset_quiet_ms=750,
            page_asset_timeout_ms=60_000,
            diagram_wait_ms=30_000,
            click_delay_ms=250,
            navigation_timeout_ms=30_000,
            exclude_patterns=(),
            asset_tracker=MagicMock(),
            data_only=True,
            data_sidecar=True,
            fast=FastDataOptions(markers=("__PAGE_MODEL",)),
        )

    assert goto.await_args is not None
    assert goto.await_args.kwargs == {"timeout_ms": 30_000, "fallback_commit": False}
    prepare.assert_not_called()
    discover.assert_not_called()
    assert [c.args[0] for c in page.evaluate.await_args_list] == [CHECK_DATA_MARKERS]
    assert links == ["https://www.example.com/properties/2"]
    out = tmp_path / "www.example.com" / "properties" / "1.html"
    assert "Two bedroom flat" in read_text(out)
    sidecar = json.loads(read_text(sidecar_path(out)))
    assert [s["text"] for s in sidecar["inline_scripts"]] == [PAGE_MODEL]


def _fake_browser(page: Any) -> tuple[Any, Any, Any]:
    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    login = _fake_page()
    login.close = AsyncMock()
    page.close = AsyncMock()
    page.route = AsyncMock()
    page.on = MagicMock()
    context.new_page.side_effect = [login, page]
    browser = AsyncMock()
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)
    return playwright, browser, context


@pytest.mark.asyncio
@pytest.mark.parametrize("full_render", [False, True])
async def test_run_crawl_fast_vs_full_render(tmp_path: Path, full_render: bool) -> None:
    page = _fake_page()
    page.eval_on_selector_all = AsyncMock(return_value=[])
    playwright, browser, context = _fake_browser(page)
    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch("folio.crawler.goto_page", new_callable=AsyncMock, return_value=True),
        patch("folio.crawler.prepare_page", new_callable=AsyncMock) as prepare,
        patch(
            "folio.crawler.discover_links_with_interaction",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("folio.crawler.block_media_requests", new_callable=AsyncMock) as media,
    ):
        result = await run_crawl(
            "https://www.example.com/properties/1",
            tmp_path,
            skip_login_wait=True,
            page_concurrency=1,
            data_only=True,
            full_render=full_render,
            allow_hosts=("cdn.example.net",),
        )

    assert result.pages_saved == 1
    assert result.crawl_seconds > 0
    assert result.page_seconds > 0
    kwargs = browser.new_context.await_args.kwargs
    if full_render:
        assert kwargs["service_workers"] == "allow"
        media.assert_awaited_once()
        page.route.assert_not_called()
        prepare.assert_awaited_once()
        page.on.assert_called()  # asset capture / quiet tracker listeners
    else:
        assert kwargs["service_workers"] == "block"
        media.assert_not_called()
        page.route.assert_awaited_once()
        prepare.assert_not_called()
        page.on.assert_not_called()
    assert (tmp_path / "www.example.com" / "properties" / "1.data.json").exists()


def _run_cli(argv: list[str]) -> dict[str, Any]:
    result = CrawlResult("https://a.com/x", 1, 0, Path("output"))
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        assert main(["crawl", "https://a.com/x", "--skip-login-wait", *argv]) == 0
    assert mock_crawl.await_args is not None
    return dict(mock_crawl.await_args.kwargs)


def test_cli_data_only_defaults_are_fast() -> None:
    kwargs = _run_cli(["--data-only"])
    assert kwargs["full_render"] is False
    assert kwargs["settle_ms"] == 300
    assert kwargs["navigation_timeout_ms"] == 30_000
    assert kwargs["marker_timeout_ms"] == 3000
    assert kwargs["allow_hosts"] == ()
    assert kwargs["wait_markers"] == ()


def test_cli_full_render_and_normal_crawls_keep_old_defaults() -> None:
    for argv in (["--data-only", "--full-render"], []):
        kwargs = _run_cli(argv)
        assert kwargs["settle_ms"] == 1000
        assert kwargs["navigation_timeout_ms"] == 60_000
    assert _run_cli(["--data-only", "--full-render"])["full_render"] is True


def test_cli_passes_fast_options_and_explicit_waits() -> None:
    kwargs = _run_cli(
        [
            "--data-only",
            "--allow-host",
            "cdn.example.net",
            "--allow-host",
            "*.cloudfront.net",
            "--wait-for-marker",
            "__MY_STATE__",
            "--marker-timeout-ms",
            "0",
            "--settle-ms",
            "50",
            "--timeout",
            "45",
        ]
    )
    assert kwargs["allow_hosts"] == ("cdn.example.net", "*.cloudfront.net")
    assert kwargs["wait_markers"] == ("__MY_STATE__",)
    assert kwargs["marker_timeout_ms"] == 0
    assert kwargs["settle_ms"] == 50
    assert kwargs["navigation_timeout_ms"] == 45_000


def test_cli_stats_line(capsys: CaptureFixture[str]) -> None:
    result = CrawlResult(
        "https://a.com/x", 20, 0, Path("output"), crawl_seconds=40.0, page_seconds=76.0
    )
    with patch("folio.cli.run_crawl", new_callable=AsyncMock, return_value=result):
        code = main(
            ["crawl", "https://a.com/x", "--data-only", "--stats", "--concurrency", "2"]
        )
    assert code == 0
    out = capsys.readouterr().out
    assert (
        "Stats: 20 new page(s) in 40.0 s: 30.0 pages/min, 2.00 s/page wall, "
        "3.80 s/page per tab (concurrency 2)"
    ) in out
