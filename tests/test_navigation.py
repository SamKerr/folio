from unittest.mock import AsyncMock

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from folio.navigation import goto_page


@pytest.mark.asyncio
async def test_goto_page_uses_domcontentloaded_first() -> None:
    page = AsyncMock()
    page.goto.return_value = None

    assert await goto_page(page, "https://example.com/", timeout_ms=5000)

    page.goto.assert_awaited_once_with(
        "https://example.com/",
        wait_until="domcontentloaded",
        timeout=5000,
    )


@pytest.mark.asyncio
async def test_goto_page_falls_back_to_commit() -> None:
    page = AsyncMock()
    page.goto.side_effect = [
        PlaywrightTimeoutError("timeout"),
        None,
    ]

    assert await goto_page(page, "https://example.com/", timeout_ms=5000)

    assert page.goto.await_count == 2
    page.goto.assert_any_await(
        "https://example.com/",
        wait_until="commit",
        timeout=5000,
    )


@pytest.mark.asyncio
async def test_goto_page_returns_false_when_both_waits_fail() -> None:
    page = AsyncMock()
    page.goto.side_effect = PlaywrightTimeoutError("timeout")

    assert not await goto_page(page, "https://example.com/", timeout_ms=5000)
