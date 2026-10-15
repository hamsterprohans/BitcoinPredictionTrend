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
