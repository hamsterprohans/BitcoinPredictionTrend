import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e


def _fresh(browser, **kw):
    ctx = browser.new_context(**kw)              # konteks baru: sessionStorage kosong, tanpa penanda "sudah dilihat"
    return ctx, ctx.new_page()


def test_splash_shows_then_escape_skips_and_is_remembered(browser, server):
    ctx, page = _fresh(browser)
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    assert "Bitcoin Trend" in page.inner_text("#splash")
    page.keyboard.press("Escape")
    page.wait_for_selector("#splash", state="hidden", timeout=3000)
    assert page.evaluate("sessionStorage.getItem('splash-seen')") == "1"
    page.wait_for_selector("#prediction-direction:not(:text('—'))")   # data tetap dimuat di belakang splash
    page.reload()
    assert page.is_hidden("#splash")                                   # tidak muncul lagi pada sesi yang sama
    assert errs == []
    ctx.close()


def test_splash_auto_dismisses(browser, server):
    ctx, page = _fresh(browser)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    page.wait_for_selector("#splash", state="hidden", timeout=8000)
    ctx.close()


def test_splash_enter_button(browser, server):
    ctx, page = _fresh(browser)
    page.goto(server + "/")
    page.click("#splash-enter")
    page.wait_for_selector("#splash", state="hidden", timeout=3000)
    ctx.close()


def test_splash_without_webgl_and_reduced_motion_no_errors(browser, server):
    ctx, page = _fresh(browser, reduced_motion="reduce")
    page.add_init_script("""
      const o = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/i.test(t) ? null : o.call(this, t, ...a); };
    """)
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    assert "Bitcoin Trend" in page.inner_text("#splash")               # judul tetap terbaca tanpa WebGL
    page.wait_for_selector("#splash", state="hidden", timeout=8000)
    assert errs == []
    ctx.close()


def test_other_pages_have_no_splash(page, server):
    page.goto(server + "/riset")
    assert page.locator("#splash").count() == 0
