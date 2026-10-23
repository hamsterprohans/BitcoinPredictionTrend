import csv
import json

import pytest

from scripts.summarize_feedback import (ANSWER_KEY, load_questions, main, render_html, segment_summary, summarize,
                                        sus_score, understanding_score)


def write_csv(path, rows, version=2, versions=None):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "created_at", "survey_version", "answers"])
        w.writeheader()
        for i, a in enumerate(rows, 1):
            w.writerow({"id": i, "created_at": f"2026-10-{15 + i}T01:00:00Z",
                        "survey_version": (versions or {}).get(i, version), "answers": json.dumps(a)})


def sus(values):
    return {f"c{i}": str(v) for i, v in enumerate(values, 1)}


BEST = sus([5, 1, 5, 1, 5, 1, 5, 1, 5, 1])
WORST = sus([1, 5, 1, 5, 1, 5, 1, 5, 1, 5])
NEUTRAL = sus([3] * 10)


def test_questions_parsed_from_the_real_frontend_schema():
    by_id = {q["id"]: q for q in load_questions()}
    assert len(by_id) == 39 and by_id["a0"]["type"] == "yn" and by_id["b3"]["type"] == "tf"
    assert by_id["c5"]["type"] == "scale" and by_id["f4"]["type"] == "long" and by_id["nama"]["type"] == "short"
    assert by_id["a1"]["options"][3] == {"value": "trading_lama", "label": "Pernah trading 1 tahun atau lebih"}
    assert by_id["c1"]["text"] == "Saya pikir saya akan sering menggunakan situs ini."
    assert by_id["b1"]["section"].startswith("B.") and by_id["d3"]["section"].startswith("D.")


def test_answer_key_matches_the_reference_document():
    assert ANSWER_KEY == {"b1": "salah", "b2": "salah", "b3": "salah", "b4": "benar", "b5": "salah", "b6": "salah"}


def test_sus_score_follows_brooke_scoring():
    assert sus_score(BEST) == 100.0 and sus_score(WORST) == 0.0 and sus_score(NEUTRAL) == 50.0
    assert sus_score(sus([4, 2, 4, 2, 4, 2, 4, 2, 4, 2])) == 75.0
    assert sus_score({**BEST, "c7": None}) is None and sus_score({k: v for k, v in BEST.items() if k != "c3"}) is None
    assert sus_score({**BEST, "c2": "9"}) is None                                   # di luar 1-5: tidak dihitung


def test_understanding_score_counts_correct_answers_and_treats_dont_know_as_wrong():
    perfect = {"b1": "salah", "b2": "salah", "b3": "salah", "b4": "benar", "b5": "salah", "b6": "salah"}
    assert understanding_score(perfect) == 6
    assert understanding_score({**perfect, "b4": "salah", "b1": "tidak_tahu"}) == 4
    assert understanding_score({k: v for k, v in perfect.items() if k != "b2"}) is None


def test_summary_has_sus_understanding_ess_and_per_item_stats():
    rows = [{**BEST, "b1": "salah", "b4": "benar", "b3": "tidak_tahu", "d0": "ya", "d1": "5", "d2": "3", "e1": "4"},
            {**WORST, "b1": "benar", "d0": "tidak", "e1": "2", "a2": "3"},
            {**NEUTRAL}]
    s = summarize(rows)
    assert s["n_responses"] == 3
    assert s["sus"]["n"] == 3 and s["sus"]["mean"] == 50.0 and s["sus"]["median"] == 50.0
    b1 = s["questions"]["b1"]
    assert b1["counts"] == {"benar": 1, "salah": 1, "tidak_tahu": 0} and b1["n"] == 2 and b1["pct_correct"] == 50.0
    assert s["questions"]["b3"]["counts"]["tidak_tahu"] == 1 and s["questions"]["b3"]["pct_correct"] == 0.0
    c1 = s["questions"]["c1"]
    assert c1["counts"] == {"1": 1, "2": 0, "3": 1, "4": 0, "5": 1} and c1["mean"] == 3.0
    assert s["ess"]["n"] == 1 and s["ess"]["mean"] == 4.0 and s["questions"]["d1"]["n"] == 1   # hanya yang membuka penjelasan
    assert s["trust"]["mean"] == 3.0 and s["questions"]["a2"]["mean"] == 3.0


def test_unknown_values_and_keys_are_ignored_not_crashing():
    s = summarize([{"c1": "tujuh", "b1": "mungkin", "zzz": "ya", "a1": "belum"}])
    assert s["questions"]["c1"]["n"] == 0 and s["questions"]["b1"]["n"] == 0
    assert s["questions"]["a1"]["counts"]["belum"] == 1 and s["sus"]["n"] == 0 and s["sus"]["mean"] is None


def test_text_answers_collected_but_never_the_name():
    s = summarize([{"nama": "Budi", "f1": "Grafiknya", "f2": "  "}])
    assert s["questions"]["f1"]["texts"] == ["Grafiknya"] and s["questions"]["f2"]["texts"] == []
    assert "nama" not in s["questions"]


def test_cli_writes_markdown_with_sus_warning_for_small_samples_and_no_name(tmp_path):
    src, out = tmp_path / "hasil.csv", tmp_path / "ringkasan.md"
    write_csv(src, [{"nama": "Budi Santoso", "a0": "ya", **BEST, "f1": "Sangat membantu", "b1": "salah"}, {"a0": "ya", **WORST}])
    main([str(src), "--out", str(out)])
    md = out.read_text()
    assert "Jumlah responden: 2" in md and "2026-10-16" in md and "2026-10-17" in md
    assert "belum dapat digeneralisasi" in md
    assert "Skor SUS" in md and "50.0" in md and "Sangat membantu" in md and "Pemahaman" in md
    assert "Budi" not in md


def test_cli_ignores_rows_from_other_survey_versions(tmp_path):
    src, out = tmp_path / "h.csv", tmp_path / "r.md"
    write_csv(src, [{"a0": "ya", **BEST}, {"a0": "Nama Lama", "b2": "ya"}, {"a0": "ya", **WORST}], versions={2: 1})
    main([str(src), "--out", str(out)])
    md = out.read_text()
    assert "Jumlah responden: 2" in md and "Nama Lama" not in md


def test_cli_rejects_csv_without_answers_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,nama\n1,x\n")
    with pytest.raises(SystemExit) as e:
        main([str(bad)])
    assert "answers" in str(e.value)


def test_empty_csv_gives_clear_message(tmp_path):
    src = tmp_path / "kosong.csv"
    write_csv(src, [])
    with pytest.raises(SystemExit) as e:
        main([str(src)])
    assert "belum ada responden" in str(e.value).lower()


SEG_ROWS = [{"a1": "trading_baru", **BEST}, {"a1": "trading_lama", **BEST}, {"a1": "belum", **WORST},
            {"a1": "berita", **NEUTRAL}, {"a1": "belum", **NEUTRAL}, {**NEUTRAL}]


def test_segment_compares_sus_between_traders_and_non_traders():
    seg = segment_summary(SEG_ROWS)
    assert seg["groups"] == {"trading": 2, "belum": 3}                              # baris tanpa a1 diabaikan
    assert seg["metrics"]["SUS"]["trading"] == {"n": 2, "mean": 100.0}
    assert seg["metrics"]["SUS"]["belum"] == {"n": 3, "mean": pytest.approx(33.3, abs=0.05)}


def test_markdown_includes_group_comparison_with_small_n_flag(tmp_path):
    src, out = tmp_path / "h.csv", tmp_path / "r.md"
    write_csv(src, SEG_ROWS)
    main([str(src), "--out", str(out)])
    md = out.read_text()
    assert "Perbandingan menurut pengalaman trading" in md and "100.0 (n=2, n kecil)" in md


def test_html_report_has_svg_bars_escapes_text_and_hides_name(tmp_path):
    rows = [{"nama": "Budi", "f1": "<script>alert(1)</script>", "b1": "salah"}, {"b1": "salah"}, {"b1": "benar"}, {"b1": "tidak_tahu"}]
    html = render_html(summarize(rows), ["2026-10-16T00:00:00Z"], rows)
    assert html.startswith("<!doctype html>") and "<svg" in html and 'role="img"' in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html and "Budi" not in html
    assert 'width="50.0%"' in html                                                  # b1: salah 2 dari 4


def test_cli_writes_html_when_requested(tmp_path):
    src, out, html = tmp_path / "h.csv", tmp_path / "r.md", tmp_path / "r.html"
    write_csv(src, SEG_ROWS)
    main([str(src), "--out", str(out), "--html", str(html)])
    text = html.read_text()
    assert "Perbandingan antar kelompok" in text and "Skor SUS" in text and html.stat().st_size > 1000
