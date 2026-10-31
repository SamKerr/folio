from pathlib import Path

import pytest

from folio.urls import (
    is_excluded_url,
    is_included_url,
    normalize_url,
    output_path_to_url,
    same_host,
    url_path_depth,
    url_path_section,
    url_to_output_path,
)


def test_normalize_url_strips_fragment_and_lowercases_host() -> None:
    assert (
        normalize_url("HTTPS://Example.com/path#section") == "https://example.com/path"
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


def test_is_included_url_empty_means_everything() -> None:
    assert is_included_url("https://a.com/anything", [])


def test_is_included_url_restricts_to_patterns() -> None:
    patterns = ["/properties/*", "/property-for-sale/find.html*"]
    assert is_included_url("https://a.com/properties/123", patterns)
    assert is_included_url("https://a.com/property-for-sale/find.html?x=1", patterns)
    assert not is_included_url("https://a.com/help", patterns)


def test_url_to_output_path_keep_query_separates_pages() -> None:
    out = Path("output")
    page1 = url_to_output_path("https://a.com/find.html?index=0", out, keep_query=True)
    page2 = url_to_output_path("https://a.com/find.html?index=24", out, keep_query=True)
    plain = url_to_output_path("https://a.com/find.html?index=24", out)
    assert page1 != page2
    assert page1.parent == Path("output/a.com") and page1.name.startswith("find.q")
    assert page1.suffix == ".html" and len(page1.stem) == len("find.q") + 10
    assert plain == Path("output/a.com/find.html")
    root = url_to_output_path("https://a.com/?q=1", out, keep_query=True)
    assert root.parent == Path("output/a.com") and root.name.startswith("index.q")


def test_output_path_to_url_strips_query_tag() -> None:
    url = output_path_to_url(
        Path("output/a.com/find.q0123456789.html"), Path("output"), "https://a.com/"
    )
    assert url == "https://a.com/find"
