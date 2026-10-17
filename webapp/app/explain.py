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
        left, right = np.searchsorted(q, v, side="left"), np.searchsorted(q, v, side="right")
        pct = int(np.clip(round((left + right) / 2 - 0.5), 0, 100))      # persentil tengah: gumpalan nol tidak jadi "tinggi"
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
            "has_news": (rec.get("sentiment") or {}).get("has_news", True),
            "auc": _id(auc, 4) if auc is not None else None, "top": top}


def facts_text(f: dict) -> str:
    lines = [f"tanggal: {f['date_id']}", f"tanggal target: {f['target_id']}",
             f"probabilitas naik (skor model): {f['prob']}", f"ambang keputusan: {f['threshold']}",
             f"selisih terhadap ambang: {f['margin']}", f"prediksi: {f['direction']}"]
    if f["level"]:
        lines.append(f"tingkat keyakinan: {f['level']}")
    if f["auc"]:
        lines.append(f"AUC uji historis: {f['auc']}")
    if not f.get("has_news", True):
        lines.append("berita hari ini: tidak ada berita bersih (nilai sentimen hanya isian forward-fill atau netral)")
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
    r"\b\w*(?:beli|jual)\w*\b"
    r"|\b(?:buy\w*|sell\w*|short|long|hold|hodl|posisi|disarankan|dianjurkan|anjuran|rekomendasi|sebaiknya|dijamin|garansi"
    r"|karena|menyebabkan|mengakibatkan|akibat|disebabkan|penyebab)\b"
    r"|\bsaran\b(?! investasi)|(?<!tidak )\bpasti\w*", re.I)
_UNCERTAIN = ("tidak pasti", "ketidakpastian", "bisa keliru", "dapat keliru", "mungkin keliru")
_NUMBER_WORDS_RE = re.compile(
    r"\b(?:nol|sebelas|\w*belas|puluh|\w+puluh|ratus|ribu|juta)\b"
    r"|\b(?:nol|satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)\s+(?:persen|poin|kali|ribu|juta|dolar)\b", re.I)
_DATE_NOYEAR_RE = re.compile(rf"\b(\d{{1,2}} (?:{_MONTHS_RE}))\b(?! \d{{4}})")
_SENT_START = r"(?:^|[.!?]\s+)"
_LIMIT_RE = re.compile(_SENT_START + r"model belum terbukti lebih baik dari tebakan acak", re.I)
_DISC_RE = re.compile(_SENT_START + r"ini bukan saran investasi\.", re.I)
_KEYWORDS = ("probabilitas", "skor", "ambang")


NARRATIVE_PROMPT = """Anda menulis penjelasan singkat dalam Bahasa Indonesia untuk investor ritel tentang satu prediksi arah harga Bitcoin dari sebuah model penelitian.

ATURAN KETAT:
- Gunakan HANYA informasi pada BLOK FAKTA. Tulis angka persis seperti tertulis di sana (jangan membulatkan, jangan menghitung ulang, jangan menambah angka baru).
- Sebut tanggal, probabilitas (skor model), arah prediksi (naik atau turun), dan sedikitnya dua dari tiga fitur teratas.
- Untuk setiap fitur yang disebut, tulis pengaruhnya persis seperti di blok fakta, lengkap dengan tanda + atau - (contoh: "pengaruh -8,8 poin persentase").
- Jangan menyatakan sebab-akibat; fitur hanya "paling memengaruhi skor model".
- Jangan mengajak membeli atau menjual, dan jangan memakai kata beli, jual, pasti, dijamin, garansi, rekomendasi, sebaiknya.
- Wajib menulis kalimat persis: "Model belum terbukti lebih baik dari tebakan acak" dan kalimat persis: "Ini bukan saran investasi."
- Akui bahwa hasil ini tidak pasti dan bisa keliru.
- Jika BLOK FAKTA menyatakan tidak ada berita bersih, jangan menggambarkan sentimen sebagai berita hari itu.
- Panjang 60 sampai 140 kata, satu paragraf.

BLOK FAKTA:
{facts}
{feedback}
Tulis penjelasannya sekarang."""


def _nearest_keyword(text: str, idx: int, window: int = 60):
    seg = text[max(0, idx - window):idx].lower()
    best, best_pos = None, -1
    for k in _KEYWORDS:
        p = seg.rfind(k)
        if p > best_pos:
            best, best_pos = k, p
    return best


def _occurrences_paired(text: str, num: str, ok_words: tuple):
    occ = [m.start() for m in re.finditer(re.escape(num), text)]
    return bool(occ), all(_nearest_keyword(text, i) in ok_words for i in occ)


def _mentioned(text: str, labels: list) -> list:
    """Label fitur yang disebut utuh; label yang lebih panjang dihitung dulu agar "Sinyal MACD" tidak sekaligus "MACD"."""
    work, found = text.lower(), []
    for lab in sorted(labels, key=len, reverse=True):
        pat = re.compile(r"(?<!\w)" + re.escape(lab.lower()) + r"(?!\w)")
        if pat.search(work):
            found.append(lab)
            work = pat.sub(" " * len(lab), work)
    return found


def _direction_ok(text: str, direction: str) -> bool:
    cleaned = re.sub(r"probabilitas naik", "probabilitas ", text, flags=re.I)
    tokens = list(re.finditer(r"\b(naik|turun)\b", cleaned, re.I))
    if not tokens:
        return False
    for m in tokens:
        start = max(cleaned.rfind(". ", 0, m.start()), cleaned.rfind("\n", 0, m.start()))
        seg = cleaned[start + 1:m.start()].lower()
        negated = re.search(r"\b(?:bukan|tidak|belum)\b(?:\W+\w+){0,2}\W*$", seg)
        if "prediksi" not in seg or m.group(1).lower() != direction.lower() or negated:
            return False
    return True


def validate(text: str, facts: dict) -> list:
    failed = []
    text = text.replace("\u2212", "-")                      # minus Unicode dari LLM = minus biasa
    low = text.lower()
    allowed_dates = {facts["date_id"], facts["target_id"]}
    allowed_iso = {facts["date"], facts["target"]}
    allowed_day_month = {d.rsplit(" ", 1)[0] for d in allowed_dates}
    if any(m not in allowed_dates for m in _DATE_RE.findall(text)) or \
            any(m not in allowed_iso for m in _ISO_RE.findall(text)) or \
            any(m not in allowed_day_month for m in _DATE_NOYEAR_RE.findall(text)):
        failed.append("tanggal_valid")
    allowed_nums = set(_NUM_RE.findall(facts_text(facts)))
    if any(n not in allowed_nums for n in _NUM_RE.findall(text)) or _NUMBER_WORDS_RE.search(text):
        failed.append("angka_valid")
    has_prob, prob_ok = _occurrences_paired(text, facts["prob"], ("probabilitas", "skor"))
    has_thr, thr_ok = _occurrences_paired(text, facts["threshold"], ("ambang",))
    if not has_prob or not prob_ok or (has_thr and not thr_ok):
        failed.append("skor_disebut")
    if not _direction_ok(text, facts["direction"]):
        failed.append("label_benar")
    mentioned = _mentioned(text, [t["label"] for t in facts["top"]])
    if len(mentioned) < 2:
        failed.append("fitur_disebut")
    nums = set(_NUM_RE.findall(text))
    # angka pengaruh boleh tidak disebut; bila disebut, tandanya (+/-) harus sama dengan blok fakta
    if any(t["delta"].lstrip("+-") in nums and t["delta"] not in text for t in facts["top"] if t["label"] in mentioned):
        failed.append("tanda_pengaruh")
    if _FORBIDDEN_RE.search(text):
        failed.append("kata_terlarang")
    if not _DISC_RE.search(text.strip()):
        failed.append("disclaimer")
    if not _LIMIT_RE.search(text.strip()):
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
    if not f.get("has_news", True):
        parts.append("Tidak ada berita bersih pada hari itu, sehingga nilai sentimen hanya isian forward-fill atau netral.")
    parts.append("Model belum terbukti lebih baik dari tebakan acak pada data uji, sehingga hasil ini tidak pasti "
                 "dan bisa keliru. Ini bukan saran investasi.")
    return " ".join(parts)


class FatalAPIError(RuntimeError):
    """Galat tagihan/autentikasi API: bukan kegagalan validasi narasi, jadi proses harus berhenti dengan pesan jelas."""


def _is_fatal(e: Exception) -> bool:
    msg = str(e).lower()
    return (getattr(e, "status_code", None) in (401, 403) or "credit balance" in msg
            or "invalid x-api-key" in msg or "authentication" in msg)


def generate_narrative(client, facts: dict, retries: int = 3) -> dict:
    ftxt, feedback, temperature = facts_text(facts), "", 0.1
    for attempt in range(1, retries + 1):
        kw = {"model": MODEL, "max_tokens": 400,
              "messages": [{"role": "user", "content": NARRATIVE_PROMPT.format(facts=ftxt, feedback=feedback)}]}
        try:
            resp = client.messages.create(temperature=temperature, **kw) if temperature is not None \
                else client.messages.create(**kw)
        except Exception as e:  # noqa: BLE001
            if _is_fatal(e):
                raise FatalAPIError(str(e)) from e
            if temperature is not None and "temperature" in str(e).lower():
                temperature = None            # API menolak suhu: lanjut dengan suhu bawaan, statusnya dicatat
                try:
                    resp = client.messages.create(**kw)
                except Exception as e2:  # noqa: BLE001
                    if _is_fatal(e2):
                        raise FatalAPIError(str(e2)) from e2
                    continue
            else:
                continue
        text = resp.content[0].text.strip()
        failed = validate(text, facts)
        if not failed:
            return {"text": text, "source": "llm", "attempts": attempt, "temperature": temperature}
        feedback = "\nPERBAIKI: percobaan sebelumnya gagal pada pemeriksaan: " + ", ".join(failed) + "."
    return {"text": template_narrative(facts), "source": "template", "attempts": retries, "temperature": temperature}


def build_live_explain(*, predictor, frame, pred, news, as_of, stats, series=None, client=None) -> dict:
    from datetime import date, timedelta
    X = predictor.build_window(frame)
    deltas = contributions_batch(predictor.models[1][0], X, replacement_vector(stats, predictor.scaler))[0]
    last = frame.iloc[-1]
    values = {f: float(last[f]) for f in FEATURE_ORDER}
    feats, contrib = feature_rows(values, stats), rank_contributions(deltas)
    prob, thr = pred["prob"], pred["threshold"]
    level = level_of(abs(prob - thr), series["level_cuts"]) if series else None
    rec = {"date": as_of, "target_date": (date.fromisoformat(as_of) + timedelta(days=1)).isoformat(),
           "prob": prob, "threshold": thr, "level": level, "features": feats, "contributions": contrib}
    titles = (news or {}).get("titles", [])
    rec["sentiment"] = {"has_news": bool(titles)}
    narrative = generate_narrative(client, build_facts(rec, auc=(series or {}).get("auc"))) if client else None
    return {"headlines": [{"title": t} for t in titles],
            "sentiment": {"has_news": bool(titles), "scores": (news or {}).get("scores"),
                          "used": values["news_sentiment"]},
            "contributions": contrib, "features": feats, "level": level, "narrative": narrative}
