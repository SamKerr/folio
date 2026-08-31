from folio.assets import is_downloadable_asset_url


def test_is_downloadable_asset_url_rejects_javascript() -> None:
    assert not is_downloadable_asset_url("https://example.com/_next/static/chunks/main.js")
    assert not is_downloadable_asset_url("https://example.com/app.mjs")


def test_is_downloadable_asset_url_allows_styles_and_images() -> None:
    assert is_downloadable_asset_url("https://example.com/app.css")
    assert is_downloadable_asset_url("https://example.com/logo.png")


def test_is_downloadable_asset_url_rejects_video_and_audio() -> None:
    assert not is_downloadable_asset_url("https://example.com/lesson.mp4")
    assert not is_downloadable_asset_url("https://example.com/stream.m3u8")
    assert not is_downloadable_asset_url("https://example.com/audio.mp3")
