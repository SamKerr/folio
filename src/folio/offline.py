"""Strip executable content from saved HTML for static offline browsing."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

JS_LINK_RELS = frozenset({"modulepreload", "manifest", "prerender"})
JS_PRELOAD_AS = frozenset({"script", "fetch", "worker"})


def _rel_values(tag: Tag) -> set[str]:
    rel_attr = tag.get("rel")
    if rel_attr is None:
        return set()
    if isinstance(rel_attr, str):
        return {rel_attr.lower()}
    return {str(value).lower() for value in rel_attr}


def prepare_static_snapshot(html: str) -> str:
    """Remove scripts and other executable hooks; keep HTML structure and styles."""
    soup = BeautifulSoup(html, "html.parser")

    for script in list(soup.find_all("script")):
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
