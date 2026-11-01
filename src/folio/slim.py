"""Convert an existing saved site to data-only form in place (``folio slim``)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from folio.error_pages import (
    DEFAULT_ERROR_RULES,
    ErrorRules,
    html_reason,
    sidecar_reason,
)
from folio.offline import DATA_MARKERS, filter_sidecar, prepare_data_snapshot
from folio.output_catalog import ASSETS_DIRNAME
from folio.storage import (
    SIDECAR_SUFFIX,
    encode_text,
    find_saved_page,
    gz_path,
    plain_path,
    read_text,
    sidecar_path,
    write_bytes_atomic,
)

PROGRESS_EVERY = 1000


@dataclass
class SlimStats:
    html_files: int = 0
    html_before: int = 0
    html_after: int = 0
    sidecar_files: int = 0
    sidecar_before: int = 0
    sidecar_after: int = 0
    changed: int = 0
    failed: int = 0


def _iter_saved_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, kind) for saved pages and sidecars, skipping ``_assets``."""
    for path in sorted(root.rglob("*")):
        if ASSETS_DIRNAME in path.relative_to(root).parts or not path.is_file():
            continue
        name = plain_path(path).name
        if name.startswith("."):
            continue  # temp files from atomic writes
        if name.endswith(SIDECAR_SUFFIX):
            yield path, "sidecar"
        elif name.endswith(".html"):
            yield path, "html"


def _slim_text(path: Path, kind: str, markers: tuple[str, ...]) -> str:
    text = read_text(path)
    if kind == "html":
        return prepare_data_snapshot(text)
    data = json.loads(text)
    if not isinstance(data, dict):
        msg = "sidecar is not a JSON object"
        raise ValueError(msg)
    return json.dumps(filter_sidecar(data, markers), ensure_ascii=False)


def slim_site(
    root: Path,
    *,
    gzip_output: bool = False,
    extra_markers: Iterable[str] = (),
    verbose: bool = True,
) -> SlimStats:
    """Reduce every saved page and sidecar under ``root`` in place.

    Pages become reduced snapshots and sidecars keep only JSON and page-state
    scripts (the ``--data-only`` rules). Writes are atomic (temp file + rename) and
    only happen when the bytes change, so a second run is a no-op. With
    ``gzip_output`` each file is rewritten as ``<name>.gz`` and the plain file is
    removed. ``_assets`` folders are never touched (other mirrors share them).
    """
    markers = tuple(dict.fromkeys(DATA_MARKERS + tuple(extra_markers)))
    stats = SlimStats()
    for index, (path, kind) in enumerate(_iter_saved_files(root), start=1):
        before = path.stat().st_size
        try:
            target = gz_path(path) if gzip_output else path
            data = encode_text(target, _slim_text(path, kind, markers))
        except (OSError, ValueError, EOFError) as exc:
            stats.failed += 1
            print(f"Warning: could not slim {path}: {exc}", file=sys.stderr)
            continue
        after = len(data)
        if target != path or path.read_bytes() != data:
            write_bytes_atomic(target, data)
            if target != path:
                path.unlink()
            stats.changed += 1
        if kind == "html":
            stats.html_files += 1
            stats.html_before += before
            stats.html_after += after
        else:
            stats.sidecar_files += 1
            stats.sidecar_before += before
            stats.sidecar_after += after
        if verbose and index % PROGRESS_EVERY == 0:
            print(f"Slimmed {index} file(s)...", file=sys.stderr, flush=True)
    return stats


@dataclass
class DropStats:
    pages_checked: int = 0
    error_pages: int = 0
    """Saved pages (with their sidecars) found to be error pages."""
    orphan_sidecars: int = 0
    """Error sidecars with no saved page beside them."""
    files_deleted: int = 0
    failed: int = 0


def _error_reason(path: Path, kind: str, rules: ErrorRules) -> str | None:
    text = read_text(path)
    return html_reason(text, rules) if kind == "html" else sidecar_reason(text, rules)


def _page_for_sidecar(side: Path) -> Path | None:
    """The saved page beside a sidecar (either gzip twin), if any."""
    plain_side = plain_path(side)
    page = plain_side.with_name(plain_side.name[: -len(SIDECAR_SUFFIX)] + ".html")
    return find_saved_page(page)


def drop_error_pages(
    root: Path,
    *,
    rules: ErrorRules = DEFAULT_ERROR_RULES,
    dry_run: bool = False,
    verbose: bool = True,
) -> DropStats:
    """Delete saved error pages under ``root`` together with their sidecars.

    A page is an error page when its ``<title>`` or ``__NEXT_DATA__.page`` (in the
    page or its sidecar) matches ``rules`` (:mod:`folio.error_pages`). A sidecar
    with no page beside it is checked on its own. ``dry_run`` only reports.
    ``_assets`` folders are never touched.
    """
    stats = DropStats()
    files = list(_iter_saved_files(root))
    pages = [path for path, kind in files if kind == "html"]
    sidecars = [path for path, kind in files if kind == "sidecar"]

    def delete(paths: list[Path], reason: str) -> None:
        for path in paths:
            if verbose:
                verb = "Would delete" if dry_run else "Deleting"
                print(f"{verb} ({reason}): {path}", file=sys.stderr, flush=True)
            if not dry_run:
                path.unlink(missing_ok=True)
            stats.files_deleted += 1

    for page in pages:
        stats.pages_checked += 1
        side = sidecar_path(page)
        side_file = find_saved_page(side)
        try:
            reason = _error_reason(page, "html", rules)
            if reason is None and side_file is not None:
                reason = _error_reason(side_file, "sidecar", rules)
        except (OSError, EOFError) as exc:
            stats.failed += 1
            print(f"Warning: could not read {page}: {exc}", file=sys.stderr)
            continue
        if reason is None:
            continue
        stats.error_pages += 1
        delete([page] + ([side_file] if side_file is not None else []), reason)

    for side in sidecars:
        if _page_for_sidecar(side) is not None or not side.exists():
            continue  # checked with its page (or deleted with it)
        try:
            reason = _error_reason(side, "sidecar", rules)
        except (OSError, EOFError) as exc:
            stats.failed += 1
            print(f"Warning: could not read {side}: {exc}", file=sys.stderr)
            continue
        if reason is not None:
            stats.orphan_sidecars += 1
            delete([side], reason)
    return stats
