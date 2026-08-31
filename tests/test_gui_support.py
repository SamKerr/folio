from pathlib import Path

from folio.crawl_runner import CrawlSettings, build_crawl_argv
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
