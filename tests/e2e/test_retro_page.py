import pytest

from tests.e2e.conftest import BASE_NOW, collect_errors

pytestmark = pytest.mark.e2e


def test_retro_page_updates_every_panel_on_date_change(page, make_server):
    url = make_server(BASE_NOW, retro=True)
    errs = collect_errors(page)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#panel-contrib .bar-row")
    banner = page.inner_text("#retro-banner")
    assert "Simulasi retrospektif" in banner and "bukan prediksi masa depan" in banner
    assert page.locator("#panel-contrib .bar-row").count() == 13
    assert page.locator("#panel-reliability tbody tr").count() == 3
    assert page.locator("#chart-retro-price canvas").count() >= 1 and page.locator("#chart-retro-prob canvas").count() >= 1
    assert "belum terverifikasi" in page.inner_text("#parity-note").lower()      # data uji sintetis memakai allow_mismatch
    assert "belum terverifikasi" in page.inner_text("#panel-reliability").lower()   # peringatan juga di dalam panel keandalan
    assert "belum tentu sama" in page.inner_text("#panel-news")                  # judul retrospektif: contoh, bukan yang dinilai

    page.locator("#day-slider").fill("0")
    page.wait_for_function("document.querySelector('#panel-narrative').textContent.includes('bukan saran investasi')")
    first = page.inner_text("#day-date")
    page.locator("#day-slider").fill("7")
    page.wait_for_function("(old) => document.getElementById('day-date').textContent !== old", arg=first)
    assert page.locator("#panel-contrib .bar-row").count() == 13
    assert "belum dibuat" in page.inner_text("#panel-narrative").lower()          # hari tanpa narasi: pesan jujur

    before = page.inner_text("#day-date")
    page.click("#day-next")
    page.wait_for_function("(old) => document.getElementById('day-date').textContent !== old", arg=before)
    before = page.inner_text("#day-date")
    page.click("#day-prev")
    page.wait_for_function("(old) => document.getElementById('day-date').textContent !== old", arg=before)
    assert [e for e in errs if "404" not in e] == []


def test_retro_page_shows_correct_or_wrong_mark_and_values(page, make_server):
    url = make_server(BASE_NOW, retro=True)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#day-pred:not(:text('—'))")
    assert page.inner_text("#day-pred") in ("NAIK", "TURUN")
    assert page.inner_text("#day-actual").split()[0] in ("NAIK", "TURUN")
    assert ("✓" in page.inner_text("#day-actual")) or ("✗" in page.inner_text("#day-actual"))
    assert "," in page.inner_text("#day-prob")


def test_retro_page_is_honest_on_days_without_news(page, make_server):
    url = make_server(BASE_NOW, retro=True)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#day-slider")
    idx = page.evaluate("""async () => {
      const s = await (await fetch('/api/retro/series')).json();
      for (let i = 0; i < s.date.length; i++) {
        const d = await (await fetch('/api/retro/day/' + s.date[i])).json();
        if (!d.sentiment.has_news) return i;
      }
      return -1;
    }""")
    assert idx >= 0
    page.locator("#day-slider").fill(str(idx))
    page.wait_for_function("document.querySelector('#panel-news').textContent.includes('Tidak ada berita')")
    assert "forward-fill" in page.inner_text("#panel-news")
    assert page.locator("#panel-news li").count() == 0                          # tidak ada judul/skor yang dikarang


def test_retro_page_without_data_explains_how_to_build(page, make_server):
    url = make_server(BASE_NOW)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#retro-empty:not([hidden])")
    assert "build_retro" in page.inner_text("#retro-empty") and page.is_hidden("#retro-app")


def test_retro_day_load_failure_clears_stale_panels(page, make_server):
    url = make_server(BASE_NOW, retro=True)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#panel-contrib .bar-row")
    series = page.evaluate("fetch('/api/retro/series').then(r => r.json())")
    target = series["date"][3]
    page.route(f"**/api/retro/day/{target}", lambda route: route.fulfill(status=500, body="x"))
    page.locator("#day-slider").fill("3")
    page.wait_for_function("document.querySelector('#panel-news').textContent.includes('Gagal memuat')")
    assert page.locator("#panel-contrib .bar-row").count() == 0                  # tidak ada sisa panel hari sebelumnya
    assert "Gagal memuat" in page.inner_text("#panel-narrative")
