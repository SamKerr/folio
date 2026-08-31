from pathlib import Path

from folio.crawler import extract_links_from_saved_html
from folio.urls import output_path_to_url


def test_output_path_to_url_round_trip() -> None:
    root = "https://www.example.com/"
    output_dir = Path("output")
    path = Path(
        "output/www.example.com/learn/salary-negotiation/introduction.html"
    )
    assert (
        output_path_to_url(path, output_dir, root)
        == "https://www.example.com/learn/salary-negotiation/introduction"
    )


def test_extract_links_from_saved_html_finds_rewritten_links() -> None:
    html = """
        <html>
          <body>
            <a href="learn/system-design.html">Design</a>
            <a href="https://external.com/x">External</a>
          </body>
        </html>
    """
    html_path = Path("output/www.example.com/index.html")
    links = extract_links_from_saved_html(
        html,
        html_path=html_path,
        output_dir=Path("output"),
        root_url="https://www.example.com/",
    )
    assert links == ["https://www.example.com/learn/system-design"]
