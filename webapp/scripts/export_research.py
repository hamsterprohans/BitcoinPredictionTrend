"""Ekspor hasil riset dari output notebook (10) dan artefak ke content/*.json dan static/research/*.png.

Pemakaian: python -m scripts.export_research "<notebook .ipynb>"
Notebook tidak diubah. Tabel yang tidak ditemukan dilaporkan, bukan diisi tebakan.
"""
import csv
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

from app import config

LABEL_NOT_PROVEN = "Belum terbukti lebih baik dari tebakan acak"
LABEL_SIGNIFICANT = "Signifikan setelah koreksi Holm (m=8)"

TABLES = {   # nama berkas: (penanda di kode sel, indeks tabel dalam sel)
    "ablation": ("ablation_rows = []", 0),
    "multiseed": ("# ===== 9b. Multi-seed", 0),
    "multihorizon": ("M4-2. Evaluasi kepekaan horizon", 0),
    "holding_period": ("M4-3. Pembanding keuangan", 0),
}


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell, self._in_head = [], None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "thead":
            self._in_head = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "thead":
            self._in_head = False
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append((self._in_head, self._row))
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _coerce(v: str):
    if v in ("NaN", "nan", "None", ""):
        return None
    if v in ("True", "False"):
        return v == "True"
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v and "e" not in v.lower() else f
    except ValueError:
        return v


def parse_html_table(html: str) -> list:
    p = _TableParser()
    p.feed(html)
    header = next(r for is_head, r in p.rows if is_head and any(c for c in r))
    cols = header[1:] if header[0] == "" else header
    skip_index = header[0] == ""
    body = [r for is_head, r in p.rows if not is_head]
    return [{c: _coerce(v) for c, v in zip(cols, r[1:] if skip_index else r)} for r in body]


def find_tables(nb: dict, marker: str) -> list:
    for cell in nb["cells"]:
        if cell["cell_type"] != "code" or marker not in "".join(cell["source"]):
            continue
        out = []
        for o in cell.get("outputs", []):
            html = "".join(o.get("data", {}).get("text/html", []))
            if "<table" in html:
                out.append(parse_html_table(html))
        return out
    return []


def _stream_text(nb: dict, marker: str) -> str:
    for cell in nb["cells"]:
        if cell["cell_type"] == "code" and marker in "".join(cell["source"]):
            return "".join("".join(o.get("text", [])) for o in cell.get("outputs", []) if o.get("output_type") == "stream")
    return ""


MC_RE = re.compile(r"^(\w) vs (\w): p-value=([\d.]+) \((.*?)\) \| hanya \w benar=(\d+), hanya \w benar=(\d+)", re.M)
WL_RE = re.compile(r"^(\w) vs (\w): statistic=([\d.]+), p-value=([\d.]+) \((.*?)\) \| mean \w=([\d.]+), mean \w=([\d.]+)", re.M)


def parse_significance(nb: dict) -> dict:
    mc = _stream_text(nb, "def run_mcnemar")
    wl = _stream_text(nb, "Wilcoxon Signed-Rank Test (berpasangan")
    return {
        "mcnemar": [{"a": a, "b": b, "p": float(p), "verdict": v, "only_a": int(x), "only_b": int(y)}
                    for a, b, p, v, x, y in MC_RE.findall(mc)],
        "wilcoxon": [{"a": a, "b": b, "statistic": float(st), "p": float(p), "verdict": v,
                      "mean_a": float(ma), "mean_b": float(mb)}
                     for a, b, st, p, v, ma, mb in WL_RE.findall(wl)],
    }


def build_evidence(rows: list) -> dict:
    ev = {}
    for r in rows:
        sig = bool(r.get("signifikan_Holm_m8"))
        ev[str(int(r["H"]))] = {
            "auc": r["AUC_F"], "ci_lo": r["CI_lo"], "ci_hi": r["CI_hi"],
            "p_holm": r["p_Holm_m8"], "significant": sig,
            "label": LABEL_SIGNIFICANT if sig else LABEL_NOT_PROVEN}
    return ev


def main(nb_path: str):
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    config.CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    for name, (marker, idx) in TABLES.items():
        tables = find_tables(nb, marker)
        if len(tables) <= idx:
            report.append(f"TIDAK DITEMUKAN: {name} (penanda: {marker!r})")
            continue
        (config.CONTENT_DIR / f"{name}.json").write_text(
            json.dumps(tables[idx], ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: {name} ({len(tables[idx])} baris)")
        if name == "multihorizon":
            (config.CONTENT_DIR / "multihorizon_evidence.json").write_text(
                json.dumps(build_evidence(tables[idx]), ensure_ascii=False, indent=1), encoding="utf-8")
            report.append("ok: multihorizon_evidence")

    sig = parse_significance(nb)
    if sig["mcnemar"] and sig["wilcoxon"]:
        (config.CONTENT_DIR / "significance.json").write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: significance (McNemar {len(sig['mcnemar'])}, Wilcoxon {len(sig['wilcoxon'])} pasangan)")
    else:
        report.append("TIDAK DITEMUKAN: McNemar/Wilcoxon (output sel notebook kosong atau formatnya berubah)")

    perm = config.ARTIFACTS / "permutation_importance.csv"
    if perm.exists():
        rows = [{k: (float(v) if k != "Fitur" else v) for k, v in r.items()}
                for r in csv.DictReader(open(perm, encoding="utf-8"))]
        (config.CONTENT_DIR / "permutation_importance.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: permutation_importance ({len(rows)} baris)")
    else:
        report.append("TIDAK DITEMUKAN: permutation_importance.csv")

    figs = config.ARTIFACTS / "figures"
    dest = config.STATIC_DIR / "research"
    dest.mkdir(parents=True, exist_ok=True)
    for png in sorted(figs.glob("*.png")) if figs.exists() else []:
        shutil.copy2(png, dest / png.name)
        report.append(f"ok: gambar {png.name}")
    report.append("CATATAN: output backtest di notebook (10) kosong; content/backtest.json tidak dibuat.")
    print("\n".join(report))


if __name__ == "__main__":
    main(sys.argv[1])
