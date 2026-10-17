from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.features import compute_features, chart_frame
from app.store import atomic_write_json, frame_to_columns


def synthetic_prices(end: date, n=400, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    dates = pd.date_range(end=pd.Timestamp(end), periods=n)
    return pd.DataFrame({"date": dates, "close": close})


class FakePredictor:
    def __init__(self):
        self.frames = []

    def predict(self, frame):
        self.frames.append(frame.copy())
        return {1: {"prob": 0.6, "threshold": 0.4557, "direction": "NAIK"},
                3: {"prob": 0.45, "threshold": 0.5, "direction": "TURUN"}}


def _explain_block():
    from app.explain import build_facts, feature_rows, rank_contributions, template_narrative
    from app.inference import FEATURE_ORDER
    stats = {"quantiles": {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}}
    deltas = np.linspace(-3, 3, 13)
    feats, contrib = feature_rows({f: 5.0 for f in FEATURE_ORDER}, stats), rank_contributions(deltas)
    rec = {"date": "2026-10-14", "target_date": "2026-10-15", "prob": 0.52, "threshold": 0.4557, "level": "tinggi",
           "features": feats, "contributions": contrib}
    return {"headlines": [{"title": f"Judul berita {i}"} for i in range(3)],
            "sentiment": {"has_news": True, "scores": {"pemahaman": 3, "detail": 2, "bullbear": 1, "mean": 2.0}, "used": 1.67},
            "contributions": contrib, "features": feats, "level": "tinggi",
            "narrative": {"text": template_narrative(build_facts(rec, auc=0.52)), "source": "llm",
                          "attempts": 1, "temperature": 0.1}}


def seed_live_dir(live_dir, content_dir, as_of=date(2026, 10, 14), demo=False, explain=True):
    """Isi live_dir dan content_dir dengan data sintetis yang bentuknya sama dengan keluaran job."""
    prices = synthetic_prices(as_of)
    prices.to_csv(live_dir / "prices.csv", index=False)
    feats = compute_features(prices)
    atomic_write_json(live_dir / "chart.json", frame_to_columns(chart_frame(feats)))
    atomic_write_json(live_dir / "latest.json", {
        **({"demo": True} if demo else {}),
        **({"explain": _explain_block()} if explain else {}),
        "as_of": as_of.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "close": round(float(prices.close.iloc[-1]), 2), "change_pct": -1.33,
        "inputs": {"news_sentiment": 1.67, "news_sentiment_raw": 2.0, "headline_count": 5, "fear_greed_index": 63.0},
        "horizons": {
            "1": {"prob": 0.52, "threshold": 0.4557, "direction": "NAIK",
                  "target_date": (as_of + timedelta(days=1)).isoformat()},
            "7": {"prob": 0.44, "threshold": 0.5, "direction": "TURUN",
                  "target_date": (as_of + timedelta(days=7)).isoformat()}}})
    hist = []
    for i in range(10, 0, -1):
        d = as_of - timedelta(days=i)
        hist.append({"date": d.isoformat(), "close": 1.0, "horizons": {
            "1": {"prob": 0.5, "threshold": 0.4557, "direction": "NAIK",
                  "actual": "NAIK" if i % 2 else "TURUN", "correct": bool(i % 2)},
            "7": {"prob": 0.4, "threshold": 0.5, "direction": "TURUN"}}})
    atomic_write_json(live_dir / "history.json", hist)
    atomic_write_json(content_dir / "multihorizon_evidence.json", {
        "7": {"auc": 0.515, "ci_lo": 0.42, "ci_hi": 0.61, "p_holm": 1.0, "significant": False,
              "label": "Belum terbukti lebih baik dari tebakan acak"}})
    atomic_write_json(content_dir / "ablation.json", [
        {"Model": "A", "Deskripsi": "Logistic Regression", "N Fitur": 11, "Accuracy": 0.4942,
         "Precision": 0.4848, "Recall": 0.3738, "F1-Weighted": 0.4870},
        {"Model": "F", "Deskripsi": "LSTM + Sentimen + F&G", "N Fitur": 13, "Accuracy": 0.51,
         "Precision": 0.5, "Recall": 0.5, "F1-Weighted": 0.5}])
    atomic_write_json(content_dir / "multiseed.json", [
        {"Model": "B", "F1 Mean": 0.48732, "F1 Std": 0.051882}, {"Model": "F", "F1 Mean": 0.49, "F1 Std": 0.03}])
    atomic_write_json(content_dir / "multihorizon.json", [
        {"H": 3, "n_efektif": 143.3, "AUC_F": 0.5, "CI_lo": 0.431, "CI_hi": 0.567, "p_geser": 0.5035,
         "p_Holm_m8": 1.0, "signifikan_Holm_m8": False},
        {"H": 30, "n_efektif": 13.0, "AUC_F": 0.622, "CI_lo": 0.4, "CI_hi": 0.8, "p_geser": 0.1,
         "p_Holm_m8": 1.0, "signifikan_Holm_m8": False}])
    atomic_write_json(content_dir / "holding_period.json", [
        {"H": 7, "subset": "seluruh data", "n_jendela": 5759, "pct_positif": 55.4, "median_pct": 0.9,
         "p5_pct": -14.7, "p95_pct": 23.4, "terburuk_pct": -70.4}])
    atomic_write_json(content_dir / "permutation_importance.json", [
        {"Fitur": "Vol_30", "Baseline F1": 0.49, "Penurunan F1 (Importance)": 0.0287, "Std": 0.0088},
        {"Fitur": "MACD_Histogram", "Baseline F1": 0.49, "Penurunan F1 (Importance)": 0.0226, "Std": 0.0076}])
    atomic_write_json(content_dir / "significance.json", {
        "mcnemar": [{"a": "A", "b": "C", "p": 0.6465, "verdict": "tidak signifikan", "only_a": 82, "only_b": 89}],
        "wilcoxon": [{"a": "C", "b": "F", "statistic": 5.0, "p": 0.625, "verdict": "tidak signifikan",
                      "mean_a": 0.4658, "mean_b": 0.4455}]})
    return feats


def seed_prices_only(live_dir, as_of=date(2026, 10, 14)):
    """Seperti keluaran `jobs --prices-only`: prices.csv + chart.json, tanpa latest.json."""
    prices = synthetic_prices(as_of)
    prices.to_csv(live_dir / "prices.csv", index=False)
    atomic_write_json(live_dir / "chart.json", frame_to_columns(chart_frame(compute_features(prices))))


SENT3_COLS = ["news_sentiment_pemahaman", "news_sentiment_detail", "news_sentiment_bullbear"]


def synthetic_retro_inputs(n_days=460, start="2025-01-01", seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n_days)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n_days)))
    prices = pd.DataFrame({"date": dates, "close": close})
    sent3 = pd.DataFrame({"date": dates, **{c: rng.integers(-5, 6, n_days).astype(float) for c in SENT3_COLS}})
    no_news = set(range(150, 153)) | set(range(5, n_days, 17))          # 3 hari berturut-turut + hari acak tanpa berita
    rows = [(d, f"judul {i}-{k}", "cryptocompare") for i, d in enumerate(dates) if i not in no_news for k in range(7)]
    news = pd.DataFrame(rows, columns=["date", "title", "source"])
    fg = pd.DataFrame({"date": dates, "fear_greed_index": rng.integers(10, 90, n_days).astype(float)})
    return {"prices": prices, "sent3": sent3, "news": news, "fg": fg, "no_news": no_news, "dates": dates,
            "start": dates[100], "end": dates[-2]}


class FakeRetroModel:
    """prob = 0.3 + 0.4 * (Fear&Greed terskala hari terakhir jendela): deterministik dan bergantung pada fitur ke-13."""
    def predict(self, W, verbose=0):
        return (0.3 + 0.4 * np.asarray(W)[:, -1, 12])[:, None]


def fit_scaler(inputs):
    from sklearn.preprocessing import RobustScaler
    from scripts.build_retro import assemble_table, split_table
    from app.features import TECH_FEATURES
    table = assemble_table(inputs["prices"], inputs["sent3"], set(pd.to_datetime(inputs["news"]["date"]).dt.normalize()),
                           inputs["fg"])
    train, _, _ = split_table(table, inputs["start"], inputs["end"])
    return RobustScaler().fit(train[TECH_FEATURES + ["news_sentiment"]])


def seed_retro(content_dir):
    """Tulis content/retro/ dengan skema nyata (dari build_outputs + model tiruan) untuk tes API dan e2e."""
    from pathlib import Path
    from app.explain import build_facts, template_narrative
    from scripts.build_retro import build_outputs, write_outputs
    inp = synthetic_retro_inputs()
    out = build_outputs(inp["prices"], inp["sent3"], inp["news"], inp["fg"], fit_scaler(inp), FakeRetroModel(), 0.5,
                        start=inp["start"], end=inp["end"], allow_mismatch=True)
    for k in list(out["days"])[:3]:
        rec = out["days"][k]
        rec["narrative"] = {"text": template_narrative(build_facts(rec, auc=out["series"]["auc"])),
                            "source": "llm", "attempts": 1, "temperature": 0.1}
    write_outputs(Path(content_dir) / "retro", out)
    return out
