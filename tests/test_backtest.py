import math

import numpy as np
import pytest

from app.backtest import (GRID, BacktestError, buy_and_hold, check_not_collapsed, equity_curve, select_threshold, sensitivity,
                          simulate)


def test_simulate_long_only_toy_example_matches_hand_calculation():
    prob = [0.9, 0.1, 0.9, 0.9]
    ret = [0.10, -0.05, 0.02, -0.01]
    r = simulate(prob, ret, threshold=0.5, capital=1000.0)
    assert r["final_equity"] == pytest.approx(1000 * 1.10 * 1.02 * 0.99)               # 1110.78: tunai di hari ke-2 (tak ikut turun)
    assert r["total_return_pct"] == pytest.approx(11.078)
    assert r["n_trades"] == 2 and r["days_in_market_pct"] == pytest.approx(75.0)
    assert r["win_rate_pct"] == pytest.approx(100.0)
    assert r["avg_win_pct"] == pytest.approx((10.0 + (1.02 * 0.99 - 1) * 100) / 2)       # per TRANSAKSI (rentetan hari long), bukan per hari
    assert r["avg_loss_pct"] is None
    assert r["max_drawdown_pct"] == pytest.approx((1110.78 / 1122.0 - 1) * 100)         # puncak 1122 -> 1110,78
    daily = np.array([0.10, 0.0, 0.02, -0.01])
    assert r["sharpe"] == pytest.approx(daily.mean() / daily.std(ddof=1) * math.sqrt(365))   # rf = 0, tahunan 365 hari


def test_simulate_counts_a_losing_trade_and_win_rate():
    r = simulate([0.9, 0.1, 0.9], [-0.04, 0.03, 0.06], 0.5)
    assert r["n_trades"] == 2 and r["win_rate_pct"] == pytest.approx(50.0)
    assert r["avg_loss_pct"] == pytest.approx(-4.0) and r["avg_win_pct"] == pytest.approx(6.0)


def test_simulate_never_in_the_market_is_flat_and_has_no_ratios():
    r = simulate([0.1, 0.2, 0.3], [0.05, 0.05, 0.05], 0.5)
    assert r["final_equity"] == 1000.0 and r["total_return_pct"] == 0.0 and r["n_trades"] == 0
    assert r["win_rate_pct"] is None and r["sharpe"] is None and r["max_drawdown_pct"] == 0.0


def test_signal_is_strictly_greater_than_threshold():
    assert simulate([0.5], [0.1], 0.5)["n_trades"] == 0                                  # prob == ambang bukan sinyal beli


def test_buy_and_hold_compounds_every_day_and_is_a_single_trade():
    r = buy_and_hold([0.10, -0.05, 0.02], capital=1000.0)
    assert r["final_equity"] == pytest.approx(1000 * 1.10 * 0.95 * 1.02)
    assert r["n_trades"] == 1 and r["days_in_market_pct"] == 100.0
    assert r["max_drawdown_pct"] == pytest.approx(-5.0)


def test_select_threshold_maximizes_final_equity_on_validation_and_breaks_ties_toward_half():
    prob = np.array([0.30, 0.60, 0.80])
    ret = np.array([-0.10, 0.10, 0.10])                                                  # beli hanya di prob > 0.30 -> hindari kerugian pertama
    best = select_threshold(prob, ret)
    assert best["threshold"] == pytest.approx(0.50)                                      # seri 0,30-0,55 (sama-sama 1210): yang terdekat ke 0,5
    assert best["final_equity"] == pytest.approx(1000 * 1.1 * 1.1)
    tie = select_threshold(np.array([0.01]), np.array([0.01]))                          # prob di bawah seluruh grid: tak pernah ada sinyal, semua sama (1000)
    assert tie["threshold"] == pytest.approx(0.50)                                       # seri: dekat 0,5


def test_grid_is_005_to_090_step_005():
    assert GRID[0] == pytest.approx(0.05) and GRID[-1] == pytest.approx(0.90) and len(GRID) == 18


def test_sensitivity_has_one_row_per_grid_point_with_metrics():
    rows = sensitivity(np.array([0.2, 0.6, 0.8]), np.array([0.01, 0.02, -0.03]))
    assert [r["threshold"] for r in rows] == [pytest.approx(g) for g in GRID]
    assert {"final_equity", "total_return_pct", "sharpe", "max_drawdown_pct", "n_trades"} <= set(rows[0])
    assert rows[-1]["n_trades"] == 0                                                     # ambang 0,90: tak ada sinyal


def test_equity_curve_has_initial_capital_point_then_one_point_per_day():
    c = equity_curve(["2026-01-01", "2026-01-02"], [0.9, 0.9], [0.10, 0.10], 0.5, capital=1000.0)
    assert c["date"] == ["2026-01-01", "2026-01-02", "2026-01-03"]                       # hasil hari berikutnya dicatat pada hari terjadinya
    assert c["model"] == pytest.approx([1000.0, 1100.0, 1210.0]) and c["buy_hold"] == pytest.approx([1000.0, 1100.0, 1210.0])


def test_collapse_check_rejects_a_model_that_always_predicts_one_class():
    actual = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
    ok = check_not_collapsed(actual, np.array([1, 0, 1, 0, 1, 1, 0, 0, 1, 0]))
    assert ok["collapsed"] is False and 0.15 <= ok["recall"] <= 0.85
    bad = check_not_collapsed(actual, np.ones(10, dtype=int))
    assert bad["collapsed"] is True and bad["recall"] == 1.0
    with pytest.raises(BacktestError, match="runtuh"):
        check_not_collapsed(actual, np.zeros(10, dtype=int), strict=True)


# ---- v2: biaya transaksi (fee per sisi), uji sinyal-digeser, CI selisih Sharpe ----
from app.backtest import FEE, daily_returns, shift_test, sharpe_diff_ci   # noqa: E402


def test_default_fee_is_010_percent_cost_plus_005_percent_slippage_per_side():
    assert FEE == pytest.approx(0.0015)


def test_simulate_charges_the_fee_on_every_entry_and_exit_and_counts_transactions():
    r = simulate([0.9, 0.1, 0.9, 0.9], [0.10, -0.05, 0.02, -0.01], 0.5, capital=1000.0, fee=0.01)
    # posisi [1,0,1,1]; pergantian [1,1,1,0] -> return harian [0,10-1, 0-1, 2-1, -1]%
    assert r["final_equity"] == pytest.approx(1000 * 1.09 * 0.99 * 1.01 * 0.99)
    assert r["n_transactions"] == 3 and r["n_trades"] == 2
    free = simulate([0.9, 0.1, 0.9, 0.9], [0.10, -0.05, 0.02, -0.01], 0.5, capital=1000.0)
    assert free["n_transactions"] == 3 and free["final_equity"] > r["final_equity"]


def test_fee_zero_leaves_every_existing_result_unchanged():
    a = simulate([0.9, 0.1, 0.9], [0.1, 0.05, -0.02], 0.5)
    b = simulate([0.9, 0.1, 0.9], [0.1, 0.05, -0.02], 0.5, fee=0.0)
    assert a == b


def test_buy_and_hold_pays_one_entry_fee_only():
    r = buy_and_hold([0.10, -0.05], capital=1000.0, fee=0.01)
    assert r["final_equity"] == pytest.approx(1000 * 1.09 * 0.95) and r["n_transactions"] == 1


def test_a_trade_is_net_of_entry_and_exit_fees():
    r = simulate([0.9, 0.1], [0.10, 0.0], 0.5, fee=0.01)                                  # masuk +10%, keluar hari ke-2
    assert r["avg_win_pct"] == pytest.approx((1.10 * 0.99 * 0.99 - 1) * 100)


def test_daily_returns_match_the_simulated_equity():
    pos = np.array([1, 1, 0, 1], dtype=float)
    ret = np.array([0.01, -0.02, 0.03, 0.04])
    r = daily_returns(pos, ret, fee=0.005)
    assert r == pytest.approx([0.01 - 0.005, -0.02, -0.005, 0.04 - 0.005])


def test_shift_test_compares_the_model_with_circularly_shifted_signals_of_the_same_exposure():
    rng = np.random.default_rng(0)
    ret = rng.normal(0, 0.02, 120)
    prob = np.where(ret > 0, 0.7, 0.3)                                                    # sinyal sempurna: tahu return besok
    out = shift_test(prob, ret, 0.5, fee=0.0)
    assert out["total"]["p"] < 0.05 and out["total"]["model"] > out["total"]["median_random"]
    noise = shift_test(rng.uniform(0, 1, 120), ret, 0.5, fee=0.0)
    assert 0.0 <= noise["total"]["p"] <= 1.0 and noise["n_shifts"] == 120 - 20


def test_sharpe_diff_ci_is_zero_for_identical_series_and_ordered_otherwise():
    r = np.random.default_rng(1).normal(0.001, 0.02, 100)
    assert sharpe_diff_ci(r, r) == pytest.approx([0.0, 0.0])
    lo, hi = sharpe_diff_ci(r, r * 0.5 + 0.002)
    assert lo < hi
