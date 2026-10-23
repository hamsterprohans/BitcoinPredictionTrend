import json
import re

import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

CONFIG = {"supabaseUrl": "https://proj.supabase.co", "supabaseAnonKey": "anon-test-key"}
# Urutan dan ID mengikuti dokumen "Referensi Kuesioner TA Hans" (A0-A4, B1-B6, SUS 1-10, D1-D8, E1-E4, F1-F4);
# "nama" dan "d0" (penyaring kelompok yang melihat penjelasan) adalah tambahan.
EXPECTED_IDS = (["a0", "nama", "a1", "a2", "a3", "a4"] + [f"b{i}" for i in range(1, 7)] + [f"c{i}" for i in range(1, 11)]
                + ["d0"] + [f"d{i}" for i in range(1, 9)] + [f"e{i}" for i in range(1, 5)] + [f"f{i}" for i in range(1, 5)])
TYPES = {"a0": "yn", "nama": "short", "a1": "choice", "a2": "scale", "a3": "choice", "a4": "choice", "d0": "yn"}
TYPES.update({f"b{i}": "tf" for i in range(1, 7)})
TYPES.update({f"c{i}": "scale" for i in range(1, 11)})
TYPES.update({f"d{i}": "scale" for i in range(1, 9)})
TYPES.update({f"e{i}": "scale" for i in range(1, 5)})
TYPES.update({f"f{i}": "long" for i in range(1, 5)})
RADIOS = {"yn": 2, "choice": None, "scale": 5, "tf": 3, "short": 1, "long": 1}


def configured(context):
    context.add_init_script(f"window.__APP_CONFIG__ = {json.dumps(CONFIG)};")


def load_schema(page, server):
    page.goto(server + "/kuesioner")
    return page.evaluate("import('/static/js/kuesioner-schema.js').then(m => m.SURVEY)")


def questions(survey):
    return [q for s in survey["sections"] for q in s["questions"]]


def by_id(survey):
    return {q["id"]: q for q in questions(survey)}


def answer_for(q, overrides):
    if q["id"] in overrides:
        return overrides[q["id"]]
    return {"yn": "ya", "choice": q.get("options", [{}])[0].get("value"), "scale": "4", "tf": "benar",
            "short": "Budi Santoso", "long": f"jawaban {q['id']}"}[q["type"]]


def fill_all(page, survey, skip=(), **overrides):
    """Isi semua soal yang sedang tampil, berurutan (persetujuan dulu agar bagian lain terbuka)."""
    for q in questions(survey):
        if q["id"] in skip or page.locator(f"[data-qid='{q['id']}']").is_hidden():
            continue
        v = answer_for(q, overrides)
        if q["type"] in ("short", "long"):
            page.locator(f"[name='{q['id']}']").fill(v)
        else:
            page.locator(f"[name='{q['id']}'][value='{v}']").check(force=True)


def capture(page, bodies, status=201):
    page.route("**/rest/v1/feedback_responses",
               lambda r: (bodies.append(r.request.post_data), r.fulfill(status=status, body="")))


def watch_supabase(page):
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    return sent


def test_schema_matches_reference_document_structure(page, server):
    survey = load_schema(page, server)
    qs = questions(survey)
    assert [q["id"] for q in qs] == EXPECTED_IDS and survey["version"] == 2
    for q in qs:
        assert q["type"] == TYPES[q["id"]] and q["text"].strip(), q["id"]
    assert [s["title"][:2] for s in survey["sections"]] == ["A.", "B.", "C.", "D.", "E.", "F."]


def test_question_wording_follows_the_reference_document(page, server):
    qm = by_id(load_schema(page, server))
    assert qm["a0"]["text"] == "Saya berusia 18 tahun atau lebih dan bersedia berpartisipasi."
    assert [o["label"] for o in qm["a1"]["options"]] == [
        "Belum pernah", "Pernah membaca atau mengikuti beritanya", "Pernah trading kurang dari 1 tahun", "Pernah trading 1 tahun atau lebih"]
    assert [o["label"] for o in qm["a3"]["options"]] == ["Tidak pernah", "Pernah melihat", "Kadang memakai", "Rutin memakai"]
    assert [o["label"] for o in qm["a4"]["options"]] == ["Ponsel", "Laptop atau komputer", "Tablet"]
    assert qm["b4"]["text"] == "Prediksi NAIK bisa muncul walaupun probabilitasnya di bawah 50%."
    assert qm["c1"]["text"] == "Saya pikir saya akan sering menggunakan situs ini."
    assert qm["c10"]["text"] == "Saya perlu mempelajari banyak hal sebelum dapat menggunakan situs ini."
    assert qm["d8"]["text"].startswith("Penjelasan ini memungkinkan saya menilai kapan saya sebaiknya percaya dan tidak percaya")
    assert qm["e1"]["text"] == "Saya percaya pada probabilitas naik dan turun yang ditampilkan situs ini."
    assert qm["e3"]["text"] == "Situs ini membuat saya tahu batas keandalan prediksinya."
    assert qm["f4"]["text"] == "Dengan kata-kata Anda sendiri, seberapa layak prediksi situs ini dijadikan dasar keputusan?"


def test_answer_key_is_not_shipped_to_the_browser(page, server):
    qs = questions(load_schema(page, server))
    for q in qs:
        assert not ({"answer", "key", "correct", "benar"} & set(q)), q["id"]       # kunci hanya ada di skrip ringkasan


def test_form_renders_every_question_with_correct_controls(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        if q["type"] in ("short",):
            assert page.locator(f"input[type=text][name={q['id']}]").count() == 1, q["id"]
        elif q["type"] == "long":
            assert page.locator(f"textarea[name={q['id']}]").count() == 1, q["id"]
        else:
            want = RADIOS[q["type"]] or len(q["options"])
            assert page.locator(f"input[type=radio][name={q['id']}]").count() == want, q["id"]


def test_every_question_is_marked_required_for_assistive_tech(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        assert page.locator(f"[name='{q['id']}']").first.get_attribute("aria-required") == "true", q["id"]


def test_only_consent_is_visible_until_the_visitor_agrees(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        assert page.locator(f"[data-qid='{q['id']}']").is_visible() == (q["id"] == "a0"), q["id"]
    page.locator("[name='a0'][value='ya']").check(force=True)
    assert page.locator("[data-qid='nama']").is_visible() and page.locator("[data-qid='c1']").is_visible()
    assert page.locator("[data-qid='d1']").is_hidden()                                   # bagian D menunggu penyaring


def test_declining_consent_ends_without_sending_anything(page, context, server):
    configured(context)
    sent = watch_supabase(page)
    load_schema(page, server)
    page.locator("[name='a0'][value='tidak']").check(force=True)
    assert page.locator("[data-qid='nama']").is_hidden()
    page.click("#survey-submit")
    page.wait_for_selector("#survey-declined", state="visible")
    assert "tidak ada jawaban yang dikirim" in page.inner_text("#survey-declined").lower()
    assert sent == [] and page.evaluate("localStorage.getItem('kuesioner-done-v2')") is None


def test_explanation_section_appears_only_for_those_who_saw_the_explainer(page, context, server):
    configured(context)
    survey = load_schema(page, server)
    page.locator("[name='a0'][value='ya']").check(force=True)
    page.locator("[name='d0'][value='tidak']").check(force=True)
    assert all(page.locator(f"[data-qid='d{i}']").is_hidden() for i in range(1, 9))
    page.locator("[name='d0'][value='ya']").check(force=True)
    assert all(page.locator(f"[data-qid='d{i}']").is_visible() for i in range(1, 9))
    assert by_id(survey)["d1"]["showIf"] == {"id": "d0", "equals": "ya"}


def test_submit_blocks_and_counts_unanswered_questions_then_focuses_first(page, context, server):
    configured(context)
    sent = watch_supabase(page)
    survey = load_schema(page, server)
    page.locator("[name='a0'][value='ya']").check(force=True)
    page.click("#survey-submit")
    shown = [q for q in questions(survey) if not q.get("showIf") and q["id"] != "a0"]
    assert f"{len(shown)} pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.locator("[aria-invalid=true]").count() >= 1 and sent == []
    assert page.evaluate("document.activeElement.name") == "nama"


def test_whitespace_only_text_counts_as_unanswered(page, context, server):
    configured(context)
    sent = watch_supabase(page)
    survey = load_schema(page, server)
    fill_all(page, survey)
    page.locator("[name='f4']").fill("   \n  ")
    page.click("#survey-submit")
    assert "1 pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.evaluate("document.activeElement.name") == "f4" and sent == []


def test_missing_name_alone_blocks_submit(page, context, server):
    configured(context)
    sent = watch_supabase(page)
    survey = load_schema(page, server)
    fill_all(page, survey, skip=("nama",))
    page.click("#survey-submit")
    assert "1 pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.locator("[name='nama']").get_attribute("aria-invalid") == "true" and sent == []


def test_submit_posts_every_answer_as_text_and_blocks_second_submit(page, context, server):
    configured(context)
    errs = collect_errors(page)
    reqs = []

    def handle(route):
        reqs.append((route.request.method, route.request.url, route.request.headers, route.request.post_data))
        route.fulfill(status=201, body="")
    page.route("**/rest/v1/feedback_responses", handle)
    survey = load_schema(page, server)
    fill_all(page, survey, nama="  Budi Santoso  ", b1="salah", b2="tidak_tahu", c3="2", a2="5")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert len(reqs) == 1
    method, url, headers, body = reqs[0]
    assert method == "POST" and url == "https://proj.supabase.co/rest/v1/feedback_responses"
    assert headers["apikey"] == "anon-test-key" and headers["authorization"] == "Bearer anon-test-key"
    assert headers["prefer"] == "return=minimal"
    data = json.loads(body)
    assert data["survey_version"] == 2 and re.fullmatch(r"[0-9a-f-]{36}", data["client_id"])
    ans = data["answers"]
    assert set(ans) == set(EXPECTED_IDS)                                              # D terisi karena d0 = ya
    assert ans["a0"] == "ya" and ans["nama"] == "Budi Santoso" and ans["a2"] == "5" and ans["c3"] == "2"
    assert ans["b1"] == "salah" and ans["b2"] == "tidak_tahu" and ans["b3"] == "benar" and ans["a1"] == "belum"
    assert all(isinstance(v, str) for v in ans.values())
    page.reload()
    assert page.is_visible("#survey-thanks") and page.locator("#survey-submit").count() == 0
    assert not errs, errs


def test_explanation_answers_are_not_sent_when_the_visitor_did_not_see_it(page, context, server):
    configured(context)
    bodies = []
    capture(page, bodies)
    survey = load_schema(page, server)
    fill_all(page, survey, d0="tidak")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    ans = json.loads(bodies[0])["answers"]
    assert ans["d0"] == "tidak" and not any(k in ans for k in (f"d{i}" for i in range(1, 9)))


def test_hidden_explanation_answers_are_dropped_when_the_filter_is_switched_off(page, context, server):
    configured(context)
    bodies = []
    capture(page, bodies)
    survey = load_schema(page, server)
    fill_all(page, survey)                                                            # d0 = ya, D terisi
    page.locator("[name='d0'][value='tidak']").check(force=True)
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert "d3" not in json.loads(bodies[0])["answers"]


def test_honeypot_filled_looks_successful_but_sends_nothing(page, context, server):
    configured(context)
    sent = watch_supabase(page)
    survey = load_schema(page, server)
    fill_all(page, survey)
    page.evaluate("document.querySelector('input[name=website]').value = 'http://spam.example'")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert sent == []


def test_server_error_keeps_answers_and_allows_retry_but_409_counts_as_done(page, context, server):
    configured(context)
    status = {"code": 500}
    page.route("**/rest/v1/feedback_responses", lambda r: r.fulfill(status=status["code"], body="{}"))
    survey = load_schema(page, server)
    fill_all(page, survey)
    page.locator("[name='f1']").fill("jawaban saya")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-error", state="visible")
    assert "gagal" in page.inner_text("#survey-error").lower()
    assert page.locator("[name='f1']").input_value() == "jawaban saya" and page.is_enabled("#survey-submit")
    status["code"] = 409
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")


def test_old_survey_identity_does_not_block_the_new_version(page, context, server):
    """Peramban yang sudah mengisi versi 1 (client_id dan tanda selesai lama) harus tetap bisa mengirim versi 2."""
    configured(context)
    context.add_init_script("localStorage.setItem('kuesioner-done-v1','1'); localStorage.setItem('kuesioner-client-id','old-id');")
    bodies = []
    capture(page, bodies)
    survey = load_schema(page, server)
    assert page.locator("#survey input[type=radio]").count() > 0
    fill_all(page, survey)
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert json.loads(bodies[0])["client_id"] != "old-id"


def test_text_inputs_are_length_limited(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        if q["type"] in ("short", "long"):
            assert int(page.locator(f"[name='{q['id']}']").get_attribute("maxlength")) == (200 if q["type"] == "short" else 2000)


def test_unconfigured_site_explains_and_never_sends(page, context, server):
    context.add_init_script("window.__APP_CONFIG__ = { supabaseUrl: '', supabaseAnonKey: '' };")
    sent = watch_supabase(page)
    page.goto(server + "/kuesioner")
    assert "belum dikonfigurasi" in page.inner_text("#survey-status").lower()
    assert page.is_disabled("#survey-submit") and sent == []


def test_page_says_all_questions_are_required_and_how_long_it_takes(page, server):
    page.goto(server + "/kuesioner")
    page.wait_for_selector("#survey")
    text = page.inner_text("main").lower()
    assert "opsional" not in text and "wajib" in text and "menit" in text
