import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from folio.crawl_runner import CrawlSettings, build_crawl_argv
from folio.gui import (
    _mousewheel_steps,
    _touchpad_vertical_step,
    _widget_is_descendant,
    apply_capture_preset,
    find_logo_path,
)
from folio.output_catalog import list_saved_sites
from folio.preview_server import PreviewServer


def test_list_saved_sites_ignores_assets_dir(tmp_path: Path) -> None:
    host_dir = tmp_path / "www.example.com"
    host_dir.mkdir()
    (host_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "_assets").mkdir()

    sites = list_saved_sites(tmp_path)

    assert len(sites) == 1
    assert sites[0].host == "www.example.com"
    assert sites[0].page_count == 1


def test_find_logo_path_returns_bundled_asset() -> None:
    path = find_logo_path()
    assert path is not None
    assert path.name == "folio.png"
    assert path.is_file()


def test_widget_is_descendant_detects_nested_widgets() -> None:
    root = tk.Tk()
    try:
        outer = tk.Frame(root)
        inner = tk.Frame(outer)
        leaf = tk.Label(inner, text="child")
        assert _widget_is_descendant(leaf, outer) is True
        assert _widget_is_descendant(outer, leaf) is False
    finally:
        root.destroy()


def test_mousewheel_steps_on_tk9(monkeypatch: pytest.MonkeyPatch) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        monkeypatch.setattr(
            "folio.gui._tk_patchlevel_at_least",
            lambda _root, major, minor: (major, minor) <= (9, 0),
        )
        wheel = SimpleNamespace(delta=120, num=0)
        assert _mousewheel_steps(wheel, root) == -1
        wheel = SimpleNamespace(delta=-240, num=0)
        assert _mousewheel_steps(wheel, root) == 2
    finally:
        root.destroy()


def test_touchpad_vertical_step_ignores_horizontal_dominant() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        vertical = SimpleNamespace(keycode=5, num=0)
        horizontal = SimpleNamespace(keycode=65536, num=0)
        assert _touchpad_vertical_step(vertical, root) == 5
        assert _touchpad_vertical_step(horizontal, root) == 0
    finally:
        root.destroy()


def test_capture_presets_define_expected_timings() -> None:
    balanced = apply_capture_preset("Balanced")
    assert balanced["image_wait_ms"] == 5000
    assert balanced["asset_quiet_ms"] == 750

    thorough = apply_capture_preset("Thorough")
    assert thorough["image_wait_ms"] > balanced["image_wait_ms"]
    assert thorough["page_asset_timeout_ms"] > balanced["page_asset_timeout_ms"]


def test_build_crawl_argv_includes_excludes() -> None:
    argv = build_crawl_argv(
        CrawlSettings(
            url="https://example.com/",
            exclude_patterns=["/community/*", "/blog/*"],
            concurrency=20,
            image_wait_ms=15000,
        )
    )
    assert "https://example.com/" in argv
    assert "--exclude" in argv
    assert "/community/*" in argv
    assert "/blog/*" in argv
    assert argv[argv.index("--concurrency") + 1] == "20"
    assert argv[argv.index("--image-wait-ms") + 1] == "15000"


def test_preview_server_serves_site_url(tmp_path: Path) -> None:
    host_dir = tmp_path / "www.example.com"
    host_dir.mkdir()
    (host_dir / "index.html").write_text("<html>hi</html>", encoding="utf-8")

    server = PreviewServer(tmp_path)
    try:
        port = server.start()
        assert port > 0
        assert server.site_url("www.example.com") == (
            f"http://127.0.0.1:{port}/www.example.com/"
        )
    finally:
        server.stop()
