"""Strip executable content from saved HTML for static offline browsing."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

JS_LINK_RELS = frozenset({"modulepreload", "manifest", "prerender"})
JS_PRELOAD_AS = frozenset({"script", "fetch", "worker"})
DATA_SCRIPT_TYPES = frozenset({"application/json", "application/ld+json"})
"""Script types browsers never execute; safe to keep in a static snapshot."""
MIN_INLINE_DATA_CHARS = 200


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


def extract_data_scripts(html: str) -> dict[str, list[dict[str, str]]]:
    """Collect the page's embedded data for a sidecar file.

    ``json_scripts``: every ``<script type="application/json|ld+json">`` body.
    ``inline_scripts``: inline (no ``src``) executable scripts that look like data
    assignments — at least :data:`MIN_INLINE_DATA_CHARS` long and containing ``{``
    (e.g. ``window.PAGE_MODEL = {...}``, ``__NEXT_DATA__``). Consumers parse these
    offline; the HTML snapshot itself stays script-free.
    """
    soup = BeautifulSoup(html, "html.parser")
    json_scripts: list[dict[str, str]] = []
    inline_scripts: list[dict[str, str]] = []
    for script in soup.find_all("script"):
        text = script.string if script.string is not None else script.get_text()
        text = (text or "").strip()
        if not text:
            continue
        script_type = _script_type(script)
        entry = {"type": script_type, "id": str(script.get("id") or ""), "text": text}
        if script_type in DATA_SCRIPT_TYPES:
            json_scripts.append(entry)
        elif (
            not script.has_attr("src")
            and len(text) >= MIN_INLINE_DATA_CHARS
            and "{" in text
        ):
            inline_scripts.append(entry)
    return {"json_scripts": json_scripts, "inline_scripts": inline_scripts}
