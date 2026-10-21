"""Bangun data dashboard retrospektif dari data scrap lokal + model F terekspor.

Pemakaian: python -m scripts.build_retro [--allow-mismatch] [--narratives]
Meniru notebook (10): sel 2.1-2.3, 3.3, 4.1-4.4 (tabel, split 70/15/15, jendela 20 hari di dalam split).
"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from app import config
from app.features import TECH_FEATURES, compute_features

SENT3 = ["news_sentiment_pemahaman", "news_sentiment_detail", "news_sentiment_bullbear"]
NB_START, NB_END = "2018-02-01", "2026-04-30"


class ParityError(RuntimeError):
    pass


def assemble_table(prices, sent3, news_days, fg) -> pd.DataFrame:
    df = compute_features(prices)
    df["next_return"] = df["close"].pct_change().shift(-1)
    df["label"] = (df["next_return"] > 0).astype(int)
    df = df.dropna(subset=TECH_FEATURES + ["next_return"]).reset_index(drop=True)

    g = fg.copy()
    g["date"] = pd.to_datetime(g["date"])
    df = df.merge(g[["date", "fear_greed_index"]], on="date", how="left")
    df["fear_greed_index"] = df["fear_greed_index"].ffill(limit=2).fillna(50)
    df["fear_greed_index_scaled"] = df["fear_greed_index"] / 100.0

    s = sent3.copy()
    s["date"] = pd.to_datetime(s["date"])
    df = df.merge(s[["date"] + SENT3], on="date", how="left")
    has_news = df["date"].isin(news_days).to_numpy()
    tmp = df[SENT3].copy()
    tmp.loc[~has_news, :] = np.nan                                  # hari tanpa berita bersih -> NaN (bukan 0)
    df["news_sentiment"] = tmp.mean(axis=1).ffill(limit=2).fillna(0)
    df["has_news"] = has_news
    return df


def split_table(df, start=NB_START, end=NB_END):
    d = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].reset_index(drop=True)
    n = len(d)
    n_train, n_val_end = int(round(n * 0.70)), int(round(n * 0.85))
    return d.iloc[:n_train].copy(), d.iloc[n_train:n_val_end].copy(), d.iloc[n_val_end:].copy()


def scaled_matrix(df, scaler) -> np.ndarray:
    cols = TECH_FEATURES + ["news_sentiment"]
    scaled = np.clip(scaler.transform(df[cols]), -config.CLIP_VAL, config.CLIP_VAL)
    return np.hstack([scaled, df[["fear_greed_index_scaled"]].to_numpy()])


def predict_split(df_split, scaler, model, threshold, seq_len=config.SEQ_LEN):
    X = scaled_matrix(df_split, scaler)
    W = np.stack([X[i:i + seq_len] for i in range(len(X) - seq_len + 1)]).astype("float32")
    prob = np.asarray(model.predict(W, verbose=0)).ravel()
    return df_split.iloc[seq_len - 1:].reset_index(drop=True), prob, W


def metrics(actual, pred) -> dict:
    return {"Accuracy": float(accuracy_score(actual, pred)),
            "F1-Weighted": float(f1_score(actual, pred, average="weighted", zero_division=0))}


def check_parity(got: dict, expected: dict, tol: float = 0.002) -> None:
    bad = {k: (got[k], expected[k]) for k in ("Accuracy", "F1-Weighted") if abs(got[k] - expected[k]) > tol}
    if bad:
        raise ParityError("Hasil hitung ulang berbeda dari tabel notebook (toleransi %.3f): " % tol +
                          "; ".join(f"{k}: hitung ulang {a:.4f} vs notebook {b:.4f}" for k, (a, b) in bad.items()))


import argparse  # noqa: E402
import os  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from sklearn.metrics import roc_auc_score  # noqa: E402

from app import explain  # noqa: E402
from app.inference import FEATURE_ORDER  # noqa: E402
from app.store import atomic_write_json, read_json  # noqa: E402


def train_stats(train_df) -> dict:
    qs = np.linspace(0, 100, 101)
    return {"quantiles": {f: [float(x) for x in np.percentile(train_df[f].to_numpy(dtype=float), qs)]
                          for f in FEATURE_ORDER}}


def build_outputs(prices, sent3, news, fg, scaler, model, threshold, *, start=NB_START, end=NB_END,
                  expected=None, allow_mismatch=False, tol=0.002) -> dict:
    news = news.assign(date=pd.to_datetime(news["date"]).dt.normalize())
    table = assemble_table(prices, sent3, set(news["date"]), fg)
    train, _val, test = split_table(table, start, end)
    rows, prob, W = predict_split(test, scaler, model, threshold)
    pred = (prob > threshold).astype(int)
    actual = rows["label"].to_numpy()
    got = metrics(actual, pred)

    parity = {"verified": False, "got": got, "expected": expected, "tolerance": tol}
    if expected is None:
        if not allow_mismatch:
            raise ParityError("Tabel notebook (content/ablation.json, baris Model F) tidak tersedia: "
                              "paritas tidak dapat diverifikasi.")
    else:
        try:
            check_parity(got, expected, tol)
            parity["verified"] = True
        except ParityError:
            if not allow_mismatch:
                raise

    stats = train_stats(train)
    deltas = explain.contributions_batch(model, W, explain.replacement_vector(stats, scaler))
    margins = np.abs(prob - threshold)
    cuts = explain.level_cuts(margins)
    correct = pred == actual
    by_date = {d: list(zip(g["title"], g["source"])) for d, g in news.groupby("date", sort=False)}
    names = {1: "NAIK", 0: "TURUN"}

    days = {}
    for i, r in rows.iterrows():
        iso = r["date"].strftime("%Y-%m-%d")
        values = {f: float(r[f]) for f in FEATURE_ORDER}
        has = bool(r["has_news"])
        scores = {k: float(r[c]) for k, c in zip(("pemahaman", "detail", "bullbear"), SENT3)}
        ok_scores = has and not any(np.isnan(v) for v in scores.values())
        days[iso] = {
            "date": iso, "target_date": (r["date"] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "close": float(r["close"]), "prob": float(prob[i]), "threshold": float(threshold),
            "direction": names[int(pred[i])], "actual": names[int(actual[i])], "correct": bool(correct[i]),
            "level": explain.level_of(float(margins[i]), cuts), "margin": float(margins[i]),
            "features": explain.feature_rows(values, stats),
            "contributions": explain.rank_contributions(deltas[i]),
            "headlines": [{"title": t, "source": s} for t, s in by_date.get(r["date"], [])[:5]],
            "sentiment": {"has_news": has,
                          "scores": {**scores, "mean": float(np.mean(list(scores.values())))} if ok_scores else None,
                          "used": float(r["news_sentiment"])},
            "narrative": None,
        }
    both = len(np.unique(actual)) == 2
    series = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "threshold": float(threshold), "n": int(len(rows)), "accuracy": got["Accuracy"],
        "auc": float(roc_auc_score(actual, prob)) if both else None,
        "level_cuts": cuts, "parity": parity,
        "date": [d for d in days], "close": [round(float(x), 2) for x in rows["close"]],
        "prob": [round(float(x), 6) for x in prob], "pred": [int(x) for x in pred],
        "actual": [int(x) for x in actual], "correct": [bool(x) for x in correct],
        "reliability": explain.reliability_table(prob, threshold, correct, cuts),
    }
    return {"series": series, "days": days, "stats": stats}


def _facts_key(rec: dict):
    top3 = tuple((c["feature"], round(c["delta_pp"], 1)) for c in rec["contributions"][:3])
    return (round(rec["prob"], 6), round(rec["threshold"], 6), rec["direction"], rec.get("level"),
            bool((rec.get("sentiment") or {}).get("has_news", True)), top3)


def write_outputs(out_dir, out: dict) -> None:
    out_dir = Path(out_dir)
    days_dir = out_dir / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_dir / "series.json", out["series"])
    atomic_write_json(out_dir / "train_stats.json", out["stats"])
    for iso, rec in out["days"].items():
        old = read_json(days_dir / f"{iso}.json")
        if old and old.get("narrative") and _facts_key(old) == _facts_key(rec):
            rec["narrative"] = old["narrative"]               # fakta tidak berubah: pertahankan narasi yang sudah dibayar
        atomic_write_json(days_dir / f"{iso}.json", rec)
    for f in days_dir.glob("*.json"):                          # buang sisa build lama yang bukan bagian seri ini
        if f.stem not in out["days"]:
            f.unlink()


def fill_narratives(out_dir, client, redo_template: bool = False) -> int:
    out_dir = Path(out_dir)
    auc = read_json(out_dir / "series.json", {}).get("auc")
    made = 0
    for f in sorted((out_dir / "days").glob("*.json")):
        rec = read_json(f)
        nar = rec.get("narrative")
        if nar and not (redo_template and nar.get("source") == "template"):
            continue
        rec["narrative"] = explain.generate_narrative(client, explain.build_facts(rec, auc=auc))
        atomic_write_json(f, rec)
        made += 1
        print(f"narasi {rec['date']} ({rec['narrative']['source']})", flush=True)
    return made


def load_fear_greed_full(cache_path, http=None) -> pd.DataFrame:
    cache_path = Path(cache_path)
    if cache_path.exists():
        return pd.read_csv(cache_path, parse_dates=["date"])
    import httpx
    from app import sources
    with (http or httpx.Client(timeout=30, follow_redirects=True)) as c:
        df = sources.fetch_fear_greed(c, limit=0)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-mismatch", action="store_true", help="tetap tulis walau paritas gagal (ditandai verified=false)")
    ap.add_argument("--narratives", action="store_true", help="buat narasi (Claude Haiku) untuk hari yang belum punya")
    ap.add_argument("--redo-template", action="store_true", help="dengan --narratives: buat ulang narasi yang jatuh ke template")
    args = ap.parse_args(argv)
    from app import jobs
    from app.inference import Predictor
    from app.sources import read_price_tsv

    jobs._load_dotenv()
    data = config.ROOT / "data"
    out_dir = config.CONTENT_DIR / "retro"
    if not (out_dir / "series.json").exists() or not args.narratives:
        try:
            pred = Predictor.from_artifacts()
        except RuntimeError as e:                              # ArtifactsMissing: pesan jelas, bukan traceback
            raise SystemExit(str(e))
        abl = read_json(config.CONTENT_DIR / "ablation.json", [])
        row = next((r for r in abl if r.get("Model") == "F"), None)
        expected = {"Accuracy": row["Accuracy"], "F1-Weighted": row["F1-Weighted"]} if row else None
        out = build_outputs(read_price_tsv(config.SEED_PRICE_TSV), pd.read_csv(data / "sentiment_cache_new.csv"),
                            pd.read_csv(data / "news_bitcoin_clean.csv", usecols=["date", "title", "source"]),
                            load_fear_greed_full(config.WEBAPP / "data" / "cache" / "fear_greed_full.csv"),
                            pred.scaler, pred.models[1][0], pred.thresholds[1],
                            expected=expected, allow_mismatch=args.allow_mismatch)
        write_outputs(out_dir, out)
        p = out["series"]["parity"]
        print(f"ditulis: {out_dir} ({out['series']['n']} hari uji); paritas terverifikasi: {p['verified']} "
              f"(hitung ulang {p['got']}, notebook {p['expected']})")
    if args.narratives:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY belum diset (environment variable atau .env)")
        try:
            print("narasi baru:", fill_narratives(out_dir, anthropic.Anthropic(api_key=key), redo_template=args.redo_template))
        except explain.FatalAPIError as e:
            raise SystemExit(f"API Anthropic menolak permintaan: {e}\nIsi saldo atau periksa key, lalu jalankan ulang perintah yang sama (dapat dilanjutkan).")


if __name__ == "__main__":
    main()
