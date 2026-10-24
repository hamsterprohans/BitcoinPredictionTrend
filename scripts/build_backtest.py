"""Bangun content/backtest.json: strategi model (long-only) vs buy and hold pada periode uji, sesuai proposal Bab 3.1.9.

Pemakaian: python -m scripts.build_backtest
Ambang trading dipilih dari grid 0,05-0,90 yang memaksimalkan modal akhir pada data VALIDASI, lalu disimulasikan pada data UJI
(periode dan prediksi yang sama dengan dashboard retrospektif; selisih probabilitas dilaporkan).
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app import config
from app.backtest import (CAPITAL, FEE, buy_and_hold, check_not_collapsed, daily_returns, equity_curve, select_threshold, sensitivity,
                          sharpe_diff_ci, shift_test, simulate)
from app.store import atomic_write_json, read_json
from scripts.build_retro import NB_END, NB_START, assemble_table, predict_split, split_table

COSTS = ("biaya transaksi 0,10% ditambah slippage 0,05% (total 0,15%) per sisi, dibebankan saat masuk dan keluar posisi; "
         "angka ini asumsi, bukan data bursa")


def _caveats(n: int) -> list:
    return [
        f"Simulasi pada data historis periode uji ({n} hari); bukan bukti kinerja di pasar nyata. Pembuktian memerlukan forward testing.",
        "Biaya transaksi dan slippage (0,15% per sisi) adalah asumsi, bukan data bursa; biaya nyata bisa lebih tinggi atau lebih rendah.",
        "Ambang trading dipilih dari data validasi (grid 0,05 sampai 0,90), bukan dari data uji, dan tanpa biaya. Tabel kepekaan menunjukkan perubahan hasil menurut ambang.",
        "Ambang trading yang dipilih di validasi membuat model berada di pasar hampir setiap hari, sehingga hasilnya sama dengan buy and hold dan tidak informatif.",
        "Satu jalur sejarah dan satu periode: lebih baik atau lebih buruknya hasil dibanding buy and hold bisa terjadi karena kebetulan. "
        "Pembandingnya sinyal yang digeser sirkular (jumlah transaksi dan eksposur sama); p-value besar berarti model tidak dapat dibedakan dari sinyal acak.",
        "Buy and hold = beli di awal periode uji dan ditahan sampai akhir. Sharpe ratio dianualkan dengan akar 365 (risk-free 0).",
    ]


def _parity(retro_series, test_prob) -> dict:
    if not retro_series:
        return {"checked": False, "note": "series retrospektif tidak tersedia untuk dibandingkan"}
    ref = np.asarray(retro_series.get("prob", []), dtype=float)
    if len(ref) != len(test_prob):
        return {"checked": False, "note": f"jumlah hari tidak sama dengan dashboard retrospektif ({len(ref)} vs {len(test_prob)})"}
    diff = float(np.max(np.abs(ref - test_prob))) if len(ref) else 0.0
    if diff > 1e-5:
        return {"checked": False, "note": f"probabilitas tidak sama dengan dashboard retrospektif (selisih maks {diff:.6f})"}
    return {"checked": True, "max_abs_prob_diff": diff}


def build_backtest_outputs(prices, sent3, news, fg, scaler, model, threshold, *, start=NB_START, end=NB_END,
                           retro_series=None, capital: float = CAPITAL, fee: float = FEE) -> dict:
    news = news.assign(date=pd.to_datetime(news["date"]).dt.normalize())
    table = assemble_table(prices, sent3, set(news["date"]), fg)
    _train, val, test = split_table(table, start, end)
    val_rows, val_prob, _ = predict_split(val, scaler, model, threshold)
    test_rows, test_prob, _ = predict_split(test, scaler, model, threshold)
    val_ret, test_ret = val_rows["next_return"].to_numpy(), test_rows["next_return"].to_numpy()

    best = select_threshold(val_prob, val_ret, capital=capital)                 # dipilih di VALIDASI
    trade_thr = best["threshold"]
    dates = [d.date().isoformat() for d in test_rows["date"]]
    pred_cls = (test_prob > threshold).astype(int)
    curve = equity_curve(dates, test_prob, test_ret, trade_thr, capital, fee)
    curve["model_classification"] = equity_curve(dates, test_prob, test_ret, threshold, capital, fee)["model"]   # varian pembanding

    def flagged(r):                                  # berada di pasar hampir setiap hari = identik buy and hold, tidak informatif
        return {**r, "identical_to_buy_and_hold": r["days_in_market_pct"] > 99.0}
    r_model = daily_returns(test_prob > threshold, test_ret, fee)
    r_hold = daily_returns(np.ones(len(test_ret)), test_ret, fee)
    return {
        "version": 2, "fee_per_side": fee,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "strategy": "long-only", "capital": capital, "costs": COSTS,
        "period": {"start": dates[0], "end": dates[-1], "n_days": len(dates)},
        "classification_threshold": threshold,
        "trading_threshold": {"value": trade_thr, "selected_on": "validasi", "val_final_equity": best["final_equity"],
                              "val_n_days": len(val_prob)},
        "model": flagged(simulate(test_prob, test_ret, trade_thr, capital, fee)),
        "model_at_classification_threshold": flagged(simulate(test_prob, test_ret, threshold, capital, fee)),
        "model_at_half": flagged(simulate(test_prob, test_ret, 0.5, capital, fee)),
        "buy_and_hold": buy_and_hold(test_ret, capital, fee),
        "permutation": {**shift_test(test_prob, test_ret, threshold, fee), "basis": "ambang klasifikasi"},
        "sharpe_diff_ci": sharpe_diff_ci(r_model, r_hold),
        "sensitivity": sensitivity(test_prob, test_ret, capital=capital, fee=fee),
        "curve": curve,
        "checks": check_not_collapsed(test_rows["label"].to_numpy(), pred_cls),
        "parity_with_retro": _parity(retro_series, test_prob),
        "caveats": _caveats(len(dates)),
    }


def main(argv=None):
    from app import jobs
    from app.inference import Predictor
    from app.sources import read_price_tsv
    from scripts.build_retro import load_fear_greed_full

    jobs._load_dotenv()
    data = config.ROOT / "data"
    try:
        pred = Predictor.from_artifacts()
    except RuntimeError as e:
        raise SystemExit(str(e))
    out = build_backtest_outputs(
        read_price_tsv(config.SEED_PRICE_TSV), pd.read_csv(data / "sentiment_cache_new.csv"),
        pd.read_csv(data / "news_bitcoin_clean.csv", usecols=["date", "title", "source"]),
        load_fear_greed_full(config.WEBAPP / "data" / "cache" / "fear_greed_full.csv"),
        pred.scaler, pred.models[1][0], pred.thresholds[1],
        retro_series=read_json(config.CONTENT_DIR / "retro" / "series.json"))
    atomic_write_json(config.CONTENT_DIR / "backtest.json", out)
    m, b = out["model"], out["buy_and_hold"]
    print(f"ditulis: content/backtest.json | {out['period']['start']}..{out['period']['end']} ({out['period']['n_days']} hari) | "
          f"ambang trading {out['trading_threshold']['value']:.2f} (dipilih di validasi)\n"
          f"biaya {out['fee_per_side'] * 100:.2f}% per sisi | permutasi p(total)={out['permutation']['total']['p']:.3f} | CI95 selisih Sharpe {out['sharpe_diff_ci']}\n"
          f"model: ${m['final_equity']:.2f} ({m['total_return_pct']:+.1f}%), Sharpe {m['sharpe']}, MDD {m['max_drawdown_pct']:.1f}% | "
          f"buy and hold: ${b['final_equity']:.2f} ({b['total_return_pct']:+.1f}%), Sharpe {b['sharpe']}, MDD {b['max_drawdown_pct']:.1f}%\n"
          f"paritas dengan retrospektif: {out['parity_with_retro']}")


if __name__ == "__main__":
    main()
