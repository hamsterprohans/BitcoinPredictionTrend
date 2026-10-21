from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.factories import seed_live_dir

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)


@pytest.fixture
def paths(tmp_path):
    live, content, static = tmp_path / "live", tmp_path / "content", tmp_path / "static"
    for p in (live, content, static):
        p.mkdir()
    (static / "index.html").write_text("<h1>home</h1>")
    return live, content, static


def make_client(paths, seeded=True):
    live, content, static = paths
    if seeded:
        seed_live_dir(live, content)
    return TestClient(create_app(live, content, static, now=lambda: NOW))


def test_latest_adds_age_and_evidence(paths):
    r = make_client(paths).get("/api/prediction/latest")
    assert r.status_code == 200
    d = r.json()
    assert d["age_days"] == 1
    assert d["horizons"]["7"]["evidence"]["label"] == "Belum terbukti lebih baik dari tebakan acak"
    assert d["horizons"]["1"]["evidence"] is None


def test_latest_404_when_missing_and_prices_404(paths):
    c = make_client(paths, seeded=False)
    assert c.get("/api/prediction/latest").status_code == 404
    assert c.get("/api/prices").status_code == 404
    assert c.get("/healthz").json() == {"status": "ok"}


def test_history_and_prices_and_research(paths):
    c = make_client(paths)
    assert len(c.get("/api/prediction/history").json()) == 10
    assert "RSI14" in c.get("/api/prices").json()
    assert c.get("/api/research/ablation").json()[0]["Model"] == "A"
    assert c.get("/api/research/tidak_ada").status_code == 404


@pytest.mark.parametrize("bad", ["..%2Flive%2Flatest", "a.b", "A", "x y"])
def test_research_name_whitelist(paths, bad):
    assert make_client(paths).get(f"/api/research/{bad}").status_code in (404, 422)


def test_home_page_served(paths):
    r = make_client(paths).get("/")
    assert r.status_code == 200 and "home" in r.text


@pytest.mark.parametrize("route", ["/", "/riset", "/metodologi"])
def test_page_routes_ignore_fname_query_param(paths, route):
    live, content, static = paths
    (static / "riset.html").write_text("<h1>riset</h1>")
    (static / "metodologi.html").write_text("<h1>metodologi</h1>")
    secret = static.parent / "secret.env"
    secret.write_text("ANTHROPIC_API_KEY=sk-test")
    c = make_client(paths)
    for q in ("../secret.env", "/etc/os-release", "../../app/config.py"):
        r = c.get(route, params={"fname": q})
        assert "sk-test" not in r.text and "ANTHROPIC" not in r.text
        assert r.status_code == 200 and "<h1>" in r.text


@pytest.mark.parametrize("route,fname", [("/latar-belakang", "latar-belakang.html"), ("/tentang", "tentang.html")])
def test_new_pages_routes(paths, route, fname):
    live, content, static = paths
    (static / fname).write_text("<h1>ok</h1>")
    r = make_client(paths).get(route)
    assert r.status_code == 200 and "ok" in r.text


def test_prices_interval_weekly_and_monthly(paths):
    c = make_client(paths)
    d = c.get("/api/prices").json()
    w = c.get("/api/prices", params={"interval": "W"}).json()
    m = c.get("/api/prices", params={"interval": "M"}).json()
    assert len(w["date"]) < len(d["date"]) / 6 and len(m["date"]) < len(w["date"]) / 3
    assert w["close"][-1] == d["close"][-1] == m["close"][-1] and w["date"][-1] == d["date"][-1]
    assert "RSI14" in w and "BB_up" in m
    assert c.get("/api/prices", params={"interval": "D"}).json() == d
    assert c.get("/api/prices", params={"interval": "H"}).status_code == 422


def test_live_price_cached_then_refreshed_and_503_on_failure(paths):
    live, content, static = paths
    seed_live_dir(live, content)
    calls, clock = [], {"t": 1000.0}
    def fetch():
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("upstream down")
        return 81000.0 + len(calls)
    app = create_app(live, content, static, now=lambda: NOW, fetch_live=fetch, monotonic=lambda: clock["t"])
    c = TestClient(app)
    a = c.get("/api/price/live").json()
    assert a["price"] == 81001.0 and a["source"] == "Coinbase" and a["fetched_at"].startswith("2026-10-15")
    clock["t"] += 10
    assert c.get("/api/price/live").json() == a and len(calls) == 1          # masih dalam TTL: tidak memanggil upstream
    clock["t"] += 30
    assert c.get("/api/price/live").json()["price"] == 81002.0 and len(calls) == 2
    clock["t"] += 30
    assert c.get("/api/price/live").status_code == 503                         # upstream gagal -> 503, bukan angka lama


def test_demo_flag_is_passed_through_latest(paths):
    live, content, static = paths
    seed_live_dir(live, content, demo=True)
    c = TestClient(create_app(live, content, static, now=lambda: NOW))
    assert c.get("/api/prediction/latest").json()["demo"] is True
    seed_live_dir(live, content)                                            # data nyata tidak punya bendera demo
    assert "demo" not in c.get("/api/prediction/latest").json()


def test_retro_series_and_day_endpoints(paths):
    from tests.factories import seed_retro
    live, content, static = paths
    seed_retro(content)
    c = TestClient(create_app(live, content, static, now=lambda: NOW))
    s = c.get("/api/retro/series").json()
    assert s["n"] == len(s["date"]) > 25 and [r["level"] for r in s["reliability"]] == ["rendah", "sedang", "tinggi"]
    day = c.get(f"/api/retro/day/{s['date'][0]}").json()
    assert day["date"] == s["date"][0] and len(day["contributions"]) == 13 and day["narrative"]["source"] == "llm"
    assert c.get(f"/api/retro/day/{s['date'][10]}").json()["narrative"] is None


def test_retro_day_rejects_bad_dates_and_traversal(paths):
    from tests.factories import seed_retro
    live, content, static = paths
    seed_retro(content)
    c = TestClient(create_app(live, content, static, now=lambda: NOW))
    assert c.get("/api/retro/day/2020-01-01").status_code == 404                       # format benar, tidak ada
    for bad in ("..%2F..%2Fseries", "abc", "2025-1-1", "2025-03-01.json", "..", "%2e%2e", "2025-03-01%2F..%2F..%2Fseries"):
        assert c.get(f"/api/retro/day/{bad}").status_code == 404, bad


def test_retro_missing_is_404_not_500(paths):
    live, content, static = paths
    c = TestClient(create_app(live, content, static, now=lambda: NOW))
    assert c.get("/api/retro/series").status_code == 404
    assert c.get("/api/retro/day/2025-03-01").status_code == 404


def test_retrospektif_page_route(paths):
    live, content, static = paths
    (static / "retrospektif.html").write_text("<h1>retro</h1>")
    r = TestClient(create_app(live, content, static, now=lambda: NOW)).get("/retrospektif")
    assert r.status_code == 200 and "retro" in r.text


def test_retro_status_never_404(paths):
    from tests.factories import seed_retro
    live, content, static = paths
    c = TestClient(create_app(live, content, static, now=lambda: NOW))
    assert c.get("/api/retro/status").json() == {"built": False, "n": None}
    out = seed_retro(content)
    assert c.get("/api/retro/status").json() == {"built": True, "n": out["series"]["n"]}
