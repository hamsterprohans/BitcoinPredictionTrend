import pytest

from tests.e2e.conftest import BASE_NOW, collect_errors

pytestmark = pytest.mark.e2e


def test_research_sections_render(page, server):
    errs = collect_errors(page)
    page.goto(server + "/riset")
    page.wait_for_selector("#sec-ablation table tbody tr")
    assert page.locator("#sec-ablation table tbody tr").count() == 2
    assert page.locator("#sec-multiseed table tbody tr").count() == 3          # B, F (utama) + F2 (eksperimen tambahan)
    assert page.locator("#sec-multihorizon table tbody tr").count() == 2
    assert "Belum terbukti lebih baik dari tebakan acak" in page.inner_text("#sec-multihorizon")
    assert page.locator("#sec-holding table tbody tr").count() == 1
    assert page.locator("#sec-signif table").count() == 3                # McNemar + Wilcoxon (AUC dan F1 ambang seimbang)
    assert page.locator("#sec-perm .bar-row").count() == 2
    assert page.locator("#bars3d-canvas").count() == 1
    # backtest tidak diekspor -> pesan jelas, bukan area kosong
    assert "belum tersedia" in page.inner_text("#sec-backtest").lower()
    assert page.locator("footer").inner_text().lower().count("bukan saran investasi") == 1
    # gambar yang tidak ada tidak boleh menimbulkan error konsol selain 404 sumber daya
    assert [e for e in errs if "404" not in e] == []


def test_methodology_page(page, server):
    page.goto(server + "/metodologi")
    assert "Metodologi" in page.inner_text("h1")
    assert "bukan saran investasi" in page.inner_text("footer").lower()


# ---- Backtesting: strategi model (long-only) vs buy and hold ----
from tests.factories import backtest_fixture   # noqa: E402


def bt_page(page, make_server, kind="always_long"):
    url = make_server(BASE_NOW, backtest=backtest_fixture(kind))
    errs = collect_errors(page)
    page.goto(url + "/riset")
    page.wait_for_selector("#bt-table")
    return errs


def test_backtest_section_compares_strategies_with_costs_and_proposal_metrics(page, make_server):
    errs = bt_page(page, make_server)
    assert "Backtesting: strategi model vs buy and hold" in page.inner_text("#h-bt")
    heads = page.locator("#bt-table thead th").all_inner_texts()
    assert heads == ["Metrik", "Klasifikasi 0,4768", "Ambang 0,5", "Trading 0,35", "Buy and hold"]
    rows = {r.locator("th").inner_text(): r.locator("td").all_inner_texts() for r in page.locator("#bt-table tbody tr").all()}
    assert rows["Modal akhir (modal awal $1.000)"] == ["$953,47", "$894,47", "$793,20", "$793,20"]
    assert rows["Total return"] == ["-4,7%", "-10,6%", "-20,7%", "-20,7%"]
    assert rows["Maximum drawdown"] == ["-26,4%", "-33,0%", "-49,1%", "-49,1%"]
    assert rows["Sharpe ratio"] == ["0,03", "-0,18", "-0,20", "-0,20"]
    assert rows["Win rate (per transaksi)"] == ["36%", "45%", "0%", "0%"]
    assert rows["Rata-rata untung per transaksi"][0] == "+7,9%" and rows["Rata-rata untung per transaksi"][2] == "—"
    assert rows["Jumlah transaksi (masuk dan keluar)"] == ["22", "22", "1", "1"]
    assert rows["Hari berada di pasar"] == ["56%", "45%", "100%", "100%"]
    assert rows["Keterangan"][2] == "sama dengan buy and hold" and rows["Keterangan"][0] == "—"
    assert "biaya transaksi 0,10%" in page.inner_text("#sec-backtest") and "asumsi" in page.inner_text("#sec-backtest")
    assert not errs, errs


def test_backtest_finding_says_model_equals_buy_and_hold_when_threshold_means_always_long(page, make_server):
    bt_page(page, make_server, "always_long")
    text = page.inner_text("#bt-finding")
    assert "sama dengan buy and hold" in text and "0,35" in text and "setiap hari" in text
    assert "bukan bukti" in text.lower()
    assert "$953,47" in text and "-4,7%" in text                                          # varian ambang klasifikasi dengan biaya


def test_backtest_finding_compares_with_circularly_shifted_random_signals_and_sharpe_interval(page, make_server):
    bt_page(page, make_server, "always_long")
    text = " ".join(page.inner_text("#bt-finding").split())
    assert "digeser sirkular" in text and "p = 0,358" in text and "tidak dapat dibedakan dari sinyal acak" in text
    assert "-1,32" in text and "1,54" in text and "memuat 0" in text


def test_backtest_finding_reports_a_better_result_without_claiming_proof(page, make_server):
    bt_page(page, make_server, "beats")
    text = page.inner_text("#bt-finding")
    assert "lebih tinggi" in text and "$1.056,13" in text and "$793,20" in text
    assert "bukan bukti" in text.lower() and "forward testing" in text


def test_backtest_sensitivity_table_lists_the_whole_grid_and_exposes_instability(page, make_server):
    bt_page(page, make_server)
    rows = page.locator("#bt-sensitivity tbody tr")
    assert rows.count() == 18
    assert rows.nth(0).locator("td").first.inner_text() == "0,05" and rows.nth(17).locator("td").first.inner_text() == "0,90"
    row060 = [r.all_inner_texts() for r in rows.all() if r.locator("td").first.inner_text() == "0,60"][0]
    assert "+5,0%" in "".join(row060)
    reading = page.inner_text("#bt-reading")
    assert "-39,4%" in reading and "+5,0%" in reading                        # rentang hasil menurut ambang: tanda hasil tidak stabil
    assert "50,1%" in reading or "akurasi" in reading.lower()


def test_backtest_equity_chart_and_caveats_are_present(page, make_server):
    bt_page(page, make_server)
    page.wait_for_selector("#bt-chart canvas")
    assert page.locator("#bt-chart canvas").count() >= 1
    assert page.locator("#bt-caveats li").count() == 6
    assert "forward testing" in page.inner_text("#bt-caveats")


def test_backtest_missing_still_shows_a_clear_message(page, server):
    page.goto(server + "/riset")
    assert "belum tersedia" in page.inner_text("#sec-backtest").lower() and page.locator("#bt-table").count() == 0


def test_multiseed_section_reports_ten_seeds_with_mean_and_sd_and_separates_extra_experiments(page, server):
    page.goto(server + "/riset")
    page.wait_for_selector("#sec-multiseed table tbody tr")
    text = " ".join(page.inner_text("#sec-multiseed").split())
    assert "10 seed" in text and "5 seed" not in text.replace("5 seed tambahan", "")
    rows = {r.locator("td").first.inner_text(): r.locator("td").all_inner_texts() for r in page.locator("#sec-multiseed tbody tr").all()}
    assert rows["F"][2:4] == ["0,495 ± 0,021", "0,437 ± 0,051"]            # AUC dan F1 (ambang seragam), rata-rata ± SD
    assert "Eksperimen tambahan" in text and "fitur rasio" in text.lower()


def test_wilcoxon_tables_show_pairs_with_holm_and_the_minimum_possible_p(page, server):
    page.goto(server + "/riset")
    page.wait_for_selector("#sec-signif table")
    text = " ".join(page.inner_text("#sec-signif").split())
    assert "10 seed" in text and "p minimum" in text and "0,002" in text and "Holm" in text
    assert "dengan 5 seed" not in text
    rows = [r.locator("td").all_inner_texts() for r in page.locator("#sec-signif table").nth(1).locator("tbody tr").all()]
    bc = next(r for r in rows if r[0] == "B vs C")
    assert "0,0195" in bc and "0,2734" in bc and bc[-1].startswith("Tidak signifikan")          # p mentah kecil, tetapi tidak lolos Holm


def test_threshold_rule_section_shows_that_accuracy_depends_on_the_rule_but_auc_does_not(page, server):
    page.goto(server + "/riset")
    page.wait_for_selector("#sec-thresholds table tbody tr")
    text = " ".join(page.inner_text("#sec-thresholds").split())
    assert "64,0%" in text and "45,7%" in text and "65,3%" in text                  # H=30 pada tiga aturan ambang
    assert "AUC" in text and "0,622" in text and "bukan bukti" in text.lower()
    heads = page.locator("#sec-thresholds thead th").all_inner_texts()
    assert any("C-Youden" in h and "situs" in h for h in heads) and any("F-Youden" in h for h in heads) and any("median" in h.lower() for h in heads)
    assert page.locator("#sec-thresholds tbody tr").count() == 2
