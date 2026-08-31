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
