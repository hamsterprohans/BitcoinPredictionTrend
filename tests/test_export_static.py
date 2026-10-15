import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.main import create_app
from scripts.export_static import export_static
from tests.factories import seed_live_dir, seed_retro

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)


def build(tmp_path, base="/sub"):
    live, content, out = tmp_path / "live", tmp_path / "content", tmp_path / "dist"
    live.mkdir()
    content.mkdir()
    seed_live_dir(live, content)
    seed_retro(content)
    app = create_app(live, content, config.STATIC_DIR, now=lambda: NOW)
    report = export_static(app, config.STATIC_DIR, content, out, base)
    return out, report


def test_exports_pages_api_and_assets(tmp_path):
    out, _ = build(tmp_path)
    for f in ("index.html", "riset.html", "retrospektif.html", "tentang.html", "latar-belakang.html", "metodologi.html",
              "api/prediction/latest.json", "api/prediction/history.json", "api/prices__D.json", "api/prices__W.json",
              "api/prices__M.json", "api/retro/status.json", "api/retro/series.json", "api/research/ablation.json",
              "static/js/common.js", "static/vendor/three.module.min.js", "static/fonts/Geist-Variable.woff2", ".nojekyll"):
        assert (out / f).exists(), f
    series = json.loads((out / "api/retro/series.json").read_text())
    for d in (series["date"][0], series["date"][-1]):
        assert (out / "api/retro/day" / f"{d}.json").exists(), d


def test_no_root_absolute_references_remain(tmp_path):
    out, _ = build(tmp_path)
    bad = re.compile(r"""(?:href|src)=["']/(?!sub/)|url\(["']?/(?!sub/)|"three":"/(?!sub/)""")
    for f in list(out.glob("*.html")) + list(out.glob("static/css/*.css")):
        assert not bad.search(f.read_text()), f
    html = (out / "index.html").read_text()
    assert 'window.__STATIC_BASE__="/sub"' in html
    assert 'href="/sub/riset"' in html and '"three":"/sub/static/vendor/three.module.min.js"' in html
    assert "url(\"/sub/static/fonts/Geist-Variable.woff2\")" in (out / "static/css/tokens.css").read_text()


def test_root_base_keeps_paths_and_latest_has_as_of(tmp_path):
    out, report = build(tmp_path, base="")
    assert 'window.__STATIC_BASE__=""' in (out / "index.html").read_text()
    assert 'href="/riset"' in (out / "index.html").read_text()
    assert json.loads((out / "api/prediction/latest.json").read_text())["as_of"]
    assert report["pages"] == 6 and report["api_files"] > 5
