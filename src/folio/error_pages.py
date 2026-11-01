"""Recognise a site's own error / challenge pages so they are never saved as content."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

DEFAULT_ERROR_PATHS: tuple[str, ...] = ("/otm-errors/", "/error", "/404", "/500")
"""Final-URL path patterns (whole path segments) that mark an error page."""

DEFAULT_ERROR_TITLES: tuple[str, ...] = (
    "Just a moment...",
    "Access denied",
    "Attention Required",
    "captcha",
)
"""``<title>`` substrings (case-insensitive) that mark an error / challenge page."""

NEXT_DATA_ID = "__NEXT_DATA__"


@dataclass(frozen=True)
class ErrorRules:
    paths: tuple[str, ...] = DEFAULT_ERROR_PATHS
    titles: tuple[str, ...] = DEFAULT_ERROR_TITLES

    @classmethod
    def build(cls, extra: Iterable[str] = ()) -> ErrorRules:
        """Defaults plus ``extra``: a pattern starting with ``/`` is a path pattern,
        anything else a title marker."""
        paths = list(DEFAULT_ERROR_PATHS)
        titles = list(DEFAULT_ERROR_TITLES)
        for pattern in extra:
            cleaned = pattern.strip()
            if not cleaned:
                continue
            (paths if cleaned.startswith("/") else titles).append(cleaned)
        return cls(tuple(dict.fromkeys(paths)), tuple(dict.fromkeys(titles)))


DEFAULT_ERROR_RULES = ErrorRules()


def _segments(path: str) -> list[str]:
    return [part.lower() for part in unquote(path).split("/") if part]


def _stem(segment: str) -> str:
    return segment.split(".", 1)[0]


def path_matches(path: str, pattern: str) -> bool:
    """True when ``pattern``'s segments appear as consecutive whole segments of
    ``path`` (case-insensitive; a path segment's extension is ignored), so ``/404``
    matches ``/404`` and ``/404.html`` but not ``/properties/40412``."""
    wanted = _segments(pattern)
    if not wanted:
        return False
    have = _segments(path)
    for start in range(len(have) - len(wanted) + 1):
        window = have[start : start + len(wanted)]
        if all(
            seg == want or _stem(seg) == want
            for seg, want in zip(window, wanted, strict=True)
        ):
            return True
    return False


def status_reason(status: int | None) -> str | None:
    if status is not None and status >= 400:
        return f"HTTP {status}"
    return None


def path_reason(path: str, rules: ErrorRules = DEFAULT_ERROR_RULES) -> str | None:
    for pattern in rules.paths:
        if path_matches(path, pattern):
            return f"error path {path}"
    return None


def url_reason(url: str | None, rules: ErrorRules = DEFAULT_ERROR_RULES) -> str | None:
    """Reason when the (final) URL's path matches an error path pattern."""
    if not url:
        return None
    try:
        path = urlsplit(url).path
    except ValueError:
        return None
    return path_reason(path, rules)


def title_reason(
    title: str | None, rules: ErrorRules = DEFAULT_ERROR_RULES
) -> str | None:
    if not title:
        return None
    lowered = title.lower()
    for marker in rules.titles:
        if marker.lower() in lowered:
            return f"error title {title.strip()!r}"
    return None


def _next_page(text: str) -> str | None:
    """``page`` of a ``__NEXT_DATA__`` JSON body, if it parses."""
    try:
        data: Any = json.loads(text)
    except ValueError:
        return None
    page = data.get("page") if isinstance(data, dict) else None
    return page if isinstance(page, str) else None


def next_page_reason(
    page: str | None, rules: ErrorRules = DEFAULT_ERROR_RULES
) -> str | None:
    if not page:
        return None
    for pattern in rules.paths:
        if path_matches(page, pattern):
            return f"error page {page}"
    return None


def html_reason(html: str, rules: ErrorRules = DEFAULT_ERROR_RULES) -> str | None:
    """Reason when a page's ``<title>`` or Next.js ``__NEXT_DATA__.page`` marks it as
    an error page (the fallback for sites that answer 200 with an error page)."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("title")
    reason = title_reason(title.get_text() if title is not None else None, rules)
    if reason:
        return reason
    script = soup.find("script", id=NEXT_DATA_ID)
    if script is not None:
        return next_page_reason(_next_page(script.get_text()), rules)
    return None


def sidecar_reason(text: str, rules: ErrorRules = DEFAULT_ERROR_RULES) -> str | None:
    """Reason when a ``<page>.data.json`` sidecar holds an error page's
    ``__NEXT_DATA__``."""
    try:
        data: Any = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("json_scripts", "inline_scripts"):
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if (
                isinstance(entry, dict)
                and entry.get("id") == NEXT_DATA_ID
                and isinstance(entry.get("text"), str)
            ):
                reason = next_page_reason(_next_page(entry["text"]), rules)
                if reason:
                    return reason
    return None
