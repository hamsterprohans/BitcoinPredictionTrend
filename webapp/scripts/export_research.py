"""Ekspor hasil riset dari output notebook (10) dan artefak ke content/*.json dan static/research/*.png.

Pemakaian: python -m scripts.export_research "<notebook .ipynb>"
Notebook tidak diubah. Tabel yang tidak ditemukan dilaporkan, bukan diisi tebakan.
"""
import base64
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


def parse_indexed_table(html: str) -> list:
    """Seperti parse_html_table, tetapi kolom indeks (mis. Model) dipertahankan sebagai kolom bernama sesuai label indeksnya."""
    p = _TableParser()
    p.feed(html)
    heads = [r for is_head, r in p.rows if is_head]
    cols = next(r for r in heads if any(r))[1:]
    index_name = next((r[0] for r in heads[1:] if r and r[0]), "index")
    body = [r for is_head, r in p.rows if not is_head]
    return [{index_name: r[0], **{c: _coerce(v) for c, v in zip(cols, r[1:])}} for r in body]


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


FIGURES = {   # nama berkas: penanda judul di kode sel notebook (gambar pertama pada sel itu)
    "ablation_f1_chart": "Ablation Study (Seed Tunggal)",
    "confusion_matrices": "Confusion Matrix — Model A sampai F",
    "learning_curves": "Learning Curves (Seed Tunggal)",
    "model_C_probability_distribution": "Model C — Distribusi Probabilitas",
    "model_C_training_curves": "Model C — Akurasi per Epoch",
    "permutation_importance": "Permutation Feature Importance — Model F",
    "stage1_lr_vs_lstm": "F1-weighted (seed tunggal)",
}                                      # multiseed_f1 (5 seed) sengaja tidak dipakai: tabel 10 seed menggantikannya


def extract_figures(nb: dict, dest: Path):
    """Tulis gambar dari OUTPUT notebook ke dest. Folder artefak lama bisa berisi gambar dari run berbeda (angka tidak sama dengan tabel)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    done, missing = [], []
    for name, marker in FIGURES.items():
        png = next((o["data"]["image/png"] for c in nb["cells"] if c["cell_type"] == "code" and marker in "".join(c["source"])
                    for o in c.get("outputs", []) if "image/png" in o.get("data", {})), None)
        if png is None:
            missing.append(name)
            continue
        (dest / f"{name}.png").write_bytes(base64.b64decode("".join(png) if isinstance(png, list) else png))
        done.append(name)
    return done, missing


PERM_ROW_RE = re.compile(r"^\s*\d+\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)", re.M)


def parse_permutation(nb: dict) -> list:
    for table in find_tables(nb, "Permutation Feature Importance untuk Model F"):    # tabel HTML (display) lebih andal daripada teks
        if table and "Fitur" in table[0] and "Penurunan F1 (Importance)" in table[0]:
            return table
    text = _stream_text(nb, "Permutation Feature Importance untuk Model F")
    return [{"Fitur": f, "Baseline F1": float(b), "Penurunan F1 (Importance)": float(d), "Std": float(sd)}
            for f, b, d, sd in PERM_ROW_RE.findall(text)]


RULE_IDS = {"C-Youden (situs saat ini)": "c_youden", "F-Youden sendiri": "f_youden", "median pv F (P2)": "median_f"}


def parse_threshold_rules(nb: dict) -> list:
    """Sel M5-2: untuk tiap horizon, akurasi uji ensemble Model F di bawah tiga aturan ambang (C-Youden = situs, F-Youden, median)."""
    for table in find_tables_indexed(nb, "M5-2. Diagnostik ambang per horizon"):
        by = {r["index"]: r for r in table}
        horizons = [k for k in table[0] if k != "index"]
        out = []
        for h in horizons:
            rules = {rid: {"thr": by[f"thr | {name}"][h], "pct_naik_pred": by[f"%NAIK prediksi | {name}"][h],
                           "akurasi": by[f"akurasi | {name}"][h]} for name, rid in RULE_IDS.items()}
            out.append({"H": int(h), "pct_naik_nyata": by["% NAIK nyata (uji)"][h], "auc_f": by["AUC uji ens F"][h], "rules": rules})
        return out
    return []


def find_tables_indexed(nb: dict, marker: str) -> list:
    for cell in nb["cells"]:
        if cell["cell_type"] == "code" and marker in "".join(cell["source"]):
            return [parse_indexed_table(h) for o in cell.get("outputs", [])
                    if "<table" in (h := "".join(o.get("data", {}).get("text/html", [])))]
    return []


PROTOCOL_MARKER = "PROTOKOL-1"
METRIC_LABEL = {"AUC_test": "AUC uji", "F1w_P2": "F1-weighted (ambang seimbang P2)"}
MODEL_DESC = {
    "B": "LSTM + Daily Return", "C": "LSTM + 11 Indikator Teknikal", "D": "LSTM + Teknikal + Sentimen Berita",
    "E": "LSTM + Teknikal + Fear & Greed", "F": "LSTM + Semua Fitur",
    "Bx": "LSTM + Daily Return (batas 300 epoch)", "C2": "LSTM + 11 Indikator (fitur rasio)",
    "D2": "LSTM + Teknikal rasio + Sentimen", "E2": "LSTM + Teknikal rasio + Fear & Greed", "F2": "LSTM + Semua Fitur (rasio)"}
PAIR_METRIC_RE = re.compile(r"metrik: (\w+)")


def _protocol_cell(nb: dict):
    return next((c for c in nb["cells"] if c["cell_type"] == "code" and PROTOCOL_MARKER in "".join(c["source"])), None)


def parse_protocol(nb: dict) -> dict:
    """Bagian 9g notebook (10 seed): tabel multi-seed per model dan uji Wilcoxon berpasangan + koreksi Holm. {} bila tidak ada."""
    cell = _protocol_cell(nb)
    if cell is None:
        return {}
    agg, pairs, metric = None, {}, None
    for o in cell.get("outputs", []):
        if o.get("output_type") == "stream":
            m = PAIR_METRIC_RE.search("".join(o.get("text", [])))
            metric = m.group(1) if m else metric
            continue
        html = "".join(o.get("data", {}).get("text/html", []))
        if "<table" not in html:
            continue
        if agg is None:
            agg = parse_indexed_table(html)
        elif metric:
            pairs[metric] = parse_html_table(html)
    if agg is None or not pairs:
        return {}
    rows = [{"Model": r["Model"], "Kelompok": "ablation" if r["Model"] in "BCDEF" and len(r["Model"]) == 1 else "tambahan",
             "Deskripsi": MODEL_DESC.get(r["Model"], r["Model"]), "N Seed": r["n_seed"],
             "AUC Mean": r["AUC_test_mean"], "AUC Std": r["AUC_test_std"], "F1 Mean": r["F1w_P1_mean"], "F1 Std": r["F1w_P1_std"],
             "F1 P2 Mean": r["F1w_P2_mean"], "F1 P2 Std": r["F1w_P2_std"], "MCC P2 Mean": r["MCC_P2_mean"], "MCC P2 Std": r["MCC_P2_std"]}
            for r in agg if r["n_seed"] and r["n_seed"] > 1]
    metrics = [{"id": k, "label": METRIC_LABEL.get(k, k), "pairs": [
        {"pair": r["pasangan"], "a": r["pasangan"].split(" vs ")[0], "b": r["pasangan"].split(" vs ")[1], "n_seed": r["n_seed"],
         "diff": r["selisih_rata2"], "ci_lo": r["CI95_lo"], "ci_hi": r["CI95_hi"], "p": r["p_wilcoxon"], "p_holm": r["p_Holm"],
         "significant": bool(r["signifikan_Holm"])} for r in v]} for k, v in pairs.items()]
    first = next(iter(pairs.values()))[0]
    return {"multiseed": rows, "wilcoxon": {"n_seed": first["n_seed"], "p_min": first["p_min_mungkin"], "metrics": metrics}}


MC_RE = re.compile(r"^(\w) vs (\w): p-value=([\d.]+) \((.*?)\) \| hanya \w benar=(\d+), hanya \w benar=(\d+)", re.M)


def parse_significance(nb: dict) -> dict:
    mc = _stream_text(nb, "def run_mcnemar")
    return {"mcnemar": [{"a": a, "b": b, "p": float(p), "verdict": v, "only_a": int(x), "only_b": int(y)}
                        for a, b, p, v, x, y in MC_RE.findall(mc)]}


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

    protocol = parse_protocol(nb)
    if protocol:
        (config.CONTENT_DIR / "multiseed.json").write_text(json.dumps(protocol["multiseed"], ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: multiseed ({len(protocol['multiseed'])} model, {protocol['wilcoxon']['n_seed']} seed)")
    else:
        report.append(f"TIDAK DITEMUKAN: protokol 10 seed (penanda: {PROTOCOL_MARKER!r}); multiseed.json dan Wilcoxon tidak diperbarui")
    sig = parse_significance(nb)
    if sig["mcnemar"] and protocol:
        sig["wilcoxon"] = protocol["wilcoxon"]
        (config.CONTENT_DIR / "significance.json").write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
        n_pairs = len(protocol["wilcoxon"]["metrics"][0]["pairs"])
        report.append(f"ok: significance (McNemar {len(sig['mcnemar'])}, Wilcoxon {n_pairs} pasangan x {len(protocol['wilcoxon']['metrics'])} metrik)")
    else:
        report.append("TIDAK DITEMUKAN: McNemar atau Wilcoxon (output sel notebook kosong atau formatnya berubah)")

    rules = parse_threshold_rules(nb)
    if rules:
        (config.CONTENT_DIR / "threshold_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: threshold_rules ({len(rules)} horizon)")
    else:
        report.append("TIDAK DITEMUKAN: diagnostik ambang per horizon (sel M5-2); threshold_rules.json tidak diperbarui")
    rows = parse_permutation(nb)
    if rows:
        (config.CONTENT_DIR / "permutation_importance.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"ok: permutation_importance ({len(rows)} baris, dari output notebook)")
    else:
        report.append("TIDAK DITEMUKAN: permutation importance di output notebook; permutation_importance.json tidak diperbarui")

    done, missing = extract_figures(nb, config.STATIC_DIR / "research")
    report += [f"ok: gambar {n}.png (dari output notebook)" for n in done]
    report += [f"TIDAK DITEMUKAN: gambar {n} (gambar lama di static/research dibiarkan; periksa apakah masih sesuai tabel)" for n in missing]
    report.append("CATATAN: content/backtest.json dibangun terpisah (python -m scripts.build_backtest), bukan dari output notebook.")
    print("\n".join(report))


if __name__ == "__main__":
    main(sys.argv[1])
