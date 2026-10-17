"""Ringkas hasil kuesioner dari CSV ekspor Supabase (tabel feedback_responses atau view feedback_flat; perlu kolom `answers`).

Pemakaian: python -m scripts.summarize_feedback hasil.csv --out ringkasan.md [--html laporan.html]
Nama (a0) dan kontak (f9) TIDAK pernah dimasukkan ke ringkasan. Skema soal dibaca dari static/js/kuesioner-schema.js.
"""
import argparse
import csv
import html as _html
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
MIN_GROUP = 5                             # kelompok lebih kecil dari ini diberi tanda "n kecil"
SEGMENTS = (("a2", "pengalaman kripto"), ("a3", "pengenalan machine learning"))

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


def segment_summary(rows: list[dict], seg_id: str, questions: list[dict] | None = None) -> dict:
    """% Ya tiap soal pilihan, dipisah menurut jawaban Ya/Tidak pada soal pengelompokan `seg_id`."""
    groups = {g: [r for r in rows if r.get(seg_id) == g] for g in ("ya", "tidak")}
    per = {g: summarize(rs, questions)["questions"] for g, rs in groups.items()}
    qs = {}
    for qid, q in per["ya"].items():
        if q["type"] not in CHOICES or qid == seg_id:
            continue
        qs[qid] = {**{k: q[k] for k in ("id", "text", "section")},
                   **{g: {"n": per[g][qid]["n"], "pct_ya": per[g][qid]["pct_ya"]} for g in groups}}
    return {"groups": {g: len(rs) for g, rs in groups.items()}, "questions": qs}


def _cell(c: dict) -> str:
    if not c["n"]:
        return "-"
    flag = ", n kecil" if c["n"] < MIN_GROUP else ""
    return f"{c['pct_ya']}% (n={c['n']}{flag})"


def _segment_markdown(seg: dict, label: str) -> list[str]:
    g = seg["groups"]
    lines = ["", f"## Perbandingan menurut {label}", "",
             f"Kelompok Ya: {g['ya']} responden; kelompok Tidak: {g['tidak']} responden. Angka = persen menjawab Ya.", "",
             "| Pertanyaan | Kelompok Ya | Kelompok Tidak |", "|---|---|---|"]
    lines += [f"| {q['id']}. {q['text']} | {_cell(q['ya'])} | {_cell(q['tidak'])} |" for q in seg["questions"].values()]
    return lines


def render_markdown(summary: dict, dates: list[str], rows: list[dict] | None = None) -> str:
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
    for seg_id, label in SEGMENTS:
        if rows is not None and any(r.get(seg_id) for r in rows):
            lines += _segment_markdown(segment_summary(rows, seg_id), label)
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


_CSS = ("body{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1c1b18}"
        "h2{margin-top:2rem}.q{margin:.9rem 0}.bar{display:block;width:100%;height:22px}"
        ".legend span{margin-right:1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
        ".note{background:#fff6dc;border-left:4px solid #c9a227;padding:.5rem .8rem}")
_FILL = {"ya": "#2f9e6e", "netral": "#9a9a9a", "tidak": "#d9534f"}


def _bar(q: dict) -> str:
    esc, n, x, parts = _html.escape, q["n"], 0.0, []
    for k, c in q["counts"].items():
        w = round(100 * c / n, 1) if n else 0.0
        if w:
            parts.append(f'<rect x="{x}%" y="0" width="{w}%" height="22" fill="{_FILL[k]}"><title>{LABEL[k]}: {c}</title></rect>')
        x += w
    label = ", ".join(f"{LABEL[k]} {c}" for k, c in q["counts"].items())
    return (f'<div class="q"><div>{esc(q["id"])}. {esc(q["text"])}</div>'
            f'<svg class="bar" role="img" aria-label="{esc(label)} (n={n})" preserveAspectRatio="none">'
            f'<rect width="100%" height="22" fill="#eee"/>{"".join(parts)}</svg><small>{esc(label)} (n={n})</small></div>')


def render_html(summary: dict, dates: list[str], rows: list[dict]) -> str:
    esc, n = _html.escape, summary["n_responses"]
    out = ["<!doctype html><html lang=\"id\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           f"<title>Ringkasan kuesioner</title><style>{_CSS}</style></head><body>", "<h1>Ringkasan kuesioner</h1>",
           f"<p>Jumlah responden: {n}" + (f" &middot; {esc(min(dates)[:10])} sampai {esc(max(dates)[:10])}" if dates else "") + "</p>"]
    if n < MIN_N:
        out.append(f'<p class="note">Responden masih kurang dari {MIN_N}; persentase belum dapat digeneralisasi.</p>')
    out.append('<p class="legend"><span style="color:%s">&#9632; Ya</span><span style="color:%s">&#9632; Netral</span>'
               '<span style="color:%s">&#9632; Tidak</span></p>' % (_FILL["ya"], _FILL["netral"], _FILL["tidak"]))
    section = None
    for q in summary["questions"].values():
        if q["type"] not in CHOICES:
            continue
        if q["section"] != section:
            section = q["section"]
            out.append(f"<h2>{esc(section)}</h2>")
        out.append(_bar(q))
    segs = [(sid, lbl, segment_summary(rows, sid)) for sid, lbl in SEGMENTS if any(r.get(sid) for r in rows)]
    if segs:
        out.append("<h2>Perbandingan antar kelompok</h2>")
    for _, lbl, seg in segs:
        out.append(f"<h3>Menurut {esc(lbl)} (Ya: {seg['groups']['ya']}, Tidak: {seg['groups']['tidak']})</h3>"
                   "<table><tr><th>Pertanyaan</th><th>Kelompok Ya</th><th>Kelompok Tidak</th></tr>")
        out += [f"<tr><td>{esc(q['id'])}. {esc(q['text'])}</td><td>{esc(_cell(q['ya']))}</td><td>{esc(_cell(q['tidak']))}</td></tr>"
                for q in seg["questions"].values()]
        out.append("</table>")
    texts = [q for q in summary["questions"].values() if q["type"] not in CHOICES and q["texts"]]
    if texts:
        out.append("<h2>Jawaban teks</h2>")
    for q in texts:
        out.append(f"<h3>{esc(q['id'])}. {esc(q['text'])}</h3><ul>" + "".join(f"<li>{esc(t)}</li>" for t in q["texts"]) + "</ul>")
    return "".join(out) + "</body></html>\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv")
    ap.add_argument("--out", default="ringkasan_kuesioner.md")
    ap.add_argument("--html", help="tulis juga laporan HTML bergrafik (berkas mandiri) ke jalur ini")
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
    summary = summarize(rows)
    Path(a.out).write_text(render_markdown(summary, dates, rows), encoding="utf-8")
    if a.html:
        Path(a.html).write_text(render_html(summary, dates, rows), encoding="utf-8")
    print(f"Ringkasan {len(rows)} responden ditulis ke {a.out}" + (f" dan {a.html}" if a.html else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
