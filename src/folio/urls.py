"""URL normalization and output path helpers for crawling."""

from __future__ import annotations

import fnmatch
import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(url: str, *, base: str | None = None) -> str:
    """Resolve relative URLs and strip fragments for deduplication."""
    if base is not None:
        url = urljoin(base, url)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported URL scheme: {parsed.scheme!r}"
        raise ValueError(msg)

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def same_host(url: str, root_url: str) -> bool:
    """Return True when both URLs share the same hostname."""
    return urlparse(url).netloc.lower() == urlparse(root_url).netloc.lower()


def url_path_segments(url: str) -> list[str]:
    """Return non-empty path segments for a URL."""
    return [segment for segment in urlparse(url).path.strip("/").split("/") if segment]


def url_path_section(url: str) -> str:
    """Return the top-level path prefix used for section-first crawl ordering."""
    segments = url_path_segments(url)
    return segments[0] if segments else ""


def url_path_depth(url: str) -> int:
    """Return the number of path segments (shallower URLs sort earlier)."""
    return len(url_path_segments(url))


def _matches_any(url: str, patterns: Sequence[str]) -> bool:
    """Return True when a URL matches any path or URL glob pattern."""
    try:
        normalized = normalize_url(url)
    except ValueError:
        return False

    parsed = urlparse(normalized)
    path = parsed.path or "/"

    for raw_pattern in patterns:
        pattern = raw_pattern.strip()
        if not pattern:
            continue

        if pattern.startswith(("http://", "https://")):
            if fnmatch.fnmatch(normalized, pattern):
                return True
            continue

        path_pattern = pattern if pattern.startswith("/") else f"/{pattern}"
        if fnmatch.fnmatch(path, path_pattern):
            return True

        if path_pattern.endswith("/*"):
            prefix = path_pattern[:-2]
            if path == prefix or path.startswith(f"{prefix}/"):
                return True
            continue

        if not any(char in path_pattern for char in "*?[]"):
            if path == path_pattern or path.startswith(f"{path_pattern}/"):
                return True

    return False


def is_excluded_url(url: str, exclude_patterns: Sequence[str]) -> bool:
    """Return True when a URL matches any exclude path or URL glob pattern."""
    if not exclude_patterns:
        return False
    return _matches_any(url, exclude_patterns)


def is_included_url(url: str, include_patterns: Sequence[str]) -> bool:
    """Return True when no include patterns are set, or the URL matches one.

    Include patterns restrict a crawl to a subset of a site (e.g. ``/properties/*``);
    the start URLs are always allowed by the crawler regardless.
    """
    if not include_patterns:
        return True
    return _matches_any(url, include_patterns)


QUERY_SUFFIX = re.compile(r"\.q[0-9a-f]{10}$")


def query_tag(query: str) -> str:
    """Short stable tag for a query string, used in output file names."""
    return "q" + hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]


def url_to_output_path(url: str, output_dir: Path, *, keep_query: bool = False) -> Path:
    """Map a crawled URL to a local HTML file under output_dir.

    With ``keep_query`` a URL that carries a query string gets its own file,
    ``<name>.q<hash>.html``, so search pages that differ only by query (page 2,
    filters) do not overwrite each other.
    """
    parsed = urlparse(url)
    host_dir = output_dir / parsed.netloc.lower()
    path = parsed.path or "/"

    if path == "/":
        base = host_dir / "index.html"
    else:
        segments = [segment for segment in path.strip("/").split("/") if segment]
        base = host_dir.joinpath(*segments).with_suffix(".html")

    if keep_query and parsed.query:
        return base.with_name(f"{base.stem}.{query_tag(parsed.query)}.html")
    return base


def output_path_to_url(path: Path, output_dir: Path, root_url: str) -> str | None:
    """Map a saved HTML file back to its canonical URL."""
    parsed_root = urlparse(root_url)
    host = parsed_root.netloc.lower()
    host_dir = (output_dir / host).resolve()
    try:
        relative = path.resolve().relative_to(host_dir)
    except ValueError:
        return None

    if relative.suffix != ".html":
        return None
    stem = QUERY_SUFFIX.sub("", relative.stem)  # the query itself is not recoverable
    relative = relative.with_name(f"{stem}.html")
    if relative.name == "index.html" and len(relative.parts) == 1:
        url_path = "/"
    else:
        url_path = "/" + str(relative.with_suffix("")).replace("\\", "/")

    return urlunparse(
        (
            parsed_root.scheme.lower(),
            host,
            url_path,
            "",
            "",
            "",
        )
    )
