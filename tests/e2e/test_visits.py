import json

import pytest

pytestmark = pytest.mark.e2e

CONFIG = {"supabaseUrl": "https://proj.supabase.co", "supabaseAnonKey": "anon-test-key"}
PATHS = ["/", "/latar-belakang", "/retrospektif", "/riset", "/metodologi", "/kuesioner", "/tentang"]
STATS = {"total": 1234, "today": 12, "week": 80, "pages": [{"path": "/", "n": 900}, {"path": "/riset", "n": 100}],
         "days": [{"d": f"2026-10-{i:02d}", "n": i * 3} for i in range(1, 31)]}


def configured(context):
    context.add_init_script(f"window.__APP_CONFIG__ = {json.dumps(CONFIG)};")


def track(page, status=201):
    bodies = []
    page.route("**/rest/v1/site_visits", lambda r: (bodies.append((r.request.headers, r.request.post_data)), r.fulfill(status=status, body="")))
    return bodies


def rpc(page, status=200, payload=None):
    calls = []
    page.route("**/rest/v1/rpc/visit_stats",
               lambda r: (calls.append((r.request.url, r.request.post_data)), r.fulfill(status=status, body=json.dumps(payload or STATS), content_type="application/json")))
    return calls


def tap(page, n):
    for _ in range(n):
        page.locator(".footer p").first.click()


def test_visit_is_recorded_once_per_session_with_only_the_page_path(page, context, server):
    configured(context)
    bodies = track(page)
    page.goto(server + "/riset")
    page.wait_for_timeout(300)
    assert len(bodies) == 1
    headers, body = bodies[0]
    assert json.loads(body) == {"path": "/riset"}                                   # tanpa IP, agen pengguna, atau identitas
    assert headers["apikey"] == "anon-test-key"
    page.reload()
    page.goto(server + "/tentang")
    page.wait_for_timeout(300)
    assert len(bodies) == 1                                                         # satu kunjungan per sesi peramban, bukan per muat ulang


@pytest.mark.parametrize("path", PATHS)
def test_every_page_records_its_visit(page, context, server, path):
    configured(context)
    bodies = track(page)
    page.goto(server + path)
    page.wait_for_timeout(300)
    assert [json.loads(b)["path"] for _, b in bodies] == [path]


def test_nothing_is_sent_when_supabase_is_not_configured(page, context, server):
    context.add_init_script("window.__APP_CONFIG__ = { supabaseUrl: '', supabaseAnonKey: '' };")
    sent = []
    page.on("request", lambda r: sent.append(r.url) if "supabase" in r.url else None)
    page.goto(server + "/")
    page.wait_for_timeout(300)
    assert sent == []


def test_a_failing_counter_never_breaks_the_page(page, context, server):
    configured(context)
    track(page, status=500)
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(server + "/")
    page.wait_for_timeout(300)
    assert page.is_visible("main") and not errs


def test_owner_browser_is_not_counted(page, context, server):
    configured(context)
    context.add_init_script("localStorage.setItem('owner-visit', '1');")
    bodies = track(page)
    page.goto(server + "/")
    page.wait_for_timeout(300)
    assert bodies == []


def test_nothing_visible_to_ordinary_visitors(page, context, server):
    configured(context)
    track(page)
    page.goto(server + "/")
    assert page.locator("[data-owner-panel]").count() == 0
    assert "kunjungan" not in page.inner_text("body").lower()
    tap(page, 4)
    assert page.locator("[data-owner-panel]").count() == 0                          # kurang dari 5 ketukan: tidak terjadi apa pun


def test_five_taps_on_footer_text_ask_for_the_passphrase_and_wrong_key_is_refused(page, context, server):
    configured(context)
    track(page)
    calls = rpc(page, status=401, payload={"message": "ditolak"})
    page.goto(server + "/")
    tap(page, 5)
    panel = page.locator("[data-owner-panel]")
    assert panel.is_visible() and panel.get_attribute("role") == "dialog"
    page.fill("[data-owner-panel] input[type=password]", "kunci-salah")
    page.click("[data-owner-panel] button[type=submit]")
    page.wait_for_selector("[data-owner-panel] [role=alert]:not([hidden])")
    assert len(calls) == 1 and "kunci-salah" not in calls[0][0]                      # kunci tidak pernah ada di URL
    assert json.loads(calls[0][1]) == {"p_key": "kunci-salah"}
    assert page.locator("[data-owner-panel] svg").count() == 0 and "1234" not in page.inner_text("body")
    assert page.evaluate("sessionStorage.getItem('owner-visit-key')") is None and page.evaluate("localStorage.getItem('owner-visit')") is None


def test_correct_key_shows_numbers_and_faint_chart_and_stops_counting_this_browser(page, context, server):
    configured(context)
    bodies = track(page)
    rpc(page)
    page.goto(server + "/")
    page.wait_for_timeout(300)
    assert len(bodies) == 1
    tap(page, 5)
    page.fill("[data-owner-panel] input[type=password]", "kunci-benar")
    page.click("[data-owner-panel] button[type=submit]")
    page.wait_for_selector("[data-owner-panel] svg")
    text = page.inner_text("[data-owner-panel]")
    assert "1.234" in text and "12" in text and "80" in text and "/riset" in text
    svg = page.locator("[data-owner-panel] svg")
    assert svg.get_attribute("role") == "img" and svg.locator("rect").count() == 30
    assert float(page.evaluate("getComputedStyle(document.querySelector('[data-owner-panel]')).opacity")) < 1   # samar-samar
    assert page.evaluate("localStorage.getItem('owner-visit')") == "1"
    page.evaluate("sessionStorage.clear()")
    page.goto(server + "/tentang")
    page.wait_for_timeout(300)
    assert len(bodies) == 1                                                         # kunjungan pemilik sendiri tidak ikut dihitung


def test_escape_closes_and_logout_forgets_the_key(page, context, server):
    configured(context)
    track(page)
    rpc(page)
    page.goto(server + "/")
    tap(page, 5)
    page.fill("[data-owner-panel] input[type=password]", "kunci-benar")
    page.click("[data-owner-panel] button[type=submit]")
    page.wait_for_selector("[data-owner-panel] svg")
    page.keyboard.press("Escape")
    assert page.locator("[data-owner-panel]").count() == 0
    tap(page, 5)                                                                    # kunci masih diingat di sesi ini: langsung tampil
    page.wait_for_selector("[data-owner-panel] svg")
    page.click("[data-owner-panel] button[data-logout]")
    assert page.locator("[data-owner-panel]").count() == 0 and page.evaluate("sessionStorage.getItem('owner-visit-key')") is None
