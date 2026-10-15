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
