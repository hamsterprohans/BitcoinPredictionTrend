"""Ringkas hasil kuesioner dari CSV ekspor Supabase (tabel feedback_responses atau view feedback_flat; perlu kolom `answers`).

Pemakaian: python -m scripts.summarize_feedback hasil.csv --out ringkasan.md [--html laporan.html]
Yang dihitung: skor SUS (Brooke, 1996), skor pemahaman objektif (kunci jawaban bagian B), rata-rata kepuasan penjelasan (D)
dan kepercayaan (E), sebaran tiap soal, serta jawaban terbuka. Nama TIDAK pernah dimasukkan ke ringkasan.
Skema soal dibaca dari static/js/kuesioner-schema.js; baris dari versi survei lain diabaikan bila CSV memuat kolom survey_version.
"""
import argparse
import csv
import html as _html
import json
import re
import statistics
import sys
from pathlib import Path

from app import config

SCHEMA_JS = config.STATIC_DIR / "js" / "kuesioner-schema.js"
PRIVATE = {"nama"}                          # data pribadi: tidak ikut laporan
# Kunci jawaban bagian B (dokumen referensi). Sengaja hanya di sini, bukan di skema frontend yang publik.
ANSWER_KEY = {"b1": "salah", "b2": "salah", "b3": "salah", "b4": "benar", "b5": "salah", "b6": "salah"}
FIXED = {"yn": ("ya", "tidak"), "tf": ("benar", "salah", "tidak_tahu"), "scale": ("1", "2", "3", "4", "5")}
LABEL = {"ya": "Ya", "tidak": "Tidak", "benar": "Benar", "salah": "Salah", "tidak_tahu": "Tidak tahu"}
SUS_IDS = [f"c{i}" for i in range(1, 11)]
ESS_IDS = [f"d{i}" for i in range(1, 9)]
TRUST_IDS = [f"e{i}" for i in range(1, 5)]
TRADERS = {"trading_baru", "trading_lama"}
MIN_N = 30
MIN_GROUP = 5                               # kelompok lebih kecil dari ini diberi tanda "n kecil"
SUS_BENCHMARK = 68                          # pembanding umum: rata-rata skor SUS dari banyak studi

_SECTION = re.compile(r'\{\s*id:\s*"\w"\s*,\s*title:\s*("(?:[^"\\]|\\.)*")')
_QUESTION = re.compile(r'\{\s*id:\s*"(\w+)"\s*,\s*type:\s*"(\w+)"')
_TEXT = re.compile(r'\btext:\s*("(?:[^"\\]|\\.)*")')
_OPTION = re.compile(r'\{\s*value:\s*"(\w+)"\s*,\s*label:\s*("(?:[^"\\]|\\.)*")')
_VERSION = re.compile(r"\bversion:\s*(\d+)")


def survey_version(path: Path = SCHEMA_JS) -> int:
    return int(_VERSION.search(Path(path).read_text()).group(1))


def load_questions(path: Path = SCHEMA_JS) -> list[dict]:
    text = Path(path).read_text()
    marks = [(m.start(), json.loads(m.group(1))) for m in _SECTION.finditer(text)]
    starts = [m for m in _QUESTION.finditer(text)]
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        chunk = text[m.start():end]
        q = {"id": m.group(1), "type": m.group(2), "text": json.loads(_TEXT.search(chunk).group(1)),
             "section": [t for pos, t in marks if pos < m.start()][-1]}
        if q["type"] == "choice":
            q["options"] = [{"value": v, "label": json.loads(label)} for v, label in _OPTION.findall(chunk)]
        out.append(q)
    return out


def _num(v):
    try:
        n = int(str(v))
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 5 else None


def _mean(xs, digits=1):
    return round(statistics.fmean(xs), digits) if xs else None


def sus_score(answers: dict) -> float | None:
    """Skor SUS 0-100: butir ganjil (skor-1), genap (5-skor), dijumlah lalu dikali 2,5. None bila ada butir kosong/tidak sah."""
    vals = [_num(answers.get(k)) for k in SUS_IDS]
    if None in vals:
        return None
    return sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(vals)) * 2.5


def understanding_score(answers: dict) -> int | None:
    """Jumlah jawaban benar bagian B (0-6). 'Tidak tahu' dihitung salah. None bila ada butir yang belum dijawab."""
    if any(answers.get(k) not in FIXED["tf"] for k in ANSWER_KEY):
        return None
    return sum(answers[k] == v for k, v in ANSWER_KEY.items())


def _scale_mean(rows, ids):
    """Rata-rata per responden (butir yang terisi), lalu rata-rata antarresponden."""
    per = [statistics.fmean(vs) for r in rows if (vs := [n for k in ids if (n := _num(r.get(k))) is not None])]
    return {"n": len(per), "mean": _mean(per, 2)}


def summarize(rows: list[dict], questions: list[dict] | None = None) -> dict:
    questions = questions or load_questions()
    res = {}
    for q in questions:
        if q["id"] in PRIVATE:
            continue
        keys = FIXED.get(q["type"]) or (tuple(o["value"] for o in q["options"]) if q["type"] == "choice" else None)
        if keys:
            counts = {k: 0 for k in keys}
            for r in rows:
                v = str(r.get(q["id"]))
                if v in counts:
                    counts[v] += 1
            n = sum(counts.values())
            item = {**q, "counts": counts, "n": n}
            if q["type"] == "scale":
                item["mean"] = _mean([int(k) * c for k, c in counts.items() for _ in range(c)], 2)
            if q["id"] in ANSWER_KEY:
                item["pct_correct"] = round(100 * counts[ANSWER_KEY[q["id"]]] / n, 1) if n else None
            res[q["id"]] = item
        else:
            texts = [str(r[q["id"]]).strip() for r in rows if str(r.get(q["id"]) or "").strip()]
            res[q["id"]] = {**q, "texts": texts, "n": len(texts)}
    scores = [s for r in rows if (s := sus_score(r)) is not None]
    under = [s for r in rows if (s := understanding_score(r)) is not None]
    return {"n_responses": len(rows), "questions": res,
            "sus": {"n": len(scores), "mean": _mean(scores), "median": round(statistics.median(scores), 1) if scores else None},
            "understanding": {"n": len(under), "mean": _mean(under, 2), "max": len(ANSWER_KEY)},
            "ess": _scale_mean(rows, ESS_IDS), "trust": _scale_mean(rows, TRUST_IDS)}


def segment_summary(rows: list[dict]) -> dict:
    """Bandingkan skor utama antara yang pernah trading (a1) dan yang belum. Baris tanpa jawaban a1 yang sah diabaikan."""
    groups = {"trading": [r for r in rows if r.get("a1") in TRADERS],
              "belum": [r for r in rows if r.get("a1") in ("belum", "berita")]}
    metrics = {"SUS": {}, "Pemahaman (0-6)": {}, "Kepuasan penjelasan (1-5)": {}, "Kepercayaan (1-5)": {}}
    for g, rs in groups.items():
        s = summarize(rs, [])
        metrics["SUS"][g] = {"n": s["sus"]["n"], "mean": s["sus"]["mean"]}
        metrics["Pemahaman (0-6)"][g] = {"n": s["understanding"]["n"], "mean": s["understanding"]["mean"]}
        metrics["Kepuasan penjelasan (1-5)"][g] = {"n": s["ess"]["n"], "mean": s["ess"]["mean"]}
        metrics["Kepercayaan (1-5)"][g] = {"n": s["trust"]["n"], "mean": s["trust"]["mean"]}
    return {"groups": {g: len(rs) for g, rs in groups.items()}, "metrics": metrics}


def _cell(c: dict) -> str:
    if not c["n"]:
        return "-"
    return f"{c['mean']} (n={c['n']}{', n kecil' if c['n'] < MIN_GROUP else ''})"


def _dist(q: dict) -> str:
    names = {o["value"]: o["label"] for o in q.get("options", [])}
    return ", ".join(f"{names.get(k) or LABEL.get(k, k)} {c}" for k, c in q["counts"].items())


def render_markdown(summary: dict, dates: list[str], rows: list[dict] | None = None) -> str:
    n, sus, und = summary["n_responses"], summary["sus"], summary["understanding"]
    lines = ["# Ringkasan kuesioner", "", f"Jumlah responden: {n}"]
    if dates:
        lines.append(f"Periode: {min(dates)[:10]} sampai {max(dates)[:10]}")
    if n < MIN_N:
        lines += ["", f"> Catatan: responden masih kurang dari {MIN_N}, sehingga hasil belum dapat digeneralisasi "
                      "dan sebaiknya dibaca sebagai gambaran awal."]
    lines += ["", "## Skor utama", "", "| Ukuran | n | Rata-rata |", "|---|---|---|",
              f"| Skor SUS (0-100; pembanding umum {SUS_BENCHMARK}) | {sus['n']} | {sus['mean'] if sus['n'] else '-'}"
              + (f" (median {sus['median']})" if sus["n"] else "") + " |",
              f"| Pemahaman objektif (benar dari {und['max']}) | {und['n']} | {und['mean'] if und['n'] else '-'} |",
              f"| Kepuasan penjelasan D (1-5, hanya yang membaca penjelasan) | {summary['ess']['n']} | {summary['ess']['mean'] or '-'} |",
              f"| Kepercayaan dan niat bergantung E (1-5) | {summary['trust']['n']} | {summary['trust']['mean'] or '-'} |"]
    section = None
    for q in summary["questions"].values():
        if q["type"] in ("short", "long"):
            continue
        if q["section"] != section:
            section = q["section"]
            lines += ["", f"## {section}", "", "| Pertanyaan | Sebaran jawaban | n | Ukuran |", "|---|---|---|---|"]
        extra = f"rata-rata {q['mean']}" if q.get("mean") is not None else (f"{q['pct_correct']}% benar" if q.get("pct_correct") is not None else "-")
        lines.append(f"| {q['id']}. {q['text']} | {_dist(q)} | {q['n']} | {extra} |")
    if rows is not None:
        seg = segment_summary(rows)
        if seg["groups"]["trading"] or seg["groups"]["belum"]:
            lines += ["", "## Perbandingan menurut pengalaman trading", "",
                      f"Pernah trading: {seg['groups']['trading']} responden; belum pernah trading: {seg['groups']['belum']} responden.", "",
                      "| Ukuran | Pernah trading | Belum pernah |", "|---|---|---|"]
            lines += [f"| {name} | {_cell(m['trading'])} | {_cell(m['belum'])} |" for name, m in seg["metrics"].items()]
    texts = [q for q in summary["questions"].values() if q["type"] in ("short", "long") and q["texts"]]
    if texts:
        lines += ["", "## Jawaban terbuka"]
        for q in texts:
            lines += ["", f"**{q['id']}. {q['text']}**", ""] + [f"- {t}" for t in q["texts"]]
    return "\n".join(lines) + "\n"


_CSS = ("body{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1c1b18}"
        "h2{margin-top:2rem}.q{margin:.9rem 0}.bar{display:block;width:100%;height:22px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
        ".note{background:#fff6dc;border-left:4px solid #c9a227;padding:.5rem .8rem}")
_FILLS = ["#d9534f", "#e8935c", "#9a9a9a", "#7fb98c", "#2f9e6e"]


def _fills(q: dict) -> list[str]:
    n = len(q["counts"])
    if q["type"] == "scale":
        return _FILLS
    if q["type"] == "tf":
        return ["#2f9e6e", "#d9534f", "#9a9a9a"]
    return ["#2f9e6e", "#3b82c4", "#c9a227", "#8a5fbf"][:n] if q["type"] == "choice" else ["#2f9e6e", "#d9534f"]


def _bar(q: dict) -> str:
    esc, n, x, parts = _html.escape, q["n"], 0.0, []
    for (k, c), fill in zip(q["counts"].items(), _fills(q)):
        w = round(100 * c / n, 1) if n else 0.0
        if w:
            parts.append(f'<rect x="{x}%" y="0" width="{w}%" height="22" fill="{fill}"><title>{esc(str(k))}: {c}</title></rect>')
        x += w
    label = _dist(q)
    return (f'<div class="q"><div>{esc(q["id"])}. {esc(q["text"])}</div>'
            f'<svg class="bar" role="img" aria-label="{esc(label)} (n={n})" preserveAspectRatio="none">'
            f'<rect width="100%" height="22" fill="#eee"/>{"".join(parts)}</svg><small>{esc(label)} (n={n})</small></div>')


def render_html(summary: dict, dates: list[str], rows: list[dict]) -> str:
    esc, n, sus = _html.escape, summary["n_responses"], summary["sus"]
    out = ["<!doctype html><html lang=\"id\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           f"<title>Ringkasan kuesioner</title><style>{_CSS}</style></head><body>", "<h1>Ringkasan kuesioner</h1>",
           f"<p>Jumlah responden: {n}" + (f" &middot; {esc(min(dates)[:10])} sampai {esc(max(dates)[:10])}" if dates else "") + "</p>"]
    if n < MIN_N:
        out.append(f'<p class="note">Responden masih kurang dari {MIN_N}; hasil belum dapat digeneralisasi.</p>')
    und = summary["understanding"]
    out.append("<h2>Skor utama</h2><table><tr><th>Ukuran</th><th>n</th><th>Rata-rata</th></tr>"
               f"<tr><td>Skor SUS (0-100; pembanding umum {SUS_BENCHMARK})</td><td>{sus['n']}</td><td>{sus['mean'] if sus['n'] else '-'}</td></tr>"
               f"<tr><td>Pemahaman objektif (benar dari {und['max']})</td><td>{und['n']}</td><td>{und['mean'] if und['n'] else '-'}</td></tr>"
               f"<tr><td>Kepuasan penjelasan D (1-5)</td><td>{summary['ess']['n']}</td><td>{summary['ess']['mean'] or '-'}</td></tr>"
               f"<tr><td>Kepercayaan dan niat bergantung E (1-5)</td><td>{summary['trust']['n']}</td><td>{summary['trust']['mean'] or '-'}</td></tr></table>")
    section = None
    for q in summary["questions"].values():
        if q["type"] in ("short", "long"):
            continue
        if q["section"] != section:
            section = q["section"]
            out.append(f"<h2>{esc(section)}</h2>")
        out.append(_bar(q))
    seg = segment_summary(rows)
    if seg["groups"]["trading"] or seg["groups"]["belum"]:
        out.append(f"<h2>Perbandingan antar kelompok</h2><p>Menurut pengalaman trading (pernah: {seg['groups']['trading']}, belum: {seg['groups']['belum']})</p>"
                   "<table><tr><th>Ukuran</th><th>Pernah trading</th><th>Belum pernah</th></tr>")
        out += [f"<tr><td>{esc(name)}</td><td>{esc(_cell(m['trading']))}</td><td>{esc(_cell(m['belum']))}</td></tr>" for name, m in seg["metrics"].items()]
        out.append("</table>")
    texts = [q for q in summary["questions"].values() if q["type"] in ("short", "long") and q["texts"]]
    if texts:
        out.append("<h2>Jawaban terbuka</h2>")
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
        if "survey_version" in (reader.fieldnames or []):          # jawaban versi lama punya soal yang berbeda: jangan dicampur
            data = [r for r in data if str(r.get("survey_version")) == str(survey_version())]
    if not data:
        raise SystemExit("Belum ada responden di CSV ini (untuk versi survei yang berlaku).")
    rows = [json.loads(r["answers"]) for r in data]
    dates = [r["created_at"] for r in data if r.get("created_at")]
    summary = summarize(rows)
    Path(a.out).write_text(render_markdown(summary, dates, rows), encoding="utf-8")
    if a.html:
        Path(a.html).write_text(render_html(summary, dates, rows), encoding="utf-8")
    print(f"Ringkasan {len(rows)} responden ditulis ke {a.out}" + (f" dan {a.html}" if a.html else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
