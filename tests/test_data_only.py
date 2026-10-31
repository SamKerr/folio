"""Data-only crawls: reduced snapshot, filtered sidecar, gzip names, folio slim.

All HTML here is synthetic.
"""

import gzip
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from folio.crawler import extract_links_from_saved_html, run_crawl
from folio.offline import (
    DATA_MARKERS,
    MAX_DATA_SCRIPT_BYTES,
    extract_data_scripts,
    filter_sidecar,
    prepare_data_snapshot,
)
from folio.slim import slim_site
from folio.storage import (
    find_saved_page,
    read_text,
    sidecar_path,
    write_text_atomic,
)
from folio.urls import output_path_to_url, url_to_output_path

PAGE_MODEL = "window.__PAGE_MODEL = " + json.dumps(
    {"propertyData": {"id": 7, "price": "£250,000", "pad": "x" * 300}}
)
TRACKING = "(function(){var cfg={experiments:[" + ",".join(["1"] * 5000) + "]};})();"
DATALAYER = (
    "window.dataLayer = window.dataLayer || []; dataLayer.push({" + "a" * 300 + "});"
)

SYNTHETIC_PAGE = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <title>2 bed flat for sale</title>
  <meta name="description" content="A synthetic listing">
  <meta property="og:title" content="2 bed flat">
  <link rel="stylesheet" href="https://cdn.example.com/site.css">
  <link rel="canonical" href="/properties/7">
  <link rel="next" href="/properties/7?page=2">
  <link rel="preload" as="font" href="/f.woff2">
  <style>.a{{color:red}} {"x" * 5000}</style>
  <script src="/app.js"></script>
  <script type="application/ld+json">{{"@type": "Residence", "name": "Flat"}}</script>
  <script>{PAGE_MODEL}</script>
  <script>{TRACKING}</script>
  <script>{DATALAYER}</script>
</head>
<body onload="boot()">
  <!-- a comment that should go -->
  <h1 style="color: blue" class="title">Two bedroom flat</h1>
  <p onclick="track()">Close to the station. Price £250,000.</p>
  <svg width="10"><path d="M0 0L10 10"/></svg>
  <img src="photo.jpg" alt="Photo">
  <picture><source srcset="a.webp"><img src="a.jpg"></picture>
  <video src="v.mp4"></video><audio src="a.mp3"></audio>
  <iframe src="https://maps.example.com/"></iframe>
  <noscript><img src="pixel.gif"></noscript>
  <object data="x.swf"></object><embed src="y.swf">
  <a href="2.html" data-folio-url="https://www.example.com/properties/2">Next</a>
</body>
</html>
"""


def test_reduced_snapshot_removes_heavy_and_executable_content() -> None:
    reduced = prepare_data_snapshot(SYNTHETIC_PAGE)
    for gone in (
        "<style",
        "<svg",
        "<img",
        "<picture",
        "<source",
        "<video",
        "<audio",
        "<iframe",
        "<noscript",
        "<object",
        "<embed",
        "app.js",
        "__PAGE_MODEL",
        "experiments",
        "dataLayer",
        "stylesheet",
        "preload",
        "style=",
        "onload",
        "onclick",
        "a comment",
    ):
        assert gone not in reduced, gone
    for kept in (
        "<title>2 bed flat for sale</title>",
        'name="description"',
        'property="og:title"',
        'rel="canonical"',
        'rel="next"',
        "application/ld+json",
        "Two bedroom flat",
        'class="title"',
        "Close to the station. Price £250,000.",
        'data-folio-url="https://www.example.com/properties/2"',
    ):
        assert kept in reduced, kept
    assert len(reduced) < len(SYNTHETIC_PAGE) / 5


def test_reduced_snapshot_is_idempotent_and_absolutises_kept_links() -> None:
    reduced = prepare_data_snapshot(
        SYNTHETIC_PAGE, base_url="https://www.example.com/properties/7"
    )
    assert 'href="https://www.example.com/properties/7?page=2"' in reduced
    assert 'href="https://www.example.com/properties/7"' in reduced
    assert prepare_data_snapshot(reduced) == reduced


def test_data_only_sidecar_keeps_page_state_and_drops_tracking() -> None:
    full = extract_data_scripts(SYNTHETIC_PAGE)
    assert len(full["inline_scripts"]) == 3  # the old rule sweeps everything in

    data = extract_data_scripts(SYNTHETIC_PAGE, markers=DATA_MARKERS)
    assert [s["type"] for s in data["json_scripts"]] == ["application/ld+json"]
    texts = [s["text"] for s in data["inline_scripts"]]
    assert texts == [PAGE_MODEL]


def test_data_marker_extends_the_list_and_cap_drops_huge_scripts() -> None:
    data = extract_data_scripts(SYNTHETIC_PAGE, markers=(*DATA_MARKERS, "experiments"))
    assert len(data["inline_scripts"]) == 2

    huge = "window.__NEXT_DATA__ = {" + "1" * (MAX_DATA_SCRIPT_BYTES + 1) + "}"
    html = f"<script>{huge}</script><script>{PAGE_MODEL}</script>"
    data = extract_data_scripts(html, markers=DATA_MARKERS)
    assert [s["text"] for s in data["inline_scripts"]] == [PAGE_MODEL]


def test_filter_sidecar_applies_the_same_rules() -> None:
    sidecar = {
        "url": "https://www.example.com/p/7",
        **extract_data_scripts(SYNTHETIC_PAGE),
    }
    filtered = filter_sidecar(sidecar, DATA_MARKERS)
    assert filtered["url"] == sidecar["url"]
    assert len(filtered["json_scripts"]) == 1
    assert [s["text"] for s in filtered["inline_scripts"]] == [PAGE_MODEL]
    assert filter_sidecar(filtered, DATA_MARKERS) == filtered


def test_gzip_path_mapping_round_trip() -> None:
    out = Path("output")
    url = "https://www.example.com/properties/7"
    gz = url_to_output_path(url, out, gzip=True)
    assert gz == Path("output/www.example.com/properties/7.html.gz")
    assert output_path_to_url(gz, out, url) == url
    queried = url_to_output_path(url + "?page=2", out, keep_query=True, gzip=True)
    assert queried.name.startswith("7.q") and queried.name.endswith(".html.gz")
    assert output_path_to_url(queried, out, url) == url
    assert sidecar_path(gz) == Path("output/www.example.com/properties/7.data.json.gz")
    assert sidecar_path(gz.with_name("7.html")).name == "7.data.json"


def test_find_saved_page_and_read_either_name(tmp_path: Path) -> None:
    plain = tmp_path / "a.html"
    assert find_saved_page(plain) is None
    write_text_atomic(plain.with_name("a.html.gz"), "<p>zipped £</p>")
    assert find_saved_page(plain) == tmp_path / "a.html.gz"
    assert read_text(tmp_path / "a.html.gz") == "<p>zipped £</p>"
    assert gzip.decompress((tmp_path / "a.html.gz").read_bytes()).startswith(b"<p>")

    other = tmp_path / "b.html"
    write_text_atomic(other, "<p>plain</p>")
    assert find_saved_page(other.with_name("b.html.gz")) == other
    assert not list(tmp_path.glob(".*.tmp"))


def test_extract_links_from_saved_html_follows_gz_hrefs() -> None:
    html = '<a href="properties/3.html.gz">3</a><a href="help.html">Help</a>'
    links = extract_links_from_saved_html(
        html,
        html_path=Path("output/www.example.com/index.html.gz"),
        output_dir=Path("output"),
        root_url="https://www.example.com/",
    )
    assert links == [
        "https://www.example.com/properties/3",
        "https://www.example.com/help",
    ]


def _mock_page(html: str) -> AsyncMock:
    page = AsyncMock()
    page.url = "https://www.example.com/"
    page.content.return_value = html
    page.eval_on_selector_all.return_value = []
    page.evaluate.return_value = []
    page.on = MagicMock()
    page.route = AsyncMock()
    page.close = AsyncMock()
    return page


@pytest.mark.asyncio
@pytest.mark.parametrize("gzip_output", [False, True])
async def test_data_only_crawl_writes_reduced_files_and_resumes(
    tmp_path: Path, gzip_output: bool
) -> None:
    root_url = "https://www.example.com/properties/1"
    site = tmp_path / "www.example.com"
    ext = ".html.gz" if gzip_output else ".html"
    # Saved by an earlier run (the gzip twin when the new run is plain, and vice
    # versa): resume must skip it and follow its recorded link to /properties/3.
    earlier = site / "properties" / ("2.html" if gzip_output else "2.html.gz")
    write_text_atomic(
        earlier,
        '<a href="3.html" data-folio-url="https://www.example.com/properties/3">3</a>',
    )
    page_html = SYNTHETIC_PAGE.replace(
        '<a href="2.html" data-folio-url="https://www.example.com/properties/2">',
        '<a href="/properties/2">',
    )
    login_page = _mock_page("<html>login</html>")
    worker_page = _mock_page(page_html)
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
    links = {
        "https://www.example.com/properties/1": [
            "https://www.example.com/properties/2"
        ],
    }

    async def discover(page: object, **kwargs: object) -> list[str]:
        return links.get(str(goto_urls[-1]), [])

    goto_urls: list[str] = []

    async def goto(page: object, url: str, **kwargs: object) -> bool:
        goto_urls.append(url)
        return True

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch("folio.crawler.prepare_page", new_callable=AsyncMock),
        patch("folio.crawler.discover_links_with_interaction", side_effect=discover),
        patch("folio.crawler.goto_page", side_effect=goto),
        patch("folio.assets.AssetMirror.mirror_page") as mirror_page,
    ):
        result = await run_crawl(
            root_url,
            tmp_path,
            skip_login_wait=True,
            page_concurrency=1,
            data_only=True,
            gzip_output=gzip_output,
        )

    mirror_page.assert_not_called()
    assert not (tmp_path / "_assets").exists()
    assert result.pages_skipped == 1
    assert result.pages_saved == 2  # /properties/1 and /properties/3
    page = site / "properties" / f"1{ext}"
    saved = read_text(page)
    assert "<style" not in saved and "Two bedroom flat" in saved
    assert f'href="2{ext}"' in saved
    assert 'data-folio-url="https://www.example.com/properties/2"' in saved
    assert 'href="https://www.example.com/properties/7"' in saved  # canonical
    sidecar = json.loads(read_text(sidecar_path(page)))
    assert sidecar["url"] == root_url
    assert [s["text"] for s in sidecar["inline_scripts"]] == [PAGE_MODEL]
    assert (site / "properties" / f"3{ext}").exists()


@pytest.mark.asyncio
async def test_gzip_requires_data_only(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="data-only"):
        await run_crawl("https://www.example.com/", tmp_path, gzip_output=True)


def _write_site(root: Path) -> None:
    site = root / "www.example.com" / "properties"
    site.mkdir(parents=True)
    (site / "7.html").write_text(SYNTHETIC_PAGE, encoding="utf-8")
    sidecar = {
        "url": "https://www.example.com/properties/7",
        **extract_data_scripts(SYNTHETIC_PAGE),
    }
    (site / "7.data.json").write_text(json.dumps(sidecar), encoding="utf-8")
    assets = root / "_assets" / "cdn.example.com"
    assets.mkdir(parents=True)
    (assets / "site.css").write_text("body{}" * 100, encoding="utf-8")
    (assets / "shared.html").write_text(SYNTHETIC_PAGE, encoding="utf-8")


def test_slim_shrinks_in_place_and_is_idempotent(tmp_path: Path) -> None:
    _write_site(tmp_path)
    page = tmp_path / "www.example.com/properties/7.html"
    side = tmp_path / "www.example.com/properties/7.data.json"
    html_before, side_before = page.stat().st_size, side.stat().st_size
    shared = (tmp_path / "_assets/cdn.example.com/shared.html").read_bytes()

    stats = slim_site(tmp_path, verbose=False)
    assert (stats.html_files, stats.sidecar_files, stats.changed) == (1, 1, 2)
    assert stats.html_before == html_before and stats.html_after == page.stat().st_size
    assert page.stat().st_size < html_before / 5
    assert side.stat().st_size < side_before / 5
    assert "Two bedroom flat" in page.read_text(encoding="utf-8")
    sidecar = json.loads(side.read_text(encoding="utf-8"))
    assert [s["text"] for s in sidecar["inline_scripts"]] == [PAGE_MODEL]
    assert (tmp_path / "_assets/cdn.example.com/shared.html").read_bytes() == shared

    snapshot = page.read_bytes(), side.read_bytes()
    again = slim_site(tmp_path, verbose=False)
    assert again.changed == 0
    assert (page.read_bytes(), side.read_bytes()) == snapshot


def test_slim_gzip_replaces_plain_files(tmp_path: Path) -> None:
    _write_site(tmp_path)
    site = tmp_path / "www.example.com/properties"
    stats = slim_site(tmp_path, gzip_output=True, verbose=False)
    assert stats.changed == 2
    assert sorted(p.name for p in site.iterdir()) == ["7.data.json.gz", "7.html.gz"]
    assert "Two bedroom flat" in read_text(site / "7.html.gz")
    assert json.loads(read_text(site / "7.data.json.gz"))["inline_scripts"]
    assert slim_site(tmp_path, gzip_output=True, verbose=False).changed == 0
    assert slim_site(tmp_path, verbose=False).changed == 0  # .gz stays .gz
    assert (tmp_path / "_assets/cdn.example.com/site.css").exists()


def test_atomic_write_keeps_normal_permissions(tmp_path: Path) -> None:
    existing = tmp_path / "a.html"
    existing.write_text("old", encoding="utf-8")
    existing.chmod(0o644)
    write_text_atomic(existing, "new")
    assert existing.stat().st_mode & 0o777 == 0o644
    fresh = tmp_path / "b.html"
    write_text_atomic(fresh, "x")
    umask = os.umask(0)
    os.umask(umask)
    assert fresh.stat().st_mode & 0o777 == 0o666 & ~umask  # not mkstemp's 0600
