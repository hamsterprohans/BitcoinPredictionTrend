import pytest

from tests.e2e.conftest import collect_errors

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
