"""Simulasi backtesting sesuai proposal (Bab 3.1.9): strategi long-only, modal awal $1.000, tanpa biaya transaksi dan slippage.

Beli pada hari prediksi NAIK (probabilitas > ambang), tunai pada hari TURUN. Sinyal hari t dieksekusi pada penutupan t dan
menghasilkan return penutupan t -> t+1. Pembanding: buy and hold. Sharpe: rata-rata/simpangan baku (ddof=1) return harian,
risk-free 0, dianualkan dengan akar 365 (kripto diperdagangkan setiap hari).
"""
import math
from datetime import date, timedelta

import numpy as np

GRID = np.round(np.arange(0.05, 0.9001, 0.05), 2)           # grid ambang trading 0,05-0,90
CAPITAL = 1000.0


class BacktestError(RuntimeError):
    pass


def _runs(mask):
    """Rentetan hari berurutan bernilai True -> daftar (awal, akhir_eksklusif)."""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        if not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def simulate(prob, next_ret, threshold, capital: float = CAPITAL) -> dict:
    prob, next_ret = np.asarray(prob, dtype=float), np.asarray(next_ret, dtype=float)
    pos = prob > threshold
    daily = np.where(pos, next_ret, 0.0)
    equity = capital * np.concatenate([[1.0], np.cumprod(1.0 + daily)])
    dd = equity / np.maximum.accumulate(equity) - 1.0
    trades = [float(np.prod(1.0 + next_ret[a:b]) - 1.0) for a, b in _runs(pos)]
    wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
    sd = daily.std(ddof=1) if len(daily) > 1 else 0.0
    return {
        "final_equity": float(equity[-1]),
        "total_return_pct": float((equity[-1] / capital - 1.0) * 100.0),
        "n_trades": len(trades),
        "win_rate_pct": None if not trades else 100.0 * len(wins) / len(trades),
        "avg_win_pct": None if not wins else 100.0 * float(np.mean(wins)),
        "avg_loss_pct": None if not losses else 100.0 * float(np.mean(losses)),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "sharpe": None if sd == 0 else float(daily.mean() / sd * math.sqrt(365)),
        "days_in_market_pct": float(pos.mean() * 100.0),
    }


def buy_and_hold(next_ret, capital: float = CAPITAL) -> dict:
    return simulate(np.ones(len(next_ret)), next_ret, 0.5, capital)


def select_threshold(prob, next_ret, grid=GRID, capital: float = CAPITAL) -> dict:
    """Ambang trading yang memaksimalkan modal akhir (dipakai pada data VALIDASI). Seri: yang paling dekat 0,5, lalu yang terendah."""
    best = None
    for g in grid:
        r = simulate(prob, next_ret, float(g), capital)
        key = (-round(r["final_equity"], 9), abs(float(g) - 0.5), float(g))
        if best is None or key < best[0]:
            best = (key, {"threshold": float(g), **r})
    return best[1]


def sensitivity(prob, next_ret, grid=GRID, capital: float = CAPITAL) -> list:
    out = []
    for g in grid:
        r = simulate(prob, next_ret, float(g), capital)
        out.append({"threshold": float(g), **{k: r[k] for k in
                    ("final_equity", "total_return_pct", "sharpe", "max_drawdown_pct", "n_trades")}})
    return out


def equity_curve(dates, prob, next_ret, threshold, capital: float = CAPITAL) -> dict:
    """Kurva ekuitas: titik awal = modal pada tanggal sinyal pertama; hasil hari berikutnya dicatat pada hari terjadinya."""
    prob, next_ret = np.asarray(prob, dtype=float), np.asarray(next_ret, dtype=float)
    model = capital * np.concatenate([[1.0], np.cumprod(1.0 + np.where(prob > threshold, next_ret, 0.0))])
    hold = capital * np.concatenate([[1.0], np.cumprod(1.0 + next_ret)])
    days = [dates[0]] + [(date.fromisoformat(d) + timedelta(days=1)).isoformat() for d in dates]
    return {"date": days, "model": [round(float(v), 2) for v in model], "buy_hold": [round(float(v), 2) for v in hold]}


def check_not_collapsed(actual, pred, strict: bool = False, lo: float = 0.15, hi: float = 0.85) -> dict:
    """Pemeriksaan proposal: model tidak boleh runtuh ke satu kelas (recall kelas NAIK di luar 0,15-0,85)."""
    actual, pred = np.asarray(actual), np.asarray(pred)
    pos = actual == 1
    recall = float((pred[pos] == 1).mean()) if pos.any() else float("nan")
    collapsed = bool(not (lo <= recall <= hi))
    if collapsed and strict:
        raise BacktestError(f"Model runtuh ke satu kelas (recall {recall:.3f} di luar {lo}-{hi}); backtest tidak bermakna")
    return {"recall": recall, "collapsed": collapsed, "range": [lo, hi]}
