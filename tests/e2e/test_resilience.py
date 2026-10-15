import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

NO_WEBGL = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (t, ...a) {
  if (/webgl/i.test(t)) return null;
  return orig.call(this, t, ...a);
};
"""


def test_without_webgl_data_still_readable(browser, server):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(NO_WEBGL)
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    assert page.evaluate("document.body.classList.contains('no-webgl')")
    assert page.inner_text("#prediction-direction") == "NAIK"
    assert page.inner_text("#price").startswith("$")
    assert page.is_hidden("#hero-canvas") and page.is_hidden("#horizon-canvas")
    assert page.locator("#chart-price canvas").count() >= 1          # grafik 2D tetap jalan
    assert errs == []
    ctx.close()


def test_reduced_motion_marked_and_no_errors(browser, server):
    ctx = browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    assert page.evaluate("document.body.dataset.motion") == "reduced"
    assert errs == []
    ctx.close()


@pytest.mark.parametrize("path", ["/", "/retrospektif", "/riset", "/metodologi", "/tentang"])
def test_no_horizontal_scroll_on_phone(browser, server, path):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(server + path)
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    ctx.close()


def test_reduced_motion_still_renders_hero_scene(browser, server):
    ctx = browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    warnings = []
    page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
    page.add_init_script("sessionStorage.setItem('splash-seen', '1')")
    page.goto(server + "/")
    page.wait_for_selector("#prediction-direction:not(:text('—'))")
    page.wait_for_timeout(1500)                                       # beri waktu start3D selesai
    assert not page.evaluate("document.body.classList.contains('no-webgl')")   # hero tidak jatuh ke fallback
    assert not [w for w in warnings if "Visual 3D dinonaktifkan" in w]
    ctx.close()
