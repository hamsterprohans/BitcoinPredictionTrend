import pytest

from app.explain import FEATURE_LABELS
from tests.e2e.conftest import BASE_NOW

pytestmark = pytest.mark.e2e

KEY_TERMS = ["Probabilitas naik", "Ambang keputusan", "Horizon prediksi", "Tingkat keyakinan", "Akurasi", "Tebakan acak", "AUC",
             "Interval kepercayaan 95%", "Periode uji", "Sentimen berita", "Fear & Greed Index", "Kontribusi fitur", "Volatilitas",
             "Rata-rata harga", "MACD", "RSI", "Bollinger", "Return harian", "LSTM", "LLM", "Harga penutupan", "Harga live"]


def terms(page):
    return page.locator("#sec-glossary dt").all_inner_texts()


def test_glossary_sits_between_the_history_and_the_questionnaire_promo(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#sec-glossary")
    order = page.evaluate("[...document.querySelectorAll('main > section')].map(s => s.id)")
    assert order.index("sec-hist") < order.index("sec-glossary") < order.index("sec-survey")
    assert "Glosarium" in page.inner_text("#h-gloss")


def test_glossary_covers_the_key_terms_with_real_definitions(page, server):
    page.goto(server + "/")
    names = [t.lower() for t in terms(page)]
    for key in KEY_TERMS:
        assert any(key.lower() in n for n in names), f"istilah '{key}' belum ada"
    assert len(names) >= 25 and len(set(names)) == len(names)
    for dd in page.locator("#sec-glossary dd").all_inner_texts():
        assert len(dd.strip()) >= 40, dd                                           # definisi sungguhan, bukan placeholder


def test_every_feature_label_shown_in_the_explanation_panel_has_a_glossary_entry(page, server):
    page.goto(server + "/")
    text = page.inner_text("#sec-glossary").lower()
    for label in FEATURE_LABELS.values():
        core = label.lower().replace(" 7 hari", "").replace(" 30 hari", "").replace(" 90 hari", "").replace(" 14 hari", "")
        assert core.split(" (")[0] in text or core.split()[0] in text, f"fitur '{label}' tidak dijelaskan"


def test_definitions_stay_honest_about_what_the_model_can_claim(page, server):
    page.goto(server + "/")
    by_term = {dt.inner_text(): dt.locator("xpath=following-sibling::dd[1]").inner_text() for dt in page.locator("#sec-glossary dt").all()}
    prob = next(v for k, v in by_term.items() if k.lower().startswith("probabilitas naik"))
    assert "bukan" in prob.lower() and "50%" in prob                                # bukan peluang pasti; 50% = tidak condong
    rnd = next(v for k, v in by_term.items() if k.lower().startswith("tebakan acak"))
    assert "50%" in rnd and "belum terbukti" in rnd.lower()
    auc = next(v for k, v in by_term.items() if k.lower().startswith("auc"))
    assert "0,5" in auc
    kontribusi = next(v for k, v in by_term.items() if k.lower().startswith("kontribusi fitur"))
    assert "sebab" in kontribusi.lower()                                            # bukan hubungan sebab-akibat


def test_search_filters_terms_and_announces_the_count(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#gloss-search")
    total = len(terms(page))
    page.fill("#gloss-search", "rsi")
    visible = page.locator("#sec-glossary dt:visible").all_inner_texts()
    assert len(visible) >= 1 and all("rsi" in v.lower() or v for v in visible) and any("RSI" in v for v in visible)
    assert f"dari {total}" in page.inner_text("#gloss-count")
    page.fill("#gloss-search", "zzzxxyy")
    assert page.locator("#sec-glossary dt:visible").count() == 0
    assert "tidak ada istilah" in page.inner_text("#gloss-count").lower()
    page.fill("#gloss-search", "")
    assert page.locator("#sec-glossary dt:visible").count() == total


def test_search_also_matches_words_inside_definitions_and_is_case_insensitive(page, server):
    page.goto(server + "/")
    page.fill("#gloss-search", "SAMA DENGAN lempar koin")
    assert page.locator("#sec-glossary dt:visible").count() >= 1                    # kata di dalam definisi, huruf besar-kecil bebas


def test_prediction_card_links_to_the_glossary(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#sec-pred")
    link = page.locator("#sec-pred a[href='#sec-glossary']")
    assert link.count() == 1 and "glosarium" in link.inner_text().lower()
    link.click()
    assert page.evaluate("location.hash") == "#sec-glossary"
    assert page.locator("#sec-glossary").is_visible()


def test_glossary_fits_a_small_phone_even_with_the_largest_text(browser, server):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": 360, "height": 800}, is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen','1'); localStorage.setItem('text-level','3'); } catch (e) {}")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_selector("#sec-glossary")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    card = page.locator("#sec-glossary").bounding_box()
    for t in page.locator("#sec-glossary dt").all()[:6]:
        assert t.bounding_box()["x"] + t.bounding_box()["width"] <= card["x"] + card["width"] + 1
    ctx.close()


def norm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))


def test_glossary_is_one_alphabetical_list_with_a_heading_per_letter(page, server):
    page.goto(server + "/")
    groups = page.locator("#sec-glossary .gloss-group")
    letters = [g.locator("h3").inner_text().strip() for g in groups.all()]
    assert letters == sorted(letters) and all(len(l) == 1 and l.isalpha() for l in letters)      # A, D, F, ... berurutan
    assert len(set(letters)) == len(letters)
    flat = []
    for g in groups.all():
        letter = g.locator("h3").inner_text().strip()
        names = g.locator("dt").all_inner_texts()
        assert names, letter
        assert all(norm(n)[0] == letter.lower() for n in names), (letter, names)                 # istilah ada di huruf awalnya
        assert [norm(n) for n in names] == sorted(norm(n) for n in names), letter                # urut abjad di dalam huruf
        flat += names
    assert len(flat) == len(terms(page))                                                         # tak ada istilah yang hilang


def test_each_term_takes_one_row_on_desktop_with_term_beside_definition(page, server):
    page.goto(server + "/")
    page.wait_for_selector("#sec-glossary")
    card = page.locator("#sec-glossary").bounding_box()
    rows = page.locator("#sec-glossary .gl").all()
    tops = [round(r.bounding_box()["y"]) for r in rows]
    assert len(set(tops)) == len(tops)                                                           # tak ada dua istilah sebaris (bukan 3 kolom)
    for r in rows[:8]:
        b = r.bounding_box()
        assert b["width"] >= (card["width"] - 40) * 0.95                                         # satu baris selebar kartu
        dt, dd = r.locator("dt").bounding_box(), r.locator("dd").bounding_box()
        assert dd["x"] > dt["x"] + dt["width"] - 1 and abs(dd["y"] - dt["y"]) < 16               # istilah di kiri, definisi di kanan


def test_term_is_stacked_above_the_definition_on_phones(browser, server):
    ctx = browser.new_context(bypass_csp=True, viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_init_script("try { sessionStorage.setItem('splash-seen','1'); } catch (e) {}")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_selector("#sec-glossary")
    r = page.locator("#sec-glossary .gl").first
    dt, dd = r.locator("dt").bounding_box(), r.locator("dd").bounding_box()
    assert dd["y"] >= dt["y"] + dt["height"] - 1 and abs(dd["x"] - dt["x"]) < 4                  # susun ke bawah agar terbaca di layar sempit
    ctx.close()
