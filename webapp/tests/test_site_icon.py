import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "static"
PAGES = sorted(STATIC.glob("*.html"))


def test_main_page_title_is_the_product_name_and_tagline():
    html = (STATIC / "index.html").read_text()
    assert "<title>Bitcoin Trend - Prediction System for Bitcoin Trend</title>" in html


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_links_the_icons_and_the_files_exist(page):
    html = page.read_text()
    hrefs = re.findall(r'<link rel="(?:icon|apple-touch-icon)"[^>]*href="(/static/img/[^"]+)"', html)
    assert {"/static/img/icon.svg", "/static/img/favicon-32.png", "/static/img/apple-touch-icon.png"} <= set(hrefs)
    for h in hrefs:
        assert (STATIC.parent / h.lstrip("/")).is_file(), h


def test_icon_svg_is_self_contained():
    svg = (STATIC / "img" / "icon.svg").read_text()
    assert svg.lstrip().startswith("<svg") and "<script" not in svg and "href=" not in svg and "<text" not in svg   # tanpa font/berkas luar
