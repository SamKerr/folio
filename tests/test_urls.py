from pathlib import Path

import pytest

from folio.urls import (
    is_excluded_url,
    normalize_url,
    same_host,
    url_path_depth,
    url_path_section,
    url_to_output_path,
)


def test_normalize_url_strips_fragment_and_lowercases_host() -> None:
    assert (
        normalize_url("HTTPS://Example.com/path#section")
        == "https://example.com/path"
    )


def test_normalize_url_resolves_relative_link() -> None:
    assert (
        normalize_url("/learn", base="https://www.example.com/pricing")
        == "https://www.example.com/learn"
    )


def test_normalize_url_strips_trailing_slash() -> None:
    assert normalize_url("https://example.com/about/") == "https://example.com/about"


def test_normalize_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        normalize_url("mailto:test@example.com")


def test_same_host_matches_www_prefix() -> None:
    root = "https://www.example.com/"
    assert same_host("https://www.example.com/learn", root)
    assert not same_host("https://example.com/learn", root)


def test_url_to_output_path_root() -> None:
    path = url_to_output_path("https://www.example.com/", Path("output"))
    assert path == Path("output/www.example.com/index.html")


def test_url_to_output_path_nested() -> None:
    path = url_to_output_path(
        "https://www.example.com/learn/system-design",
        Path("output"),
    )
    assert path == Path("output/www.example.com/learn/system-design.html")


def test_url_path_section_uses_first_segment() -> None:
    assert url_path_section("https://example.com/") == ""
    assert url_path_section("https://example.com/learn") == "learn"
    assert url_path_section("https://example.com/learn/first") == "learn"
    assert url_path_section("https://example.com/code/foo") == "code"


def test_url_path_depth_counts_segments() -> None:
    assert url_path_depth("https://example.com/") == 0
    assert url_path_depth("https://example.com/learn") == 1
    assert url_path_depth("https://example.com/learn/first") == 2


def test_is_excluded_url_matches_path_globs() -> None:
    patterns = ("/community/*",)
    assert is_excluded_url(
        "https://www.example.com/community/discussions",
        patterns,
    )
    assert is_excluded_url("https://www.example.com/community", patterns)
    assert not is_excluded_url(
        "https://www.example.com/learn/system-design",
        patterns,
    )
