"""Validate browser-side JavaScript before it reaches Playwright."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from folio.browser_scripts import BROWSER_SCRIPTS


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(
    not _node_available(),
    reason="Node.js is required for JS syntax checks",
)
@pytest.mark.parametrize("name", sorted(BROWSER_SCRIPTS))
def test_browser_script_has_valid_syntax(name: str, tmp_path: Path) -> None:
    script = BROWSER_SCRIPTS[name].strip()
    script_path = tmp_path / f"{name}.js"
    script_path.write_text(f"const fn = {script};\n", encoding="utf-8")

    result = subprocess.run(
        ["node", "--check", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
