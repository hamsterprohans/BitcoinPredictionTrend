from datetime import timedelta

import pytest

from tests.e2e.conftest import BASE_NOW, collect_errors

pytestmark = pytest.mark.e2e


def test_prediction_page_renders_data(page, server):
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    assert page.inner_text("#price").startswith("$")
    assert page.locator("#horizon-tabs [role=tab]").count() == 2          # horizon 1 dan 7 pada data uji
    assert page.inner_text("#prediction-direction") == "NAIK"
    assert page.locator("#evidence-badge").is_visible()                   # H=1: tetap berlabel jujur
    assert "Belum terbukti lebih baik dari tebakan acak" in page.inner_text("#evidence-badge")
    assert "semua horizon" in page.inner_text("footer")
    page.click("#horizon-tabs [role=tab]:has-text('7 hari')")
    assert page.inner_text("#prediction-direction") == "TURUN"
    assert "Belum terbukti lebih baik dari tebakan acak" in page.inner_text("#evidence-badge")
    assert page.locator("#chart-price canvas").count() >= 1
    assert page.locator("#chart-rsi canvas").count() >= 1
    assert page.locator("#history-body tr").count() >= 1
    assert page.locator("#hero-canvas").count() == 1
    assert page.is_hidden("#banner")
    assert errs == []


def test_range_buttons_exist_and_toggle(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#ranges button")
    labels = page.locator("#ranges button").all_inner_texts()
    assert labels == ["1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"]
    page.click("#ranges button:has-text('3M')")
    assert page.get_attribute("#ranges button:has-text('3M')", "aria-pressed") == "true"


def test_stale_data_shows_banner(page, make_server):
    url = make_server(BASE_NOW + timedelta(days=10))
    page.goto(url + "/")
    page.wait_for_selector("#banner:not([hidden])")
    assert "lebih dari 2 hari" in page.inner_text("#banner")


def test_missing_data_shows_banner_not_blank_page(page, make_server):
    url = make_server(BASE_NOW, seed=False)
    page.goto(url + "/")
    page.wait_for_selector("#banner:not([hidden])")
    assert "belum tersedia" in page.inner_text("#banner").lower()
