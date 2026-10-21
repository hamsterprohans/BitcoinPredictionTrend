import pytest

from tests.e2e.conftest import BASE_NOW, collect_errors

pytestmark = pytest.mark.e2e


def test_research_sections_render(page, server):
    errs = collect_errors(page)
    page.goto(server + "/riset")
    page.wait_for_selector("#sec-ablation table tbody tr")
    assert page.locator("#sec-ablation table tbody tr").count() == 2
    assert page.locator("#sec-multiseed table tbody tr").count() == 2
    assert page.locator("#sec-multihorizon table tbody tr").count() == 2
    assert "Belum terbukti lebih baik dari tebakan acak" in page.inner_text("#sec-multihorizon")
    assert page.locator("#sec-holding table tbody tr").count() == 1
    assert page.locator("#sec-signif table").count() == 2                # McNemar dan Wilcoxon
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


def test_backtest_section_compares_three_strategies_with_proposal_metrics(page, make_server):
    errs = bt_page(page, make_server)
    assert "Backtesting: strategi model vs buy and hold" in page.inner_text("#h-bt")
    heads = page.locator("#bt-table thead th").all_inner_texts()
    assert heads == ["Metrik", "Model (ambang trading 0,35)", "Model (ambang klasifikasi 0,4768)", "Buy and hold"]
    rows = {r.locator("th").inner_text(): r.locator("td").all_inner_texts() for r in page.locator("#bt-table tbody tr").all()}
    assert rows["Modal akhir (modal awal $1.000)"] == ["$794,38", "$985,31", "$794,38"]
    assert rows["Total return"] == ["-20,6%", "-1,5%", "-20,6%"]
    assert rows["Maximum drawdown"] == ["-49,1%", "-26,0%", "-49,1%"]
    assert rows["Sharpe ratio"] == ["-0,20", "0,12", "-0,20"]
    assert rows["Win rate (per transaksi)"] == ["0%", "36%", "0%"]
    assert rows["Rata-rata untung per transaksi"][1] == "+9,2%" and rows["Rata-rata untung per transaksi"][0] == "—"
    assert rows["Rata-rata rugi per transaksi"][1] == "-6,1%"
    assert rows["Jumlah transaksi"] == ["1", "11", "1"] and rows["Hari berada di pasar"] == ["100%", "56%", "100%"]
    assert not errs, errs


def test_backtest_finding_says_model_equals_buy_and_hold_when_threshold_means_always_long(page, make_server):
    bt_page(page, make_server, "always_long")
    text = page.inner_text("#bt-finding")
    assert "sama dengan buy and hold" in text and "0,35" in text and "setiap hari" in text
    assert "bukan bukti" in text.lower()


def test_backtest_finding_reports_a_better_result_without_claiming_proof(page, make_server):
    bt_page(page, make_server, "beats")
    text = page.inner_text("#bt-finding")
    assert "lebih tinggi" in text and "$1.056,13" in text and "$794,38" in text
    assert "bukan bukti" in text.lower() and "forward testing" in text


def test_backtest_sensitivity_table_lists_the_whole_grid_and_exposes_instability(page, make_server):
    bt_page(page, make_server)
    rows = page.locator("#bt-sensitivity tbody tr")
    assert rows.count() == 18
    assert rows.nth(0).locator("td").first.inner_text() == "0,05" and rows.nth(17).locator("td").first.inner_text() == "0,90"
    row060 = [r.all_inner_texts() for r in rows.all() if r.locator("td").first.inner_text() == "0,60"][0]
    assert "+5,6%" in "".join(row060)
    reading = page.inner_text("#bt-reading")
    assert "-38,8%" in reading and "+5,6%" in reading                        # rentang hasil menurut ambang: tanda hasil tidak stabil
    assert "50,1%" in reading or "akurasi" in reading.lower()


def test_backtest_equity_chart_and_caveats_are_present(page, make_server):
    bt_page(page, make_server)
    page.wait_for_selector("#bt-chart canvas")
    assert page.locator("#bt-chart canvas").count() >= 1
    assert page.locator("#bt-caveats li").count() == 5
    assert "forward testing" in page.inner_text("#bt-caveats")


def test_backtest_missing_still_shows_a_clear_message(page, server):
    page.goto(server + "/riset")
    assert "belum tersedia" in page.inner_text("#sec-backtest").lower() and page.locator("#bt-table").count() == 0
