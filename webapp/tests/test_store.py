import json
from datetime import date

import numpy as np
import pandas as pd

from app.store import (append_news, append_sentiment, atomic_write_json, evaluate_history,
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


def test_upsert_adds_new_dates_sorted():
    h = [{"date": "2026-10-13", "horizons": {}}, {"date": "2026-10-14", "horizons": {}}]
    h = upsert_history(h, {"date": "2026-10-12", "horizons": {}})
    assert [e["date"] for e in h] == ["2026-10-12", "2026-10-13", "2026-10-14"]


def test_upsert_never_overwrites_an_issued_prediction_but_may_add_new_horizons():
    old = {"date": "2026-10-13", "close": 100.0, "horizons": {"1": {"prob": 0.6, "direction": "NAIK", "threshold": 0.5}}}
    new = {"date": "2026-10-13", "close": 999.0, "backfilled": True, "horizons": {
        "1": {"prob": 0.3, "direction": "TURUN", "threshold": 0.5}, "3": {"prob": 0.7, "direction": "NAIK", "threshold": 0.5}}}
    out = upsert_history([old], new)
    assert out[0]["close"] == 100.0 and "backfilled" not in out[0]               # penerbitan pertama yang berlaku
    assert out[0]["horizons"]["1"] == {"prob": 0.6, "direction": "NAIK", "threshold": 0.5}
    assert out[0]["horizons"]["3"]["direction"] == "NAIK"                         # horizon baru boleh ditambahkan
    assert old["horizons"].get("3") is None                                       # tidak memutasi masukan


def test_evaluate_history_fills_only_matured_horizons():
    prices = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=5),
                           "close": [100, 101, 99, 105, 98]})
    hist = [{"date": "2026-10-01", "horizons": {
        "1": {"direction": "NAIK"}, "3": {"direction": "NAIK"}, "7": {"direction": "TURUN"}}}]
    out = evaluate_history(hist, prices)
    h = out[0]["horizons"]
    assert h["1"] == {"direction": "NAIK", "actual": "NAIK", "correct": True, "locked": True}   # dikunci setelah dibandingkan
    assert h["3"]["actual"] == "NAIK" and h["3"]["correct"] is True   # 105 > 100
    assert "actual" not in h["7"] and "locked" not in h["7"]           # belum jatuh tempo: belum dikunci


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


def test_evaluated_result_is_final_even_if_prices_are_later_revised():
    prices = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=2), "close": [100, 101]})
    hist = evaluate_history([{"date": "2026-10-01", "horizons": {"1": {"direction": "NAIK"}}}], prices)
    revised = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=2), "close": [100, 90]})
    again = evaluate_history(hist, revised)
    assert again[0]["horizons"]["1"] == {"direction": "NAIK", "actual": "NAIK", "correct": True, "locked": True}


def test_old_evaluated_entries_without_flag_get_locked():
    prices = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=2), "close": [100, 101]})
    hist = [{"date": "2026-10-01", "horizons": {"1": {"direction": "NAIK", "actual": "NAIK", "correct": True}}}]
    assert evaluate_history(hist, prices)[0]["horizons"]["1"]["locked"] is True


def test_append_news_stores_urls_only_when_any_exists(tmp_path):
    append_news(tmp_path, date(2026, 10, 14), ["A", "B"], None, urls=["https://x.com/a", None])
    append_news(tmp_path, date(2026, 10, 15), ["C"], None, urls=[None])
    append_news(tmp_path, date(2026, 10, 16), ["D"], None)
    log = read_json(tmp_path / "news_log.json")
    assert log["2026-10-14"]["urls"] == ["https://x.com/a", None] and log["2026-10-14"]["titles"] == ["A", "B"]
    assert "urls" not in log["2026-10-15"] and "urls" not in log["2026-10-16"]
