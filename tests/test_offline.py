from folio.offline import prepare_static_snapshot


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
