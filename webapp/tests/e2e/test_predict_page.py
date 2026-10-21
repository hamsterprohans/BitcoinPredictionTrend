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
    assert page.locator("#evidence-badge").count() == 0                   # label di bawah prediksi sudah dihapus (permintaan pemilik)
    assert "semua horizon" in page.inner_text("footer")
    page.click("#horizon-tabs [role=tab]:has-text('7 hari')")
    assert page.inner_text("#prediction-direction") == "TURUN"
    assert page.locator("#evidence-badge").count() == 0 and page.locator("#sec-pred .badge.warn").count() == 0
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


def test_backfilled_history_rows_are_labeled_as_computed_afterwards(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#history-body tr")
    rows = page.locator("#history-body tr")
    labeled = [r for r in rows.all_inner_texts() if "dihitung susulan" in r]
    assert len(labeled) == 1                                              # hanya entri yang ditandai backfilled
    assert page.locator("#history-body tr:has-text('dihitung susulan') td").first.get_attribute("title") \
        == "Dihitung setelah harinya lewat dari data tersimpan; bukan prediksi yang terbit pada hari itu"


def test_open_page_reloads_itself_when_a_new_daily_snapshot_is_published(page, context, server):
    context.add_init_script("window.__SNAPSHOT_POLL_MS__ = 300;")
    calls = {"n": 0}

    def handle(route):
        calls["n"] += 1
        if calls["n"] == 1:                                              # pemuatan awal: data apa adanya
            return route.continue_()
        body = route.fetch().json()
        body["as_of"] = "2026-10-15"                                     # snapshot baru terbit
        route.fulfill(json=body)
    page.route("**/api/prediction/latest", handle)
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    page.evaluate("window.__stayed = true")
    page.wait_for_function("!window.__stayed", timeout=8000)             # halaman dimuat ulang sendiri
    assert calls["n"] >= 2


def test_open_page_does_not_reload_when_snapshot_is_unchanged(page, context, server):
    context.add_init_script("window.__SNAPSHOT_POLL_MS__ = 200;")
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    page.evaluate("window.__stayed = true")
    page.wait_for_timeout(1500)
    assert page.evaluate("window.__stayed") is True


def test_chart_gets_a_live_point_for_today_and_follows_the_live_price(browser, make_server):
    url = make_server(BASE_NOW, live_price=99999.5)
    ctx = browser.new_context(bypass_csp=True)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    page = ctx.new_page()
    errs = collect_errors(page)
    page.goto(url + "/")
    page.wait_for_function("document.body.dataset.chartLive")                 # titik live masuk ke grafik
    today = page.evaluate("new Date().toISOString().slice(0, 10)")           # jam browser, bukan jam palsu server uji
    assert page.evaluate("document.body.dataset.chartLive") == f"{today}:99999.5"   # tanggal hari ini (UTC) : harga live
    page.locator("#intervals button:has-text('W')").click()
    page.wait_for_function("!document.body.dataset.chartLive")                # W/M: tidak ada titik live (bar berbeda satuan)
    page.locator("#intervals button:has-text('D')").click()
    page.wait_for_function("document.body.dataset.chartLive")                 # kembali ke D: titik live dipasang lagi
    assert not errs, errs
    ctx.close()


def test_no_live_point_when_live_price_is_unavailable(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#chart-price canvas")
    page.wait_for_timeout(800)
    assert page.evaluate("document.body.dataset.chartLive || ''") == ""


def test_history_shows_no_lock_wording_but_keeps_the_outcome(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#history-body tr")
    texts = page.locator("#history-body tr").all_inner_texts()
    assert not any("dikunci" in t for t in texts)                          # tulisan "dikunci" dihapus atas permintaan pemilik
    assert page.locator("#history-body td[title*='dikunci' i]").count() == 0
    assert any("✓" in t or "✗" in t for t in texts)                        # hasil tetap tampil; penguncian ada di data/kode (tes store & jobs)


def test_survey_promo_section_with_button_leads_to_questionnaire(page, server):
    page.goto(server + "/")
    promo = page.locator("#sec-survey")
    assert promo.count() == 1
    assert "kuesioner" in promo.inner_text().lower() and "5 menit" in promo.inner_text()
    assert "opsional" not in promo.inner_text().lower() and "dikosongkan" not in promo.inner_text()   # semua soal wajib
    assert page.locator("#sec-hist").evaluate("(h, s) => h.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING",
                                              promo.element_handle())                      # di bawah riwayat, di atas footer
    btn = promo.locator("a.btn-link[href='/kuesioner']")
    assert btn.is_visible() and btn.inner_text() == "Isi kuesioner"
    btn.click()
    page.wait_for_url("**/kuesioner")
    assert page.locator("#survey-root").count() == 1


def test_hovering_the_chart_shows_detailed_date_and_price_tooltip(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#chart-price canvas")
    page.wait_for_timeout(500)
    cols = page.evaluate("fetch('/api/prices?interval=D').then(r => r.json())")
    page.locator("#chart-price").scroll_into_view_if_needed()                              # grafik di bawah lipatan layar
    box = page.locator("#chart-price").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.5)
    page.mouse.move(box["x"] + box["width"] * 0.56, box["y"] + box["height"] * 0.5)
    tip = page.locator("#chart-tooltip")
    tip.wait_for(state="visible")
    date = tip.get_attribute("data-date")
    assert date in cols["date"]                                                             # tanggal titik data sungguhan
    expected_date = page.evaluate("(d) => new Date(d + 'T00:00:00Z').toLocaleDateString('id-ID', "
                                  "{weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC'})", date)
    text = tip.inner_text()
    assert expected_date in text                                                            # mis. "Selasa, 14 Juli 2026"
    price = cols["close"][cols["date"].index(date)]
    shown = page.evaluate("(p) => '$' + new Intl.NumberFormat('id-ID', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(p)", price)
    assert "Harga" in text and shown in text                                                # harga penutupan titik itu, dua desimal
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] - 200)                            # keluar dari grafik
    page.wait_for_selector("#chart-tooltip", state="hidden")


def test_tooltip_stays_inside_the_chart_near_the_edges(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#chart-price canvas")
    page.wait_for_timeout(500)
    page.locator("#chart-price").scroll_into_view_if_needed()
    box = page.locator("#chart-price").bounding_box()
    for fx in (0.04, 0.88):                                                                  # kiri dan tepi kanan data (data berakhir ~89%)
        page.mouse.move(box["x"] + box["width"] * fx, box["y"] + box["height"] * 0.4)
        page.mouse.move(box["x"] + box["width"] * fx + 1, box["y"] + box["height"] * 0.4)
        page.locator("#chart-tooltip").wait_for(state="visible")
        t = page.locator("#chart-tooltip").bounding_box()
        assert t["x"] >= box["x"] - 1 and t["x"] + t["width"] <= box["x"] + box["width"] + 1


def test_headlines_link_to_the_original_articles_safely(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#live-news li")
    items = page.locator("#live-news li")
    assert items.count() == 3
    link = items.nth(0).locator("a")
    assert link.get_attribute("href") == "https://contoh.com/berita-0" and link.inner_text() == "Judul berita 0"
    assert link.get_attribute("target") == "_blank"
    assert set(link.get_attribute("rel").split()) >= {"noopener", "noreferrer"}              # tab asal tidak bisa dibajak
    assert items.nth(1).locator("a").count() == 0 and items.nth(1).inner_text() == "Judul berita 1"   # javascript: tidak menjadi tautan
    assert items.nth(2).locator("a").count() == 0                                            # tanpa URL: teks biasa


def test_explanation_panel_spans_the_full_card_width_without_empty_side(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#live-narrative .narr")
    card = page.locator("#sec-explain").bounding_box()
    panel = page.locator("#live-narrative").bounding_box()
    pad = 2 * 18                                                           # padding kartu kiri+kanan
    assert panel["width"] >= card["width"] - pad - 2                       # selebar isi kartu: tidak ada kolom kosong di samping
    narr = page.locator("#live-narrative .narr").bounding_box()
    assert narr["width"] >= card["width"] - pad - 2


def test_explanation_panel_stays_single_column_on_phone(browser, server):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": 390, "height": 844})
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_selector("#live-narrative .narr")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    card = page.locator("#sec-explain").bounding_box()
    assert page.locator("#live-narrative .narr").bounding_box()["width"] <= card["width"]
    ctx.close()


def test_history_rows_are_labeled_by_the_date_they_predict_with_the_source_close_shown(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#history-body tr")
    assert page.locator("#sec-hist thead th").first.inner_text() == "Prediksi untuk"        # bukan 'Tanggal prediksi' (ambigu)
    hist = page.evaluate("fetch('/api/prediction/history').then(r => r.json())")
    first = max((e for e in hist if e["horizons"].get('1')), key=lambda e: e["date"])
    fmt = "(d) => new Date(d + 'T00:00:00Z').toLocaleDateString('id-ID', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})"
    target = page.evaluate("(d) => new Date(new Date(d + 'T00:00:00Z').getTime() + 86400000).toISOString().slice(0, 10)", first["date"])
    cell = page.locator("#history-body tr").first.locator("td").first.inner_text()
    assert page.evaluate(fmt, target) in cell                                              # tanggal TARGET (hari yang diprediksi) di baris teratas
    assert f"dari penutupan {page.evaluate(fmt, first['date'])}" in cell                   # asal data penutupan tetap jelas


def test_history_target_date_follows_the_selected_horizon(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#history-body tr")
    page.click("#horizon-tabs [role=tab]:has-text('7 hari')")
    hist = page.evaluate("fetch('/api/prediction/history').then(r => r.json())")
    first = max((e for e in hist if e["horizons"].get('7')), key=lambda e: e["date"])
    target = page.evaluate("(d) => new Date(new Date(d + 'T00:00:00Z').getTime() + 7 * 86400000).toISOString().slice(0, 10)", first["date"])
    expected = page.evaluate("(d) => new Date(d + 'T00:00:00Z').toLocaleDateString('id-ID', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})", target)
    assert expected in page.locator("#history-body tr").first.locator("td").first.inner_text()


def _with_news_source(page, source):
    def handle(route):
        body = route.fetch().json()
        body["explain"]["news_source"] = source
        route.fulfill(json=body)
    page.route("**/api/prediction/latest", handle)


def test_fallback_news_source_is_disclosed_next_to_the_headlines(page, server):
    _with_news_source(page, "rss")
    page.goto(server + "/")
    page.wait_for_selector("#live-news li")
    note = page.locator("#live-news .source-note")
    assert note.count() == 1
    text = note.inner_text()
    assert "cadangan" in text.lower() and "RSS" in text and "sedikit berbeda" in text         # jujur soal pergeseran distribusi


@pytest.mark.parametrize("source", [None, "cryptocompare"])
def test_primary_news_source_shows_no_fallback_note(page, server, source):
    _with_news_source(page, source)
    page.goto(server + "/")
    page.wait_for_selector("#live-news li")
    assert page.locator("#live-news .source-note").count() == 0
