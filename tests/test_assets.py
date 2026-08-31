from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from folio.assets import (
    AssetMirror,
    is_same_host_page_url,
    relative_uri,
    rewrite_srcset,
    url_to_asset_path,
)


def test_url_to_asset_path_preserves_directories() -> None:
    path = url_to_asset_path(
        "https://www.example.com/_next/static/chunks/main.css",
        Path("output/_assets"),
    )
    assert path == Path(
        "output/_assets/www.example.com/_next/static/chunks/main.css"
    )


def test_url_to_asset_path_extensionless_avoids_directory_conflict() -> None:
    path = url_to_asset_path(
        "https://www.example.com/learn/low-level-design",
        Path("output/_assets"),
    )
    assert path == Path(
        "output/_assets/www.example.com/learn/low-level-design.asset"
    )
    nested = url_to_asset_path(
        "https://www.example.com/learn/low-level-design/chunk.css",
        Path("output/_assets"),
    )
    assert nested == Path(
        "output/_assets/www.example.com/learn/low-level-design/chunk.css"
    )
    assert not str(path).endswith("/low-level-design")
    assert path.name == "low-level-design.asset"


def test_url_to_asset_path_hashes_query_strings() -> None:
    first = url_to_asset_path(
        "https://fonts.googleapis.com/css2?family=Inter",
        Path("output/_assets"),
    )
    second = url_to_asset_path(
        "https://fonts.googleapis.com/css2?family=Roboto",
        Path("output/_assets"),
    )
    assert first != second


def test_relative_uri_points_to_asset_from_html() -> None:
    html_path = Path("output/www.example.com/index.html")
    asset_path = Path("output/_assets/www.example.com/style.css")
    assert (
        relative_uri(html_path, asset_path)
        == "../_assets/www.example.com/style.css"
    )


def test_rewrite_srcset_rewrites_each_candidate(tmp_path: Path) -> None:
    image = url_to_asset_path(
        "https://www.example.com/images/hero.png",
        tmp_path / "_assets",
    )
    cache = {"https://www.example.com/images/hero.png": image}
    html_path = tmp_path / "www.example.com/index.html"
    rewritten = rewrite_srcset(
        "https://www.example.com/images/hero.png 1x, "
        "https://www.example.com/images/hero@2x.png 2x",
        page_url="https://www.example.com/",
        file_path=html_path,
        cache=cache,
    )
    assert "../_assets/www.example.com/images/hero.png 1x" in rewritten


def test_rewrite_html_rewrites_svg_sprite_fragment(tmp_path: Path) -> None:
    mirror = AssetMirror(AsyncMock(), tmp_path)
    sprite = url_to_asset_path(
        "https://www.example.com/icons.svg",
        mirror._assets_root,
    )
    mirror._cache["https://www.example.com/icons.svg"] = sprite

    html = """
        <html>
          <body>
            <svg><use href="https://www.example.com/icons.svg#chevron"></use></svg>
          </body>
        </html>
    """
    html_path = tmp_path / "www.example.com/index.html"
    rewritten = mirror.rewrite_html(
        html,
        page_url="https://www.example.com/",
        html_path=html_path,
        root_url="https://www.example.com/",
    )

    assert "../_assets/www.example.com/icons.svg#chevron" in rewritten


def test_rewrite_html_rewrites_object_and_embed(tmp_path: Path) -> None:
    mirror = AssetMirror(AsyncMock(), tmp_path)
    diagram = url_to_asset_path(
        "https://www.example.com/diagram.svg",
        mirror._assets_root,
    )
    mirror._cache["https://www.example.com/diagram.svg"] = diagram

    html = """
        <html>
          <body>
            <object data="https://www.example.com/diagram.svg"></object>
            <embed src="https://www.example.com/diagram.svg">
          </body>
        </html>
    """
    html_path = tmp_path / "www.example.com/index.html"
    rewritten = mirror.rewrite_html(
        html,
        page_url="https://www.example.com/",
        html_path=html_path,
        root_url="https://www.example.com/",
    )

    assert "../_assets/www.example.com/diagram.svg" in rewritten
    assert rewritten.count("../_assets/www.example.com/diagram.svg") == 2


def test_rewrite_html_replaces_stylesheet_and_page_links(tmp_path: Path) -> None:
    mirror = AssetMirror(AsyncMock(), tmp_path)
    stylesheet = url_to_asset_path(
        "https://www.example.com/static/app.css",
        mirror._assets_root,
    )
    mirror._cache["https://www.example.com/static/app.css"] = stylesheet

    html = """
        <html>
          <head>
            <link rel="stylesheet" href="https://www.example.com/static/app.css">
          </head>
          <body>
            <a href="https://www.example.com/learn">Learn</a>
          </body>
        </html>
    """
    html_path = tmp_path / "www.example.com/index.html"
    rewritten = mirror.rewrite_html(
        html,
        page_url="https://www.example.com/",
        html_path=html_path,
        root_url="https://www.example.com/",
    )

    assert "../_assets/www.example.com/static/app.css" in rewritten
    assert 'href="learn.html"' in rewritten


def test_rewrite_html_rewrites_srcset_and_lazy_src(tmp_path: Path) -> None:
    mirror = AssetMirror(AsyncMock(), tmp_path)
    image = url_to_asset_path(
        "https://www.example.com/images/card.png",
        mirror._assets_root,
    )
    mirror._cache["https://www.example.com/images/card.png"] = image

    html = """
        <html>
          <body>
            <img data-src="https://www.example.com/images/card.png">
            <source srcset="https://www.example.com/images/card.png 1x">
          </body>
        </html>
    """
    html_path = tmp_path / "www.example.com/index.html"
    rewritten = mirror.rewrite_html(
        html,
        page_url="https://www.example.com/",
        html_path=html_path,
        root_url="https://www.example.com/",
    )

    assert "../_assets/www.example.com/images/card.png" in rewritten
    assert "folio-offline-guard" not in rewritten


@pytest.mark.asyncio
async def test_mirror_page_strips_scripts_from_saved_html(tmp_path: Path) -> None:
    mirror = AssetMirror(AsyncMock(), tmp_path)
    page = AsyncMock()
    page.content.return_value = """
        <html><head><script src="/app.js"></script></head><body>Hi</body></html>
    """
    page.evaluate.return_value = []

    html_path = tmp_path / "www.example.com/index.html"
    result = await mirror.mirror_page(
        page,
        page_url="https://www.example.com/",
        html_path=html_path,
        root_url="https://www.example.com/",
    )
    assert "<script" not in result
    assert "Hi" in result


@pytest.mark.asyncio
async def test_ensure_asset_downloads_css_and_nested_urls(tmp_path: Path) -> None:
    css_url = "https://www.example.com/static/app.css"
    font_url = "https://www.example.com/static/font.woff2"

    css_response = AsyncMock()
    css_response.ok = True
    css_response.headers = {"content-type": "text/css"}
    css_response.body = AsyncMock(
        return_value=b"body { background: url('/static/font.woff2'); }"
    )

    font_response = AsyncMock()
    font_response.ok = True
    font_response.headers = {"content-type": "font/woff2"}
    font_response.body = AsyncMock(return_value=b"font-bytes")

    request = AsyncMock()

    async def fake_get(url: str, *, timeout: int) -> AsyncMock:
        _ = timeout
        if url == css_url:
            return css_response
        if url == font_url:
            return font_response
        raise AssertionError(f"Unexpected URL: {url}")

    request.get.side_effect = fake_get

    mirror = AssetMirror(request, tmp_path)
    local_css = await mirror.ensure_asset(css_url, base=css_url)

    assert local_css is not None
    assert local_css.exists()
    saved_css = local_css.read_text(encoding="utf-8")
    assert "font.woff2" in saved_css
    assert (tmp_path / "_assets/www.example.com/static/font.woff2").exists()


def test_is_same_host_page_url_detects_extensionless_routes() -> None:
    base = "https://www.example.com/learn/system-design"
    assert is_same_host_page_url(
        "https://www.example.com/learn/salary-negotiation/introduction",
        base=base,
    )
    assert not is_same_host_page_url(
        "https://www.example.com/static/app.css",
        base=base,
    )
    assert not is_same_host_page_url(
        "https://fonts.googleapis.com/css2?family=Inter",
        base=base,
    )


@pytest.mark.asyncio
async def test_ensure_asset_skips_same_host_page_urls(tmp_path: Path) -> None:
    request = AsyncMock()
    mirror = AssetMirror(request, tmp_path)

    result = await mirror.ensure_asset(
        "https://www.example.com/learn/salary-negotiation/introduction",
        base="https://www.example.com/learn/system-design",
    )

    assert result is None
    request.get.assert_not_awaited()
