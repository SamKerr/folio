"""Convert an existing saved site to data-only form in place (``folio slim``)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from folio.offline import DATA_MARKERS, filter_sidecar, prepare_data_snapshot
from folio.output_catalog import ASSETS_DIRNAME
from folio.storage import (
    SIDECAR_SUFFIX,
    encode_text,
    gz_path,
    plain_path,
    read_text,
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
