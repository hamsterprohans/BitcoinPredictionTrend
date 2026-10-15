import json
from datetime import date

import numpy as np
import pandas as pd

from app.store import (append_sentiment, atomic_write_json, evaluate_history,
                       frame_to_columns, load_sentiment_log, read_json, upsert_history)


def test_atomic_write_and_read(tmp_path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1})
    assert read_json(p) == {"a": 1}
    assert read_json(tmp_path / "none.json", default="d") == "d"
    assert not list(tmp_path.glob("*.tmp"))


def test_sentiment_log_roundtrip_with_nan(tmp_path):
    append_sentiment(tmp_path, date(2026, 10, 13), 2.5, 4)
    append_sentiment(tmp_path, date(2026, 10, 14), None, 0)
    log = load_sentiment_log(tmp_path)
    assert log.loc[pd.Timestamp("2026-10-13"), "raw"] == 2.5
    assert np.isnan(log.loc[pd.Timestamp("2026-10-14"), "raw"])
    assert log["count"].tolist() == [4, 0]


def test_sentiment_log_empty(tmp_path):
    assert load_sentiment_log(tmp_path).empty


def test_upsert_replaces_same_date_and_sorts():
    h = [{"date": "2026-10-13", "v": 1}, {"date": "2026-10-14", "v": 1}]
    h = upsert_history(h, {"date": "2026-10-13", "v": 2})
    h = upsert_history(h, {"date": "2026-10-12", "v": 3})
    assert [e["date"] for e in h] == ["2026-10-12", "2026-10-13", "2026-10-14"]
    assert h[1]["v"] == 2


def test_evaluate_history_fills_only_matured_horizons():
    prices = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=5),
                           "close": [100, 101, 99, 105, 98]})
    hist = [{"date": "2026-10-01", "horizons": {
        "1": {"direction": "NAIK"}, "3": {"direction": "NAIK"}, "7": {"direction": "TURUN"}}}]
    out = evaluate_history(hist, prices)
    h = out[0]["horizons"]
    assert h["1"] == {"direction": "NAIK", "actual": "NAIK", "correct": True}
    assert h["3"]["actual"] == "NAIK" and h["3"]["correct"] is True   # 105 > 100
    assert "actual" not in h["7"]                                      # belum jatuh tempo


def test_frame_to_columns_nan_to_null_and_json_safe():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-10-01", "2026-10-02"]),
                       "x": [1.234567, np.nan]})
    cols = frame_to_columns(df)
    assert cols == {"date": ["2026-10-01", "2026-10-02"], "x": [1.2346, None]}
    json.dumps(cols)


def test_news_log_roundtrip(tmp_path):
    from app.store import append_news, read_news_entry
    scores = {"pemahaman": 1, "detail": 2, "bullbear": 3, "mean": 2.0}
    append_news(tmp_path, date(2026, 10, 14), ["a", "b"], scores)
    append_news(tmp_path, date(2026, 10, 13), ["c"], None)
    assert read_news_entry(tmp_path, date(2026, 10, 14)) == {"titles": ["a", "b"], "scores": scores}
    assert read_news_entry(tmp_path, date(2026, 10, 13))["scores"] is None
    assert read_news_entry(tmp_path, date(2026, 1, 1)) is None
