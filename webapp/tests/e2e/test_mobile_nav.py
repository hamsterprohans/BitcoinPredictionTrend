import pytest

pytestmark = pytest.mark.e2e

PATHS = ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"]
NAV = ["Prediksi", "Latar Belakang", "Retrospektif", "Riset", "Metodologi", "Kuesioner", "Tentang"]


def mobile_page(browser, width=390):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": width, "height": 844})
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    return ctx, ctx.new_page()


@pytest.mark.parametrize("path", PATHS)
def test_mobile_shows_hamburger_and_hides_links_until_opened(browser, server, path):
    ctx, page = mobile_page(browser)
    page.goto(server + path)
    toggle = page.locator("#nav-toggle")
    assert toggle.is_visible() and toggle.get_attribute("aria-expanded") == "false"
    assert toggle.get_attribute("aria-controls") == "main-nav"
    assert page.locator("#main-nav a:visible").count() == 0                   # tertutup: tautan tidak terlihat
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert page.locator("#main-nav a:visible").all_inner_texts() == NAV       # terbuka: ketujuh tautan terlihat
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")  # tanpa gulir horizontal
    ctx.close()


def test_menu_closes_on_escape_outside_click_and_toggle(browser, server):
    ctx, page = mobile_page(browser)
    page.goto(server + "/tentang")
    toggle = page.locator("#nav-toggle")
    toggle.click()
    page.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false" and page.locator("#main-nav a:visible").count() == 0
    assert page.evaluate("document.activeElement.id") == "nav-toggle"           # fokus kembali ke tombol
    toggle.click()
    page.mouse.click(200, 700)                                                  # klik di luar menu
    assert toggle.get_attribute("aria-expanded") == "false"
    toggle.click()
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "false"
    ctx.close()


def test_mobile_link_navigates_and_current_page_is_marked(browser, server):
    ctx, page = mobile_page(browser)
    page.goto(server + "/")
    page.locator("#nav-toggle").click()
    page.locator("#main-nav a", has_text="Kuesioner").click()
    page.wait_for_url("**/kuesioner")
    page.locator("#nav-toggle").click()
    assert page.locator("#main-nav a[aria-current]").inner_text() == "Kuesioner"
    ctx.close()


@pytest.mark.parametrize("path", PATHS)
def test_desktop_keeps_inline_nav_without_hamburger(page, server, path):
    page.goto(server + path)                                                    # viewport bawaan 1280 lebar
    assert page.locator("#nav-toggle").is_hidden()
    assert page.locator("#main-nav a:visible").all_inner_texts() == NAV


def test_tools_live_inside_the_menu_on_mobile_and_work_from_there(browser, server):
    ctx, page = mobile_page(browser)
    page.goto(server + "/")
    for sel in ("#theme-toggle", "#font-inc", "#font-dec"):
        assert page.locator(sel).is_hidden(), sel                                  # tidak ada di header ponsel
    visible_in_header = page.evaluate("[...document.querySelectorAll('.topbar > *')].filter(e => e.getBoundingClientRect().width > 0).map(e => e.id || e.className)")
    assert set(visible_in_header) == {"nav-toggle"} | {v for v in visible_in_header if v == "brand"}   # hanya merek + hamburger
    page.click("#nav-toggle")
    for sel in ("#theme-toggle", "#font-inc", "#font-dec"):
        assert page.locator(f"#main-nav {sel}").is_visible(), sel                  # muncul di dalam panel menu
    labels = page.locator("#main-nav .tool-label").all_inner_texts()
    assert labels == ["Ukuran teks", "Tema"]
    before = page.evaluate("document.documentElement.dataset.theme")
    page.click("#theme-toggle")
    assert page.evaluate("document.documentElement.dataset.theme") != before       # tema berubah dari dalam menu
    size = page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")
    page.click("#font-inc")
    assert page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)") > size
    assert page.locator("#nav-toggle").get_attribute("aria-expanded") == "true"    # menu tetap terbuka agar bisa menyetel beberapa kali
    ctx.close()


def test_desktop_keeps_tools_inline_in_the_header_bar(page, server):
    page.goto(server + "/")
    assert page.locator("#nav-toggle").is_hidden()
    for sel in ("#theme-toggle", "#font-inc", "#font-dec"):
        assert page.locator(sel).is_visible(), sel
    assert page.locator("#main-nav .tool-label").first.is_hidden()                 # label hanya di panel menu


def test_hamburger_is_gold_and_follows_the_theme(page, context, server):
    context.add_init_script("window.__x = 1;")
    ctx = page.context
    page.set_viewport_size({"width": 390, "height": 800})
    page.goto(server + "/")
    probe = """(token) => { const d = document.createElement('div'); d.style.background = `var(${token})`; document.body.append(d);
      const c = getComputedStyle(d).backgroundColor; d.remove(); return c; }"""
    dark_bg = page.evaluate("getComputedStyle(document.querySelector('#nav-toggle')).backgroundColor")
    assert dark_bg == page.evaluate(probe, "--gold")                                # emas (token tema), bukan abu-abu
    assert page.evaluate("getComputedStyle(document.querySelector('#nav-toggle')).color") == page.evaluate(probe, "--on-gold")
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    light_bg = page.evaluate("getComputedStyle(document.querySelector('#nav-toggle')).backgroundColor")
    assert light_bg == page.evaluate(probe, "--gold") and light_bg != dark_bg       # menyesuaikan tema terang
