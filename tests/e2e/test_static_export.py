import functools
import http.server
import threading

import pytest

from app import config
from app.main import create_app
from scripts.export_static import export_static
from tests.e2e.conftest import BASE_NOW, collect_errors
from tests.factories import seed_live_dir, seed_retro


class SubpathHandler(http.server.SimpleHTTPRequestHandler):
    """Meniru github.io/<repo>/: hanya melayani di bawah /sub/, /riset -> riset.html."""
    def translate_path(self, path):
        path = path.split("?", 1)[0]
        assert path.startswith("/sub"), path
        rel = path[len("/sub"):] or "/"
        if rel == "/":
            rel = "/index.html"
        elif "." not in rel.rsplit("/", 1)[-1]:
            rel += ".html"
        return super().translate_path(rel)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def static_site(tmp_path_factory):
    base = tmp_path_factory.mktemp("static-site")
    live, content, out = base / "live", base / "content", base / "dist"
    live.mkdir()
    content.mkdir()
    seed_live_dir(live, content)
    seed_retro(content)
    export_static(create_app(live, content, config.STATIC_DIR, now=lambda: BASE_NOW), config.STATIC_DIR, content, out, "/sub")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SubpathHandler, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/sub"
    srv.shutdown()


def test_static_prediction_page_and_interval_work_under_subpath(page, static_site):
    errs = collect_errors(page)
    failed = []
    page.on("response", lambda r: failed.append(r.url) if r.status >= 400 and "coinbase" not in r.url and not r.url.endswith("/research/backtest.json") else None)   # backtest memang belum diekspor: halaman menampilkan "belum tersedia"
    page.route("**/api.coinbase.com/**", lambda route: route.fulfill(
        status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
        body='{"data":{"amount":"99999.5"}}'))
    page.goto(static_site + "/")
    page.wait_for_selector("#price")
    page.wait_for_function("document.querySelector('#live-badge') && !document.querySelector('#live-badge').hidden")
    assert "99.999,50" in page.inner_text("#price")                      # harga live dari Coinbase langsung di browser
    page.wait_for_selector("#intervals button")
    page.locator("#intervals button:has-text('W')").click()
    page.wait_for_function("[...document.querySelectorAll('#intervals button')].find(b => b.textContent === 'W').getAttribute('aria-pressed') === 'true'")
    page.goto(static_site + "/retrospektif")
    page.wait_for_selector("#day-slider")
    page.wait_for_function("document.querySelector('#day-slider').max > 0")
    page.goto(static_site + "/kuesioner")
    page.wait_for_selector("#survey input[type=radio]")                  # modul, skema, dan konfigurasi termuat di subpath
    page.goto(static_site + "/riset")
    page.wait_for_load_state("networkidle")
    assert not failed, failed
    assert not [e for e in errs if "status of 404" not in e], errs      # 404 backtest.json: lihat catatan di atas
