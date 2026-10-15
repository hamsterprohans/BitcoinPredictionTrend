import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

NAV = ["Prediksi", "Latar Belakang", "Riset", "Metodologi", "Tentang"]


@pytest.mark.parametrize("path", ["/", "/latar-belakang", "/riset", "/metodologi", "/tentang"])
def test_nav_has_five_links_on_every_page(page, server, path):
    page.goto(server + path)
    assert page.locator("header nav a").all_inner_texts() == NAV
    assert page.get_attribute("header nav a[aria-current]", "href") == path


def test_background_page_fills_numbers_from_research_data(page, server):
    errs = collect_errors(page)
    page.goto(server + "/latar-belakang")
    page.wait_for_selector("#summary [data-fill]:not(:text('…'))")
    assert "Rumusan masalah" in page.inner_text("main")
    assert page.locator("#rq li").count() == 6                       # enam rumusan masalah
    summary = page.inner_text("#summary")
    assert "0,6465" in summary or "0,839" in summary                  # p-value McNemar dari significance.json (id-ID)
    assert "bukan saran investasi" in page.inner_text("footer").lower()
    assert [e for e in errs if "404" not in e] == []


def test_background_page_is_honest_about_unfinished_parts(page, server):
    page.goto(server + "/latar-belakang")
    text = page.inner_text("main").lower()
    assert "belum" in text and "explainer" in text                   # lapisan penjelas belum ada di website
    assert "backtest" in text


def test_about_page_shows_only_approved_facts(page, server):
    page.goto(server + "/tentang")
    text = page.inner_text("main")
    for fact in ("Hans Christian Cakrawangsa", "5026231130", "Sistem Informasi", "Institut Teknologi Sepuluh Nopember",
                 "Renny Pradina Kusumawardani"):
        assert fact in text, fact
    assert page.locator("a[href*='github.com/hanscakrawangsa15']").count() == 1
