import numpy as np
import pandas as pd
import pytest

from app.backtest import FEE, GRID, buy_and_hold, daily_returns, select_threshold, sensitivity, simulate
from scripts.build_backtest import build_backtest_outputs
from scripts.build_retro import assemble_table, build_outputs, predict_split, split_table
from tests.factories import FakeRetroModel, fit_scaler, synthetic_retro_inputs

IN = synthetic_retro_inputs()
SCALER = fit_scaler(IN)
THR = 0.5


def run(**kw):
    return build_backtest_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], SCALER, FakeRetroModel(), THR,
                                  start=IN["start"], end=IN["end"], **kw)


def parts():
    table = assemble_table(IN["prices"], IN["sent3"], set(pd.to_datetime(IN["news"]["date"]).dt.normalize()), IN["fg"])
    _, val, test = split_table(table, IN["start"], IN["end"])
    vr, vp, _ = predict_split(val, SCALER, FakeRetroModel(), THR)
    tr, tp, _ = predict_split(test, SCALER, FakeRetroModel(), THR)
    return vr, vp, tr, tp


def test_trading_threshold_is_chosen_on_validation_only_then_applied_to_test():
    out = run()
    vr, vp, tr, tp = parts()
    expected = select_threshold(vp, vr["next_return"].to_numpy())
    assert out["trading_threshold"]["value"] == pytest.approx(expected["threshold"])
    assert out["trading_threshold"]["selected_on"] == "validasi"
    assert out["trading_threshold"]["val_final_equity"] == pytest.approx(expected["final_equity"])
    sim = simulate(tp, tr["next_return"].to_numpy(), expected["threshold"], fee=FEE)
    assert out["model"]["final_equity"] == pytest.approx(sim["final_equity"])                  # diterapkan ke periode UJI


def test_buy_and_hold_and_classification_threshold_variants_are_reported():
    out = run()
    _, _, tr, tp = parts()
    ret = tr["next_return"].to_numpy()
    assert out["buy_and_hold"]["final_equity"] == pytest.approx(buy_and_hold(ret, fee=FEE)["final_equity"])
    assert out["model_at_classification_threshold"]["final_equity"] == pytest.approx(simulate(tp, ret, THR, fee=FEE)["final_equity"])
    assert out["classification_threshold"] == THR
    assert out["capital"] == 1000.0 and out["strategy"] == "long-only"


def test_backtest_v2_charges_transaction_costs_and_says_so():
    out = run()
    assert out["version"] == 2 and out["fee_per_side"] == FEE
    assert "biaya transaksi" in out["costs"] and "tanpa biaya" not in out["costs"] and "0,15%" in out["costs"]
    _, _, tr, tp = parts()
    ret = tr["next_return"].to_numpy()
    free = simulate(tp, ret, THR)
    assert out["model_at_classification_threshold"]["final_equity"] <= free["final_equity"] + 1e-9           # biaya tidak menambah modal
    assert out["model_at_classification_threshold"]["n_transactions"] == free["n_transactions"]


def test_half_threshold_variant_permutation_comparison_and_sharpe_ci_are_reported():
    out = run()
    _, _, tr, tp = parts()
    ret = tr["next_return"].to_numpy()
    assert out["model_at_half"]["final_equity"] == pytest.approx(simulate(tp, ret, 0.5, fee=FEE)["final_equity"])
    perm = out["permutation"]
    assert set(perm) >= {"total", "sharpe", "n_shifts"} and 0.0 <= perm["total"]["p"] <= 1.0 and perm["n_shifts"] == len(ret) - 20
    assert perm["total"]["model"] == pytest.approx(out["model_at_classification_threshold"]["total_return_pct"] / 100, abs=1e-9)
    lo, hi = out["sharpe_diff_ci"]
    assert lo <= hi and out["permutation"]["basis"] == "ambang klasifikasi"


def test_every_strategy_is_flagged_when_it_is_in_the_market_all_the_time():
    out = run()
    for key in ("model", "model_at_classification_threshold", "model_at_half"):
        assert out[key]["identical_to_buy_and_hold"] == (out[key]["days_in_market_pct"] > 99.0)


def test_sensitivity_covers_the_whole_grid_and_curve_has_n_plus_one_points():
    out = run()
    assert [r["threshold"] for r in out["sensitivity"]] == [pytest.approx(g) for g in GRID]
    _, _, tr0, tp0 = parts()
    assert out["sensitivity"][3]["final_equity"] == pytest.approx(sensitivity(tp0, tr0["next_return"].to_numpy(), fee=FEE)[3]["final_equity"])
    n = out["period"]["n_days"]
    c = out["curve"]
    assert len(c["date"]) == n + 1 == len(c["model"]) == len(c["buy_hold"]) == len(c["model_classification"])
    assert c["model"][0] == c["buy_hold"][0] == c["model_classification"][0] == 1000.0
    assert c["model_classification"][-1] == pytest.approx(out["model_at_classification_threshold"]["final_equity"], abs=0.01)
    assert out["curve"]["buy_hold"][-1] == pytest.approx(out["buy_and_hold"]["final_equity"], abs=0.01)
    assert out["curve"]["model"][-1] == pytest.approx(out["model"]["final_equity"], abs=0.01)


def test_period_matches_the_retrospective_test_series_exactly():
    retro = build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], SCALER, FakeRetroModel(), THR,
                          start=IN["start"], end=IN["end"], allow_mismatch=True)["series"]
    out = run(retro_series=retro)
    assert out["period"]["n_days"] == retro["n"]
    assert out["period"]["start"] == retro["date"][0] and out["period"]["end"] == retro["date"][-1]
    assert out["parity_with_retro"] == {"checked": True, "max_abs_prob_diff": pytest.approx(0.0, abs=1e-6)}


def test_mismatch_with_the_retrospective_probabilities_is_reported_not_hidden():
    retro = {"n": 3, "date": ["2025-01-01"], "prob": [0.9, 0.9, 0.9]}
    out = run(retro_series=retro)
    assert out["parity_with_retro"]["checked"] is False and "tidak sama" in out["parity_with_retro"]["note"]


def test_collapse_check_and_caveats_are_included():
    out = run()
    assert set(out["checks"]) >= {"recall", "collapsed"}
    text = " ".join(out["caveats"]).lower()
    for part in ("bukan", "forward", "biaya transaksi", "validasi", "asumsi", "geser"):
        assert part in text, part
