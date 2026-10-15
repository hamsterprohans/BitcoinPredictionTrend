"""Ekspor situs statis untuk GitHub Pages: halaman, aset, dan SEMUA balasan API dibekukan menjadi berkas.

Pemakaian: python -m scripts.export_static --base /NamaRepo --out dist
Tanpa server Python: frontend membaca api/*.json (lihat getJSON di static/js/common.js); harga live diambil langsung
dari Coinbase oleh browser. Prediksi harian hanya berubah bila ekspor dijalankan ulang.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PAGES = {"index.html": "/", "latar-belakang.html": "/latar-belakang", "retrospektif.html": "/retrospektif",
         "riset.html": "/riset", "metodologi.html": "/metodologi", "kuesioner.html": "/kuesioner", "tentang.html": "/tentang"}


def _rebase_html(text: str, base: str) -> str:
    text = re.sub(r'((?:href|src)=")/(?!/)', lambda m: m.group(1) + base + "/", text)
    text = text.replace('"three":"/static/', f'"three":"{base}/static/')
    return text.replace("<head>", f'<head>\n  <script>window.__STATIC_BASE__="{base}"</script>', 1)


def _rebase_css(text: str, base: str) -> str:
    return re.sub(r'url\((["\']?)/(?!/)', lambda m: f"url({m.group(1)}{base}/", text)


def export_static(app, static_dir, content_dir, out, base: str) -> dict:
    base = base.rstrip("/")
    static_dir, content_dir, out = Path(static_dir), Path(content_dir), Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(static_dir, out / "static", ignore=shutil.ignore_patterns("*.html"))
    for css in (out / "static" / "css").glob("*.css"):
        css.write_text(_rebase_css(css.read_text(), base))
    client = TestClient(app)
    for fname, route in PAGES.items():
        r = client.get(route)
        r.raise_for_status()
        (out / fname).write_text(_rebase_html(r.text, base))
    api_files = 0

    def dump(url: str, rel: str, required=True):
        nonlocal api_files
        r = client.get(url)
        if r.status_code != 200:
            if required:
                raise RuntimeError(f"{url} -> HTTP {r.status_code}")
            return False
        dest = out / "api" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        api_files += 1
        return True

    dump("/api/prediction/latest", "prediction/latest.json")
    dump("/api/prediction/history", "prediction/history.json")
    for iv in ("D", "W", "M"):
        dump(f"/api/prices?interval={iv}", f"prices__{iv}.json")
    dump("/api/retro/status", "retro/status.json")
    if dump("/api/retro/series", "retro/series.json", required=False):
        for f in sorted((content_dir / "retro" / "days").glob("*.json")):
            dump(f"/api/retro/day/{f.stem}", f"retro/day/{f.name}")
    for f in sorted(content_dir.glob("*.json")):
        dump(f"/api/research/{f.stem}", f"research/{f.name}", required=False)
    (out / ".nojekyll").write_text("")
    return {"pages": len(PAGES), "api_files": api_files}


if __name__ == "__main__":
    from app import config
    from app.main import create_app
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="subpath situs, mis. /BitcoinPredictionTugasAkhir (kosong untuk user.github.io)")
    ap.add_argument("--out", default="dist")
    a = ap.parse_args()
    rep = export_static(create_app(), config.STATIC_DIR, config.CONTENT_DIR, a.out, a.base)
    print(f"Terekspor ke {a.out}: {rep['pages']} halaman, {rep['api_files']} berkas API", file=sys.stderr)
