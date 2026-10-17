import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn

from app import config
from app.main import create_app
from tests.factories import seed_live_dir, seed_prices_only, seed_retro

BASE_NOW = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)


def _serve(app):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    return srv, t, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session")
def make_server(tmp_path_factory):
    started = []

    def _make(now, seed=True, chart_only=False, live_price=None, demo=False, retro=False, explain=True):
        base = tmp_path_factory.mktemp("e2e")
        live, content = base / "live", base / "content"
        live.mkdir()
        content.mkdir()
        if chart_only:
            seed_prices_only(live)
        elif seed:
            seed_live_dir(live, content, demo=demo, explain=explain)
        if retro:
            seed_retro(content)
        def fetch_live():                       # tes tidak boleh menyentuh jaringan
            if live_price is None:
                raise RuntimeError("harga live tidak tersedia")
            return live_price
        srv, t, url = _serve(create_app(live, content, config.STATIC_DIR, now=lambda: now, fetch_live=fetch_live))
        started.append((srv, t))
        return url

    yield _make
    for srv, t in started:
        srv.should_exit = True
        t.join(timeout=5)


@pytest.fixture(scope="session")
def server(make_server):
    return make_server(BASE_NOW)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {**browser_type_launch_args, "args": ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]}


def collect_errors(page):
    errs = []
    # 503 dari /api/price/live adalah simulasi gangguan yang disengaja pada server e2e (tes tidak boleh menyentuh jaringan)
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" and "status of 503" not in m.text else None)
    page.on("pageerror", lambda e: errs.append(str(e)))
    return errs


@pytest.fixture
def context(context):
    """Splash screen tampil sekali per sesi; tes lain menandainya sudah dilihat agar tidak menghalangi klik."""
    context.add_init_script("try { sessionStorage.setItem('splash-seen', '1'); } catch (e) {}")
    return context
