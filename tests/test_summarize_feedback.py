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
