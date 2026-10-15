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
