"""Rate limits (T18): Retry-After, cool-down, re-queue, back-off, adaptive delay.

No network: pages, responses and the browser are fakes; ``asyncio.sleep`` is patched to
record each pause (and yield without waiting).
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _pytest.capture import CaptureFixture

from folio.cli import format_crawl_stats, main
from folio.crawler import CrawlResult, run_crawl
from folio.navigation import NavigationResult, goto_page
from folio.rate_limit import backoff_seconds, is_rate_limited, parse_retry_after

ROOT = "https://www.example.com/for-sale/leeds"
L1 = "https://www.example.com/details/1"
L2 = "https://www.example.com/details/2"
L3 = "https://www.example.com/details/3"
HTML = (
    "<html><head><title>2 bed flat</title></head>"
    '<body><a href="/details/1">1</a></body></html>'
)

# --- pure rules -------------------------------------------------------------


def test_parse_retry_after() -> None:
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after(" 2.5 ") == 2.5
    assert parse_retry_after("-3") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("soon") is None
    assert parse_retry_after("inf") is None
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Sun, 01 Nov 2026 12:01:30 GMT", now=now) == 90.0
    assert parse_retry_after("Sun, 01 Nov 2026 11:00:00 GMT", now=now) == 0.0


def test_is_rate_limited() -> None:
    assert is_rate_limited(429, None)
    assert is_rate_limited(429, 5.0)
    assert is_rate_limited(503, 0.0)
    assert not is_rate_limited(503, None)  # a plain 503 stays an error page
    assert not is_rate_limited(500, 5.0)
    assert not is_rate_limited(200, None)
    assert not is_rate_limited(None, None)


def test_backoff_seconds_doubles_to_the_cap() -> None:
    pauses = [backoff_seconds(n, None, base=30, cap=300) for n in range(1, 7)]
    assert pauses == [30, 60, 120, 240, 300, 300]
    assert backoff_seconds(1, 7.0, base=30, cap=300) == 7.0
    assert backoff_seconds(4, 7.0, base=30, cap=300) == 7.0  # header wins
    assert backoff_seconds(1, 900.0, base=30, cap=300) == 300  # header capped
    assert backoff_seconds(10_000, None, base=30, cap=300) == 300


@pytest.mark.asyncio
async def test_goto_page_reads_retry_after_header() -> None:
    page = MagicMock()
    page.goto = AsyncMock(
        return_value=MagicMock(
            status=429, url="https://x.com/a", headers={"retry-after": "7"}
        )
    )
    nav = await goto_page(page, "https://x.com/a", timeout_ms=1000)
    assert (nav.status, nav.retry_after) == (429, 7.0)
    page.goto = AsyncMock(return_value=MagicMock(status=200, url="https://x.com/a"))
    assert (await goto_page(page, "https://x.com/a")).retry_after is None


# --- crawl ------------------------------------------------------------------


def _page(html: str) -> Any:
    page = MagicMock()
    page.url = ROOT
    page.content = AsyncMock(return_value=html)
    page.close = AsyncMock()
    page.route = AsyncMock()
    page.on = MagicMock()
    return page


def _fake_browser(tabs: int) -> tuple[Any, Any]:
    login = _page("<html>login</html>")
    context = AsyncMock()
    context.request = AsyncMock()
    context.set_default_navigation_timeout = MagicMock()
    context.set_default_timeout = MagicMock()
    context.new_page.side_effect = [login] + [_page(HTML) for _ in range(tabs)]
    browser = AsyncMock()
    browser.new_context.return_value = context
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    playwright.__aenter__ = AsyncMock(return_value=playwright)
    playwright.__aexit__ = AsyncMock(return_value=False)
    return playwright, login


Response = tuple[int, float | None]


async def _crawl(
    tmp_path: Path,
    responses: dict[str, list[Response]],
    *,
    links: list[str] | None = None,
    tabs: int = 1,
    **kwargs: Any,
) -> tuple[CrawlResult, list[str], list[float]]:
    """Crawl ROOT (linking to ``links``); ``responses[url]`` gives the (status,
    retry_after) of each successive fetch (the last repeats; default 200)."""
    playwright, login = _fake_browser(tabs)
    calls: list[str] = []
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def goto(page: object, url: str, **_: object) -> NavigationResult:
        if page is login:
            return NavigationResult(True, 200, url)
        calls.append(url)
        seq = responses.get(url, [(200, None)])
        status, retry_after = seq[min(calls.count(url), len(seq)) - 1]
        return NavigationResult(True, status, url, retry_after)

    async def extract(page: object) -> list[str]:
        return list(links if links is not None else [L1, L2])

    async def fake_sleep(seconds: float, *args: Any) -> None:
        if seconds >= 0.1:  # ignore the idle-queue polls
            sleeps.append(seconds)
        await real_sleep(0)

    with (
        patch("folio.crawler.async_playwright", return_value=playwright),
        patch("folio.crawler.goto_page", side_effect=goto),
        patch("folio.crawler.prepare_data_page", new_callable=AsyncMock),
        patch("folio.crawler.install_data_request_filter", new_callable=AsyncMock),
        patch("folio.crawler.extract_links", side_effect=extract),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        result = await run_crawl(
            ROOT,
            tmp_path,
            skip_login_wait=True,
            page_concurrency=tabs,
            data_only=True,
            retry_delay=0,
            **kwargs,
        )
    return result, calls, sleeps


def _saved(tmp_path: Path, n: int) -> Path:
    return tmp_path / "www.example.com" / "details" / f"{n}.html"


@pytest.mark.asyncio
async def test_429_with_retry_after_pauses_requeues_and_saves(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    result, calls, sleeps = await _crawl(
        tmp_path, {L1: [(429, 7.0), (200, None)]}, adaptive=False
    )
    assert sleeps == [7.0]
    # Re-queued on the main queue (no end-of-run retry round), fetched again, saved.
    assert calls.count(L1) == 2 and calls.count(L2) == 1
    assert (result.pages_saved, result.pages_failed) == (3, 0)
    assert result.rate_limit_pauses == 1 and result.final_delay == 0.0
    assert _saved(tmp_path, 1).exists()
    err = capsys.readouterr().err
    assert err.count("Rate limited (HTTP 429): pausing 7 s") == 1
    assert "Retrying" not in err  # not the end-of-run retry list


@pytest.mark.asyncio
async def test_consecutive_429s_double_to_the_cap(tmp_path: Path) -> None:
    limited: list[Response] = [(429, None)] * 5
    responses: dict[str, list[Response]] = {L1: [*limited, (200, None)]}
    result, calls, sleeps = await _crawl(
        tmp_path,
        responses,
        links=[L1],  # nothing else to save in between: the 429s are consecutive
        backoff=30,
        max_backoff=100,
        retry_failed=5,
        adaptive=False,
    )
    assert sleeps == [30, 60, 100, 100, 100]
    assert calls == [ROOT] + [L1] * 6
    assert (result.pages_saved, result.pages_failed) == (2, 0)


@pytest.mark.asyncio
async def test_retry_after_is_capped(tmp_path: Path) -> None:
    _, _, sleeps = await _crawl(
        tmp_path, {L1: [(429, 900.0), (200, None)]}, max_backoff=300, adaptive=False
    )
    assert sleeps == [300]


@pytest.mark.asyncio
async def test_success_resets_the_backoff(tmp_path: Path) -> None:
    # The re-queued L1 goes behind L2; L2 saves in between, so L1's second 429 is a
    # first pause again (30, not 60).
    responses: dict[str, list[Response]] = {L1: [(429, None), (429, None), (200, None)]}
    result, calls, sleeps = await _crawl(
        tmp_path, responses, retry_failed=3, adaptive=False
    )
    assert calls == [ROOT, L1, L2, L1, L1]
    assert sleeps == [30, 30]
    assert (result.pages_saved, result.pages_failed) == (3, 0)


@pytest.mark.asyncio
async def test_rate_limited_beyond_retry_failed_counts_failed(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    result, calls, sleeps = await _crawl(
        tmp_path, {L1: [(429, 1.0)]}, retry_failed=1, adaptive=False
    )
    assert calls.count(L1) == 2
    assert sleeps == [1.0, 1.0]
    assert (result.pages_saved, result.pages_failed) == (2, 1)
    assert not _saved(tmp_path, 1).exists()
    assert "Failed (rate limited 2 time(s), left unsaved)" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_plain_503_stays_an_error_page(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    result, calls, sleeps = await _crawl(tmp_path, {L1: [(503, None), (200, None)]})
    assert sleeps == []
    assert result.rate_limit_pauses == 0
    assert calls[-1] == L1 and result.pages_failed == 0  # end-of-run retry (T17)
    assert "Skipped (HTTP 503)" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_503_with_retry_after_is_a_rate_limit(tmp_path: Path) -> None:
    result, _, sleeps = await _crawl(
        tmp_path, {L1: [(503, 4.0), (200, None)]}, adaptive=False
    )
    assert sleeps == [4.0] and result.rate_limit_pauses == 1


@pytest.mark.asyncio
async def test_adaptive_raises_the_per_page_delay(tmp_path: Path) -> None:
    # Data-only: adaptive is on by default.
    result, _, sleeps = await _crawl(
        tmp_path, {L1: [(429, 7.0), (200, None)]}, adaptive_step=1.5
    )
    assert result.final_delay == 1.5
    assert sleeps[0] == 7.0
    assert set(sleeps[1:]) == {1.5}  # every later page waits the new delay

    result, _, sleeps = await _crawl(
        tmp_path / "b",
        {L1: [(429, 7.0), (429, 7.0), (200, None)]},
        delay_seconds=2.0,
        retry_failed=2,
    )
    assert result.final_delay == 4.0  # 2 + 1 + 1


@pytest.mark.asyncio
async def test_no_adaptive_keeps_the_delay(tmp_path: Path) -> None:
    result, _, sleeps = await _crawl(
        tmp_path, {L1: [(429, 7.0), (200, None)]}, delay_seconds=0.5, adaptive=False
    )
    assert result.final_delay == 0.5
    assert sleeps == [0.5, 7.0, 0.5, 0.5]


@pytest.mark.asyncio
async def test_all_tabs_hold_during_a_cooldown(tmp_path: Path) -> None:
    # Three tabs; the second fetch is rate limited. One pause is taken, the other
    # tabs wait at the gate rather than fetching through it, and everything saves.
    responses: dict[str, list[Response]] = {
        L1: [(429, 5.0), (200, None)],
        L2: [(429, 5.0), (200, None)],
    }
    result, calls, sleeps = await _crawl(
        tmp_path, responses, links=[L1, L2, L3], tabs=3, adaptive=False
    )
    assert (result.pages_saved, result.pages_failed) == (4, 0)
    assert calls.count(L1) == 2 and calls.count(L2) == 2
    assert 1 <= len(sleeps) <= 2 and set(sleeps) == {5.0}


@pytest.mark.asyncio
async def test_negative_backoff_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="backoff"):
        await run_crawl(ROOT, tmp_path, backoff=-1)
    with pytest.raises(ValueError, match="adaptive_step"):
        await run_crawl(ROOT, tmp_path, adaptive_step=-1)


# --- CLI --------------------------------------------------------------------


def _run_cli(argv: list[str]) -> dict[str, Any]:
    result = CrawlResult("https://a.com/x", 1, 0, Path("output"))
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        assert main(["crawl", "https://a.com/x", "--skip-login-wait", *argv]) == 0
    assert mock_crawl.await_args is not None
    return dict(mock_crawl.await_args.kwargs)


def test_cli_rate_limit_defaults() -> None:
    kwargs = _run_cli([])
    assert kwargs["backoff"] == 30.0
    assert kwargs["max_backoff"] == 300.0
    assert kwargs["adaptive"] is None  # run_crawl: on for data-only
    assert kwargs["adaptive_step"] == 1.0


def test_cli_rate_limit_flags() -> None:
    kwargs = _run_cli(
        [
            "--backoff",
            "10",
            "--max-backoff",
            "120",
            "--adaptive",
            "--adaptive-step",
            "0.5",
        ]
    )
    assert (kwargs["backoff"], kwargs["max_backoff"]) == (10.0, 120.0)
    assert kwargs["adaptive"] is True and kwargs["adaptive_step"] == 0.5
    assert _run_cli(["--data-only", "--no-adaptive"])["adaptive"] is False


@pytest.mark.parametrize("flag", ["--backoff", "--max-backoff", "--adaptive-step"])
def test_cli_rejects_negative(flag: str, capsys: CaptureFixture[str]) -> None:
    with patch("folio.cli.run_crawl", new_callable=AsyncMock) as mock_crawl:
        assert main(["crawl", "https://a.com/x", flag, "-1"]) == 1
    mock_crawl.assert_not_called()
    assert flag in capsys.readouterr().err


def test_stats_line_reports_final_delay(capsys: CaptureFixture[str]) -> None:
    result = CrawlResult(
        "https://a.com/x",
        20,
        0,
        Path("output"),
        crawl_seconds=40.0,
        page_seconds=76.0,
        final_delay=3.0,
        rate_limit_pauses=3,
    )
    line = format_crawl_stats(result, 2)
    assert line.endswith("(concurrency 2); final delay 3 s/page, 3 rate-limit pause(s)")
    with patch("folio.cli.run_crawl", new_callable=AsyncMock, return_value=result):
        assert main(["crawl", "https://a.com/x", "--data-only", "--stats"]) == 0
    assert "final delay 3 s/page" in capsys.readouterr().out
