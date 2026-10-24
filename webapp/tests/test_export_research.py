from scripts.export_research import build_evidence, find_tables, parse_html_table

HTML = """<table border="1"><thead><tr style="text-align: right;"><th></th><th>H</th><th>AUC_F</th>
<th>p_Holm_m8</th><th>signifikan_Holm_m8</th></tr></thead><tbody>
<tr><th>0</th><td>3</td><td>0.500</td><td>1.0</td><td>False</td></tr>
<tr><th>1</th><td>30</td><td>0.622</td><td>NaN</td><td>True</td></tr></tbody></table>"""


def test_parse_html_table_types():
    rows = parse_html_table(HTML)
    assert rows == [
        {"H": 3, "AUC_F": 0.5, "p_Holm_m8": 1.0, "signifikan_Holm_m8": False},
        {"H": 30, "AUC_F": 0.622, "p_Holm_m8": None, "signifikan_Holm_m8": True}]


def test_find_tables_by_marker():
    nb = {"cells": [
        {"cell_type": "code", "source": ["x = 1"], "outputs": []},
        {"cell_type": "code", "source": ["# M4-2. Evaluasi kepekaan horizon\n", "y = 2"],
         "outputs": [{"output_type": "display_data", "data": {"text/html": [HTML]}}]}]}
    tables = find_tables(nb, "M4-2. Evaluasi kepekaan horizon")
    assert len(tables) == 1 and tables[0][0]["H"] == 3


def test_build_evidence_labels():
    rows = [{"H": 3, "AUC_F": 0.5, "CI_lo": 0.43, "CI_hi": 0.57, "p_Holm_m8": 1.0, "signifikan_Holm_m8": False},
            {"H": 30, "AUC_F": 0.9, "CI_lo": 0.8, "CI_hi": 0.95, "p_Holm_m8": 0.01, "signifikan_Holm_m8": True}]
    ev = build_evidence(rows)
    assert ev["3"]["label"] == "Belum terbukti lebih baik dari tebakan acak" and ev["3"]["significant"] is False
    assert ev["30"]["label"].startswith("Signifikan") and ev["30"]["significant"] is True


def test_parse_mcnemar_from_stream_output():
    from scripts.export_research import parse_significance
    mc = ("A vs C: p-value=0.6465 (tidak signifikan) | hanya A benar=82, hanya C benar=89\n"
          "D vs E: p-value=0.0457 (signifikan) | hanya D benar=35, hanya E benar=52\n")
    nb = {"cells": [{"cell_type": "code", "source": ["def run_mcnemar(a):\n"], "outputs": [{"output_type": "stream", "text": [mc]}]}]}
    out = parse_significance(nb)
    assert out["mcnemar"][0] == {"a": "A", "b": "C", "p": 0.6465, "verdict": "tidak signifikan", "only_a": 82, "only_b": 89}
    assert out["mcnemar"][1]["verdict"] == "signifikan"


# ---- Protokol 10 seed (Bagian 9g notebook): tabel multi-seed dan Wilcoxon 15 pasangan dengan koreksi Holm ----
import pandas as pd   # noqa: E402

from scripts.export_research import parse_indexed_table, parse_protocol   # noqa: E402

AGG = pd.DataFrame({"n_seed": [1, 10, 10, 10], "AUC_test_mean": [0.492, 0.488, 0.495, 0.521], "AUC_test_std": [None, 0.016, 0.021, 0.024],
                    "F1w_P1_mean": [0.487, 0.447, 0.437, 0.501], "F1w_P1_std": [None, 0.05, 0.051, 0.042],
                    "F1w_P2_mean": [0.491, 0.473, 0.465, 0.505], "F1w_P2_std": [None, 0.028, 0.03, 0.021],
                    "MCC_P2_mean": [-0.01, -0.01, 0.0, 0.023], "MCC_P2_std": [None, 0.03, 0.03, 0.041]},
                   index=pd.Index(["A", "C", "F2", "B"], name="Model"))
PAIRS_AUC = pd.DataFrame({"pasangan": ["C vs F", "B vs C"], "n_seed": [10, 10], "selisih_rata2": [0.0067, -0.0336],
                          "CI95_lo": [-0.0102, -0.0505], "CI95_hi": [0.0241, -0.0165], "p_wilcoxon": [0.6953, 0.0195],
                          "p_min_mungkin": [0.002, 0.002], "p_Holm": [1.0, 0.2734], "signifikan_Holm": [False, False]})
PAIRS_F1 = PAIRS_AUC.assign(p_wilcoxon=[0.7695, 0.0371], p_Holm=[1.0, 0.5566])


def _protocol_nb():
    html = lambda df: {"output_type": "display_data", "data": {"text/html": [df.to_html()]}}   # noqa: E731
    stream = lambda t: {"output_type": "stream", "name": "stdout", "text": [t]}                  # noqa: E731
    return {"cells": [{"cell_type": "code", "source": ["# ===== PROTOKOL-1. Tabel per-run\n"], "outputs": [
        html(AGG), stream("pctNAIK_P2 jauh dari 50%\n\n=== Uji berpasangan antar-seed | metrik: AUC_test | selisih = ... ===\n"), html(PAIRS_AUC),
        stream("\n=== Uji berpasangan antar-seed | metrik: F1w_P2 | selisih = ... ===\n"), html(PAIRS_F1), stream("Baca: ...")]}]}


def test_indexed_table_keeps_the_model_label_that_the_plain_parser_drops():
    rows = parse_indexed_table(AGG.to_html())
    assert [r["Model"] for r in rows] == ["A", "C", "F2", "B"] and rows[1]["AUC_test_mean"] == 0.488 and rows[0]["AUC_test_std"] is None


def test_protocol_multiseed_rows_cover_only_multi_seed_models_with_descriptions():
    rows = parse_protocol(_protocol_nb())["multiseed"]
    assert [r["Model"] for r in rows] == ["B", "C", "F2"] or [r["Model"] for r in rows] == ["C", "F2", "B"]   # A (seed tunggal) dibuang
    by = {r["Model"]: r for r in rows}
    assert by["F2"]["Kelompok"] == "tambahan" and by["C"]["Kelompok"] == "ablation" and by["B"]["N Seed"] == 10
    assert by["C"]["AUC Mean"] == 0.488 and by["C"]["AUC Std"] == 0.016 and by["C"]["F1 Mean"] == 0.447 and by["C"]["F1 P2 Mean"] == 0.473
    assert "Indikator" in by["C"]["Deskripsi"] and "rasio" in by["F2"]["Deskripsi"]


def test_protocol_wilcoxon_pairs_are_grouped_by_metric_with_holm():
    w = parse_protocol(_protocol_nb())["wilcoxon"]
    assert w["n_seed"] == 10 and w["p_min"] == 0.002
    assert [m["id"] for m in w["metrics"]] == ["AUC_test", "F1w_P2"]
    auc = w["metrics"][0]["pairs"]
    assert auc[1] == {"pair": "B vs C", "a": "B", "b": "C", "n_seed": 10, "diff": -0.0336, "ci_lo": -0.0505, "ci_hi": -0.0165,
                      "p": 0.0195, "p_holm": 0.2734, "significant": False}
    assert w["metrics"][1]["pairs"][0]["p"] == 0.7695


def test_protocol_absent_returns_empty_instead_of_guessing():
    assert parse_protocol({"cells": [{"cell_type": "code", "source": ["x=1"], "outputs": []}]}) == {}


# ---- gambar diambil dari output notebook terbaru, bukan dari folder artefak lama (angkanya bisa berbeda dari tabel) ----
import base64   # noqa: E402

from scripts.export_research import extract_figures   # noqa: E402

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def _fig_nb():
    img = {"output_type": "display_data", "data": {"image/png": PNG + "\n", "text/plain": ["<Figure>"]}}
    return {"cells": [
        {"cell_type": "code", "source": ["ax.set_title('Ablation Study (Seed Tunggal) — F1-Weighted per Model')"], "outputs": [img]},
        {"cell_type": "code", "source": ["plt.suptitle('Learning Curves (Seed Tunggal) — Model B sampai F')"],
         "outputs": [{"output_type": "stream", "text": ["x"]}, img, img]},
        {"cell_type": "code", "source": ["print('tanpa gambar')"], "outputs": []}]}


def test_figures_are_written_from_notebook_outputs_and_missing_ones_are_reported(tmp_path):
    done, missing = extract_figures(_fig_nb(), tmp_path)
    assert set(done) == {"ablation_f1_chart", "learning_curves"}
    assert (tmp_path / "ablation_f1_chart.png").read_bytes().startswith(b"\x89PNG") and (tmp_path / "learning_curves.png").exists()
    assert "confusion_matrices" in missing and "multiseed_f1" not in missing and "multiseed_f1" not in done   # gambar 5 seed sengaja tidak dipakai


# ---- permutation importance dari output notebook (CSV artefak bisa berasal dari run lain) ----
from scripts.export_research import parse_permutation   # noqa: E402

PERM_OUT = """--- Permutation Feature Importance untuk Model F ---

                      Fitur  Baseline F1  Penurunan F1 (Importance)       Std
0                    Vol_30     0.499436                   0.016003  0.004671
1                      MACD     0.499436                   0.013566  0.009890
12              MACD_Signal     0.499436                  -0.011687  0.011389<Figure size 800x500 with 1 Axes>
Fitur paling penting: Vol_30 (penurunan F1=+0.0160)
"""


def test_permutation_importance_is_parsed_from_the_notebook_output():
    nb = {"cells": [{"cell_type": "code", "source": ["# --- Permutation Feature Importance untuk Model F (pengganti SHAP) ---"],
                     "outputs": [{"output_type": "stream", "name": "stdout", "text": [PERM_OUT]}]}]}
    rows = parse_permutation(nb)
    assert [r["Fitur"] for r in rows] == ["Vol_30", "MACD", "MACD_Signal"]
    assert rows[0] == {"Fitur": "Vol_30", "Baseline F1": 0.499436, "Penurunan F1 (Importance)": 0.016003, "Std": 0.004671}
    assert rows[2]["Penurunan F1 (Importance)"] == -0.011687
    assert parse_permutation({"cells": []}) == []


def test_permutation_importance_prefers_the_html_table_in_the_notebook_output():
    df = pd.DataFrame({"Fitur": ["Vol_30", "MACD"], "Baseline F1": [0.499436, 0.499436],
                       "Penurunan F1 (Importance)": [0.016003, 0.013566], "Std": [0.004671, 0.00989]})
    nb = {"cells": [{"cell_type": "code", "source": ["# --- Permutation Feature Importance untuk Model F ---"],
                     "outputs": [{"output_type": "display_data", "data": {"text/html": [df.to_html()]}}]}]}
    assert parse_permutation(nb)[1] == {"Fitur": "MACD", "Baseline F1": 0.499436, "Penurunan F1 (Importance)": 0.013566, "Std": 0.00989}


# ---- diagnostik ambang per horizon (sel M5-2): akurasi bergantung pada aturan ambang, AUC tidak ----
from scripts.export_research import parse_threshold_rules   # noqa: E402

RULES = pd.DataFrame(
    {"1": [49.423, 0.473, 0.496, 7.39, 51.039, 0.477, 37.875, 48.268, 0.485, 21.709, 49.654],
     "30": [50.124, 0.622, 0.481, 20.099, 64.02, 0.446, 86.104, 45.658, 0.471, 32.754, 65.261]},
    index=["% NAIK nyata (uji)", "AUC uji ens F", "thr | C-Youden (situs saat ini)", "%NAIK prediksi | C-Youden (situs saat ini)",
           "akurasi | C-Youden (situs saat ini)", "thr | F-Youden sendiri", "%NAIK prediksi | F-Youden sendiri",
           "akurasi | F-Youden sendiri", "thr | median pv F (P2)", "%NAIK prediksi | median pv F (P2)", "akurasi | median pv F (P2)"])


def test_threshold_rules_table_is_parsed_into_per_horizon_records():
    nb = {"cells": [{"cell_type": "code", "source": ["# ===== M5-2. Diagnostik ambang per horizon: seberapa sering situs akan berkata NAIK? ====="],
                     "outputs": [{"output_type": "display_data", "data": {"text/html": [RULES.to_html()]}}]}]}
    out = parse_threshold_rules(nb)
    assert [h["H"] for h in out] == [1, 30]
    h30 = out[1]
    assert h30["pct_naik_nyata"] == 50.124 and h30["auc_f"] == 0.622
    assert h30["rules"]["c_youden"] == {"thr": 0.481, "pct_naik_pred": 20.099, "akurasi": 64.02}
    assert h30["rules"]["f_youden"]["akurasi"] == 45.658 and h30["rules"]["median_f"]["akurasi"] == 65.261
    assert parse_threshold_rules({"cells": []}) == []
