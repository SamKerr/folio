from unittest.mock import AsyncMock

import pytest

from folio.assets import extract_asset_urls


@pytest.mark.asyncio
async def test_extract_asset_urls_filters_page_links() -> None:
    page = AsyncMock()
    page.url = "https://www.example.com/learn/system-design"
    page.evaluate.return_value = [
        "https://www.example.com/static/app.css",
        "https://www.example.com/learn/salary-negotiation/introduction",
        "https://example.com/logo.png",
    ]

    urls = await extract_asset_urls(page)

    assert urls == [
        "https://www.example.com/static/app.css",
        "https://example.com/logo.png",
    ]
    page.evaluate.assert_awaited_once()
    script = page.evaluate.await_args.args[0]
    assert 'element.tagName === "A"' in script
