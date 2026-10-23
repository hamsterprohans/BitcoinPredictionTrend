from app import config
from scripts.summarize_feedback import ANSWER_KEY, load_questions

SQL = (config.WEBAPP / "supabase" / "schema.sql").read_text()


def test_database_requires_consent_and_name_for_new_rows_but_keeps_old_rows():
    low = " ".join(SQL.lower().split())
    for name in ("feedback_name_required", "feedback_consent_required"):
        assert f"drop constraint if exists {name}" in low                          # aman dijalankan berulang
        assert f"add constraint {name}" in low
    assert "length(btrim(coalesce(answers->>'nama', ''))) > 0" in low             # nama tidak boleh kosong/spasi saja
    assert "answers->>'a0' = 'ya'" in low                                         # tanpa persetujuan, baris ditolak
    assert "length(btrim(coalesce(answers->>'a0', ''))) > 0" not in low           # syarat nama versi lama (a0 = nama) sudah diganti
    assert low.count("not valid") >= 3                                            # hanya baris baru; baris versi 1 tidak diperiksa ulang


def test_flat_view_has_one_column_per_question_plus_scores_and_stays_private():
    low = " ".join(SQL.lower().split())
    assert "drop view if exists public.feedback_flat" in low                      # kolom lama dibuang: create or replace saja tidak cukup
    view = low[low.index("create view public.feedback_flat"):low.index("revoke all on public.feedback_flat")]
    for q in load_questions():
        assert f"a->>'{q['id']}' as {q['id']}" in view, q["id"]                   # satu kolom per soal, bisa dibaca satu per satu
    assert "as skor_sus" in view and "as skor_pemahaman" in view
    assert "survey_version = 2" in view                                           # jawaban versi 1 punya arti kolom berbeda: tidak dicampur
    assert "~ '^[1-5]$'" in view                                                  # nilai bukan angka dari kunci publik tidak boleh merusak view
    assert "revoke all on public.feedback_flat from anon, authenticated" in low


def test_view_understanding_score_uses_the_same_answer_key_as_the_summary_script():
    low = " ".join(SQL.lower().split())
    for qid, ans in ANSWER_KEY.items():
        assert f"(a->>'{qid}' = '{ans}')::int" in low, qid


def test_anon_still_only_inserts():
    low = " ".join(SQL.lower().split())
    assert "grant insert on public.feedback_responses to anon" in low
    assert "grant select" not in low and "grant update" not in low and "grant delete" not in low


# ---- penguatan terhadap penyalahgunaan kunci publik: bentuk data dibatasi dan laju kiriman dibatasi ----
import re   # noqa: E402



def test_answers_may_only_contain_known_question_ids_with_short_string_values():
    low = " ".join(SQL.lower().split())
    assert "create or replace function public.feedback_answers_ok(a jsonb)" in low
    assert "jsonb_typeof(e.value) <> 'string'" in low and "length(e.value #>> '{}') > 2000" in low
    assert re.search(r"add constraint feedback_answers_shape check \(public\.feedback_answers_ok\(answers\)\) not valid", low)
    listed = set(re.findall(r"'(\w+)'", SQL[SQL.lower().index("array["):SQL.index("]", SQL.lower().index("array["))]))
    assert listed == {q["id"] for q in load_questions()}                      # daftar kunci SQL = soal di frontend (tak boleh melenceng)


def test_insert_rate_is_capped_by_a_trigger_that_does_not_need_read_access_for_anon():
    low = " ".join(SQL.lower().split())
    assert "create or replace function public.feedback_rate_limit()" in low
    assert "security definer" in low and "set search_path = public" in low    # menghitung baris tanpa memberi anon izin SELECT
    assert "interval '10 minutes'" in low and "> 120" in low
    assert "before insert on public.feedback_responses" in low
    assert "revoke all on function public.feedback_rate_limit() from public" in low   # fungsi tidak dapat dipanggil langsung oleh siapa pun
