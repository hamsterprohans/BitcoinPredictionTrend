import csv
import json

import pytest

from scripts.summarize_feedback import load_questions, summarize, main


def write_csv(path, rows, extra=None):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "created_at", "answers"] + (extra or []))
        w.writeheader()
        for i, a in enumerate(rows, 1):
            w.writerow({"id": i, "created_at": f"2026-10-{15 + i}T01:00:00Z", "answers": json.dumps(a)})


def test_questions_parsed_from_the_real_frontend_schema():
    qs = load_questions()
    by_id = {q["id"]: q for q in qs}
    assert by_id["b2"]["type"] == "ynn" and by_id["a2"]["type"] == "yn" and by_id["g3"]["type"] == "long"
    assert by_id["d2"]["text"].startswith("Apakah pernyataan \"bukan saran investasi\"")        # escape JS terbaca benar
    assert by_id["b2"]["section"].startswith("B.") and len(qs) >= 40


def test_counts_and_percent_use_answered_as_denominator():
    rows = [{"b2": "ya"}, {"b2": "ya"}, {"b2": "netral"}, {"b2": "tidak"}, {"a2": "ya"}]
    s = summarize(rows)
    b2 = s["questions"]["b2"]
    assert b2["counts"] == {"ya": 2, "netral": 1, "tidak": 1} and b2["n"] == 4 and b2["pct_ya"] == 50.0
    assert s["n_responses"] == 5 and s["questions"]["a2"]["n"] == 1


def test_text_answers_collected_but_never_name_or_contact():
    rows = [{"a0": "Budi", "f9": "budi@mail.com", "g3": "Bagus sekali", "f6": "ETH"}, {"g3": "  "}]
    s = summarize(rows)
    assert s["questions"]["g3"]["texts"] == ["Bagus sekali"]
    assert "a0" not in s["questions"] and "f9" not in s["questions"]


def test_unknown_values_and_keys_are_ignored_not_crashing():
    s = summarize([{"b2": "mungkin", "zzz": "ya", "b1": "ya"}])
    assert s["questions"]["b2"]["n"] == 0 and s["questions"]["b1"]["counts"]["ya"] == 1


def test_cli_writes_markdown_with_warning_for_small_samples_and_no_pii(tmp_path):
    src, out = tmp_path / "hasil.csv", tmp_path / "ringkasan.md"
    write_csv(src, [{"a0": "Budi Santoso", "f9": "budi@mail.com", "b2": "ya", "g3": "Sangat membantu"},
                    {"b2": "tidak", "c1": "netral"}])
    main([str(src), "--out", str(out)])
    md = out.read_text()
    assert "Jumlah responden: 2" in md and "2026-10-16" in md and "2026-10-17" in md
    assert "belum dapat digeneralisasi" in md                                # n < 30
    assert "| Ya | Netral | Tidak |" in md and "Sangat membantu" in md
    assert "Budi" not in md and "budi@mail.com" not in md


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


from scripts.summarize_feedback import render_html, segment_summary   # noqa: E402


SEG_ROWS = [{"a2": "ya", "b2": "ya"}, {"a2": "ya", "b2": "ya"}, {"a2": "ya", "b2": "tidak"},
            {"a2": "tidak", "b2": "tidak"}, {"a2": "tidak", "b2": "netral"}, {"a2": "tidak"}]


def test_segment_summary_splits_percent_ya_by_group_and_skips_the_grouping_question():
    seg = segment_summary(SEG_ROWS, "a2")
    assert seg["groups"] == {"ya": 3, "tidak": 3}
    b2 = seg["questions"]["b2"]
    assert b2["ya"] == {"n": 3, "pct_ya": 66.7} and b2["tidak"] == {"n": 2, "pct_ya": 0.0}
    assert "a2" not in seg["questions"]


def test_segment_ignores_rows_without_the_grouping_answer():
    seg = segment_summary([{"b2": "ya"}, {"a2": "ya", "b2": "ya"}], "a2")
    assert seg["groups"] == {"ya": 1, "tidak": 0} and seg["questions"]["b2"]["ya"]["n"] == 1


def test_markdown_includes_group_comparison_with_small_n_flag(tmp_path):
    src, out = tmp_path / "h.csv", tmp_path / "r.md"
    write_csv(src, [{**r, "a3": "ya" if i % 2 else "tidak"} for i, r in enumerate(SEG_ROWS)])
    main([str(src), "--out", str(out)])
    md = out.read_text()
    assert "Perbandingan menurut pengalaman kripto" in md and "Perbandingan menurut pengenalan machine learning" in md
    assert "66.7% (n=3, n kecil)" in md                                         # n < 5 diberi tanda


def test_html_report_has_svg_bars_escapes_text_and_hides_pii(tmp_path):
    rows = [{"a0": "Budi", "f9": "budi@mail.com", "b2": "ya", "g3": "<script>alert(1)</script>"},
            {"b2": "ya"}, {"b2": "tidak"}, {"b2": "netral"}]
    html = render_html(summarize(rows), ["2026-10-16T00:00:00Z"], [])
    assert html.startswith("<!doctype html>") and "<svg" in html and 'role="img"' in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "Budi" not in html and "budi@mail.com" not in html
    assert 'width="50.0%"' in html                                              # ya 2 dari 4 jawaban


def test_cli_writes_html_when_requested(tmp_path):
    src, out, html = tmp_path / "h.csv", tmp_path / "r.md", tmp_path / "r.html"
    write_csv(src, SEG_ROWS)
    main([str(src), "--out", str(out), "--html", str(html)])
    assert "Perbandingan antar kelompok" in html.read_text() and html.stat().st_size > 1000
