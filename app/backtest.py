"""Simulasi backtesting sesuai proposal (Bab 3.1.9): strategi long-only, modal awal $1.000. Versi 2: biaya transaksi dan slippage
per sisi (FEE) dibebankan pada setiap pergantian posisi (masuk dan keluar); fee=0 memberi hasil tanpa biaya (versi 1).

Beli pada hari prediksi NAIK (probabilitas > ambang), tunai pada hari TURUN. Sinyal hari t dieksekusi pada penutupan t dan
menghasilkan return penutupan t -> t+1. Pembanding: buy and hold. Sharpe: rata-rata/simpangan baku (ddof=1) return harian,
risk-free 0, dianualkan dengan akar 365 (kripto diperdagangkan setiap hari).
"""
import math
from datetime import date, timedelta

import numpy as np

GRID = np.round(np.arange(0.05, 0.9001, 0.05), 2)           # grid ambang trading 0,05-0,90
CAPITAL = 1000.0
FEE = 0.001 + 0.0005                                        # 0,10% biaya + 0,05% slippage per sisi (asumsi, bukan data bursa)


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


def _turnover(pos):
    return np.abs(np.diff(np.concatenate([[0.0], np.asarray(pos, dtype=float)])))     # mulai dari tunai


def daily_returns(pos, next_ret, fee: float = 0.0):
    """Return harian bersih: posisi x return hari itu, dikurangi fee pada hari terjadinya pergantian posisi."""
    pos = np.asarray(pos, dtype=float)
    return pos * np.asarray(next_ret, dtype=float) - _turnover(pos) * fee


def simulate(prob, next_ret, threshold, capital: float = CAPITAL, fee: float = 0.0) -> dict:
    prob, next_ret = np.asarray(prob, dtype=float), np.asarray(next_ret, dtype=float)
    pos = prob > threshold
    turn = _turnover(pos)
    daily = daily_returns(pos, next_ret, fee)
    equity = capital * np.concatenate([[1.0], np.cumprod(1.0 + daily)])
    dd = equity / np.maximum.accumulate(equity) - 1.0
    runs = _runs(pos)
    # satu transaksi = satu rentetan hari long; bersih dari biaya masuk dan (bila sempat keluar) biaya keluar
    trades = [float(np.prod(1.0 + next_ret[a:b]) * (1.0 - fee) * ((1.0 - fee) if b < len(pos) else 1.0) - 1.0) for a, b in runs]
    wins, losses = [t for t in trades if t > 0], [t for t in trades if t <= 0]
    sd = daily.std(ddof=1) if len(daily) > 1 else 0.0
    return {
        "final_equity": float(equity[-1]),
        "total_return_pct": float((equity[-1] / capital - 1.0) * 100.0),
        "n_trades": len(trades),
        "n_transactions": int(turn.sum()),
        "win_rate_pct": None if not trades else 100.0 * len(wins) / len(trades),
        "avg_win_pct": None if not wins else 100.0 * float(np.mean(wins)),
        "avg_loss_pct": None if not losses else 100.0 * float(np.mean(losses)),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "sharpe": None if sd == 0 else float(daily.mean() / sd * math.sqrt(365)),
        "days_in_market_pct": float(pos.mean() * 100.0),
    }


def buy_and_hold(next_ret, capital: float = CAPITAL, fee: float = 0.0) -> dict:
    return simulate(np.ones(len(next_ret)), next_ret, 0.5, capital, fee)


def _sharpe(r):
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(365)) if sd > 0 else float("nan")


def shift_test(prob, next_ret, threshold, fee: float = 0.0, min_shift: int = 10) -> dict:
    """p-value pembanding acak: sinyal digeser sirkular (jumlah transaksi dan eksposur tetap) lalu disimulasikan.
    p = proporsi sinyal geser yang hasilnya >= model. Satu jalur sejarah, jadi ini pembanding kasar, bukan bukti kinerja."""
    prob, next_ret = np.asarray(prob, dtype=float), np.asarray(next_ret, dtype=float)
    s0 = (prob > threshold).astype(float)
    n = len(s0)

    def stats(pos):
        r = daily_returns(pos, next_ret, fee)
        return float(np.prod(1.0 + r) - 1.0), _sharpe(r)
    model = stats(s0)
    sims = np.array([stats(np.roll(s0, sh)) for sh in range(min_shift, n - min_shift)])
    out = {"n_shifts": int(len(sims))}
    for i, key in enumerate(("total", "sharpe")):
        v = sims[:, i]
        out[key] = {"model": model[i], "median_random": float(np.nanmedian(v)), "p": float((v >= model[i]).mean())}
    return out


def sharpe_diff_ci(r_a, r_b, block: int = 10, B: int = 3000, seed: int = 0) -> list:
    """CI 95% selisih Sharpe (a - b) dengan moving-block bootstrap atas hari (blok menjaga korelasi antarhari)."""
    r_a, r_b = np.asarray(r_a, dtype=float), np.asarray(r_b, dtype=float)
    g = np.random.default_rng(seed)
    n = len(r_a)
    nb = int(math.ceil(n / block))
    out = []
    for _ in range(B):
        ix = np.concatenate([np.arange(s, s + block) for s in g.integers(0, n - block + 1, nb)])[:n]
        out.append(_sharpe(r_a[ix]) - _sharpe(r_b[ix]))
    return [float(x) for x in np.nanpercentile(out, [2.5, 97.5])]


def select_threshold(prob, next_ret, grid=GRID, capital: float = CAPITAL) -> dict:
    """Ambang trading yang memaksimalkan modal akhir (dipakai pada data VALIDASI). Seri: yang paling dekat 0,5, lalu yang terendah."""
    best = None
    for g in grid:
        r = simulate(prob, next_ret, float(g), capital)
        key = (-round(r["final_equity"], 9), abs(float(g) - 0.5), float(g))
        if best is None or key < best[0]:
            best = (key, {"threshold": float(g), **r})
    return best[1]


def sensitivity(prob, next_ret, grid=GRID, capital: float = CAPITAL, fee: float = 0.0) -> list:
    out = []
    for g in grid:
        r = simulate(prob, next_ret, float(g), capital, fee)
        out.append({"threshold": float(g), **{k: r[k] for k in
                    ("final_equity", "total_return_pct", "sharpe", "max_drawdown_pct", "n_trades")}})
    return out


def equity_curve(dates, prob, next_ret, threshold, capital: float = CAPITAL, fee: float = 0.0) -> dict:
    """Kurva ekuitas: titik awal = modal pada tanggal sinyal pertama; hasil hari berikutnya dicatat pada hari terjadinya."""
    prob, next_ret = np.asarray(prob, dtype=float), np.asarray(next_ret, dtype=float)
    model = capital * np.concatenate([[1.0], np.cumprod(1.0 + daily_returns(prob > threshold, next_ret, fee))])
    hold = capital * np.concatenate([[1.0], np.cumprod(1.0 + daily_returns(np.ones(len(next_ret)), next_ret, fee))])
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
