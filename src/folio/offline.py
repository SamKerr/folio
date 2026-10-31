"""Strip executable content from saved HTML for static offline browsing."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString

JS_LINK_RELS = frozenset({"modulepreload", "manifest", "prerender"})
JS_PRELOAD_AS = frozenset({"script", "fetch", "worker"})
DATA_SCRIPT_TYPES = frozenset({"application/json", "application/ld+json"})
"""Script types browsers never execute; safe to keep in a static snapshot."""
MIN_INLINE_DATA_CHARS = 200

DATA_MARKERS: tuple[str, ...] = (
    "__PAGE_MODEL",
    "PAGE_MODEL",
    "__NEXT_DATA__",
    "__PRELOADED_STATE__",
    "__INITIAL_STATE__",
    "__NUXT__",
    "__APOLLO_STATE__",
    "__REDUX_STATE__",
    "initialState",
    "window.__data",
)
"""Substrings that mark an inline script as page state in data-only sidecars.

``dataLayer`` (analytics) is deliberately not a marker. Extend per run with
``--data-marker``.
"""
MAX_DATA_SCRIPT_BYTES = 2 * 1024 * 1024
"""Data-only sidecars drop any single script larger than this (UTF-8 bytes);
truncating would leave unparseable JSON / JS."""

DATA_ONLY_KEEP_LINK_RELS = frozenset({"canonical", "next", "prev"})
WHITESPACE_KEEP_PARENTS = frozenset({"pre", "textarea"})
DATA_ONLY_DROP_TAGS = (
    "style",
    "svg",
    "img",
    "picture",
    "source",
    "video",
    "audio",
    "iframe",
    "noscript",
    "object",
    "embed",
)


def _rel_values(tag: Tag) -> set[str]:
    rel_attr = tag.get("rel")
    if rel_attr is None:
        return set()
    if isinstance(rel_attr, str):
        return {rel_attr.lower()}
    return {str(value).lower() for value in rel_attr}


def _script_type(tag: Tag) -> str:
    value = tag.get("type")
    return str(value).strip().lower() if isinstance(value, str) else ""


def prepare_static_snapshot(html: str, *, keep_data_scripts: bool = False) -> str:
    """Remove scripts and other executable hooks; keep HTML structure and styles.

    With ``keep_data_scripts`` the non-executable JSON scripts
    (:data:`DATA_SCRIPT_TYPES`, e.g. schema.org JSON-LD) stay in the snapshot.
    """
    soup = BeautifulSoup(html, "html.parser")

    for script in list(soup.find_all("script")):
        if keep_data_scripts and _script_type(script) in DATA_SCRIPT_TYPES:
            continue
        script.decompose()

    for link in list(soup.find_all("link", rel=True)):
        rels = _rel_values(link)
        if rels & JS_LINK_RELS:
            link.decompose()
            continue
        if "preload" in rels and str(link.get("as", "")).lower() in JS_PRELOAD_AS:
            link.decompose()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on"):
                del tag[attr]

    for video in soup.find_all("video"):
        if video.has_attr("src"):
            del video["src"]
        for source in video.find_all("source"):
            source.decompose()

    for audio in soup.find_all("audio"):
        if audio.has_attr("src"):
            del audio["src"]
        for source in audio.find_all("source"):
            source.decompose()

    return str(soup)


# Backwards-compatible alias used by asset mirroring.
prepare_for_offline = prepare_static_snapshot


def prepare_data_snapshot(html: str, *, base_url: str | None = None) -> str:
    """Reduce a page to its text, structure and head metadata (data-only mode).

    Removes executable scripts (JSON script types stay), styles, SVG, media,
    iframes, ``<noscript>``, ``<object>`` / ``<embed>``, every ``<link>`` except
    ``rel=canonical|next|prev``, inline ``style=`` and ``on*=`` attributes, and HTML
    comments. Keeps ``<title>``, ``<meta>``, the body text / structure and anchors
    (with any ``data-folio-url``). With ``base_url`` the kept links' hrefs are made
    absolute so a resumed crawl can follow them. Idempotent.
    """
    soup = BeautifulSoup(html, "html.parser")

    for script in list(soup.find_all("script")):
        if _script_type(script) not in DATA_SCRIPT_TYPES:
            script.decompose()

    for tag in list(soup.find_all(DATA_ONLY_DROP_TAGS)):
        if not tag.decomposed:
            tag.decompose()

    for link in list(soup.find_all("link")):
        if not _rel_values(link) & DATA_ONLY_KEEP_LINK_RELS:
            link.decompose()
            continue
        href = link.get("href")
        if base_url and isinstance(href, str) and href:
            link["href"] = urljoin(base_url, href)

    for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
        comment.extract()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr == "style" or attr.startswith("on"):
                del tag[attr]

    _collapse_whitespace_nodes(soup)
    return str(soup)


def _collapse_whitespace_nodes(soup: BeautifulSoup) -> None:
    """Shrink whitespace-only text nodes left by removals to one character and drop
    repeats, so the output is compact and re-parsing it gives the same string."""
    for text in list(soup.find_all(string=True)):
        if text.strip() or not isinstance(text, NavigableString):
            continue
        parent = text.parent
        if parent is not None and parent.name in WHITESPACE_KEEP_PARENTS:
            continue
        previous = text.previous_sibling
        if isinstance(previous, NavigableString) and not previous.strip():
            text.extract()
            continue
        text.replace_with("\n" if "\n" in text else " ")


def _script_text(script: Tag) -> str:
    text = script.string if script.string is not None else script.get_text()
    return (text or "").strip()


def _within_cap(text: str) -> bool:
    return len(text.encode("utf-8")) <= MAX_DATA_SCRIPT_BYTES


def is_page_state_script(text: str, markers: Iterable[str]) -> bool:
    """True when an inline script's text contains one of the page-state markers."""
    return any(marker and marker in text for marker in markers)


def extract_data_scripts(
    html: str, *, markers: Iterable[str] | None = None
) -> dict[str, list[dict[str, str]]]:
    """Collect the page's embedded data for a sidecar file.

    ``json_scripts``: every ``<script type="application/json|ld+json">`` body.
    ``inline_scripts``: inline (no ``src``) executable scripts that look like data
    assignments — at least :data:`MIN_INLINE_DATA_CHARS` long and containing ``{``
    (e.g. ``window.PAGE_MODEL = {...}``, ``__NEXT_DATA__``). Consumers parse these
    offline; the HTML snapshot itself stays script-free.

    With ``markers`` (data-only mode) an inline script is kept only when it
    contains one of them (see :data:`DATA_MARKERS`), and any script over
    :data:`MAX_DATA_SCRIPT_BYTES` is dropped.
    """
    marker_list = tuple(markers) if markers is not None else None
    soup = BeautifulSoup(html, "html.parser")
    json_scripts: list[dict[str, str]] = []
    inline_scripts: list[dict[str, str]] = []
    for script in soup.find_all("script"):
        text = _script_text(script)
        if not text:
            continue
        if marker_list is not None and not _within_cap(text):
            continue
        script_type = _script_type(script)
        entry = {"type": script_type, "id": str(script.get("id") or ""), "text": text}
        if script_type in DATA_SCRIPT_TYPES:
            json_scripts.append(entry)
        elif (
            not script.has_attr("src")
            and len(text) >= MIN_INLINE_DATA_CHARS
            and "{" in text
            and (marker_list is None or is_page_state_script(text, marker_list))
        ):
            inline_scripts.append(entry)
    return {"json_scripts": json_scripts, "inline_scripts": inline_scripts}


def filter_sidecar(data: dict[str, Any], markers: Iterable[str]) -> dict[str, Any]:
    """Apply the data-only rules to an existing sidecar dict (``folio slim``)."""
    marker_list = tuple(markers)

    def entries(key: str) -> list[dict[str, Any]]:
        value = data.get(key)
        if not isinstance(value, list):
            return []
        return [
            entry
            for entry in value
            if isinstance(entry, dict)
            and isinstance(entry.get("text"), str)
            and _within_cap(entry["text"])
        ]

    filtered = dict(data)
    filtered["json_scripts"] = entries("json_scripts")
    filtered["inline_scripts"] = [
        entry
        for entry in entries("inline_scripts")
        if is_page_state_script(entry["text"], marker_list)
    ]
    return filtered
