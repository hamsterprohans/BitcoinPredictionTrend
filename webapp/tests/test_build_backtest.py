import numpy as np
import pandas as pd
import pytest

from app.backtest import GRID, buy_and_hold, select_threshold, simulate
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
    sim = simulate(tp, tr["next_return"].to_numpy(), expected["threshold"])
    assert out["model"]["final_equity"] == pytest.approx(sim["final_equity"])                  # diterapkan ke periode UJI


def test_buy_and_hold_and_classification_threshold_variants_are_reported():
    out = run()
    _, _, tr, tp = parts()
    ret = tr["next_return"].to_numpy()
    assert out["buy_and_hold"]["final_equity"] == pytest.approx(buy_and_hold(ret)["final_equity"])
    assert out["model_at_classification_threshold"]["final_equity"] == pytest.approx(simulate(tp, ret, THR)["final_equity"])
    assert out["classification_threshold"] == THR
    assert out["capital"] == 1000.0 and out["strategy"] == "long-only" and "tanpa biaya" in out["costs"]


def test_sensitivity_covers_the_whole_grid_and_curve_has_n_plus_one_points():
    out = run()
    assert [r["threshold"] for r in out["sensitivity"]] == [pytest.approx(g) for g in GRID]
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
    for part in ("bukan", "forward", "biaya transaksi", "validasi"):
        assert part in text, part
