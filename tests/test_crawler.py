from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from folio.crawler import extract_links, extract_links_from_saved_html, run_crawl
from folio.urls import url_to_output_path


@pytest.mark.asyncio
async def test_extract_links_returns_hrefs() -> None:
    page = AsyncMock()
    page.eval_on_selector_all.return_value = [
        "https://example.com/a",
        "https://example.com/b",
    ]

    assert await extract_links(page) == [
        "https://example.com/a",
        "https://example.com/b",
    ]


@pytest.mark.asyncio
async def test_run_crawl_saves_pages_and_follows_same_host_links(
    tmp_path: Path,
) -> None:
    root_url = "https://www.example.com/"
    login_page = _mock_page(
        html="<html>login</html>",
        links=[],
        page_url=root_url,
    )
    worker_page = _mock_page(
        html="<html><a href='/learn'>Learn</a></html>",
        links=["https://www.example.com/learn"],
        page_url=root_url,
    )
    worker_page.content.side_effect = [
        "<html><a href='/learn'>Learn</a></html>",
        "<html>learn page</html>",
    ]
    worker_page.eval_on_selector_all.side_effect = [
        ["https://www.example.com/learn"],
        [],
    ]

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login_page, worker_page]

    browser = AsyncMock()
    browser.new_context.return_value = context

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch(
            "folio.crawler.prepare_page",
            new_callable=AsyncMock,
        ),
        patch(
            "folio.crawler.discover_links_with_interaction",
            new_callable=AsyncMock,
            side_effect=[
                ["https://www.example.com/learn"],
                [],
            ],
        ),
        patch(
            "folio.crawler.goto_page",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_goto,
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            delay_seconds=0,
            max_pages=10,
            page_concurrency=1,
        )

    assert result.pages_saved == 2
    assert (tmp_path / "www.example.com/index.html").exists()
    assert (tmp_path / "www.example.com/learn.html").exists()
    mock_goto.assert_awaited()
    login_page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_crawl_skips_existing_html_when_resuming(tmp_path: Path) -> None:
    root_url = "https://www.example.com/"
    existing = tmp_path / "www.example.com/index.html"
    existing.parent.mkdir(parents=True)
    existing.write_text(
        '<html><body><a href="learn.html">Learn</a></body></html>',
        encoding="utf-8",
    )

    login_page = _mock_page(
        html="<html>login</html>",
        links=[],
        page_url=root_url,
    )
    worker_page = _mock_page(
        html="<html>learn</html>",
        links=[],
        page_url="https://www.example.com/learn",
    )

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login_page, worker_page]

    browser = AsyncMock()
    browser.new_context.return_value = context

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch(
            "folio.crawler.prepare_page",
            new_callable=AsyncMock,
        ),
        patch(
            "folio.crawler.goto_page",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            delay_seconds=0,
            max_pages=10,
            page_concurrency=1,
            resume=True,
        )

    assert result.pages_skipped >= 1
    assert result.pages_saved == 1
    assert (tmp_path / "www.example.com/learn.html").exists()


@pytest.mark.asyncio
async def test_run_crawl_waits_for_login_prompt(tmp_path: Path) -> None:
    login_page = _mock_page(
        html="<html>login</html>",
        links=[],
        page_url="https://www.example.com/",
    )
    worker_page = _mock_page(
        html="<html>home</html>",
        links=[],
        page_url="https://www.example.com/",
    )

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login_page, worker_page]

    browser = AsyncMock()
    browser.new_context.return_value = context

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    prompt = MagicMock()

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch(
            "folio.crawler.prepare_page",
            new_callable=AsyncMock,
        ),
        patch(
            "folio.crawler.goto_page",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        await run_crawl(
            "https://www.example.com/",
            tmp_path,
            login_prompt=prompt,
            delay_seconds=0,
            max_pages=1,
            page_concurrency=1,
        )

    prompt.assert_called_once()


@pytest.mark.asyncio
async def test_run_crawl_finishes_path_section_before_next(tmp_path: Path) -> None:
    root_url = "https://www.example.com/"
    page_links: dict[str, list[str]] = {
        root_url: [
            "https://www.example.com/learn/a",
            "https://www.example.com/code/b",
        ],
        "https://www.example.com/learn/a": [
            "https://www.example.com/learn/c",
            "https://www.example.com/code/d",
        ],
        "https://www.example.com/learn/c": [],
        "https://www.example.com/code/b": [],
        "https://www.example.com/code/d": [],
    }
    crawl_order: list[str] = []

    login_page = _mock_page(html="<html>login</html>", links=[], page_url=root_url)
    worker_page = _mock_page(html="<html>page</html>", links=[], page_url=root_url)

    async def links_for_current_page(*_args: object, **_kwargs: object) -> list[str]:
        return page_links.get(worker_page.url, [])

    worker_page.eval_on_selector_all.side_effect = links_for_current_page

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login_page, worker_page]

    browser = AsyncMock()
    browser.new_context.return_value = context

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    async def track_goto(page: AsyncMock, url: str, **_kwargs: object) -> bool:
        page.url = url
        crawl_order.append(url)
        return True

    async def discover_links(page: AsyncMock, **_kwargs: object) -> list[str]:
        return page_links.get(page.url, [])

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch(
            "folio.crawler.prepare_page",
            new_callable=AsyncMock,
        ),
        patch(
            "folio.crawler.discover_links_with_interaction",
            side_effect=discover_links,
        ),
        patch(
            "folio.crawler.goto_page",
            side_effect=track_goto,
        ),
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            delay_seconds=0,
            max_pages=10,
            page_concurrency=1,
            resume=False,
        )

    assert result.pages_saved == 5
    assert crawl_order[-5:] == [
        root_url,
        "https://www.example.com/learn/a",
        "https://www.example.com/learn/c",
        "https://www.example.com/code/b",
        "https://www.example.com/code/d",
    ]


@pytest.mark.asyncio
async def test_run_crawl_skips_excluded_paths(tmp_path: Path) -> None:
    root_url = "https://www.example.com/"
    page_links: dict[str, list[str]] = {
        root_url: [
            "https://www.example.com/learn",
            "https://www.example.com/community/thread",
        ],
        "https://www.example.com/learn": [],
    }
    crawl_order: list[str] = []

    login_page = _mock_page(html="<html>login</html>", links=[], page_url=root_url)
    worker_page = _mock_page(html="<html>page</html>", links=[], page_url=root_url)

    async def links_for_current_page(*_args: object, **_kwargs: object) -> list[str]:
        return page_links.get(worker_page.url, [])

    worker_page.eval_on_selector_all.side_effect = links_for_current_page

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login_page, worker_page]

    browser = AsyncMock()
    browser.new_context.return_value = context

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    async def track_goto(page: AsyncMock, url: str, **_kwargs: object) -> bool:
        page.url = url
        crawl_order.append(url)
        return True

    async def discover_links(page: AsyncMock, **_kwargs: object) -> list[str]:
        return page_links.get(page.url, [])

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch(
            "folio.crawler.prepare_page",
            new_callable=AsyncMock,
        ),
        patch(
            "folio.crawler.discover_links_with_interaction",
            side_effect=discover_links,
        ),
        patch(
            "folio.crawler.goto_page",
            side_effect=track_goto,
        ),
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            delay_seconds=0,
            max_pages=10,
            page_concurrency=1,
            resume=False,
            exclude_patterns=("/community/*",),
        )

    assert result.pages_saved == 2
    assert crawl_order[-2:] == [root_url, "https://www.example.com/learn"]
    assert not (tmp_path / "www.example.com/community/thread.html").exists()


def _mock_page(*, html: str, links: list[str], page_url: str) -> AsyncMock:
    page = AsyncMock()
    page.url = page_url
    page.content.return_value = html
    page.eval_on_selector_all.return_value = links
    page.evaluate.return_value = []
    page.on = MagicMock()
    page.route = AsyncMock()
    page.close = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_run_crawl_include_patterns_extra_seeds_and_keep_query(
    tmp_path: Path,
) -> None:
    root_url = "https://www.example.com/search?area=leeds"
    other = "https://www.example.com/other"
    links = {
        "https://www.example.com/search?area=leeds": [
            "https://www.example.com/properties/1",
            "https://www.example.com/help",
            "https://www.example.com/search?area=leeds&index=24",
        ],
        "https://www.example.com/search?area=leeds&index=24": [
            "https://www.example.com/properties/2",
        ],
        other: ["https://www.example.com/properties/3"],
    }

    async def fake_save_page(
        page: object,
        capture: object,
        mirror: object,
        *,
        url: str,
        output_dir: Path,
        keep_query: bool,
        **kwargs: object,
    ) -> list[str]:
        out = url_to_output_path(url, output_dir, keep_query=keep_query)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<html></html>", encoding="utf-8")
        return links.get(url, [])

    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.return_value = _mock_page(html="", links=[], page_url=root_url)
    browser = AsyncMock()
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch("folio.crawler._save_page", side_effect=fake_save_page),
        patch("folio.crawler.goto_page", new_callable=AsyncMock, return_value=True),
        patch("folio.crawler.AssetMirror"),
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            include_patterns=("/properties/*", "/search*"),
            keep_query=True,
            extra_start_urls=(other,),
            page_concurrency=1,
        )

    site = tmp_path / "www.example.com"
    assert result.pages_saved == 6  # 2 search pages, other, 3 properties
    assert not (site / "help.html").exists()  # not included
    assert (site / "other.html").exists()  # a seed outside the include set
    assert len(list(site.glob("search.q*.html"))) == 2  # one file per query
    assert {p.name for p in (site / "properties").iterdir()} == {
        "1.html",
        "2.html",
        "3.html",
    }


@pytest.mark.asyncio
async def test_run_crawl_rejects_extra_seed_on_another_host(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="another host"):
        await run_crawl(
            "https://www.example.com/",
            tmp_path,
            skip_login_wait=True,
            extra_start_urls=("https://other.com/",),
        )


def test_extract_links_from_saved_html_prefers_the_recorded_url() -> None:
    html = (
        '<a href="find.q0123456789.html" '
        'data-folio-url="https://www.example.com/find?index=24">Next</a>'
        '<a href="help.html">Help</a>'
    )
    links = extract_links_from_saved_html(
        html,
        html_path=Path("output/www.example.com/find.html"),
        output_dir=Path("output"),
        root_url="https://www.example.com/",
        include_patterns=("/find*",),
    )
    assert links == ["https://www.example.com/find?index=24"]
