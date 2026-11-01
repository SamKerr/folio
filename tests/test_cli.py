from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from _pytest.capture import CaptureFixture

from folio.cli import main


def test_version(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "folio 0.1.0" in captured.out


def test_help(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "doctor" in captured.out


def test_doctor_success(capsys: CaptureFixture[str]) -> None:
    with patch("folio.cli.run_doctor", new_callable=AsyncMock) as mock_doctor:
        assert main(["doctor"]) == 0

    mock_doctor.assert_awaited_once()
    captured = capsys.readouterr()
    assert "Doctor check passed" in captured.out


def test_doctor_failure(capsys: CaptureFixture[str]) -> None:
    with patch(
        "folio.cli.run_doctor",
        new_callable=AsyncMock,
        side_effect=RuntimeError("browser missing"),
    ):
        assert main(["doctor"]) == 1

    captured = capsys.readouterr()
    assert "Doctor check failed" in captured.err
    assert "playwright install chromium" in captured.err


def test_no_command_prints_help(capsys: CaptureFixture[str]) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()


def test_crawl_help(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["crawl", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--skip-login-wait" in captured.out
    assert "--max-pages" in captured.out


def test_crawl_success(capsys: CaptureFixture[str]) -> None:
    crawl_result = MagicMock(pages_saved=3, pages_skipped=0, output_dir=Path("output"))

    with patch("folio.cli.run_crawl", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = crawl_result
        assert (
            main(
                [
                    "crawl",
                    "https://www.example.com/",
                    "--skip-login-wait",
                    "--max-pages",
                    "3",
                ]
            )
            == 0
        )

    mock_crawl.assert_awaited_once()
    captured = capsys.readouterr()
    assert "Crawl complete: saved 3 new page(s), skipped 0 existing" in captured.out


def test_crawl_failure(capsys: CaptureFixture[str]) -> None:
    with patch(
        "folio.cli.run_crawl",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        assert main(["crawl", "https://www.example.com/"]) == 1

    captured = capsys.readouterr()
    assert "Crawl failed" in captured.err


def test_crawl_passes_include_keep_query_and_extra_urls(
    capsys: CaptureFixture[str],
) -> None:
    from folio.crawler import CrawlResult

    result = CrawlResult("https://a.com/x", 2, 0, Path("output"))
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        code = main(
            [
                "crawl",
                "https://a.com/x",
                "https://a.com/y",
                "--include",
                "/p/*",
                "--keep-query",
                "--data-sidecar",
                "--headless",
                "--skip-login-wait",
            ]
        )
    assert code == 0
    assert mock_crawl.await_args is not None
    args, kwargs = mock_crawl.await_args
    assert args[0] == "https://a.com/x"
    assert kwargs["extra_start_urls"] == ("https://a.com/y",)
    assert kwargs["include_patterns"] == ("/p/*",)
    assert kwargs["keep_query"] is True
    assert kwargs["data_sidecar"] is True
    assert "saved 2 new page(s)" in capsys.readouterr().out


def test_crawl_passes_data_only_markers_and_gzip() -> None:
    from folio.crawler import CrawlResult

    result = CrawlResult("https://a.com/x", 1, 0, Path("output"))
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        code = main(
            [
                "crawl",
                "https://a.com/x",
                "--data-only",
                "--data-marker",
                "__MY_STATE__",
                "--data-marker",
                "listingData",
                "--gzip",
                "--skip-login-wait",
            ]
        )
    assert code == 0
    assert mock_crawl.await_args is not None
    kwargs = mock_crawl.await_args.kwargs
    assert kwargs["data_only"] is True
    assert kwargs["data_markers"] == ("__MY_STATE__", "listingData")
    assert kwargs["gzip_output"] is True


def test_crawl_gzip_without_data_only_fails(capsys: CaptureFixture[str]) -> None:
    with patch("folio.cli.run_crawl", new_callable=AsyncMock) as mock_crawl:
        assert main(["crawl", "https://a.com/x", "--gzip"]) == 1
    mock_crawl.assert_not_called()
    assert "--gzip requires --data-only" in capsys.readouterr().err


def test_slim_command(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    from folio.slim import SlimStats

    stats = SlimStats(html_files=2, html_before=2048, html_after=1024, changed=2)
    with patch("folio.slim.slim_site", return_value=stats) as mock_slim:
        assert main(["slim", str(tmp_path), "--gzip", "--data-marker", "X"]) == 0
    mock_slim.assert_called_once_with(tmp_path, gzip_output=True, extra_markers=("X",))
    out = capsys.readouterr().out
    assert "Slimmed 2 page(s): 2.0 KB -> 1.0 KB" in out


def test_slim_command_rejects_missing_dir(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    assert main(["slim", str(tmp_path / "nope")]) == 1
    assert "Not a directory" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [
        ([], "section"),
        (["--data-only"], "interleave"),
        (["--data-only", "--order", "section"], "section"),
        (["--order", "discovered"], "discovered"),
        (["--order", "interleave"], "interleave"),
    ],
)
def test_crawl_passes_order(extra_args: list[str], expected: str) -> None:
    from folio.crawler import CrawlResult

    result = CrawlResult("https://a.com/x", 1, 0, Path("output"))
    with patch(
        "folio.cli.run_crawl", new_callable=AsyncMock, return_value=result
    ) as mock_crawl:
        code = main(["crawl", "https://a.com/x", "--skip-login-wait", *extra_args])
    assert code == 0
    assert mock_crawl.await_args is not None
    assert mock_crawl.await_args.kwargs["order"] == expected


def test_crawl_rejects_unknown_order(capsys: CaptureFixture[str]) -> None:
    with patch("folio.cli.run_crawl", new_callable=AsyncMock) as mock_crawl:
        with pytest.raises(SystemExit):
            main(["crawl", "https://a.com/x", "--order", "random"])
    mock_crawl.assert_not_called()
    assert "invalid choice" in capsys.readouterr().err


def test_gui_defaults_to_web_ui() -> None:
    with patch("folio.webui.app.run_webui", return_value=0) as run_webui:
        assert main(["gui"]) == 0
    run_webui.assert_called_once_with(browser=False)


def test_gui_browser_flag() -> None:
    with patch("folio.webui.app.run_webui", return_value=0) as run_webui:
        assert main(["gui", "--browser"]) == 0
    run_webui.assert_called_once_with(browser=True)


def test_gui_classic_flag() -> None:
    with patch("folio.gui.run_gui") as run_gui:
        assert main(["gui", "--classic"]) == 0
    run_gui.assert_called_once_with()


def test_gui_browser_and_classic_are_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["gui", "--browser", "--classic"])
