import pickle

import numpy as np
import pandas as pd
import pytest

from app import config
from app.features import TECH_FEATURES, assemble_frame, chart_frame, compute_features


def _prices(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"date": pd.date_range("2025-01-01", periods=n), "close": close})


def test_ma7_and_ranges():
    p = _prices()
    f = compute_features(p)
    assert list(f.columns[:2]) == ["date", "close"]
    assert f["MA7"].iloc[-1] == pytest.approx(p["close"].iloc[-7:].mean())
    assert f["RSI14"].dropna().between(0, 100).all()
    assert f["MA90"].iloc[:89].isna().all() and not np.isnan(f["MA90"].iloc[89])
    assert len(TECH_FEATURES) == 11


def test_bollinger_consistent_with_bb_width():
    f = compute_features(_prices())
    c = chart_frame(f).dropna()
    width = (c["BB_up"] - c["BB_dn"]) / c["BB_mid"]
    np.testing.assert_allclose(width, f.loc[c.index, "BB_width"], rtol=1e-9)


def test_assemble_frame_sentiment_ffill_and_fg_default():
    f = compute_features(_prices(120))
    last = f["date"].iloc[-1]
    idx = pd.date_range(last - pd.Timedelta(days=5), last)
    raw = pd.Series([5.0, np.nan, np.nan, np.nan, 2.0, np.nan], index=idx)
    fg = pd.DataFrame({"date": [last - pd.Timedelta(days=1)], "fear_greed_index": [80.0]})
    out = assemble_frame(f, raw, fg)
    tail = out.set_index("date").loc[idx]
    # ffill(limit=2): 5,5,5,0,2,2
    assert tail["news_sentiment"].tolist() == [5.0, 5.0, 5.0, 0.0, 2.0, 2.0]
    assert out["fear_greed_index_scaled"].iloc[-2] == pytest.approx(0.8)
    assert out["fear_greed_index_scaled"].iloc[-1] == pytest.approx(0.8)  # ffill 1 hari
    assert out["fear_greed_index_scaled"].iloc[-30] == pytest.approx(0.5)  # default 50


def test_parity_with_notebook_test_split():
    from app.sources import read_price_tsv  # modul dibuat di Task 4
    pkl = config.ARTIFACTS / "preprocessed.pkl"
    tsv = config.SEED_PRICE_TSV
    if not pkl.exists() or not tsv.exists():
        pytest.skip("preprocessed.pkl / coin_metrics.tsv tidak ada")
    test_df = pickle.load(open(pkl, "rb"))["test_df"]
    feats = compute_features(read_price_tsv(tsv))
    m = test_df[["date"] + TECH_FEATURES].merge(
        feats[["date"] + TECH_FEATURES], on="date", suffixes=("_nb", "_web"))
    assert len(m) == len(test_df)
    for f in TECH_FEATURES:
        np.testing.assert_allclose(m[f + "_web"], m[f + "_nb"], rtol=1e-6, atol=1e-9, err_msg=f)


def test_resample_prices_weekly_monthly_bars_dated_by_last_day():
    from app.features import resample_prices
    p = _prices(400)
    w, m = resample_prices(p, "W"), resample_prices(p, "M")
    assert len(w) < len(p) / 6 and len(m) < len(w) / 3
    assert w["date"].iloc[-1] == p["date"].iloc[-1] and w["close"].iloc[-1] == p["close"].iloc[-1]  # bar terakhir = hari terakhir
    assert (w["date"].iloc[:-1].dt.dayofweek == 6).all()                                        # minggu berakhir Minggu
    assert m["date"].is_monotonic_increasing and m["close"].iloc[-1] == p["close"].iloc[-1]
    with pytest.raises(ValueError):
        resample_prices(p, "H")
