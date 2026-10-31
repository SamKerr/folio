"""Gzip-aware saved-file helpers: path twins, atomic writes, transparent reads."""

from __future__ import annotations

import gzip
import os
import tempfile
from pathlib import Path

GZ_SUFFIX = ".gz"
SIDECAR_SUFFIX = ".data.json"


def is_gz(path: Path) -> bool:
    return path.suffix == GZ_SUFFIX


def gz_path(path: Path) -> Path:
    """``x.html`` -> ``x.html.gz`` (unchanged when already gzipped)."""
    return path if is_gz(path) else path.with_name(path.name + GZ_SUFFIX)


def plain_path(path: Path) -> Path:
    """``x.html.gz`` -> ``x.html`` (unchanged when not gzipped)."""
    return path.with_name(path.name[: -len(GZ_SUFFIX)]) if is_gz(path) else path


def sidecar_path(html_path: Path) -> Path:
    """Sidecar beside a saved page: ``x.html`` -> ``x.data.json``,
    ``x.html.gz`` -> ``x.data.json.gz``."""
    side = plain_path(html_path).with_suffix(SIDECAR_SUFFIX)
    return gz_path(side) if is_gz(html_path) else side


def find_saved_page(path: Path) -> Path | None:
    """Return the saved file for ``path`` or its gzip / plain twin, if either exists."""
    for candidate in (path, gz_path(path) if not is_gz(path) else plain_path(path)):
        if candidate.is_file():
            return candidate
    return None


def read_text(path: Path) -> str:
    """Read UTF-8 text, decompressing when the name ends in ``.gz``."""
    data = path.read_bytes()
    if is_gz(path):
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


def encode_text(path: Path, text: str) -> bytes:
    data = text.encode("utf-8")
    # mtime=0 keeps the bytes deterministic, so re-slimming is a no-op.
    return gzip.compress(data, mtime=0) if is_gz(path) else data


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write via a temp file in the same folder, then rename over ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp_name, _file_mode(path))  # mkstemp creates 0600
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _file_mode(path: Path) -> int:
    """Keep an existing file's permissions; new files get 0666 minus the umask."""
    try:
        return path.stat().st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def write_text_atomic(path: Path, text: str) -> None:
    """Atomically write UTF-8 text, gzip-compressed when the name ends in ``.gz``."""
    write_bytes_atomic(path, encode_text(path, text))
