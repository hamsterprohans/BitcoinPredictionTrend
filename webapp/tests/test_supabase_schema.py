from app import config

SQL = (config.WEBAPP / "supabase" / "schema.sql").read_text()


def test_database_rejects_rows_without_a_name_but_keeps_old_rows():
    low = " ".join(SQL.lower().split())
    assert "drop constraint if exists feedback_name_required" in low                # aman dijalankan berulang
    assert "add constraint feedback_name_required" in low
    assert "length(btrim(coalesce(answers->>'a0', ''))) > 0" in low                 # nama tidak boleh kosong/spasi saja
    assert low.index("add constraint feedback_name_required") < low.index("not valid", low.index("add constraint feedback_name_required"))
    assert "not valid" in low                                                       # hanya baris baru; baris lama (tanpa nama) tidak diperiksa ulang


def test_anon_still_only_inserts():
    low = " ".join(SQL.lower().split())
    assert "grant insert on public.feedback_responses to anon" in low
    assert "grant select" not in low and "grant update" not in low and "grant delete" not in low


# ---- penguatan terhadap penyalahgunaan kunci publik: bentuk data dibatasi dan laju kiriman dibatasi ----
import re   # noqa: E402

from scripts.summarize_feedback import load_questions   # noqa: E402


def test_answers_may_only_contain_known_question_ids_with_short_string_values():
    low = " ".join(SQL.lower().split())
    assert "create or replace function public.feedback_answers_ok(a jsonb)" in low
    assert "jsonb_typeof(e.value) <> 'string'" in low and "length(e.value #>> '{}') > 2000" in low
    assert re.search(r"add constraint feedback_answers_shape check \(public\.feedback_answers_ok\(answers\)\) not valid", low)
    listed = set(re.findall(r"'([a-g]\d)'", SQL[SQL.lower().index("array["):SQL.index("]", SQL.lower().index("array["))]))
    assert listed == {q["id"] for q in load_questions()}                      # daftar kunci SQL = soal di frontend (tak boleh melenceng)


def test_insert_rate_is_capped_by_a_trigger_that_does_not_need_read_access_for_anon():
    low = " ".join(SQL.lower().split())
    assert "create or replace function public.feedback_rate_limit()" in low
    assert "security definer" in low and "set search_path = public" in low    # menghitung baris tanpa memberi anon izin SELECT
    assert "interval '10 minutes'" in low and "> 120" in low
    assert "before insert on public.feedback_responses" in low
    assert "revoke all on function public.feedback_rate_limit() from public" in low   # fungsi tidak dapat dipanggil langsung oleh siapa pun
