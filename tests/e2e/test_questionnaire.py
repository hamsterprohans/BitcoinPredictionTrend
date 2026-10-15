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


def fill_required(page, survey, choice="ya"):
    for sec in survey["sections"]:
        for q in sec["questions"]:
            if q["type"] in ("yn", "ynn") and q.get("required", True) and not q.get("showIf"):
                value = choice if (choice != "netral" or q["type"] == "ynn") else "ya"     # soal Ya/Tidak tak punya Netral
                page.locator(f"[name='{q['id']}'][value='{value}']").check(force=True)


def test_schema_has_all_four_question_types_and_unique_ids(page, server):
    survey = load_schema(page, server)
    qs = [q for s in survey["sections"] for q in s["questions"]]
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
    for sec in survey["sections"]:
        for q in sec["questions"]:
            sel = {"yn": f"input[type=radio][name={q['id']}]", "ynn": f"input[type=radio][name={q['id']}]",
                   "short": f"input[type=text][name={q['id']}]", "long": f"textarea[name={q['id']}]"}[q["type"]]
            n = {"yn": 2, "ynn": 3, "short": 1, "long": 1}[q["type"]]
            assert page.locator(sel).count() == n, q["id"]


def test_unconfigured_site_explains_and_never_sends(page, context, server):
    context.add_init_script("window.__APP_CONFIG__ = { supabaseUrl: '', supabaseAnonKey: '' };")
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    page.goto(server + "/kuesioner")
    assert "belum dikonfigurasi" in page.inner_text("#survey-status").lower()
    assert page.is_disabled("#survey-submit")
    assert sent == []


def test_submit_blocks_when_required_missing_and_focuses_first(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    page.goto(server + "/kuesioner")
    page.click("#survey-submit")
    assert page.is_visible("#survey-error") and "belum dijawab" in page.inner_text("#survey-error")
    assert page.locator("[aria-invalid=true]").count() >= 1
    assert sent == []


def test_submit_posts_to_supabase_rest_and_blocks_second_submit(page, context, server):
    configured(context)
    errs = collect_errors(page)
    reqs = []

    def handle(route):
        reqs.append((route.request.method, route.request.url, route.request.headers, route.request.post_data))
        route.fulfill(status=201, body="")
    page.route("**/rest/v1/feedback_responses", handle)
    survey = load_schema(page, server)
    fill_required(page, survey, "netral")
    page.locator("[name='g3']").fill("Sangat membantu, tambahkan ETH.")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert len(reqs) == 1
    method, url, headers, body = reqs[0]
    assert method == "POST" and url == "https://proj.supabase.co/rest/v1/feedback_responses"
    assert headers["apikey"] == "anon-test-key" and headers["authorization"] == "Bearer anon-test-key"
    assert headers["prefer"] == "return=minimal"
    data = json.loads(body)
    assert data["survey_version"] == 1 and re.fullmatch(r"[0-9a-f-]{36}", data["client_id"])
    for s in survey["sections"]:
        for q in s["questions"]:
            if q["type"] in ("yn", "ynn") and not q.get("showIf"):
                assert data["answers"][q["id"]] == ("netral" if q["type"] == "ynn" else "ya"), q["id"]
    assert data["answers"]["g3"] == "Sangat membantu, tambahkan ETH."
    assert "a1" not in data["answers"]                                    # soal teks kosong tidak dikirim
    page.reload()
    assert page.is_visible("#survey-thanks") and page.locator("#survey-submit").count() == 0   # tak bisa kirim dua kali
    assert not errs, errs


def test_conditional_question_hidden_until_triggered_and_not_sent_when_hidden(page, context, server):
    configured(context)
    bodies = []
    page.route("**/rest/v1/feedback_responses", lambda r: (bodies.append(r.request.post_data), r.fulfill(status=201, body="")))
    survey = load_schema(page, server)
    cond = [q for s in survey["sections"] for q in s["questions"] if q.get("showIf")]
    assert cond
    for q in cond:
        trig = q["showIf"]
        assert page.locator(f"[data-qid='{q['id']}']").is_hidden()
        page.locator(f"[name='{trig['id']}'][value='{trig['equals']}']").check(force=True)
        assert page.locator(f"[data-qid='{q['id']}']").is_visible()
        page.locator(f"[name='{q['id']}']").first.fill("x") if q["type"] in ("short", "long") else None
        other = "tidak" if trig["equals"] == "ya" else "ya"
        page.locator(f"[name='{trig['id']}'][value='{other}']").check(force=True)
        assert page.locator(f"[data-qid='{q['id']}']").is_hidden()
    fill_required(page, survey)
    for q in cond:
        page.locator(f"[name='{q['showIf']['id']}'][value='{'tidak' if q['showIf']['equals']=='ya' else 'ya'}']").check(force=True)
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    answers = json.loads(bodies[0])["answers"]
    assert all(q["id"] not in answers for q in cond)


def test_honeypot_filled_looks_successful_but_sends_nothing(page, context, server):
    configured(context)
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    survey = load_schema(page, server)
    fill_required(page, survey)
    page.evaluate("document.querySelector('input[name=website]').value = 'http://spam.example'")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert sent == []


def test_server_error_keeps_answers_and_allows_retry_but_409_counts_as_done(page, context, server):
    configured(context)
    status = {"code": 500}
    page.route("**/rest/v1/feedback_responses", lambda r: r.fulfill(status=status["code"], body="{}"))
    survey = load_schema(page, server)
    fill_required(page, survey)
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
    for s in survey["sections"]:
        for q in s["questions"]:
            if q["type"] in ("short", "long"):
                limit = int(page.locator(f"[name='{q['id']}']").get_attribute("maxlength"))
                assert limit == (200 if q["type"] == "short" else 2000)


def test_name_field_is_first_optional_and_sent_trimmed(page, context, server):
    configured(context)
    bodies = []
    page.route("**/rest/v1/feedback_responses", lambda r: (bodies.append(r.request.post_data), r.fulfill(status=201, body="")))
    survey = load_schema(page, server)
    first = survey["sections"][0]["questions"][0]
    assert first["id"] == "a0" and first["type"] == "short" and "nama" in first["text"].lower()
    assert page.locator("[name='a0']").get_attribute("autocomplete") == "name"
    assert "tanpa nama" not in page.inner_text("#survey-root").lower()            # teks lama sudah tidak benar
    fill_required(page, survey)
    page.click("#survey-submit")                                                  # nama kosong: tetap boleh dikirim
    page.wait_for_selector("#survey-thanks", state="visible")
    assert "a0" not in json.loads(bodies[0])["answers"]


def test_name_is_sent_when_filled(page, context, server):
    configured(context)
    bodies = []
    page.route("**/rest/v1/feedback_responses", lambda r: (bodies.append(r.request.post_data), r.fulfill(status=201, body="")))
    survey = load_schema(page, server)
    fill_required(page, survey)
    page.locator("[name='a0']").fill("  Budi Santoso  ")
    page.click("#survey-submit")
    page.wait_for_selector("#survey-thanks", state="visible")
    assert json.loads(bodies[0])["answers"]["a0"] == "Budi Santoso"
