"""Download and rewrite static assets for offline browsing."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from playwright.async_api import APIRequestContext, Page
from playwright.async_api import Error as PlaywrightError

from folio.browser_scripts import EXTRACT_ASSET_URLS
from folio.offline import prepare_static_snapshot
from folio.urls import normalize_url, same_host, url_to_output_path

CSS_URL_PATTERN = re.compile(r"""url\(\s*['"]?([^'")]+?)['"]?\s*\)""", re.IGNORECASE)
CSS_IMPORT_PATTERN = re.compile(
    r"""@import\s+(?:url\()?['"]?([^'"\s;)]+)['"]?\)?""",
    re.IGNORECASE,
)
INLINE_STYLE_URL_PATTERN = re.compile(
    r"""url\(\s*['"]?([^'")]+?)['"]?\s*\)""",
    re.IGNORECASE,
)

TAG_ATTRS: dict[str, tuple[str, ...]] = {
    "link": ("href",),
    "img": ("src", "data-src", "data-lazy-src"),
    "source": ("srcset", "data-srcset"),
    "video": ("poster",),
    "image": ("href", "xlink:href"),
    "use": ("href", "xlink:href"),
    "object": ("data",),
    "embed": ("src",),
    "input": ("src",),
}

MIRROR_LINK_RELS = frozenset(
    {"stylesheet", "icon", "shortcut icon", "apple-touch-icon", "preload"}
)
MIRROR_PRELOAD_AS = frozenset({"style", "font", "image"})


def url_to_asset_path(url: str, assets_root: Path) -> Path:
    """Map a remote asset URL to a local path under assets_root."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = (parsed.path or "/").rstrip("/") or "/"

    if path == "/":
        relative = Path(host) / "index.asset"
    else:
        relative = Path(host) / path.lstrip("/")
        if not Path(relative.name).suffix:
            relative = relative.with_name(f"{relative.name}.asset")

    if parsed.query:
        query_hash = hashlib.sha256(parsed.query.encode()).hexdigest()[:10]
        suffix = relative.suffix
        stem = relative.stem
        relative = relative.with_name(f"{stem}.{query_hash}{suffix}")

    return assets_root / relative


def relative_uri(from_file: Path, to_file: Path) -> str:
    """Return a relative path from one saved file to another."""
    return Path(os.path.relpath(to_file, start=from_file.parent)).as_posix()


def is_fetchable_url(url: str) -> bool:
    """Return True for http(s) URLs that can be downloaded."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"}


JS_EXTENSIONS = (".js", ".mjs", ".cjs", ".map")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi", ".ogv", ".m3u8")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a", ".aac")
SKIPPED_EXTENSIONS = JS_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS
ASSET_EXTENSIONS = frozenset(
    {
        ".css",
        ".scss",
        ".sass",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".avif",
        ".bmp",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".json",
        ".xml",
        ".txt",
        ".wasm",
    }
)
PAGE_LIKE_SUFFIXES = (".html", ".htm", ".php", ".asp", ".aspx")
KNOWN_ASSET_PATH_PREFIXES = (
    "/_next/static/",
    "/_next/image",
    "/static/",
    "/assets/",
    "/images/",
)


def is_known_asset_path(url: str) -> bool:
    """Return True for common extensionless asset routes (e.g. Next.js image proxy)."""
    path = urlparse(url).path.lower()
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in KNOWN_ASSET_PATH_PREFIXES
    )


def resolve_asset_url(url: str) -> str:
    """Map optimizer/proxy URLs to their underlying static asset when possible."""
    parsed = urlparse(url)
    if parsed.path.rstrip("/") != "/_next/image":
        return url

    inner_urls = parse_qs(parsed.query).get("url", [])
    if not inner_urls:
        return url

    inner_path = unquote(inner_urls[0])
    if not inner_path.startswith("/"):
        return url

    return normalize_url(inner_path, base=url)


def is_downloadable_asset_url(url: str) -> bool:
    """Return True for CSS/image/font URLs; skip JS, video, and audio."""
    path = urlparse(url).path.lower()
    return not path.endswith(SKIPPED_EXTENSIONS)


def is_same_host_page_url(url: str, *, base: str) -> bool:
    """Return True when a URL looks like a same-host HTML page, not a static asset."""
    try:
        absolute = normalize_url(url, base=base)
    except ValueError:
        return False

    if not same_host(absolute, base):
        return False

    if is_known_asset_path(absolute):
        return False

    path = urlparse(absolute).path.lower()
    suffix = Path(path).suffix
    if suffix in ASSET_EXTENSIONS or path.endswith(SKIPPED_EXTENSIONS):
        return False
    if suffix in PAGE_LIKE_SUFFIXES or not suffix:
        return True
    return False


def is_media_content_type(content_type: str) -> bool:
    """Return True for video/audio MIME types."""
    lowered = content_type.lower()
    return lowered.startswith("video/") or lowered.startswith("audio/")


def rewrite_srcset(
    value: str,
    *,
    page_url: str,
    file_path: Path,
    cache: dict[str, Path],
) -> str:
    """Rewrite each URL in an HTML srcset attribute."""
    rewritten: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        pieces = item.split()
        url = pieces[0]
        descriptor = " ".join(pieces[1:])
        try:
            absolute = normalize_url(url, base=page_url)
        except ValueError:
            rewritten.append(item)
            continue
        local_path = cache.get(absolute) or cache.get(resolve_asset_url(absolute))
        if local_path is None:
            rewritten.append(item)
            continue
        rel = relative_uri(file_path, local_path)
        rewritten.append(f"{rel} {descriptor}".strip())
    return ", ".join(rewritten)


async def extract_asset_urls(page: Page) -> list[str]:
    """Collect absolute asset URLs referenced by the rendered page."""
    raw_urls: list[str] = await page.evaluate(EXTRACT_ASSET_URLS)
    base = page.url
    return [
        url
        for url in raw_urls
        if is_fetchable_url(url)
        and is_downloadable_asset_url(url)
        and not is_same_host_page_url(url, base=base)
    ]


class AssetMirror:
    """Download assets once and rewrite HTML/CSS to reference local copies."""

    def __init__(
        self,
        request: APIRequestContext,
        output_dir: Path,
        *,
        assets_dirname: str = "_assets",
        concurrency: int = 12,
        keep_query: bool = False,
    ) -> None:
        self._request = request
        self._output_dir = output_dir
        self._keep_query = keep_query
        self.keep_data_scripts = False
        self._assets_root = output_dir / assets_dirname
        self._cache: dict[str, Path] = {}
        self._in_progress: set[str] = set()
        self._concurrency = max(1, concurrency)

    async def mirror_page(
        self,
        page: Page,
        *,
        page_url: str,
        html_path: Path,
        root_url: str,
        extra_urls: Iterable[str] = (),
    ) -> str:
        """Download page assets and return HTML with local references."""
        html = await page.content()
        discovered = set(await extract_asset_urls(page))
        discovered.update(extra_urls)
        await self.ensure_assets(discovered, base=page_url)

        rewritten = self.rewrite_html(
            html,
            page_url=page_url,
            html_path=html_path,
            root_url=root_url,
        )
        return prepare_static_snapshot(
            rewritten, keep_data_scripts=self.keep_data_scripts
        )

    async def ensure_assets(self, urls: Iterable[str], *, base: str) -> None:
        """Download many assets concurrently."""
        unique_urls = list(dict.fromkeys(urls))
        semaphore = asyncio.Semaphore(self._concurrency)

        async def download(url: str) -> None:
            async with semaphore:
                await self.ensure_asset(url, base=base)

        await asyncio.gather(*(download(url) for url in unique_urls))

    async def ensure_asset(self, url: str, *, base: str) -> Path | None:
        """Download an asset if needed and return its local path."""
        try:
            original = normalize_url(url, base=base)
        except ValueError:
            return None

        absolute = resolve_asset_url(original)

        if not is_fetchable_url(absolute):
            return None

        if not is_downloadable_asset_url(absolute):
            return None

        if is_same_host_page_url(absolute, base=base):
            return None

        if original in self._cache:
            return self._cache[original]
        if absolute in self._cache:
            self._cache[original] = self._cache[absolute]
            return self._cache[absolute]
        if original in self._in_progress or absolute in self._in_progress:
            return None

        self._in_progress.add(original)
        self._in_progress.add(absolute)
        local_path = url_to_asset_path(absolute, self._assets_root)
        if local_path.exists() and local_path.is_file():
            self._cache[absolute] = local_path
            self._cache[original] = local_path
            return local_path
        try:
            response = await self._request.get(absolute, timeout=30_000)
            if not response.ok:
                return None

            body = await response.body()
            local_path.parent.mkdir(parents=True, exist_ok=True)

            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type or is_media_content_type(content_type):
                return None
            if local_path.exists() and local_path.is_dir():
                return None
            if "css" in content_type or local_path.suffix == ".css":
                css_text = body.decode("utf-8", errors="replace")
                css_text = await self._rewrite_css(css_text, absolute, local_path)
                local_path.write_text(css_text, encoding="utf-8")
            else:
                local_path.write_bytes(body)

            self._cache[absolute] = local_path
            self._cache[original] = local_path
            return local_path
        except (PlaywrightError, OSError):
            return None
        finally:
            self._in_progress.discard(original)
            self._in_progress.discard(absolute)

    async def _rewrite_css(self, css_text: str, css_url: str, css_path: Path) -> str:
        for match in CSS_IMPORT_PATTERN.finditer(css_text):
            imported = match.group(1)
            if not is_fetchable_url(urljoin(css_url, imported)):
                continue
            await self.ensure_asset(imported, base=css_url)

        for match in CSS_URL_PATTERN.finditer(css_text):
            reference = match.group(1)
            if reference.startswith(("data:", "#", "blob:")):
                continue
            if not is_fetchable_url(urljoin(css_url, reference)):
                continue
            await self.ensure_asset(reference, base=css_url)

        def replace_url(match: re.Match[str]) -> str:
            reference = match.group(1)
            if reference.startswith(("data:", "#", "blob:")):
                return match.group(0)
            try:
                absolute = normalize_url(reference, base=css_url)
            except ValueError:
                return match.group(0)
            local_path = self._cache.get(absolute)
            if local_path is None:
                return match.group(0)
            return f'url("{relative_uri(css_path, local_path)}")'

        css_text = CSS_URL_PATTERN.sub(replace_url, css_text)

        def replace_import(match: re.Match[str]) -> str:
            reference = match.group(1)
            try:
                absolute = normalize_url(reference, base=css_url)
            except ValueError:
                return match.group(0)
            local_path = self._cache.get(absolute)
            if local_path is None:
                return match.group(0)
            rel = relative_uri(css_path, local_path)
            return f'@import url("{rel}")'

        return CSS_IMPORT_PATTERN.sub(replace_import, css_text)

    def rewrite_html(
        self,
        html: str,
        *,
        page_url: str,
        html_path: Path,
        root_url: str,
    ) -> str:
        """Rewrite asset and same-host navigation URLs in HTML."""
        soup = BeautifulSoup(html, "html.parser")

        for tag_name, attrs in TAG_ATTRS.items():
            for tag in soup.find_all(tag_name):
                if tag_name == "link" and not _should_mirror_link(tag):
                    continue
                for attr in attrs:
                    if tag.has_attr(attr):
                        self._rewrite_tag_attr(
                            tag,
                            attr,
                            page_url=page_url,
                            file_path=html_path,
                        )
                if tag.has_attr("srcset"):
                    self._rewrite_srcset_attr(
                        tag,
                        page_url=page_url,
                        file_path=html_path,
                    )
                if tag.has_attr("data-srcset"):
                    self._rewrite_srcset_attr(
                        tag,
                        page_url=page_url,
                        file_path=html_path,
                        attr="data-srcset",
                    )

        for tag in soup.find_all(style=True):
            self._rewrite_inline_style(tag, page_url=page_url, file_path=html_path)

        for anchor in soup.find_all("a", href=True):
            self._rewrite_anchor(
                anchor,
                page_url=page_url,
                html_path=html_path,
                root_url=root_url,
            )

        return str(soup)

    def _rewrite_srcset_attr(
        self,
        tag: Tag,
        *,
        page_url: str,
        file_path: Path,
        attr: str = "srcset",
    ) -> None:
        value = tag.get(attr)
        if not isinstance(value, str):
            return
        tag[attr] = rewrite_srcset(
            value,
            page_url=page_url,
            file_path=file_path,
            cache=self._cache,
        )

    def _rewrite_inline_style(
        self,
        tag: Tag,
        *,
        page_url: str,
        file_path: Path,
    ) -> None:
        style = tag.get("style")
        if not isinstance(style, str):
            return

        def replace_url(match: re.Match[str]) -> str:
            reference = match.group(1)
            if reference.startswith(("data:", "#", "blob:")):
                return match.group(0)
            try:
                absolute = normalize_url(reference, base=page_url)
            except ValueError:
                return match.group(0)
            local_path = self._cache.get(absolute)
            if local_path is None:
                return match.group(0)
            return f'url("{relative_uri(file_path, local_path)}")'

        tag["style"] = INLINE_STYLE_URL_PATTERN.sub(replace_url, style)

    def _rewrite_tag_attr(
        self,
        tag: Tag,
        attr: str,
        *,
        page_url: str,
        file_path: Path,
    ) -> None:
        value = tag.get(attr)
        if not isinstance(value, str):
            return
        joined = urljoin(page_url, value)
        fragment = urlparse(joined).fragment
        try:
            absolute = normalize_url(value, base=page_url)
        except ValueError:
            return
        local_path = self._cache.get(absolute)
        if local_path is None:
            return
        rel = relative_uri(file_path, local_path)
        if fragment:
            rel = f"{rel}#{fragment}"
        tag[attr] = rel
        is_lazy_img = attr in {"data-src", "data-lazy-src"} and tag.name == "img"
        if is_lazy_img and not tag.get("src"):
            tag["src"] = rel

    def _rewrite_anchor(
        self,
        anchor: Tag,
        *,
        page_url: str,
        html_path: Path,
        root_url: str,
    ) -> None:
        href = anchor.get("href")
        if not isinstance(href, str):
            return
        try:
            absolute = normalize_url(href, base=page_url)
        except ValueError:
            return
        if not same_host(absolute, root_url):
            return
        local_page = url_to_output_path(
            absolute, self._output_dir, keep_query=self._keep_query
        )
        anchor["href"] = relative_uri(html_path, local_page)
        anchor["data-folio-url"] = absolute  # exact URL for resume (query included)


def _should_mirror_link(tag: Tag) -> bool:
    rel_attr = tag.get("rel")
    if rel_attr is None:
        return False
    if isinstance(rel_attr, str):
        rel_values = {rel_attr.lower()}
    else:
        rel_values = {str(value).lower() for value in rel_attr}
    if rel_values & MIRROR_LINK_RELS:
        return True
    if "preload" in rel_values:
        return str(tag.get("as", "")).lower() in MIRROR_PRELOAD_AS
    return False
