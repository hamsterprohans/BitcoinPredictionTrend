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
