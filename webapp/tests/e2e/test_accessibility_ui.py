import pytest

pytestmark = pytest.mark.e2e

PATHS = ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"]
ROOT_PX = "parseFloat(getComputedStyle(document.documentElement).fontSize)"


def press(page, selector):
    """Klik tombol ukuran teks; bila header sudah beralih ke hamburger, buka menu dulu (tombol berada di dalamnya)."""
    if not page.locator(selector).is_visible() and page.locator("#nav-toggle").is_visible():
        page.click("#nav-toggle")
    page.click(selector)



def mobile_page(browser, width=390):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": width, "height": 844})
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    return ctx, ctx.new_page()


@pytest.mark.parametrize("path", PATHS)
def test_disclaimer_banner_is_on_top_of_every_page(page, server, path):
    page.goto(server + path)
    bar = page.locator(".notice-bar")
    assert bar.count() == 1 and bar.is_visible() and bar.get_attribute("role") == "note"
    text = bar.inner_text()
    for part in ("hanyalah prediksi", "bukan saran investasi", "tidak bertanggung jawab", "kerugian", "investasi yang dilakukan"):
        assert part in text, part
    assert bar.bounding_box()["y"] < page.locator("header.topbar").bounding_box()["y"]      # di atas header
    assert bar.bounding_box()["height"] < 80                                                # banner kecil


@pytest.mark.parametrize("path", PATHS)
def test_text_size_controls_exist_and_default_is_larger_than_16px(page, server, path):
    page.goto(server + path)
    assert page.locator("#font-inc").is_visible() and page.locator("#font-dec").is_visible()
    assert page.locator("[role=group][aria-label='Ukuran teks']").count() == 1
    assert page.evaluate(ROOT_PX) > 16                                                       # default sudah lebih besar


def test_increase_and_decrease_change_size_and_stop_at_limits(page, server):
    page.goto(server + "/tentang")
    sizes = [page.evaluate(ROOT_PX)]
    while not page.locator("#font-inc").is_disabled():
        press(page, "#font-inc")
        sizes.append(page.evaluate(ROOT_PX))
        assert len(sizes) < 10
    assert sizes == sorted(sizes) and len(set(sizes)) == len(sizes) and sizes[-1] >= 24      # sampai 150%
    body_px = page.evaluate("parseFloat(getComputedStyle(document.querySelector('.prose p')).fontSize)")
    assert body_px >= 20                                                                     # isi teks ikut membesar
    while not page.locator("#font-dec").is_disabled():
        press(page, "#font-dec")
    assert page.evaluate(ROOT_PX) == 16                                                      # terkecil = ukuran standar


def test_text_size_choice_persists_across_pages_and_reloads(page, server):
    page.goto(server + "/tentang")
    press(page, "#font-inc")
    chosen = page.evaluate(ROOT_PX)
    page.goto(server + "/riset")
    assert page.evaluate(ROOT_PX) == chosen
    page.reload()
    assert page.evaluate(ROOT_PX) == chosen


def test_buttons_announce_state_to_assistive_tech(page, server):
    page.goto(server + "/tentang")
    assert page.get_attribute("#font-inc", "aria-label") == "Perbesar teks"
    assert page.get_attribute("#font-dec", "aria-label") == "Perkecil teks"
    while not page.locator("#font-inc").is_disabled():
        press(page, "#font-inc")
    assert page.get_attribute("#font-inc", "disabled") is not None                           # batas atas: dinonaktifkan


@pytest.mark.parametrize("path", PATHS)
def test_largest_text_on_phone_has_no_horizontal_scroll_and_header_fits(browser, server, path):
    ctx, page = mobile_page(browser)
    page.goto(server + path)
    page.click("#nav-toggle")                                                                  # kontrol ukuran teks ada di dalam menu
    while not page.locator("#font-inc").is_disabled():
        page.click("#font-inc")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
    for sel in ("#nav-toggle", "#font-inc", "#font-dec", "#theme-toggle"):
        box = page.locator(sel).bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, sel                 # semua tombol muat di layar (menu terbuka)
    ctx.close()


SAME_ROW = ("(() => { const links = [...document.querySelectorAll('#main-nav a')];"
            " const tops = new Set(links.map((a) => Math.round(a.getBoundingClientRect().top)));"
            " const oneLine = links.every((a) => { const r = document.createRange(); r.selectNodeContents(a); return r.getClientRects().length === 1; });"
            " return tops.size === 1 && oneLine; })()")          # sebaris DAN tiap teks tautan satu baris (tak ada yang terpotong)


def set_level(page, level):
    page.evaluate(f"localStorage.setItem('text-level', '{level}')")
    page.reload()


@pytest.mark.parametrize("path", PATHS)
def test_desktop_default_text_keeps_nav_on_one_row_without_wrapping(page, server, path):
    page.goto(server + path)                                                                 # 1280 lebar, ukuran teks bawaan
    assert page.locator("#nav-toggle").is_hidden()
    assert page.evaluate(SAME_ROW)                                                           # "Latar Belakang" tidak terpotong dua baris
    assert page.evaluate("document.querySelector('.topbar').scrollWidth <= document.querySelector('.topbar').clientWidth")


@pytest.mark.parametrize("level", [2, 3])
def test_header_switches_to_hamburger_when_larger_text_no_longer_fits(page, server, level):
    page.goto(server + "/tentang")
    set_level(page, level)
    assert page.locator("#nav-toggle").is_visible()                                          # tidak muat sebaris: otomatis hamburger
    assert page.locator("#main-nav a:visible").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.click("#nav-toggle")
    assert page.evaluate(SAME_ROW) is False                                                  # menu terbuka: tautan bertumpuk vertikal
    assert page.locator("#main-nav a:visible").count() == 7


def test_header_returns_to_inline_nav_when_text_is_made_smaller_again(page, server):
    page.goto(server + "/tentang")
    set_level(page, 3)
    assert page.locator("#nav-toggle").is_visible()
    page.click("#nav-toggle")                                                                  # ukuran teks diubah dari dalam menu
    page.click("#font-dec")
    page.click("#font-dec")
    page.click("#font-dec")
    assert page.locator("#nav-toggle").is_hidden() and page.evaluate(SAME_ROW)               # kembali ke tampilan desktop biasa
