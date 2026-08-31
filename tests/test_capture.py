import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from folio.capture import (
    AssetQuietTracker,
    _is_quiet_asset_request,
    _is_static_asset,
    prepare_page,
)


def test_is_static_asset_detects_css_by_content_type() -> None:
    assert _is_static_asset(
        "https://example.com/app.css",
        "text/css",
    )


def test_is_static_asset_rejects_javascript() -> None:
    assert not _is_static_asset(
        "https://example.com/_next/static/chunks/main.js",
        "application/octet-stream",
    )
    assert not _is_static_asset(
        "https://example.com/chunk.js",
        "application/javascript",
    )


def test_is_static_asset_rejects_html_document() -> None:
    assert not _is_static_asset(
        "https://example.com/learn",
        "text/html",
    )


def test_is_quiet_asset_request_tracks_images_and_stylesheets() -> None:
    image_request = MagicMock(
        method="GET",
        resource_type="image",
        url="https://example.com/a.png",
    )
    css_request = MagicMock(
        method="GET",
        resource_type="stylesheet",
        url="https://example.com/app.css",
    )
    script_request = MagicMock(
        method="GET",
        resource_type="script",
        url="https://example.com/app.js",
    )

    assert _is_quiet_asset_request(image_request)
    assert _is_quiet_asset_request(css_request)
    assert not _is_quiet_asset_request(script_request)


@pytest.mark.asyncio
async def test_asset_quiet_tracker_waits_for_quiet_period() -> None:
    tracker = AssetQuietTracker()
    request = MagicMock(
        method="GET",
        resource_type="image",
        url="https://example.com/a.png",
    )

    tracker._on_request(request)
    wait_task = asyncio.create_task(
        tracker.wait_for_quiet(quiet_ms=50, timeout_ms=500)
    )
    await asyncio.sleep(0.01)
    assert not wait_task.done()

    tracker._on_request_finished(request)
    await wait_task
    assert wait_task.done()


@pytest.mark.asyncio
async def test_prepare_page_scrolls_waits_for_images_and_settles() -> None:
    page = AsyncMock()
    tracker = AssetQuietTracker()

    await prepare_page(
        page,
        settle_ms=100,
        image_wait_ms=250,
        asset_quiet_ms=0,
        diagram_wait_ms=0,
        asset_tracker=tracker,
    )

    assert page.evaluate.await_count == 5
    assert page.evaluate.await_args_list[4].args[1] == 250


@pytest.mark.asyncio
async def test_prepare_page_can_skip_interact() -> None:
    page = AsyncMock()
    tracker = AssetQuietTracker()

    await prepare_page(
        page,
        settle_ms=0,
        image_wait_ms=0,
        asset_quiet_ms=0,
        diagram_wait_ms=0,
        skip_interact=True,
        asset_tracker=tracker,
    )

    assert page.evaluate.await_count == 3
