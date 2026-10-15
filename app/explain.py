"""Penjelasan prediksi: kontribusi fitur lokal, keandalan historis, blok fakta, narasi dan validatornya."""
import math

import numpy as np

from . import config
from .inference import FEATURE_ORDER

FEATURE_LABELS = {
    "daily_return": "Return harian", "MA7": "Rata-rata harga 7 hari", "MA30": "Rata-rata harga 30 hari",
    "MA90": "Rata-rata harga 90 hari", "Vol_7": "Volatilitas 7 hari", "Vol_30": "Volatilitas 30 hari",
    "RSI14": "RSI 14 hari", "MACD": "MACD", "MACD_Signal": "Sinyal MACD", "MACD_Histogram": "Histogram MACD",
    "BB_width": "Lebar Bollinger", "news_sentiment": "Sentimen berita", "fear_greed_index_scaled": "Fear & Greed Index",
}
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
          "November", "Desember"]


def _id(x, d=0, sign=False) -> str:
    s = f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def date_id(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def format_value(feature: str, v: float) -> str:
    if feature == "daily_return":
        return _id(v * 100, 2, sign=True) + "%"
    if feature in ("MA7", "MA30", "MA90"):
        return "US$" + _id(v, 0)
    if feature in ("MACD", "MACD_Signal", "MACD_Histogram"):
        return "US$" + _id(v, 1, sign=True)
    if feature in ("Vol_7", "Vol_30"):
        return _id(v * 100, 2) + "%"
    if feature == "RSI14":
        return _id(v, 1)
    if feature == "BB_width":
        return _id(v * 100, 1) + "%"
    if feature == "news_sentiment":
        return _id(v, 2, sign=True)
    if feature == "fear_greed_index_scaled":
        return _id(v * 100, 0) + " dari 100"
    return _id(v, 2)


def replacement_vector(stats, scaler=None) -> np.ndarray:
    q = stats["quantiles"]
    fg = q["fear_greed_index_scaled"][50]
    if scaler is None:
        head = np.zeros(12)
    else:
        import pandas as pd
        cols = list(FEATURE_ORDER[:12])
        row = pd.DataFrame([{c: q[c][50] for c in cols}])[cols]
        head = np.clip(scaler.transform(row)[0], -config.CLIP_VAL, config.CLIP_VAL)
    return np.concatenate([head, [fg]]).astype("float32")


def contributions_batch(model, X, replace) -> np.ndarray:
    X = np.asarray(X, dtype="float32")
    n = len(X)
    p0 = np.asarray(model.predict(X, verbose=0)).reshape(n)
    out = np.zeros((n, X.shape[2]))
    for j in range(X.shape[2]):
        Xr = X.copy()
        Xr[:, :, j] = replace[j]
        pj = np.asarray(model.predict(Xr, verbose=0)).reshape(n)
        out[:, j] = 100.0 * (p0 - pj)
    return out


def rank_contributions(deltas_row) -> list:
    rows = [{"feature": f, "label": FEATURE_LABELS[f], "delta_pp": round(float(d), 3)}
            for f, d in zip(FEATURE_ORDER, deltas_row)]
    return sorted(rows, key=lambda r: abs(r["delta_pp"]), reverse=True)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, c - h), min(1.0, c + h))


LEVELS = ("rendah", "sedang", "tinggi")


def level_cuts(margins):
    q = np.quantile(np.asarray(margins, dtype=float), [1 / 3, 2 / 3])
    return [float(q[0]), float(q[1])]


def level_of(margin, cuts) -> str:
    return LEVELS[0] if margin <= cuts[0] else LEVELS[1] if margin <= cuts[1] else LEVELS[2]


def reliability_table(prob, threshold, correct, cuts=None) -> list:
    prob, correct = np.asarray(prob, dtype=float), np.asarray(correct, dtype=bool)
    margins = np.abs(prob - threshold)
    cuts = cuts or level_cuts(margins)
    lv = np.array([level_of(m, cuts) for m in margins])
    out = []
    for name in LEVELS:
        mask = lv == name
        n, k = int(mask.sum()), int(correct[mask].sum())
        lo, hi = wilson(k, n)
        out.append({"level": name, "n": n, "accuracy": (k / n if n else None),
                    "ci_lo": lo, "ci_hi": hi, "includes_chance": bool(lo <= 0.5 <= hi)})
    return out


def feature_rows(values: dict, stats) -> list:
    rows = []
    for f in FEATURE_ORDER:
        q = np.asarray(stats["quantiles"][f], dtype=float)
        v = float(values[f])
        pct = int(np.clip(np.searchsorted(q, v, side="right") - 1, 0, 100))
        cat = "rendah" if pct < 33.3 else "tinggi" if pct > 66.7 else "sedang"
        rows.append({"feature": f, "label": FEATURE_LABELS[f], "value": v, "value_text": format_value(f, v),
                     "percentile": pct, "category": cat,
                     "outside_train_range": bool(v < q[0] or v > q[-1])})
    return rows


def build_facts(rec: dict, auc=None) -> dict:
    feats = {r["feature"]: r for r in rec["features"]}
    top = []
    for c in rec["contributions"][:3]:
        f = feats[c["feature"]]
        top.append({"label": c["label"], "value_text": f["value_text"], "percentile": int(f["percentile"]),
                    "category": f["category"], "delta": _id(c["delta_pp"], 1, sign=True)})
    prob, thr = rec["prob"], rec["threshold"]
    return {"date": rec["date"], "date_id": date_id(rec["date"]),
            "target": rec["target_date"], "target_id": date_id(rec["target_date"]),
            "prob": _id(prob, 4), "threshold": _id(thr, 4), "margin": _id(abs(prob - thr), 4),
            "direction": "NAIK" if prob > thr else "TURUN", "level": rec.get("level"),
            "auc": _id(auc, 4) if auc is not None else None, "top": top}


def facts_text(f: dict) -> str:
    lines = [f"tanggal: {f['date_id']}", f"tanggal target: {f['target_id']}",
             f"probabilitas naik (skor model): {f['prob']}", f"ambang keputusan: {f['threshold']}",
             f"selisih terhadap ambang: {f['margin']}", f"prediksi: {f['direction']}"]
    if f["level"]:
        lines.append(f"tingkat keyakinan: {f['level']}")
    if f["auc"]:
        lines.append(f"AUC uji historis: {f['auc']}")
    lines.append("fitur teratas yang paling memengaruhi skor:")
    for i, t in enumerate(f["top"], 1):
        lines.append(f"{i}. {t['label']}: nilai {t['value_text']}, persentil {t['percentile']} terhadap data latih, "
                     f"kategori {t['category']}, pengaruh {t['delta']} poin persentase")
    return "\n".join(lines)


import re  # noqa: E402

MODEL = "claude-haiku-4-5"

_MONTHS_RE = "|".join(MONTHS)
_DATE_RE = re.compile(rf"\b\d{{1,2}} (?:{_MONTHS_RE}) \d{{4}}\b")
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM_RE = re.compile(r"\d[\d.,]*\d|\d")
_FORBIDDEN_RE = re.compile(
    r"\b(?:beli|membeli|jual|menjual|buy|sell|dijamin|garansi|rekomendasi|sebaiknya)\b|(?<!tidak )\bpasti\b", re.I)
_UNCERTAIN = ("tidak pasti", "ketidakpastian", "bisa keliru", "dapat keliru", "mungkin keliru")

NARRATIVE_PROMPT = """Anda menulis penjelasan singkat dalam Bahasa Indonesia untuk investor ritel tentang satu prediksi arah harga Bitcoin dari sebuah model penelitian.

ATURAN KETAT:
- Gunakan HANYA informasi pada BLOK FAKTA. Tulis angka persis seperti tertulis di sana (jangan membulatkan, jangan menghitung ulang, jangan menambah angka baru).
- Sebut tanggal, probabilitas (skor model), arah prediksi (naik atau turun), dan sedikitnya dua dari tiga fitur teratas.
- Jangan menyatakan sebab-akibat; fitur hanya "paling memengaruhi skor model".
- Jangan mengajak membeli atau menjual, dan jangan memakai kata beli, jual, pasti, dijamin, garansi, rekomendasi, sebaiknya.
- Wajib menulis kalimat persis: "Model belum terbukti lebih baik dari tebakan acak" dan kalimat persis: "Ini bukan saran investasi."
- Akui bahwa hasil ini tidak pasti dan bisa keliru.
- Panjang 60 sampai 140 kata, satu paragraf.

BLOK FAKTA:
{facts}
{feedback}
Tulis penjelasannya sekarang."""


def validate(text: str, facts: dict) -> list:
    failed = []
    low = text.lower()
    allowed_dates = {facts["date_id"], facts["target_id"]}
    allowed_iso = {facts["date"], facts["target"]}
    if any(m not in allowed_dates for m in _DATE_RE.findall(text)) or \
            any(m not in allowed_iso for m in _ISO_RE.findall(text)):
        failed.append("tanggal_valid")
    allowed_nums = set(_NUM_RE.findall(facts_text(facts)))
    if any(n not in allowed_nums for n in _NUM_RE.findall(text)):
        failed.append("angka_valid")
    if facts["prob"] not in text:
        failed.append("skor_disebut")
    m = re.search(r"prediksi\w*[^.]*?\b(naik|turun)\b", text, re.I | re.S)
    if not m or m.group(1).lower() != facts["direction"].lower():
        failed.append("label_benar")
    if sum(1 for t in facts["top"] if t["label"].lower() in low) < 2:
        failed.append("fitur_disebut")
    if _FORBIDDEN_RE.search(text):
        failed.append("kata_terlarang")
    if "bukan saran investasi" not in low:
        failed.append("disclaimer")
    if "belum terbukti lebih baik dari tebakan acak" not in low:
        failed.append("keterbatasan")
    if not any(u in low for u in _UNCERTAIN):
        failed.append("ketidakpastian")
    if not 40 <= len(text.split()) <= 170:
        failed.append("panjang")
    return failed


def _join(items: list) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return " dan ".join(items)
    return ", ".join(items[:-1]) + ", dan " + items[-1]


def template_narrative(f: dict) -> str:
    parts = [f"Pada {f['date_id']}, Model F memberi probabilitas naik {f['prob']} terhadap ambang keputusan "
             f"{f['threshold']}, sehingga prediksinya {f['direction'].lower()} untuk {f['target_id']}."]
    if f.get("level"):
        parts.append(f"Tingkat keyakinannya {f['level']}.")
    items = [f"{t['label']} ({t['delta']} poin persentase)" for t in f["top"]]
    if items:
        parts.append("Fitur yang paling memengaruhi skor adalah " + _join(items) + ".")
    parts.append("Model belum terbukti lebih baik dari tebakan acak pada data uji, sehingga hasil ini tidak pasti "
                 "dan bisa keliru. Ini bukan saran investasi.")
    return " ".join(parts)


def generate_narrative(client, facts: dict, retries: int = 3) -> dict:
    ftxt, feedback, temperature = facts_text(facts), "", 0.1
    for attempt in range(1, retries + 1):
        kw = {"model": MODEL, "max_tokens": 400,
              "messages": [{"role": "user", "content": NARRATIVE_PROMPT.format(facts=ftxt, feedback=feedback)}]}
        try:
            resp = client.messages.create(temperature=temperature, **kw) if temperature is not None \
                else client.messages.create(**kw)
        except Exception as e:  # noqa: BLE001
            if temperature is not None and "temperature" in str(e).lower():
                temperature = None            # API menolak suhu: lanjut dengan suhu bawaan, statusnya dicatat
                try:
                    resp = client.messages.create(**kw)
                except Exception:  # noqa: BLE001
                    continue
            else:
                continue
        text = resp.content[0].text.strip()
        failed = validate(text, facts)
        if not failed:
            return {"text": text, "source": "llm", "attempts": attempt, "temperature": temperature}
        feedback = "\nPERBAIKI: percobaan sebelumnya gagal pada pemeriksaan: " + ", ".join(failed) + "."
    return {"text": template_narrative(facts), "source": "template", "attempts": retries, "temperature": temperature}
