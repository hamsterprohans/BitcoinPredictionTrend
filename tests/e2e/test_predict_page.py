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


def test_interval_selector_default_daily_and_switch_to_weekly(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#intervals button")
    assert page.locator("#intervals button").all_inner_texts() == ["D", "W", "M"]
    assert page.get_attribute("#intervals button:has-text('D')", "aria-pressed") == "true"
    assert "Harian" in page.inner_text("#tf-label")
    with page.expect_response(lambda r: "/api/prices" in r.url and "interval=W" in r.url) as resp:
        page.click("#intervals button:has-text('W')")
    assert resp.value.ok
    page.wait_for_selector("#intervals button:has-text('W')[aria-pressed='true']")      # halaman memperbarui setelah setData selesai
    page.wait_for_function("document.getElementById('tf-label').textContent.includes('Mingguan')")


def test_without_prediction_still_shows_real_chart_and_last_close(page, make_server):
    url = make_server(BASE_NOW, chart_only=True)
    errs = collect_errors(page)
    page.goto(url + "/")
    page.wait_for_selector("#banner:not([hidden])")
    page.wait_for_selector("#chart-price canvas")
    assert page.inner_text("#price").startswith("$")                    # harga terakhir dari data harga
    assert "Penutupan" in page.inner_text("#asof")
    assert page.is_hidden("#sec-pred") and page.is_hidden("#sec-hist")  # tidak ada kartu prediksi kosong
    assert "belum tersedia" in page.inner_text("#banner").lower()
    assert [e for e in errs if "404" not in e] == []                    # 404 /api/prediction/latest memang disengaja


def test_live_price_badge_and_change_since_close(page, make_server):
    url = make_server(BASE_NOW, live_price=81131.45)
    page.goto(url + "/")
    page.wait_for_selector("#live-badge:not([hidden])")
    assert "LIVE" in page.inner_text("#live-badge")
    assert page.inner_text("#price") == "$81.131,45"
    close = 38006.74                                                       # penutupan terakhir pada data uji sintetis
    pct = f"{(81131.45 / close - 1) * 100:+,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    since = page.inner_text("#since-close")
    assert "sejak penutupan" in since and pct in since and "$38.006,74" in since
    assert "patokan penutupan" in page.inner_text("#prediction-live")     # prediksi tetap resmi harian
    assert pct in page.inner_text("#change")                               # perubahan di samping harga live = terhadap penutupan
    assert page.is_hidden("#asof")                                         # baris penutupan tidak diulang


def test_live_price_failure_falls_back_to_last_close(page, make_server):
    url = make_server(BASE_NOW, live_price=None)
    errs = collect_errors(page)
    page.goto(url + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    page.wait_for_timeout(1200)
    assert page.is_hidden("#live-badge")
    assert page.inner_text("#price") == "$38.006,74"                       # harga penutupan, bukan live
    assert page.is_visible("#asof") and "-1,33%" in page.inner_text("#change")   # perubahan harian penutupan dikembalikan
    assert errs == []


def test_demo_data_is_labelled_and_not_mixed_with_live_price(page, make_server):
    url = make_server(BASE_NOW, live_price=82091.09, demo=True)
    page.goto(url + "/")
    page.wait_for_selector("#banner:not([hidden])")
    banner = page.inner_text("#banner")
    assert "DEMO" in banner and "bukan harga atau prediksi asli" in banner
    page.wait_for_timeout(1500)
    assert page.is_hidden("#live-badge")                                   # harga live asli tidak ditempel pada patokan demo
    assert "+115" not in page.inner_text("main")                           # tidak ada persentase campuran
    assert page.inner_text("#price") == "$38.006,74"                       # tetap tampil sebagai angka demo, berlabel


def test_live_explain_panels_render_from_latest(page, make_server):
    url = make_server(BASE_NOW, retro=True)
    errs = collect_errors(page)
    page.goto(url + "/")
    page.wait_for_selector("#sec-explain:not([hidden])")
    assert page.locator("#live-news li").count() == 3
    assert page.locator("#live-contrib .bar-row").count() == 13
    assert "bukan saran investasi" in page.inner_text("#live-narrative")
    page.wait_for_selector("#live-reliability tbody tr")
    assert page.locator("#live-reliability tbody tr").count() == 3
    assert "belum terverifikasi" in page.inner_text("#live-reliability").lower()      # paritas belum terverifikasi: ada peringatan
    assert [e for e in errs if "404" not in e] == []


def test_live_explain_reliability_explains_when_retro_not_built(page, make_server):
    url = make_server(BASE_NOW)
    page.goto(url + "/")
    page.wait_for_selector("#sec-explain:not([hidden])")
    page.wait_for_function("document.querySelector('#live-reliability').textContent.length > 0")
    assert "build_retro" in page.inner_text("#live-reliability")


def test_live_explain_section_hidden_without_block(page, make_server):
    url = make_server(BASE_NOW, explain=False)
    page.goto(url + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    page.wait_for_timeout(500)
    assert page.is_hidden("#sec-explain")
