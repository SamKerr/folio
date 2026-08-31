"""URL normalization and output path helpers for crawling."""

from __future__ import annotations

import fnmatch
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


def is_excluded_url(url: str, exclude_patterns: Sequence[str]) -> bool:
    """Return True when a URL matches any exclude path or URL glob pattern."""
    if not exclude_patterns:
        return False

    try:
        normalized = normalize_url(url)
    except ValueError:
        return False

    parsed = urlparse(normalized)
    path = parsed.path or "/"

    for raw_pattern in exclude_patterns:
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


def url_to_output_path(url: str, output_dir: Path) -> Path:
    """Map a crawled URL to a local HTML file under output_dir."""
    parsed = urlparse(url)
    host_dir = output_dir / parsed.netloc.lower()
    path = parsed.path or "/"

    if path == "/":
        return host_dir / "index.html"

    segments = [segment for segment in path.strip("/").split("/") if segment]
    return host_dir.joinpath(*segments).with_suffix(".html")


def output_path_to_url(path: Path, output_dir: Path, root_url: str) -> str | None:
    """Map a saved HTML file back to its canonical URL."""
    parsed_root = urlparse(root_url)
    host = parsed_root.netloc.lower()
    host_dir = (output_dir / host).resolve()
    try:
        relative = path.resolve().relative_to(host_dir)
    except ValueError:
        return None

    if relative.name == "index.html" and len(relative.parts) == 1:
        url_path = "/"
    elif relative.suffix == ".html":
        url_path = "/" + str(relative.with_suffix("")).replace("\\", "/")
    else:
        return None

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
