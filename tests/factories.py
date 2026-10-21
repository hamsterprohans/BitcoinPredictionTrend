from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.features import compute_features, chart_frame
from app.store import atomic_write_json, frame_to_columns


def synthetic_prices(end: date, n=400, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    dates = pd.date_range(end=pd.Timestamp(end), periods=n)
    return pd.DataFrame({"date": dates, "close": close})


class FakePredictor:
    def __init__(self):
        self.frames = []

    def predict(self, frame):
        self.frames.append(frame.copy())
        return {1: {"prob": 0.6, "threshold": 0.4557, "direction": "NAIK"},
                3: {"prob": 0.45, "threshold": 0.5, "direction": "TURUN"}}


def _explain_block():
    from app.explain import build_facts, feature_rows, rank_contributions, template_narrative
    from app.inference import FEATURE_ORDER
    stats = {"quantiles": {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}}
    deltas = np.linspace(-3, 3, 13)
    feats, contrib = feature_rows({f: 5.0 for f in FEATURE_ORDER}, stats), rank_contributions(deltas)
    rec = {"date": "2026-10-14", "target_date": "2026-10-15", "prob": 0.52, "threshold": 0.4557, "level": "tinggi",
           "features": feats, "contributions": contrib}
    return {"headlines": [{"title": "Judul berita 0", "url": "https://contoh.com/berita-0"},
                          {"title": "Judul berita 1", "url": "javascript:alert(1)"},        # skema berbahaya: tidak boleh jadi tautan
                          {"title": "Judul berita 2 SuperPanjangTanpaSpasiBitcoin(BTC)Worth$72.64MtoCoinbasePrimeAndMore"}],   # tanpa URL; kata panjang menguji pembungkusan
            "sentiment": {"has_news": True, "scores": {"pemahaman": 3, "detail": 2, "bullbear": 1, "mean": 2.0}, "used": 1.67},
            "contributions": contrib, "features": feats, "level": "tinggi",
            "narrative": {"text": template_narrative(build_facts(rec, auc=0.52)), "source": "llm",
                          "attempts": 1, "temperature": 0.1}}


def seed_live_dir(live_dir, content_dir, as_of=date(2026, 10, 14), demo=False, explain=True):
    """Isi live_dir dan content_dir dengan data sintetis yang bentuknya sama dengan keluaran job."""
    prices = synthetic_prices(as_of)
    prices.to_csv(live_dir / "prices.csv", index=False)
    feats = compute_features(prices)
    atomic_write_json(live_dir / "chart.json", frame_to_columns(chart_frame(feats)))
    atomic_write_json(live_dir / "latest.json", {
        **({"demo": True} if demo else {}),
        **({"explain": _explain_block()} if explain else {}),
        "as_of": as_of.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "close": round(float(prices.close.iloc[-1]), 2), "change_pct": -1.33,
        "inputs": {"news_sentiment": 1.67, "news_sentiment_raw": 2.0, "headline_count": 5, "fear_greed_index": 63.0},
        "horizons": {
            "1": {"prob": 0.52, "threshold": 0.4557, "direction": "NAIK",
                  "target_date": (as_of + timedelta(days=1)).isoformat()},
            "7": {"prob": 0.44, "threshold": 0.5, "direction": "TURUN",
                  "target_date": (as_of + timedelta(days=7)).isoformat()}}})
    hist = []
    for i in range(10, 0, -1):
        d = as_of - timedelta(days=i)
        hist.append({"date": d.isoformat(), "close": 1.0, **({"backfilled": True} if i == 3 else {}), "horizons": {
            "1": {"prob": 0.5, "threshold": 0.4557, "direction": "NAIK",
                  "actual": "NAIK" if i % 2 else "TURUN", "correct": bool(i % 2), "locked": True},
            "7": {"prob": 0.4, "threshold": 0.5, "direction": "TURUN"}}})
    atomic_write_json(live_dir / "history.json", hist)
    atomic_write_json(content_dir / "multihorizon_evidence.json", {
        "7": {"auc": 0.515, "ci_lo": 0.42, "ci_hi": 0.61, "p_holm": 1.0, "significant": False,
              "label": "Belum terbukti lebih baik dari tebakan acak"}})
    atomic_write_json(content_dir / "ablation.json", [
        {"Model": "A", "Deskripsi": "Logistic Regression", "N Fitur": 11, "Accuracy": 0.4942,
         "Precision": 0.4848, "Recall": 0.3738, "F1-Weighted": 0.4870},
        {"Model": "F", "Deskripsi": "LSTM + Sentimen + F&G", "N Fitur": 13, "Accuracy": 0.51,
         "Precision": 0.5, "Recall": 0.5, "F1-Weighted": 0.5}])
    atomic_write_json(content_dir / "multiseed.json", [
        {"Model": "B", "F1 Mean": 0.48732, "F1 Std": 0.051882}, {"Model": "F", "F1 Mean": 0.49, "F1 Std": 0.03}])
    atomic_write_json(content_dir / "multihorizon.json", [
        {"H": 3, "n_efektif": 143.3, "AUC_F": 0.5, "CI_lo": 0.431, "CI_hi": 0.567, "p_geser": 0.5035,
         "p_Holm_m8": 1.0, "signifikan_Holm_m8": False},
        {"H": 30, "n_efektif": 13.0, "AUC_F": 0.622, "CI_lo": 0.4, "CI_hi": 0.8, "p_geser": 0.1,
         "p_Holm_m8": 1.0, "signifikan_Holm_m8": False}])
    atomic_write_json(content_dir / "holding_period.json", [
        {"H": 7, "subset": "seluruh data", "n_jendela": 5759, "pct_positif": 55.4, "median_pct": 0.9,
         "p5_pct": -14.7, "p95_pct": 23.4, "terburuk_pct": -70.4}])
    atomic_write_json(content_dir / "permutation_importance.json", [
        {"Fitur": "Vol_30", "Baseline F1": 0.49, "Penurunan F1 (Importance)": 0.0287, "Std": 0.0088},
        {"Fitur": "MACD_Histogram", "Baseline F1": 0.49, "Penurunan F1 (Importance)": 0.0226, "Std": 0.0076}])
    atomic_write_json(content_dir / "significance.json", {
        "mcnemar": [{"a": "A", "b": "C", "p": 0.6465, "verdict": "tidak signifikan", "only_a": 82, "only_b": 89}],
        "wilcoxon": [{"a": "C", "b": "F", "statistic": 5.0, "p": 0.625, "verdict": "tidak signifikan",
                      "mean_a": 0.4658, "mean_b": 0.4455}]})
    return feats


def seed_prices_only(live_dir, as_of=date(2026, 10, 14)):
    """Seperti keluaran `jobs --prices-only`: prices.csv + chart.json, tanpa latest.json."""
    prices = synthetic_prices(as_of)
    prices.to_csv(live_dir / "prices.csv", index=False)
    atomic_write_json(live_dir / "chart.json", frame_to_columns(chart_frame(compute_features(prices))))


SENT3_COLS = ["news_sentiment_pemahaman", "news_sentiment_detail", "news_sentiment_bullbear"]


def synthetic_retro_inputs(n_days=460, start="2025-01-01", seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n_days)
    close = 60000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n_days)))
    prices = pd.DataFrame({"date": dates, "close": close})
    sent3 = pd.DataFrame({"date": dates, **{c: rng.integers(-5, 6, n_days).astype(float) for c in SENT3_COLS}})
    no_news = set(range(150, 153)) | set(range(5, n_days, 17))          # 3 hari berturut-turut + hari acak tanpa berita
    rows = [(d, f"judul {i}-{k}", "cryptocompare") for i, d in enumerate(dates) if i not in no_news for k in range(7)]
    news = pd.DataFrame(rows, columns=["date", "title", "source"])
    fg = pd.DataFrame({"date": dates, "fear_greed_index": rng.integers(10, 90, n_days).astype(float)})
    return {"prices": prices, "sent3": sent3, "news": news, "fg": fg, "no_news": no_news, "dates": dates,
            "start": dates[100], "end": dates[-2]}


class FakeRetroModel:
    """prob = 0.3 + 0.4 * (Fear&Greed terskala hari terakhir jendela): deterministik dan bergantung pada fitur ke-13."""
    def predict(self, W, verbose=0):
        return (0.3 + 0.4 * np.asarray(W)[:, -1, 12])[:, None]


def fit_scaler(inputs):
    from sklearn.preprocessing import RobustScaler
    from scripts.build_retro import assemble_table, split_table
    from app.features import TECH_FEATURES
    table = assemble_table(inputs["prices"], inputs["sent3"], set(pd.to_datetime(inputs["news"]["date"]).dt.normalize()),
                           inputs["fg"])
    train, _, _ = split_table(table, inputs["start"], inputs["end"])
    return RobustScaler().fit(train[TECH_FEATURES + ["news_sentiment"]])


def seed_retro(content_dir):
    """Tulis content/retro/ dengan skema nyata (dari build_outputs + model tiruan) untuk tes API dan e2e."""
    from pathlib import Path
    from app.explain import build_facts, template_narrative
    from scripts.build_retro import build_outputs, write_outputs
    inp = synthetic_retro_inputs()
    out = build_outputs(inp["prices"], inp["sent3"], inp["news"], inp["fg"], fit_scaler(inp), FakeRetroModel(), 0.5,
                        start=inp["start"], end=inp["end"], allow_mismatch=True)
    for k in list(out["days"])[:3]:
        rec = out["days"][k]
        rec["narrative"] = {"text": template_narrative(build_facts(rec, auc=out["series"]["auc"])),
                            "source": "llm", "attempts": 1, "temperature": 0.1}
    write_outputs(Path(content_dir) / "retro", out)
    return out


def backtest_fixture(kind="always_long"):
    """content/backtest.json tetap (skema nyata). always_long: ambang validasi membuat model = buy and hold, seperti hasil nyata."""
    def m(final, ret, trades, win, aw, al, mdd, sharpe, inmkt):
        return {"final_equity": final, "total_return_pct": ret, "n_trades": trades, "win_rate_pct": win, "avg_win_pct": aw,
                "avg_loss_pct": al, "max_drawdown_pct": mdd, "sharpe": sharpe, "days_in_market_pct": inmkt}
    bh = m(794.38, -20.562, 1, 0.0, None, -20.562, -49.1, -0.1984, 100.0)
    cls = m(985.31, -1.469, 11, 36.36, 9.2, -6.1, -26.0, 0.12, 56.0)
    model = bh if kind == "always_long" else m(1056.13, 5.613, 2, 100.0, 5.6, None, -5.7, 0.51, 20.0)
    thr = 0.35 if kind == "always_long" else 0.60
    rets = [(0.05, -20.6, 1), (0.10, -20.6, 1), (0.15, -20.6, 1), (0.20, -20.6, 1), (0.25, -20.6, 1), (0.30, -20.6, 1), (0.35, -20.6, 1),
            (0.40, -38.8, 4), (0.45, -31.2, 16), (0.50, -7.5, 11), (0.55, 0.2, 9), (0.60, 5.6, 2), (0.65, 0.0, 0), (0.70, 0.0, 0),
            (0.75, 0.0, 0), (0.80, 0.0, 0), (0.85, 0.0, 0), (0.90, 0.0, 0)]
    sens = [{"threshold": t, "final_equity": round(1000 * (1 + r / 100), 2), "total_return_pct": r, "sharpe": None if n == 0 else 0.1,
             "max_drawdown_pct": -10.0, "n_trades": n} for t, r, n in rets]
    return {"generated_at": "2026-10-21T00:00:00+00:00", "strategy": "long-only", "capital": 1000.0,
            "costs": "tanpa biaya transaksi dan slippage", "period": {"start": "2025-02-21", "end": "2026-04-29", "n_days": 433},
            "classification_threshold": 0.4768, "trading_threshold": {"value": thr, "selected_on": "validasi",
                                                                      "val_final_equity": 2654.44, "val_n_days": 432},
            "model": model, "model_at_classification_threshold": cls, "buy_and_hold": bh, "sensitivity": sens,
            "curve": {"date": ["2025-02-21", "2025-02-22", "2025-02-23", "2025-02-24"], "model": [1000, 1010, 990, 980],
                      "model_classification": [1000, 1000, 1000, 1005], "buy_hold": [1000, 1010, 990, 980]},
            "checks": {"recall": 0.56, "collapsed": False, "range": [0.15, 0.85]},
            "parity_with_retro": {"checked": True, "max_abs_prob_diff": 5e-07},
            "caveats": ["Simulasi pada data historis periode uji (433 hari); bukan bukti kinerja di pasar nyata. Pembuktian memerlukan forward testing.",
                        "Tanpa biaya transaksi dan slippage.", "Ambang trading dipilih dari data validasi.",
                        "Satu jalur sejarah dan satu periode.", "Buy and hold = beli di awal periode uji."]}
