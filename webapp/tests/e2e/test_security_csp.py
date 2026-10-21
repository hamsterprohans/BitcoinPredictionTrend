import re

import pytest

from app import config

pytestmark = pytest.mark.e2e

PATHS = ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"]
SUPABASE_HOST = re.search(r'supabaseUrl: "(https://[^"]+)"', (config.STATIC_DIR / "js" / "app-config.js").read_text()).group(1)


@pytest.fixture
def strict_page(browser):
    """Halaman dengan CSP ditegakkan (tanpa bypass), splash dianggap sudah dilihat."""
    ctx = browser.new_context(bypass_csp=False)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    yield ctx.new_page()
    ctx.close()


def csp_of(page):
    return page.evaluate("document.querySelector('meta[http-equiv=Content-Security-Policy]')?.content || ''")


@pytest.mark.parametrize("path", PATHS)
def test_every_page_has_a_strict_csp_without_unsafe_script_sources(strict_page, server, path):
    strict_page.goto(server + path)
    csp = csp_of(strict_page)
    assert csp, f"{path}: tidak ada CSP"
    directives = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in csp.split(";")) if d}
    assert directives["script-src"] == ["'self'"]                                   # tanpa unsafe-inline / unsafe-eval / domain luar
    assert directives["object-src"] == ["'none'"] and directives["base-uri"] == ["'none'"] and directives["form-action"] == ["'none'"]
    assert set(directives["connect-src"]) == {"'self'", "https://api.coinbase.com", SUPABASE_HOST}   # hanya tujuan yang memang dipakai
    assert directives["default-src"] == ["'self'"]
    assert "unsafe-eval" not in csp


@pytest.mark.parametrize("path", PATHS)
def test_no_inline_script_remains_and_pages_load_without_csp_violations(strict_page, server, path):
    violations = []
    strict_page.on("console", lambda m: violations.append(m.text) if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    strict_page.on("pageerror", lambda e: violations.append(str(e)))
    strict_page.goto(server + path)
    strict_page.wait_for_timeout(700)
    assert strict_page.evaluate("document.querySelectorAll('script:not([src])').length") == 0, f"{path}: masih ada skrip inline"
    assert violations == [], violations


def test_csp_really_blocks_injected_inline_script_and_handlers(strict_page, server):
    """Bukti perlindungan nyata: seandainya ada celah XSS, skrip/handler inline yang disuntikkan tidak dijalankan."""
    strict_page.goto(server + "/tentang")
    strict_page.evaluate("""() => { window.__violations = 0;
      document.addEventListener('securitypolicyviolation', () => { window.__violations++; });
      document.body.insertAdjacentHTML('beforeend', '<img src="x" onerror="window.__pwn = 1">');
      const s = document.createElement('script'); s.textContent = 'window.__pwn2 = 1'; document.body.append(s); }""")
    strict_page.wait_for_timeout(400)
    assert strict_page.evaluate("window.__pwn === undefined && window.__pwn2 === undefined")
    assert strict_page.evaluate("window.__violations") >= 2


def test_three_js_loads_by_relative_path_not_by_import_map(strict_page, server):
    strict_page.goto(server + "/")
    assert strict_page.locator("script[type=importmap]").count() == 0
    strict_page.goto(server + "/riset")
    assert strict_page.locator("script[type=importmap]").count() == 0
