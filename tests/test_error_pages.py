"""Error pages are never saved (T17): detection, crawl skip + retry, slim --drop-errors.

No network: pages, responses and the browser are fakes.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _pytest.capture import CaptureFixture

from folio.cli import main
from folio.crawler import CrawlResult, FastDataOptions, _save_page, run_crawl
from folio.error_pages import (
    ErrorRules,
    html_reason,
    path_matches,
    sidecar_reason,
    status_reason,
    url_reason,
)
from folio.navigation import NavigationResult, goto_page
from folio.slim import drop_error_pages
from folio.storage import sidecar_path, write_text_atomic

ROOT = "https://www.example.com/for-sale/leeds"
LISTING = "https://www.example.com/details/40412"
NEXT_500 = json.dumps({"page": "/otm-errors/500", "props": {"pageProps": {}}})
NEXT_OK = json.dumps({"page": "/details/[id]", "props": {"pageProps": {"id": 1}}})


def _html(title: str, next_data: str = NEXT_OK) -> str:
    return (
        f"<html><head><title>{title}</title>"
        f'<script id="__NEXT_DATA__" type="application/json">{next_data}</script>'
        "</head><body><p>Two bedroom flat</p></body></html>"
    )


ERROR_500_HTML = _html("Something went wrong", NEXT_500)
LISTING_HTML = _html("2 bed flat for sale")


# --- detection rules -------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pattern", "hit"),
    [
        ("/otm-errors/500", "/otm-errors/", True),
        ("/otm-errors/500", "/500", True),
        ("/404", "/404", True),
        ("/404.html", "/404", True),
        ("/Error", "/error", True),
        ("/error/oops", "/error", True),
        ("/details/40412", "/404", False),  # listing id starting 404
        ("/properties/500123", "/500", False),
        ("/otm-errors/500", "/error", False),  # whole segments only
        ("/errors-and-omissions", "/error", False),
        ("/a/b/c", "/b/c", True),
        ("/a/b/x/c", "/b/c", False),
        ("/anything", "/", False),
    ],
)
def test_path_patterns_match_whole_segments(path: str, pattern: str, hit: bool) -> None:
    assert path_matches(path, pattern) is hit


def test_status_and_url_reasons() -> None:
    assert status_reason(500) == "HTTP 500"
    assert status_reason(404) == "HTTP 404"
    assert status_reason(200) is None and status_reason(302) is None
    assert status_reason(None) is None
    assert (
        url_reason("https://x.com/otm-errors/500?x=1") == "error path /otm-errors/500"
    )
    assert url_reason(LISTING) is None
    assert url_reason(None) is None


def test_html_reason_title_and_next_data() -> None:
    assert html_reason(ERROR_500_HTML) == "error page /otm-errors/500"
    assert html_reason(_html("Just a moment...")) == "error title 'Just a moment...'"
    assert html_reason(_html("Please solve this CAPTCHA")) is not None
    assert html_reason(_html("Attention Required! | Cloudflare")) is not None
    assert html_reason(LISTING_HTML) is None
    # body text is not a marker: only the title
    assert html_reason("<title>Flat</title><p>Access denied to pets</p>") is None


def test_error_marker_extends_paths_and_titles() -> None:
    rules = ErrorRules.build(["/oops", "Service Unavailable", " "])
    assert "/oops" in rules.paths and "/404" in rules.paths
    assert "Service Unavailable" in rules.titles and "captcha" in rules.titles
    assert url_reason("https://x.com/oops", rules) is not None
    assert html_reason(_html("503 Service Unavailable"), rules) is not None
    assert html_reason(_html("503 Service Unavailable")) is None


def test_sidecar_reason_reads_next_data() -> None:
    bad = {"url": LISTING, "json_scripts": [{"id": "__NEXT_DATA__", "text": NEXT_500}]}
    good = {"url": LISTING, "json_scripts": [{"id": "__NEXT_DATA__", "text": NEXT_OK}]}
    assert sidecar_reason(json.dumps(bad)) == "error page /otm-errors/500"
    assert sidecar_reason(json.dumps(good)) is None
    assert sidecar_reason("not json") is None


@pytest.mark.asyncio
async def test_goto_page_reports_final_status_and_url() -> None:
    page = MagicMock()
    page.goto = AsyncMock(
        return_value=MagicMock(status=500, url="https://x.com/otm-errors/500")
    )
    nav = await goto_page(page, "https://x.com/details/1", timeout_ms=1000)
    assert nav and nav.status == 500 and nav.url == "https://x.com/otm-errors/500"


# --- _save_page ------------------------------------------------------------


def _page(html: str, *, status: int = 200, final_url: str = LISTING) -> Any:
    page = MagicMock()
    page.url = final_url
    page.goto = AsyncMock(return_value=MagicMock(status=status, url=final_url))
    page.content = AsyncMock(return_value=html)
    page.eval_on_selector_all = AsyncMock(return_value=[])
    page.evaluate = AsyncMock(return_value={"found": True, "complete": True})
    return page


async def _save(
    page: Any, tmp_path: Path, *, fast: bool = True, sidecar: bool = True
) -> list[str] | None:
    mirror = MagicMock()
    mirror.rewrite_anchors = MagicMock(side_effect=lambda html, **_: html)
    mirror.mirror_page = AsyncMock(return_value=await page.content())
    with (
        patch("folio.crawler.prepare_page", new_callable=AsyncMock),
        patch("folio.crawler.prepare_data_page", new_callable=AsyncMock),
        patch(
            "folio.crawler.discover_links_with_interaction",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        return await _save_page(
            page,
            MagicMock(),
            mirror,
            url=LISTING,
            root_url=ROOT,
            output_dir=tmp_path,
            settle_ms=0,
            image_wait_ms=0,
            asset_quiet_ms=0,
            page_asset_timeout_ms=0,
            diagram_wait_ms=0,
            click_delay_ms=0,
            navigation_timeout_ms=1000,
            exclude_patterns=(),
            asset_tracker=MagicMock(),
            data_only=fast,
            data_sidecar=sidecar,
            fast=FastDataOptions() if fast else None,
        )


def _saved_files(tmp_path: Path) -> list[Path]:
    return [p for p in tmp_path.rglob("*") if p.is_file()]


@pytest.mark.asyncio
@pytest.mark.parametrize("fast", [True, False])
async def test_http_500_is_not_saved(
    tmp_path: Path, fast: bool, capsys: CaptureFixture[str]
) -> None:
    # A 200-looking body: the status alone decides.
    page = _page(LISTING_HTML, status=500)
    assert await _save(page, tmp_path, fast=fast) is None
    assert _saved_files(tmp_path) == []
    assert f"Skipped (HTTP 500): {LISTING}" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_redirect_to_error_path_is_not_saved(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    page = _page(LISTING_HTML, final_url="https://www.example.com/otm-errors/500")
    assert await _save(page, tmp_path) is None
    assert _saved_files(tmp_path) == []
    assert "Skipped (error path /otm-errors/500)" in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.parametrize("fast", [True, False])
@pytest.mark.parametrize(
    "html", [_html("Just a moment..."), _html("Oops", NEXT_500)], ids=["title", "next"]
)
async def test_body_marker_page_is_not_saved(
    tmp_path: Path, fast: bool, html: str
) -> None:
    assert await _save(_page(html), tmp_path, fast=fast) is None
    assert _saved_files(tmp_path) == []


@pytest.mark.asyncio
async def test_normal_page_is_saved(tmp_path: Path) -> None:
    assert await _save(_page(LISTING_HTML), tmp_path) == []
    out = tmp_path / "www.example.com" / "details" / "40412.html"
    assert out.exists() and sidecar_path(out).exists()


# --- retry through run_crawl -----------------------------------------------


def _fake_browser() -> tuple[Any, Any]:
    # Every page links to both listings, so a resumed crawl finds them in saved HTML.
    anchors = '<a href="/details/1">1</a><a href="/details/2">2</a></body>'
    worker = _page(LISTING_HTML.replace("</body>", anchors))
    worker.close = AsyncMock()
    worker.route = AsyncMock()
    worker.on = MagicMock()
    login = _page("<html>login</html>")
    login.close = AsyncMock()
    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login, worker]
    browser = AsyncMock()
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)
    return playwright, login


L1 = "https://www.example.com/details/1"
L2 = "https://www.example.com/details/2"


async def _crawl(
    tmp_path: Path, statuses: dict[str, list[int]], **kwargs: Any
) -> tuple[CrawlResult, list[str]]:
    playwright, login = _fake_browser()
    calls: list[str] = []

    async def goto(page: object, url: str, **_: object) -> NavigationResult:
        if page is login:
            return NavigationResult(True, 200, url)
        calls.append(url)
        seq = statuses.get(url, [200])
        status = seq[min(calls.count(url), len(seq)) - 1]
        return NavigationResult(True, status, url)

    async def links(page: object) -> list[str]:
        return [L1, L2] if calls[-1] == ROOT else []

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch("folio.crawler.goto_page", side_effect=goto),
        patch("folio.crawler.prepare_data_page", new_callable=AsyncMock),
        patch("folio.crawler.install_data_request_filter", new_callable=AsyncMock),
        patch("folio.crawler.extract_links", side_effect=links),
    ):
        result = await run_crawl(
            ROOT,
            tmp_path,
            skip_login_wait=True,
            page_concurrency=1,
            data_only=True,
            retry_delay=0,
            **kwargs,
        )
    return result, calls


def _listing_file(tmp_path: Path, n: int) -> Path:
    return tmp_path / "www.example.com" / "details" / f"{n}.html"


@pytest.mark.asyncio
async def test_failed_url_is_retried_once_at_the_end_then_saved(tmp_path: Path) -> None:
    result, calls = await _crawl(tmp_path, {L1: [500, 200]})
    assert calls == [ROOT, L1, L2, L1]  # retried after everything else
    assert (result.pages_saved, result.pages_failed) == (3, 0)
    assert _listing_file(tmp_path, 1).exists()


@pytest.mark.asyncio
async def test_url_failing_again_is_counted_and_left_unsaved(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    result, calls = await _crawl(tmp_path, {L1: [500]})
    assert calls == [ROOT, L1, L2, L1]
    assert (result.pages_saved, result.pages_failed) == (2, 1)
    assert not _listing_file(tmp_path, 1).exists()
    assert not sidecar_path(_listing_file(tmp_path, 1)).exists()
    err = capsys.readouterr().err
    assert "Retrying 1 failed URL(s)" in err
    assert f"Failed (after 2 attempt(s), left unsaved): {L1}" in err

    # A resumed crawl fetches it again (its file was never written).
    result, calls = await _crawl(tmp_path, {}, retry_failed=0)
    assert calls == [L1]
    assert (result.pages_saved, result.pages_skipped, result.pages_failed) == (1, 2, 0)


@pytest.mark.asyncio
async def test_retry_failed_zero_and_two(tmp_path: Path) -> None:
    result, calls = await _crawl(tmp_path / "a", {L1: [500]}, retry_failed=0)
    assert calls == [ROOT, L1, L2] and result.pages_failed == 1
    result, calls = await _crawl(tmp_path / "b", {L1: [500]}, retry_failed=2)
    assert calls == [ROOT, L1, L2, L1, L1] and result.pages_failed == 1


@pytest.mark.asyncio
async def test_retry_failed_must_not_be_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="retry_failed"):
        await run_crawl(ROOT, tmp_path, retry_failed=-1)


# --- slim --drop-errors ----------------------------------------------------


def _write_page(path: Path, html: str, next_data: str | None = None) -> None:
    write_text_atomic(path, html)
    side: dict[str, Any] = {"url": LISTING, "json_scripts": [], "inline_scripts": []}
    if next_data is not None:
        side["json_scripts"].append(
            {"type": "application/json", "id": "__NEXT_DATA__", "text": next_data}
        )
    write_text_atomic(sidecar_path(path), json.dumps(side))


def _error_site(root: Path) -> dict[str, Path]:
    details = root / "www.example.com" / "details"
    files = {
        "good": details / "1.html",
        "bad_plain": details / "2.html",  # error only visible in the sidecar
        "bad_gz": details / "3.html.gz",  # challenge title
        "orphan": details / "4.data.json",
        "assets": root / "_assets" / "cdn.example.com" / "500.html",
    }
    _write_page(files["good"], LISTING_HTML, NEXT_OK)
    _write_page(files["bad_plain"], "<title>Oops</title><p>sorry</p>", NEXT_500)
    _write_page(files["bad_gz"], _html("Just a moment..."))
    write_text_atomic(
        files["orphan"],
        json.dumps({"json_scripts": [{"id": "__NEXT_DATA__", "text": NEXT_500}]}),
    )
    write_text_atomic(files["assets"], ERROR_500_HTML)
    return files


def test_drop_errors_dry_run_then_delete(tmp_path: Path) -> None:
    files = _error_site(tmp_path)
    before = sorted(_saved_files(tmp_path))

    dry = drop_error_pages(tmp_path, dry_run=True, verbose=False)
    assert (dry.pages_checked, dry.error_pages, dry.orphan_sidecars) == (3, 2, 1)
    assert dry.files_deleted == 5
    assert sorted(_saved_files(tmp_path)) == before

    stats = drop_error_pages(tmp_path, verbose=False)
    assert (stats.error_pages, stats.orphan_sidecars, stats.files_deleted) == (2, 1, 5)
    left = sorted(p.relative_to(tmp_path).as_posix() for p in _saved_files(tmp_path))
    assert left == [
        "_assets/cdn.example.com/500.html",
        "www.example.com/details/1.data.json",
        "www.example.com/details/1.html",
    ]
    assert not files["bad_gz"].exists()
    assert drop_error_pages(tmp_path, verbose=False).files_deleted == 0


def test_cli_slim_drop_errors(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    _error_site(tmp_path)
    assert main(["slim", str(tmp_path), "--drop-errors", "--dry-run"]) == 0
    assert "Would delete 2 error page(s) of 3" in capsys.readouterr().out
    assert main(["slim", str(tmp_path), "--drop-errors"]) == 0
    assert "Deleted 2 error page(s) of 3 and 1 orphan" in capsys.readouterr().out
    assert main(["slim", str(tmp_path), "--dry-run"]) == 1  # needs --drop-errors


def test_cli_slim_drop_errors_extra_marker(tmp_path: Path) -> None:
    page = tmp_path / "www.example.com" / "x.html"
    _write_page(page, _html("Service Unavailable"))
    assert main(["slim", str(tmp_path), "--drop-errors"]) == 0
    assert page.exists()
    argv = ["slim", str(tmp_path), "--drop-errors", "--error-marker", "unavailable"]
    assert main(argv) == 0
    assert not page.exists() and not sidecar_path(page).exists()


# --- crawl CLI plumbing ----------------------------------------------------


def _run_cli(argv: list[str], failed: int = 0) -> dict[str, Any]:
    result = CrawlResult("https://a.com/x", 1, 0, Path("output"), pages_failed=failed)
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        assert main(["crawl", "https://a.com/x", "--skip-login-wait", *argv]) == 0
    assert mock_crawl.await_args is not None
    return dict(mock_crawl.await_args.kwargs)


def test_cli_error_and_retry_defaults() -> None:
    kwargs = _run_cli([])
    assert kwargs["error_markers"] == ()
    assert kwargs["retry_failed"] == 1
    assert kwargs["retry_delay"] == 5.0


def test_cli_error_and_retry_flags(capsys: CaptureFixture[str]) -> None:
    kwargs = _run_cli(
        [
            "--error-marker",
            "/oops",
            "--error-marker",
            "Service Unavailable",
            "--retry-failed",
            "3",
            "--retry-delay",
            "0.5",
        ],
        failed=7,
    )
    assert kwargs["error_markers"] == ("/oops", "Service Unavailable")
    assert kwargs["retry_failed"] == 3
    assert kwargs["retry_delay"] == 0.5
    assert "7 page(s) failed" in capsys.readouterr().out


def test_cli_rejects_negative_retry(capsys: CaptureFixture[str]) -> None:
    with patch("folio.cli.run_crawl", new_callable=AsyncMock) as mock_crawl:
        assert main(["crawl", "https://a.com/x", "--retry-failed", "-1"]) == 1
    mock_crawl.assert_not_called()
    assert "--retry-failed" in capsys.readouterr().err
