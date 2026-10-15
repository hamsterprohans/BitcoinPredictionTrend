import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e


def test_fonts_loaded_and_theme_toggle(page, server):
    errs = collect_errors(page)
    page.goto(server + "/")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("document.fonts.load('1em Geist').then(f => f.length > 0)")
    assert page.evaluate("document.fonts.load('1em \"Geist Mono\"').then(f => f.length > 0)")
    assert page.evaluate("getComputedStyle(document.body).fontFamily").startswith("Geist")
    assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--gold').trim()") == "#e6c068"
    page.click("#theme-toggle")
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert errs == []
