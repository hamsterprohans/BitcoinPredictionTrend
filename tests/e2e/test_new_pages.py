import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

NAV = ["Prediksi", "Latar Belakang", "Retrospektif", "Riset", "Metodologi", "Kuesioner", "Tentang"]


@pytest.mark.parametrize("path", ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"])
def test_nav_has_seven_links_on_every_page(page, server, path):
    page.goto(server + path)
    assert page.locator("header nav a").all_inner_texts() == NAV
    assert page.get_attribute("header nav a[aria-current]", "href") == path


def test_background_page_fills_numbers_from_research_data(page, server):
    errs = collect_errors(page)
    page.goto(server + "/latar-belakang")
    page.wait_for_selector("#summary [data-fill]:not(:text('…'))")
    assert "Rumusan masalah" in page.inner_text("main")
    assert page.locator("#rq li").count() == 6                       # enam rumusan masalah
    summary = page.inner_text("#summary")
    assert "0,6465" in summary or "0,839" in summary                  # p-value McNemar dari significance.json (id-ID)
    assert "bukan saran investasi" in page.inner_text("footer").lower()
    assert [e for e in errs if "404" not in e] == []


def test_background_page_is_honest_about_unfinished_parts(page, server):
    page.goto(server + "/latar-belakang")
    text = page.inner_text("main").lower()
    assert "belum" in text and "explainer" in text                   # lapisan penjelas belum ada di website
    assert "backtest" in text


def test_about_page_shows_only_approved_facts(page, server):
    page.goto(server + "/tentang")
    text = page.inner_text("main")
    for fact in ("Hans Christian Cakrawangsa", "5026231130", "Sistem Informasi", "Institut Teknologi Sepuluh Nopember",
                 "Renny Pradina Kusumawardani"):
        assert fact in text, fact
    assert page.locator("a[href*='github.com/hanscakrawangsa15']").count() == 1


def test_about_page_has_photo_summary_and_linkedin_link(page, server):
    page.goto(server + "/tentang")
    img = page.locator("img.about-photo")
    assert img.count() == 1 and "Hans" in img.get_attribute("alt")
    page.wait_for_function("document.querySelector('img.about-photo').complete")
    assert page.evaluate("document.querySelector('img.about-photo').naturalWidth") == 354         # PNG termuat
    assert img.get_attribute("src").endswith(".png")
    link = page.locator("a[href='https://www.linkedin.com/in/hanscakrawangsa/']")
    assert link.count() >= 1 and "noopener" in link.first.get_attribute("rel")
    words = len(page.inner_text("#about-summary p:not(:has(a))").split())
    assert words <= 90, words                                                                     # ringkasan singkat
    summary = page.inner_text("#about-summary")
    for fact in ("Sistem Informasi", "Institut Teknologi Sepuluh Nopember", "LSTM", "LinkedIn"):
        assert fact in summary, fact
    assert "Bitcoin" in summary


def test_about_page_experience_certifications_and_skills_from_linkedin(page, server):
    page.goto(server + "/tentang")
    summary = page.inner_text("#about-summary")
    for fact in ("Blockchain Developer", "Vallidge Consulting", "FlyRank AI", "Solidity", "LSTM"):
        assert fact in summary, fact
    assert "berbohong" not in summary and "negatif" not in summary          # tanpa kalimat ambigu
    exp = page.inner_text("#about-experience")
    for fact in ("Asisten Dosen", "Backend AI Engineer", "FlyRank AI", "Vallidge Consulting", "BEP-20", "ERC-1155",
                 "Polygon", "Odoo", "PKMBK"):
        assert fact in exp, fact
    assert page.locator("#about-experience > ul > li").count() >= 5
    cert = page.inner_text("#about-certs")
    for fact in ("AWS Academy", "Cloud Foundations", "Prompt Design in Vertex AI", "Cisco DevNet Associate",
                 "Anthropic Academy", "Model Context Protocol", "Claude 101"):
        assert fact in cert, fact
    skills = page.inner_text("#about-skills")
    assert "Kepemimpinan Organisasi" in skills and "Pengembangan Aplikasi Cloud" in skills
    assert "profil LinkedIn" in page.inner_text("#about-source")                  # sumber disebut jelas
