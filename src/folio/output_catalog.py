"""Discover saved sites under a Folio output directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ASSETS_DIRNAME = "_assets"


@dataclass(frozen=True)
class SavedSite:
    host: str
    root: Path
    page_count: int
    modified_at: float


def list_saved_sites(output_dir: Path) -> list[SavedSite]:
    """Return host directories that contain saved HTML pages."""
    if not output_dir.is_dir():
        return []

    sites: list[SavedSite] = []
    for entry in sorted(output_dir.iterdir()):
        if not entry.is_dir() or entry.name == ASSETS_DIRNAME:
            continue
        html_files = list(entry.rglob("*.html"))
        if not html_files:
            continue
        modified_at = max(path.stat().st_mtime for path in html_files)
        sites.append(
            SavedSite(
                host=entry.name,
                root=entry,
                page_count=len(html_files),
                modified_at=modified_at,
            )
        )

    sites.sort(key=lambda site: site.modified_at, reverse=True)
    return sites
