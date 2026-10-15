"""Ringkas hasil kuesioner dari CSV ekspor Supabase (tabel feedback_responses atau view feedback_flat; perlu kolom `answers`).

Pemakaian: python -m scripts.summarize_feedback hasil.csv --out ringkasan.md
Nama (a0) dan kontak (f9) TIDAK pernah dimasukkan ke ringkasan. Skema soal dibaca dari static/js/kuesioner-schema.js.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

from app import config

SCHEMA_JS = config.STATIC_DIR / "js" / "kuesioner-schema.js"
PRIVATE = {"a0", "f9"}                      # data pribadi: tidak ikut laporan
CHOICES = {"yn": ("ya", "tidak"), "ynn": ("ya", "netral", "tidak")}
LABEL = {"ya": "Ya", "netral": "Netral", "tidak": "Tidak"}
MIN_N = 30

_SECTION = re.compile(r'\{\s*id:\s*"\w"\s*,\s*title:\s*("(?:[^"\\]|\\.)*")')
_QUESTION = re.compile(r'\{\s*id:\s*"(\w+)"\s*,\s*type:\s*"(\w+)"\s*,\s*text:\s*("(?:[^"\\]|\\.)*")')


def load_questions(path: Path = SCHEMA_JS) -> list[dict]:
    text = Path(path).read_text()
    marks = [(m.start(), json.loads(m.group(1))) for m in _SECTION.finditer(text)]
    out = []
    for m in _QUESTION.finditer(text):
        section = [t for pos, t in marks if pos < m.start()][-1]
        out.append({"id": m.group(1), "type": m.group(2), "text": json.loads(m.group(3)), "section": section})
    return out


def summarize(rows: list[dict], questions: list[dict] | None = None) -> dict:
    questions = questions or load_questions()
    res = {}
    for q in questions:
        if q["id"] in PRIVATE:
            continue
        if q["type"] in CHOICES:
            counts = {c: 0 for c in CHOICES[q["type"]]}
            for r in rows:
                v = r.get(q["id"])
                if v in counts:
                    counts[v] += 1
            n = sum(counts.values())
            res[q["id"]] = {**q, "counts": counts, "n": n, "pct_ya": round(100 * counts["ya"] / n, 1) if n else None}
        else:
            texts = [str(r[q["id"]]).strip() for r in rows if str(r.get(q["id"]) or "").strip()]
            res[q["id"]] = {**q, "texts": texts, "n": len(texts)}
    return {"n_responses": len(rows), "questions": res}


def render_markdown(summary: dict, dates: list[str]) -> str:
    n = summary["n_responses"]
    lines = ["# Ringkasan kuesioner", "", f"Jumlah responden: {n}"]
    if dates:
        lines.append(f"Periode: {min(dates)[:10]} sampai {max(dates)[:10]}")
    if n < MIN_N:
        lines += ["", f"> Catatan: responden masih kurang dari {MIN_N}, sehingga persentase belum dapat digeneralisasi "
                      "dan sebaiknya dibaca sebagai gambaran awal."]
    section = None
    for q in summary["questions"].values():
        if q["section"] != section:
            section = q["section"]
            lines += ["", f"## {section}"]
        if q["type"] in CHOICES:
            c = q["counts"]
            pct = "-" if q["pct_ya"] is None else f"{q['pct_ya']}%"
            lines.append(f"| {q['id']}. {q['text']} | {c['ya']} | {c.get('netral', '-')} | {c['tidak']} | {q['n']} | {pct} |")
    lines = _with_table_headers(lines)
    texts = [q for q in summary["questions"].values() if q["type"] not in CHOICES and q["texts"]]
    if texts:
        lines += ["", "## Jawaban teks"]
        for q in texts:
            lines += ["", f"**{q['id']}. {q['text']}**", ""] + [f"- {t}" for t in q["texts"]]
    return "\n".join(lines) + "\n"


def _with_table_headers(lines):
    """Sisipkan header tabel tepat sebelum baris pilihan pertama pada tiap bagian."""
    header = ["| Pertanyaan | Ya | Netral | Tidak | n | % Ya |", "|---|---|---|---|---|---|"]
    out, in_table = [], False
    for ln in lines:
        if ln.startswith("| ") and not in_table:
            out += [""] + header
            in_table = True
        if ln.startswith("## "):
            in_table = False
        out.append(ln)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv")
    ap.add_argument("--out", default="ringkasan_kuesioner.md")
    a = ap.parse_args(argv)
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if "answers" not in (reader.fieldnames or []):
            raise SystemExit("CSV tidak punya kolom 'answers'. Ekspor dari tabel feedback_responses atau view feedback_flat.")
        data = list(reader)
    if not data:
        raise SystemExit("Belum ada responden di CSV ini.")
    rows = [json.loads(r["answers"]) for r in data]
    dates = [r["created_at"] for r in data if r.get("created_at")]
    Path(a.out).write_text(render_markdown(summarize(rows), dates), encoding="utf-8")
    print(f"Ringkasan {len(rows)} responden ditulis ke {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
