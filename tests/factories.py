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


def seed_live_dir(live_dir, content_dir, as_of=date(2026, 10, 14)):
    """Isi live_dir dan content_dir dengan data sintetis yang bentuknya sama dengan keluaran job."""
    prices = synthetic_prices(as_of)
    feats = compute_features(prices)
    atomic_write_json(live_dir / "chart.json", frame_to_columns(chart_frame(feats)))
    atomic_write_json(live_dir / "latest.json", {
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
    return feats
