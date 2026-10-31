from folio.offline import extract_data_scripts, prepare_static_snapshot


def test_prepare_static_snapshot_removes_all_scripts() -> None:
    html = """
        <html>
          <head>
            <script src="/app.js"></script>
            <script>console.log("hi")</script>
            <link rel="stylesheet" href="/app.css">
          </head>
          <body onclick="alert(1)">Hello</body>
        </html>
    """
    result = prepare_static_snapshot(html)
    assert "<script" not in result
    assert "console.log" not in result
    assert 'href="/app.css"' in result
    assert "onclick" not in result


def test_prepare_static_snapshot_strips_video_and_audio_sources() -> None:
    html = """
        <html>
          <body>
            <video src="/lesson.mp4" poster="/thumb.jpg">
              <source src="/lesson.webm">
            </video>
            <audio src="/audio.mp3"></audio>
          </body>
        </html>
    """
    result = prepare_static_snapshot(html)
    assert ".mp4" not in result
    assert ".webm" not in result
    assert 'poster="/thumb.jpg"' in result


def test_prepare_static_snapshot_removes_js_preload_links() -> None:
    html = """
        <html>
          <head>
            <link rel="modulepreload" href="/chunk.js">
            <link rel="preload" href="/chunk.js" as="script">
            <link rel="preload" href="/font.woff2" as="font">
          </head>
          <body>Hello</body>
        </html>
    """
    result = prepare_static_snapshot(html)
    assert "modulepreload" not in result
    assert 'as="script"' not in result
    assert 'as="font"' in result


_DATA_PAGE = (
    """
<html><head>
<script type="application/ld+json">{"@type": "Residence", "name": "x"}</script>
<script src="/app.js"></script>
<script>window.PAGE_MODEL = {"propertyData": {"id": 1, "price": 100000}};"""
    + ("/* padding */ " * 20)
    + """</script>
<script>var tiny = 1;</script>
</head><body><p>hello</p></body></html>
"""
)


def test_prepare_static_snapshot_can_keep_json_scripts() -> None:
    stripped = prepare_static_snapshot(_DATA_PAGE)
    assert "<script" not in stripped
    kept = prepare_static_snapshot(_DATA_PAGE, keep_data_scripts=True)
    assert kept.count("<script") == 1 and "application/ld+json" in kept
    assert "PAGE_MODEL" not in kept  # executable inline scripts still go


def test_extract_data_scripts_collects_json_and_inline_data() -> None:
    data = extract_data_scripts(_DATA_PAGE)
    assert [s["type"] for s in data["json_scripts"]] == ["application/ld+json"]
    assert len(data["inline_scripts"]) == 1
    assert data["inline_scripts"][0]["text"].startswith("window.PAGE_MODEL")
