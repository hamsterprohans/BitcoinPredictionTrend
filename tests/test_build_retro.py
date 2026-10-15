import numpy as np
import pandas as pd
import pytest

from scripts.build_retro import (ParityError, assemble_table, check_parity, metrics, predict_split, scaled_matrix,
                                 split_table)
from tests.factories import FakeRetroModel, SENT3_COLS, fit_scaler, synthetic_retro_inputs

IN = synthetic_retro_inputs()
NEWS_DAYS = set(pd.to_datetime(IN["news"]["date"]).dt.normalize())


def table():
    return assemble_table(IN["prices"], IN["sent3"], NEWS_DAYS, IN["fg"])


def test_label_alignment_and_last_row_dropped():
    t = table()
    close = IN["prices"].set_index("date")["close"]
    for d in (t["date"].iloc[10], t["date"].iloc[-1]):
        assert t.loc[t["date"] == d, "label"].iloc[0] == int(close[d + pd.Timedelta(days=1)] > close[d])
    assert t["date"].max() == IN["dates"][-2]                       # hari terakhir tidak punya label


def test_news_sentiment_mean_ffill_two_days_then_zero():
    t = table().set_index("date")
    d = IN["dates"]
    mean = lambda i: IN["sent3"].iloc[i][SENT3_COLS].mean()
    assert t.loc[d[149], "news_sentiment"] == pytest.approx(mean(149))
    assert t.loc[d[150], "news_sentiment"] == pytest.approx(mean(149))      # ffill hari ke-1
    assert t.loc[d[151], "news_sentiment"] == pytest.approx(mean(149))      # ffill hari ke-2
    assert t.loc[d[152], "news_sentiment"] == 0.0                           # lebih dari 2 hari -> 0
    assert not t.loc[d[150], "has_news"] and t.loc[d[149], "has_news"]


def test_fear_greed_scaled_is_plain_division_by_100():
    t = table()
    assert np.allclose(t["fear_greed_index_scaled"] * 100, t["fear_greed_index"])


def test_split_sizes_follow_notebook_rounding():
    t = table()
    tr, va, te = split_table(t, IN["start"], IN["end"])
    n = len(tr) + len(va) + len(te)
    assert len(tr) == round(n * 0.70) and len(tr) + len(va) == round(n * 0.85)
    assert tr["date"].max() < va["date"].min() and va["date"].max() < te["date"].min()


def test_windows_stay_inside_the_test_split():
    t = table()
    tr, va, te = split_table(t, IN["start"], IN["end"])
    sc = fit_scaler(IN)
    rows, prob, W = predict_split(te, sc, FakeRetroModel(), 0.5)
    assert len(rows) == len(te) - 19 == len(prob) == len(W)
    assert rows["date"].iloc[0] == te["date"].iloc[19]                       # prediksi pertama = hari ke-20 split uji
    X = scaled_matrix(te, sc)
    assert np.allclose(W[0], X[:20]) and W.shape[1:] == (20, 13)
    assert rows["date"].min() > va["date"].max()                              # tidak ada jendela yang menyentuh val
    assert (rows["label"].to_numpy() == te["label"].iloc[19:].to_numpy()).all()


def test_scaled_matrix_clips_and_keeps_fear_greed_unscaled():
    t = table()
    t.loc[t.index[-1], "Vol_7"] = 1e9
    X = scaled_matrix(t, fit_scaler(IN))
    assert np.abs(X[:, :12]).max() <= 5.0 + 1e-9
    assert np.allclose(X[:, 12], t["fear_greed_index_scaled"].to_numpy())


def test_parity_pass_and_fail_messages():
    got = {"Accuracy": 0.5012, "F1-Weighted": 0.4994}
    check_parity(got, {"Accuracy": 0.5013, "F1-Weighted": 0.4990})            # dalam 0,002
    with pytest.raises(ParityError) as e:
        check_parity(got, {"Accuracy": 0.5500, "F1-Weighted": 0.4994})
    assert "0.5012" in str(e.value) and "0.5500" in str(e.value) and "Accuracy" in str(e.value)


def test_metrics_values():
    m = metrics(np.array([1, 0, 1, 1]), np.array([1, 0, 0, 1]))
    assert m["Accuracy"] == pytest.approx(0.75) and 0.0 <= m["F1-Weighted"] <= 1.0
