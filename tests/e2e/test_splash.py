import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

NO_WEBGL = """
const o = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/i.test(t) ? null : o.call(this, t, ...a); };
"""


def _fresh(browser, **kw):
    ctx = browser.new_context(**kw)              # konteks baru: sessionStorage kosong, tanpa penanda "sudah dilihat"
    return ctx, ctx.new_page()


def test_splash_waits_for_user_and_button_enters(browser, server):
    ctx, page = _fresh(browser)
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    assert page.inner_text("#splash-enter") == "Lanjutkan ke Dashboard Prediksi"
    assert page.inner_text(".splash-author") == "Oleh Hans Christian Cakrawangsa"      # di bawah tagline
    assert page.evaluate("document.querySelector('.splash-tag').nextElementSibling.className") == "splash-author"
    page.wait_for_timeout(4500)                                          # tidak boleh tertutup sendiri
    assert page.is_visible("#splash")
    page.click("#splash", position={"x": 20, "y": 20})                   # klik di area kosong tidak melanjutkan
    page.wait_for_timeout(700)
    assert page.is_visible("#splash")
    page.click("#splash-enter")
    page.wait_for_selector("#splash", state="hidden", timeout=3000)
    assert page.evaluate("sessionStorage.getItem('splash-seen')") == "1"
    page.wait_for_selector("#prediction-direction:not(:text('—'))")      # data dimuat di belakang splash
    page.reload()
    assert page.is_hidden("#splash")                                     # tidak muncul lagi pada sesi yang sama
    assert errs == []
    ctx.close()


def test_splash_enter_and_escape_keys_are_explicit_confirmation(browser, server):
    for key in ("Enter", "Escape"):
        ctx, page = _fresh(browser)
        page.goto(server + "/")
        page.wait_for_selector("#splash:not([hidden])")
        assert page.evaluate("document.activeElement.id") == "splash-enter"   # fokus awal di tombol
        page.keyboard.press(key)
        page.wait_for_selector("#splash", state="hidden", timeout=3000)
        ctx.close()


def test_splash_draws_bitcoin_symbol_particles(browser, server):
    ctx, page = _fresh(browser)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    page.wait_for_function("document.getElementById('splash').dataset.mark === 'bitcoin'", timeout=5000)
    ctx.close()


def test_splash_without_webgl_and_reduced_motion_still_waits_and_shows_symbol(browser, server):
    ctx, page = _fresh(browser, reduced_motion="reduce")
    page.add_init_script(NO_WEBGL)
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#splash:not([hidden])")
    assert "Bitcoin Trend" in page.inner_text("#splash")
    assert page.is_visible("#splash-fallback-mark")                      # simbol ₿ statis tanpa WebGL
    page.wait_for_timeout(2500)
    assert page.is_visible("#splash")                                    # tetap menunggu pengguna
    page.click("#splash-enter")
    page.wait_for_selector("#splash", state="hidden", timeout=3000)
    assert errs == []
    ctx.close()


def test_other_pages_have_no_splash(page, server):
    page.goto(server + "/riset")
    assert page.locator("#splash").count() == 0


def test_bitcoin_mark_has_ring_that_encloses_the_symbol(browser, server):
    ctx, page = _fresh(browser)
    page.goto(server + "/")
    r = page.evaluate("""async () => {
      const m = await import('/static/js/splash-scene.js');
      const sym = await m.sampleBitcoin(3000, 3.6);
      const R = m.ringRadiusFor(sym), T = 0.16;
      const ring = m.ringPoints(1500, R, T);
      const dist = ([x, y]) => Math.hypot(x, y - m.CENTER_Y);
      return { R, T, n: ring.length, symMax: Math.max(...sym.map(dist)),
               ringMin: Math.min(...ring.map(dist)), ringMax: Math.max(...ring.map(dist)) };
    }""")
    assert r["n"] == 1500
    assert r["symMax"] < r["R"] - r["T"] / 2                       # ring melingkupi seluruh simbol
    assert r["R"] - r["T"] / 2 - 1e-6 <= r["ringMin"] and r["ringMax"] <= r["R"] + r["T"] / 2 + 1e-6   # titik berada pada pita cincin
    page.wait_for_function("document.getElementById('splash').dataset.ring === '1'", timeout=5000)
    ctx.close()
