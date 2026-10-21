import pytest

from tests.e2e.conftest import BASE_NOW

pytestmark = pytest.mark.e2e

PATHS = ["/", "/latar-belakang", "/riset", "/metodologi", "/kuesioner", "/tentang"]
WIDTHS = [320, 360, 390, 412]

# Elemen mana pun di dalam kartu yang menjorok keluar dari kartunya (kecuali kontainer gulir/kanvas/absolut) = cacat tata letak.
OUTSIDE_CARD = """() => {
  const bad = [];
  for (const card of document.querySelectorAll('.card')) {
    const cr = card.getBoundingClientRect();
    if (cr.width === 0) continue;
    for (const el of card.querySelectorAll('*')) {
      if (el.closest('.table-wrap, .chart, canvas, svg, [hidden]')) continue;
      const cs = getComputedStyle(el);
      if (cs.position === 'absolute' || cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > cr.right + 1 || r.left < cr.left - 1)
        bad.push(`${el.tagName}.${el.className} keluar ${Math.round(Math.max(r.right - cr.right, cr.left - r.left))}px: ${(el.textContent || '').trim().slice(0, 40)}`);
    }
  }
  return bad.slice(0, 6);
}"""


def phone(browser, width, level=None):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": width, "height": 800}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}"
                        + (f"localStorage.setItem('text-level', '{level}');" if level is not None else ""))
    return ctx, ctx.new_page()


def assert_fits(page, label):
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), f"{label}: halaman melebar"
    assert page.evaluate(OUTSIDE_CARD) == [], label


@pytest.mark.parametrize("width", WIDTHS)
def test_live_page_content_stays_inside_cards_on_phones(browser, server, width):
    ctx, page = phone(browser, width)
    page.goto(server + "/")
    page.wait_for_selector("#live-news li")
    page.wait_for_selector("#live-contrib .bar-row")
    assert_fits(page, f"/ @{width}")
    ctx.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_contribution_rows_show_label_and_number_fully(browser, server, width):
    ctx, page = phone(browser, width)
    page.goto(server + "/")
    page.wait_for_selector("#live-contrib .bar-row")
    rows = page.locator("#live-contrib .bar-row")
    card = page.locator("#sec-explain").bounding_box()
    for i in range(rows.count()):
        cells = rows.nth(i).locator(":scope > *")
        num = cells.nth(2).bounding_box()
        assert num["x"] + num["width"] <= card["x"] + card["width"] + 1, f"baris {i}: angka terpotong @{width}"
        label_h = cells.nth(0).bounding_box()["height"]
        assert label_h <= 3 * float(page.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")) * 1.7, f"baris {i}: label terlalu tinggi"
    ctx.close()


@pytest.mark.parametrize("path", PATHS)
def test_other_pages_do_not_overflow_on_a_phone(browser, server, path):
    ctx, page = phone(browser, 360)
    page.goto(server + path)
    page.wait_for_timeout(300)
    assert_fits(page, f"{path} @360")
    ctx.close()


@pytest.mark.parametrize("path", ["/", "/tentang", "/riset"])
def test_largest_text_also_fits_on_a_small_phone(browser, server, path):
    ctx, page = phone(browser, 360, level=3)
    page.goto(server + path)
    page.wait_for_timeout(400)
    assert_fits(page, f"{path} @360 teks 150%")
    ctx.close()


def test_retro_page_fits_on_a_phone(browser, make_server):
    url = make_server(BASE_NOW, retro=True)
    ctx, page = phone(browser, 360)
    page.goto(url + "/retrospektif")
    page.wait_for_selector("#day-slider")
    page.wait_for_function("document.querySelector('#day-slider').max > 0")
    page.wait_for_timeout(400)
    assert_fits(page, "/retrospektif @360")
    ctx.close()


@pytest.mark.parametrize("width", [360, 390, 412])
def test_history_table_fits_without_sideways_scroll_on_phones(browser, server, width):
    ctx, page = phone(browser, width)
    page.goto(server + "/")
    page.wait_for_selector("#history-body tr")
    fits = page.evaluate("(() => { const w = document.querySelector('#sec-hist .table-wrap'); return w.scrollWidth <= w.clientWidth + 1; })()")
    assert fits, f"tabel riwayat bergulir ke samping @{width}"
    ctx.close()


def test_backtest_section_fits_on_a_phone(browser, make_server):
    from tests.factories import backtest_fixture
    url = make_server(BASE_NOW, backtest=backtest_fixture())
    ctx, page = phone(browser, 360)
    page.goto(url + "/riset")
    page.wait_for_selector("#bt-table")
    page.wait_for_selector("#bt-chart canvas")
    assert_fits(page, "/riset backtest @360")
    for sel in ("#bt-table", "#bt-sensitivity"):
        assert page.evaluate("(s) => { const w = document.querySelector(s).closest('.table-wrap'); return w.scrollWidth <= w.clientWidth + 1; }", sel), f"{sel} bergulir ke samping"
    ctx.close()
