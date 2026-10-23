import pytest

from tests.e2e.conftest import BASE_NOW, collect_errors

pytestmark = pytest.mark.e2e


def patched(page, prob=None, threshold=None, horizon="1"):
    """Ubah probabilitas/ambang pada balasan latest.json (untuk kasus ekstrem)."""
    def handle(route):
        body = route.fetch().json()
        if prob is not None:
            body["horizons"][horizon]["prob"] = prob
        if threshold is not None:
            body["horizons"][horizon]["threshold"] = threshold
        body["horizons"][horizon]["direction"] = "NAIK" if body["horizons"][horizon]["prob"] > body["horizons"][horizon]["threshold"] else "TURUN"
        route.fulfill(json=body)
    page.route("**/api/prediction/latest", handle)


def fmt1(page, x):
    return page.evaluate("(x) => new Intl.NumberFormat('id-ID', {minimumFractionDigits: 1, maximumFractionDigits: 1}).format(x)", x)


def x_center(page, sel):
    b = page.locator(sel).bounding_box()
    return b["x"] + b["width"] / 2


def test_gauge_states_the_exact_distance_to_the_flip_threshold(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#margin-text")
    h = page.evaluate("fetch('/api/prediction/latest').then(r => r.json()).then(d => d.horizons['1'])")
    margin = (h["prob"] - h["threshold"]) * 100
    text = page.inner_text("#margin-text")
    side = "TURUN" if h["direction"] == "NAIK" else "NAIK"
    assert f"Jarak ke ambang {side}: {fmt1(page, abs(margin))} poin persentase" in text
    assert fmt1(page, h["prob"] * 100) + "%" in text and fmt1(page, h["threshold"] * 100) + "%" in text   # angka acuan ikut tampil


def test_marker_sits_right_of_the_tick_when_up_and_left_when_down_and_follows_the_horizon(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#gauge-dot")
    assert page.evaluate("document.querySelector('#prediction-direction').textContent") == "NAIK"
    assert x_center(page, "#gauge-dot") > x_center(page, "#gauge-tick")                       # NAIK: probabilitas di atas ambang
    page.click("#horizon-tabs [role=tab]:has-text('7 hari')")
    assert page.evaluate("document.querySelector('#prediction-direction').textContent") == "TURUN"
    assert x_center(page, "#gauge-dot") < x_center(page, "#gauge-tick")                       # TURUN: di bawah ambang
    assert "Jarak ke ambang NAIK" in page.inner_text("#margin-text")


def test_marker_stays_inside_the_gauge_even_for_extreme_probabilities(page, server):
    patched(page, prob=0.995, threshold=0.5)
    page.goto(server + "/")
    page.wait_for_selector("#gauge-dot")
    gauge, dot = page.locator("#gauge").bounding_box(), page.locator("#gauge-dot").bounding_box()
    assert gauge["x"] - 1 <= dot["x"] and dot["x"] + dot["width"] <= gauge["x"] + gauge["width"] + 1
    assert "99,5%" in page.inner_text("#margin-text")                                         # angka tetap jujur walau penanda dijepit


def test_exactly_at_the_threshold_is_called_out(page, server):
    patched(page, prob=0.5, threshold=0.5)
    page.goto(server + "/")
    page.wait_for_selector("#margin-text")
    text = page.inner_text("#margin-text")
    assert "tepat di ambang" in text.lower() and "TURUN" in page.inner_text("#prediction-direction")


def test_gauge_is_accessible_and_links_to_the_glossary_entry(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#gauge")
    g = page.locator("#gauge")
    assert g.get_attribute("role") == "img"
    label = g.get_attribute("aria-label")
    assert "ambang" in label and "probabilitas" in label.lower() and "poin persentase" in label
    link = page.locator("#margin-gauge a[href='#g-ambang']")
    assert link.count() == 1 and "ambang" in link.inner_text().lower()
    link.click()
    assert page.evaluate("location.hash") == "#g-ambang" and page.locator("#g-ambang").is_visible()


def test_gauge_fits_a_small_phone_with_the_largest_text(browser, server):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": 360, "height": 800}, is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen','1'); localStorage.setItem('text-level','3'); } catch (e) {}")
    page = ctx.new_page()
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_selector("#gauge")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    card = page.locator("#sec-pred").bounding_box()
    for sel in ("#margin-text", "#gauge", ".gauge-scale"):
        b = page.locator(sel).bounding_box()
        assert b["x"] >= card["x"] - 1 and b["x"] + b["width"] <= card["x"] + card["width"] + 1, sel
    assert not errs, errs
    ctx.close()
