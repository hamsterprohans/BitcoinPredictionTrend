import pytest

pytestmark = pytest.mark.e2e

PATHS = ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"]
NAV = ["Prediksi", "Latar Belakang", "Retrospektif", "Riset", "Metodologi", "Kuesioner", "Tentang"]


def mobile_page(browser, width=390):
    ctx = browser.new_context(viewport={"width": width, "height": 844})
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


def test_theme_toggle_remains_visible_on_mobile(browser, server):
    ctx, page = mobile_page(browser)
    page.goto(server + "/")
    assert page.locator("#theme-toggle").is_visible()
    ctx.close()
