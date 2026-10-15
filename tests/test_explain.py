import numpy as np
import pytest
from sklearn.preprocessing import RobustScaler

from app.explain import (FEATURE_LABELS, build_facts, contributions_batch, date_id, facts_text, feature_rows,
                         level_cuts, level_of, rank_contributions, reliability_table, replacement_vector, wilson)
from app.inference import FEATURE_ORDER


class OneFeatureModel:
    """prob = 0.5 + 0.1 * rata-rata fitur ke-j sepanjang jendela (hanya satu fitur berpengaruh)."""
    def __init__(self, j):
        self.j = j

    def predict(self, X, verbose=0):
        return (0.5 + 0.1 * X[:, :, self.j].mean(axis=1))[:, None]


def stats():
    return {"quantiles": {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}}


def test_only_the_influential_feature_has_nonzero_delta():
    j = FEATURE_ORDER.index("RSI14")
    X = np.full((2, 20, 13), 2.0, dtype="float32")
    d = contributions_batch(OneFeatureModel(j), X, replacement_vector(stats()))
    assert d.shape == (2, 13)
    # p0 = 0.5 + 0.2 = 0.7; RSI14 diganti 0 (tanpa scaler) -> 0.5; delta = 20
    assert d[0, j] == pytest.approx(20.0, abs=1e-4)
    assert np.allclose(np.delete(d, j, axis=1), 0.0)


def test_replacement_vector_without_scaler_is_zero_plus_fg_median():
    rep = replacement_vector(stats())
    assert rep.shape == (13,) and rep[:12].tolist() == [0.0] * 12 and rep[12] == pytest.approx(5.0)


def test_replacement_vector_with_scaler_maps_train_median_to_zero():
    import pandas as pd
    rng = np.random.default_rng(0)
    cols = list(FEATURE_ORDER[:12])
    df = pd.DataFrame(rng.normal(3, 2, (301, 12)), columns=cols)
    sc = RobustScaler().fit(df)
    st = {"quantiles": {f: [float(np.median(df[f]))] * 101 for f in cols}}
    st["quantiles"]["fear_greed_index_scaled"] = [0.4] * 101
    rep = replacement_vector(st, sc)
    assert np.allclose(rep[:12], 0.0, atol=1e-6) and rep[12] == pytest.approx(0.4)


def test_rank_contributions_sorted_by_abs_with_labels():
    rows = rank_contributions(np.array([1.0, -5.0, 3.0] + [0.0] * 10))
    assert [r["feature"] for r in rows[:3]] == [FEATURE_ORDER[1], FEATURE_ORDER[2], FEATURE_ORDER[0]]
    assert rows[0]["delta_pp"] == -5.0 and rows[0]["label"] == FEATURE_LABELS[FEATURE_ORDER[1]]
    assert len(rows) == 13


def test_wilson_reference_values():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(10, 10)[1] == pytest.approx(1.0, abs=1e-9)


def test_levels_and_reliability_table():
    margins = np.array([0.01, 0.02, 0.05, 0.06, 0.09, 0.10])
    cuts = level_cuts(margins)
    assert level_of(0.01, cuts) == "rendah" and level_of(0.05, cuts) == "sedang" and level_of(0.10, cuts) == "tinggi"
    thr = 0.4557
    prob = thr + np.array([0.01, -0.02, 0.05, -0.06, 0.09, -0.10])
    correct = np.array([True, False, True, True, False, True])
    tab = reliability_table(prob, thr, correct)
    assert [r["level"] for r in tab] == ["rendah", "sedang", "tinggi"]
    assert [r["n"] for r in tab] == [2, 2, 2]
    for r in tab:
        assert r["ci_lo"] <= r["accuracy"] <= r["ci_hi"] and isinstance(r["includes_chance"], bool)


def test_feature_rows_percentile_category_and_outside_range():
    vals = {f: 5.0 for f in FEATURE_ORDER}
    vals["RSI14"], vals["MA7"], vals["Vol_7"] = 11.0, -1.0, 1.0
    rows = {r["feature"]: r for r in feature_rows(vals, stats())}
    assert rows["MA30"]["percentile"] == 50 and rows["MA30"]["category"] == "sedang"
    assert rows["RSI14"]["outside_train_range"] is True and rows["RSI14"]["percentile"] == 100
    assert rows["RSI14"]["category"] == "tinggi"
    assert rows["MA7"]["outside_train_range"] is True and rows["MA7"]["percentile"] == 0
    assert rows["MA7"]["category"] == "rendah" and rows["Vol_7"]["percentile"] == 10
    assert all(r["value_text"] for r in rows.values())


def _rec(prob=0.5193, thr=0.4557):
    vals = {f: 5.0 for f in FEATURE_ORDER}
    deltas = np.zeros(13)
    deltas[FEATURE_ORDER.index("Vol_30")], deltas[FEATURE_ORDER.index("RSI14")] = 3.24, -2.1
    deltas[FEATURE_ORDER.index("MACD")] = 1.05
    return {"date": "2026-02-16", "target_date": "2026-02-17", "prob": prob, "threshold": thr, "level": "tinggi",
            "features": feature_rows(vals, stats()), "contributions": rank_contributions(deltas)}


def test_build_facts_and_text_are_formatted_in_indonesian():
    f = build_facts(_rec(), auc=0.52)
    assert f["date_id"] == "16 Februari 2026" == date_id("2026-02-16") and f["target_id"] == "17 Februari 2026"
    assert f["prob"] == "0,5193" and f["threshold"] == "0,4557" and f["margin"] == "0,0636"
    assert f["direction"] == "NAIK" and f["auc"] == "0,5200"
    assert [t["label"] for t in f["top"]] == [FEATURE_LABELS["Vol_30"], FEATURE_LABELS["RSI14"], FEATURE_LABELS["MACD"]]
    assert f["top"][0]["delta"] == "+3,2" and f["top"][1]["delta"] == "-2,1"
    txt = facts_text(f)
    assert "probabilitas naik (skor model): 0,5193" in txt and "tingkat keyakinan: tinggi" in txt
    assert build_facts(_rec(prob=0.40))["direction"] == "TURUN"


def test_zero_heavy_feature_value_zero_is_not_called_high():
    q = [0.0] * 44 + [float(x) for x in np.linspace(0.1, 5, 57)]          # 44 titik nol + 57 naik = 101 titik
    st = stats()
    st["quantiles"]["news_sentiment"] = q
    vals = {f: 5.0 for f in FEATURE_ORDER}
    vals["news_sentiment"] = 0.0
    row = {r["feature"]: r for r in feature_rows(vals, st)}["news_sentiment"]
    assert row["category"] != "tinggi" and row["percentile"] < 40         # persentil tengah, bukan batas atas gumpalan nol


def test_facts_and_template_flag_days_without_news():
    from app.explain import template_narrative, validate
    rec = _rec()
    rec["sentiment"] = {"has_news": False, "scores": None, "used": 0.0}
    f = build_facts(rec)
    assert f["has_news"] is False and "tidak ada berita bersih" in facts_text(f).lower()
    t = template_narrative(f)
    assert "tidak ada berita" in t.lower() and validate(t, f) == []
    f2 = build_facts(_rec())
    assert f2["has_news"] is True and "tidak ada berita" not in template_narrative(f2).lower()
