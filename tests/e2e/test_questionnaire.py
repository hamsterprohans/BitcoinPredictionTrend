import json
import re

import pytest

from tests.e2e.conftest import collect_errors

pytestmark = pytest.mark.e2e

CONFIG = {"supabaseUrl": "https://proj.supabase.co", "supabaseAnonKey": "anon-test-key"}


def configured(context):
    context.add_init_script(f"window.__APP_CONFIG__ = {json.dumps(CONFIG)};")


def load_schema(page, server):
    page.goto(server + "/kuesioner")
    return page.evaluate("import('/static/js/kuesioner-schema.js').then(m => m.SURVEY)")


def questions(survey):
    return [q for s in survey["sections"] for q in s["questions"]]


def fill_all(page, survey, choice="ya", skip=()):
    """Isi SEMUA soal yang terlihat (pilihan dan teks); soal bersyarat hanya bila sedang tampil."""
    for q in questions(survey):
        if q["id"] in skip or page.locator(f"[data-qid='{q['id']}']").is_hidden():
            continue
        if q["type"] in ("yn", "ynn"):
            value = choice if (choice != "netral" or q["type"] == "ynn") else "ya"     # soal Ya/Tidak tak punya Netral
            page.locator(f"[name='{q['id']}'][value='{value}']").check(force=True)
        else:
            page.locator(f"[name='{q['id']}']").fill(f"jawaban {q['id']}")


def capture(page, bodies, status=201):
    page.route("**/rest/v1/feedback_responses",
               lambda r: (bodies.append(r.request.post_data), r.fulfill(status=status, body="")))


def test_schema_has_all_four_question_types_and_unique_ids(page, server):
    survey = load_schema(page, server)
    qs = questions(survey)
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)) and survey["version"] == 1
    count = lambda t: sum(q["type"] == t for q in qs)                    # noqa: E731
    assert count("yn") >= 6 and count("ynn") >= 12 and count("short") >= 4 and count("long") >= 3
    assert len(survey["sections"]) >= 6 and all(q["text"].strip() for q in qs)
    for q in qs:                                                          # soal bersyarat menunjuk soal lain yang ada
        if q.get("showIf"):
            assert q["showIf"]["id"] in ids and q["showIf"]["id"] != q["id"]


def test_form_renders_every_question_with_correct_controls(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        sel = {"yn": f"input[type=radio][name={q['id']}]", "ynn": f"input[type=radio][name={q['id']}]",
               "short": f"input[type=text][name={q['id']}]", "long": f"textarea[name={q['id']}]"}[q["type"]]
        n = {"yn": 2, "ynn": 3, "short": 1, "long": 1}[q["type"]]
        assert page.locator(sel).count() == n, q["id"]


def test_every_question_is_marked_required_for_assistive_tech(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        sel = f"[name='{q['id']}']"
        assert page.locator(sel).first.get_attribute("aria-required") == "true", q["id"]


def test_no_optional_wording_remains_on_the_questionnaire_page(page, server):
    page.goto(server + "/kuesioner")
    page.wait_for_selector("#survey")
    text = page.inner_text("main").lower()
    assert "opsional" not in text and "boleh dikosongkan" not in text
    assert "wajib" in text                                                # pengunjung diberi tahu semua soal wajib


def test_unconfigured_site_explains_and_never_sends(page, context, server):
    context.add_init_script("window.__APP_CONFIG__ = { supabaseUrl: '', supabaseAnonKey: '' };")
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    page.goto(server + "/kuesioner")
    assert "belum dikonfigurasi" in page.inner_text("#survey-status").lower()
    assert page.is_disabled("#survey-submit")
    assert sent == []


def test_submit_blocks_when_nothing_answered_and_focuses_first(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    survey = load_schema(page, server)
    page.click("#survey-submit")
    assert page.is_visible("#survey-error") and "belum dijawab" in page.inner_text("#survey-error")
    total = sum(1 for q in questions(survey) if not q.get("showIf"))
    assert f"{total} pertanyaan belum dijawab" in page.inner_text("#survey-error")        # termasuk nama dan soal teks
    assert page.locator("[aria-invalid=true]").count() >= 1
    assert page.evaluate("document.activeElement.name") == "a0"                           # nama: soal pertama yang kosong
    assert sent == []


def test_all_choices_answered_but_text_missing_still_blocks(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    survey = load_schema(page, server)
    for q in questions(survey):
        if q["type"] in ("yn", "ynn") and not q.get("showIf"):
            page.locator(f"[name='{q['id']}'][value='tidak']").check(force=True)           # 'Tidak': tidak memicu soal bersyarat
    page.click("#survey-submit")
    n_text = sum(1 for q in questions(survey) if q["type"] in ("short", "long") and not q.get("showIf"))
    assert f"{n_text} pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.locator("textarea[aria-invalid=true]").count() >= 1 and sent == []


def test_whitespace_only_text_counts_as_unanswered(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    survey = load_schema(page, server)
    fill_all(page, survey)
    page.locator("[name='g3']").fill("   \n  ")
    page.click("#survey-submit")
    assert "1 pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.evaluate("document.activeElement.name") == "g3" and sent == []


def test_name_is_first_required_question_without_optional_label(page, server):
    survey = load_schema(page, server)
    first = questions(survey)[0]
    assert first["id"] == "a0" and first["type"] == "short" and first["text"] == "Nama Anda:"
    assert page.locator("[name='a0']").get_attribute("autocomplete") == "name"


def test_missing_name_alone_blocks_submit(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    survey = load_schema(page, server)
    fill_all(page, survey, skip=("a0",))
    page.click("#survey-submit")
    assert "1 pertanyaan belum dijawab" in page.inner_text("#survey-error")
    assert page.locator("[name='a0']").get_attribute("aria-invalid") == "true" and sent == []


def test_submit_posts_every_answer_to_supabase_rest_and_blocks_second_submit(page, context, server):
    configured(context)
    errs = collect_errors(page)
    reqs = []

    def handle(route):
        reqs.append((route.request.method, route.request.url, route.request.headers, route.request.post_data))
        route.fulfill(status=201, body="")
    page.route("**/rest/v1/feedback_responses", handle)
    survey = load_schema(page, server)
    fill_all(page, survey, "netral")
    page.locator("[name='a0']").fill("  Budi Santoso  ")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert len(reqs) == 1
    method, url, headers, body = reqs[0]
    assert method == "POST" and url == "https://proj.supabase.co/rest/v1/feedback_responses"
    assert headers["apikey"] == "anon-test-key" and headers["authorization"] == "Bearer anon-test-key"
    assert headers["prefer"] == "return=minimal"
    data = json.loads(body)
    assert data["survey_version"] == 1 and re.fullmatch(r"[0-9a-f-]{36}", data["client_id"])
    for q in questions(survey):
        trig = q.get("showIf")
        if trig and data["answers"].get(trig["id"]) != trig["equals"]:
            assert q["id"] not in data["answers"]                         # soal bersyarat yang tersembunyi tidak dikirim
        elif q["type"] == "ynn":
            assert data["answers"][q["id"]] == "netral", q["id"]
        elif q["type"] == "yn":
            assert data["answers"][q["id"]] == "ya", q["id"]
        elif q["id"] == "a0":
            assert data["answers"]["a0"] == "Budi Santoso"                # nama dipangkas
        else:
            assert data["answers"][q["id"]] == f"jawaban {q['id']}", q["id"]   # termasuk soal bersyarat yang terpicu ('ya')
    assert "e7" in data["answers"] and "f9" in data["answers"]            # dipicu oleh jawaban 'ya' pada e6 dan f8
    page.reload()
    assert page.is_visible("#survey-thanks") and page.locator("#survey-submit").count() == 0   # tak bisa kirim dua kali
    assert not errs, errs


def test_conditional_questions_appear_become_required_and_vanish(page, context, server):
    configured(context)
    bodies = []
    capture(page, bodies)
    survey = load_schema(page, server)
    cond = [q for q in questions(survey) if q.get("showIf")]
    assert cond
    for q in cond:
        trig = q["showIf"]
        assert page.locator(f"[data-qid='{q['id']}']").is_hidden()
        page.locator(f"[name='{trig['id']}'][value='{trig['equals']}']").check(force=True)
        assert page.locator(f"[data-qid='{q['id']}']").is_visible()
        assert page.locator(f"[name='{q['id']}']").first.get_attribute("aria-required") == "true"
    fill_all(page, survey)                                                # semua tampil (pemicu 'ya') dan terisi
    page.locator("[name='e7']").fill("")                                  # satu soal bersyarat dikosongkan
    page.click("#survey-submit")
    assert "1 pertanyaan belum dijawab" in page.inner_text("#survey-error") and bodies == []   # soal bersyarat yang tampil juga wajib
    for q in cond:                                                        # matikan semua pemicu: soal bersyarat hilang dan tidak wajib
        trig = q["showIf"]
        page.locator(f"[name='{trig['id']}'][value='tidak']").check(force=True)
        assert page.locator(f"[data-qid='{q['id']}']").is_hidden()
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    answers = json.loads(bodies[0])["answers"]
    assert all(q["id"] not in answers for q in cond)


def test_honeypot_filled_looks_successful_but_sends_nothing(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
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
    page.locator("[name='g3']").fill("jawaban saya")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-error", state="visible")
    assert "gagal" in page.inner_text("#survey-error").lower()
    assert page.locator("[name='g3']").input_value() == "jawaban saya" and page.is_enabled("#survey-submit")
    status["code"] = 409                                                   # client_id sudah ada: sudah terkirim sebelumnya
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")


def test_text_inputs_are_length_limited(page, server):
    survey = load_schema(page, server)
    for q in questions(survey):
        if q["type"] in ("short", "long"):
            limit = int(page.locator(f"[name='{q['id']}']").get_attribute("maxlength"))
            assert limit == (200 if q["type"] == "short" else 2000)
