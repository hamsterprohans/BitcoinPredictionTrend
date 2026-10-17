"""Job harian: harga -> fitur -> sentimen -> prediksi -> snapshot JSON.

Pemakaian: python -m app.jobs [--force]
"""
import argparse
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from . import config
from .sources import SourceError
from .features import TECH_FEATURES, assemble_frame, chart_frame, compute_features
from .store import (append_news, append_sentiment, atomic_write_json, evaluate_history, frame_to_columns,
                    load_sentiment_log, read_json, read_news_entry, upsert_history)


@dataclass
class Deps:
    live_dir: Path
    seed_tsv: Path
    fetch_prices: Callable[[date], pd.DataFrame]
    fetch_fear_greed: Callable[[], pd.DataFrame]
    fetch_headlines: Callable[[date], list]
    score: Callable[[list], Optional[float]]
    predictor: Any
    now: Callable[[], datetime]
    score_detail: Optional[Callable[[list], Optional[dict]]] = None
    explainer: Optional[Callable[[dict], Optional[dict]]] = None


def patient(fetch, cooldown: int = 900, max_waits: int = 48, sleep=time.sleep):
    """Bungkus fetch_headlines: bila GDELT memblokir, tunggu lalu ulangi HARI YANG SAMA (tanpa melewati hari)."""
    def _fetch(day):
        for i in range(max_waits + 1):
            try:
                return fetch(day)
            except SourceError as e:
                if i == max_waits:
                    raise
                print(f"[{day}] {e}; menunggu {cooldown}s lalu mengulang ({i + 1}/{max_waits})", flush=True)
                sleep(cooldown)
    return _fetch


def make_headline_fetcher(http, env=None, patient_mode: bool = False):
    """Pilih sumber berita live: CryptoCompare bila ada API key (sumber korpus latih), selain itu GDELT."""
    from . import sources
    env = os.environ if env is None else env
    key = env.get("COINDESK_API_KEY") or env.get("CRYPTOCOMPARE_API_KEY")
    if key:
        base = lambda day: sources.fetch_headlines_cryptocompare(http, day, key)  # noqa: E731
        name = "cryptocompare"
    else:
        base = lambda day: sources.fetch_headlines(http, day)  # noqa: E731
        name = "gdelt"
    return (patient(base) if patient_mode else base), name


def load_prices(live_dir: Path, seed_tsv: Path) -> pd.DataFrame:
    p = live_dir / "prices.csv"
    if p.exists():
        return pd.read_csv(p, parse_dates=["date"])
    from .sources import read_price_tsv
    return read_price_tsv(seed_tsv)


def refresh_prices(prices: pd.DataFrame, fetch, today: date) -> pd.DataFrame:
    start = prices["date"].max().date() + timedelta(days=1)
    if start < today:
        new = fetch(start)
        prices = pd.concat([prices, new]).drop_duplicates("date", keep="last")
    prices = prices[prices["date"] < pd.Timestamp(today)]  # buang hari berjalan yang belum selesai
    return prices.sort_values("date").reset_index(drop=True)


def ensure_sentiment(live_dir: Path, days: list, fetch_headlines, score, score_detail=None) -> pd.DataFrame:
    log = load_sentiment_log(live_dir)
    for day in days:
        ts = pd.Timestamp(day)
        if ts in log.index:
            continue
        heads = fetch_headlines(day)
        detail = score_detail(heads) if (score_detail and heads) else None
        if detail is not None:
            raw = detail["mean"]
        else:
            raw = score(heads) if heads else None
        append_sentiment(live_dir, day, raw, len(heads))
        if heads:
            append_news(live_dir, day, heads[:5], detail)
        log.loc[ts, "raw"] = np.nan if raw is None else raw
        log.loc[ts, "count"] = len(heads)
    return log.sort_index()


def run_prices_only(deps: Deps):
    """Perbarui hanya harga dan data grafik (tanpa sentimen, model, atau API key). Mengembalikan tanggal terakhir."""
    live = deps.live_dir
    live.mkdir(parents=True, exist_ok=True)
    today = deps.now().astimezone(timezone.utc).date()
    prices = refresh_prices(load_prices(live, deps.seed_tsv), deps.fetch_prices, today)
    prices.to_csv(live / "prices.csv", index=False)
    atomic_write_json(live / "chart.json", frame_to_columns(chart_frame(compute_features(prices))))
    return prices["date"].max().date()


def run_daily(deps: Deps, force: bool = False):
    live = deps.live_dir
    live.mkdir(parents=True, exist_ok=True)
    today = deps.now().astimezone(timezone.utc).date()

    prices = refresh_prices(load_prices(live, deps.seed_tsv), deps.fetch_prices, today)
    prices.to_csv(live / "prices.csv", index=False)
    as_of = prices["date"].max().date()

    previous = read_json(live / "latest.json")
    if previous and previous.get("as_of") == as_of.isoformat() and not force:
        return None

    feats = compute_features(prices)
    window_days = [d.date() for d in feats.dropna(subset=TECH_FEATURES)["date"].iloc[-config.SEQ_LEN:]]
    if len(window_days) < config.SEQ_LEN or (window_days[-1] - window_days[0]).days != config.SEQ_LEN - 1:
        raise RuntimeError("Data harga tidak cukup atau berlubang untuk window 20 hari")
    first = window_days[0] - timedelta(days=2)  # 2 hari sebelum window, untuk ffill(limit=2)
    days = [first + timedelta(days=i) for i in range((as_of - first).days + 1)]

    sent = ensure_sentiment(live, days, deps.fetch_headlines, deps.score, deps.score_detail)
    fg = deps.fetch_fear_greed()
    frame = assemble_frame(feats, sent["raw"], fg)
    frame = frame[frame["date"] <= pd.Timestamp(as_of)]

    preds = deps.predictor.predict(frame)

    close, prev_close = float(prices["close"].iloc[-1]), float(prices["close"].iloc[-2])
    last = frame.iloc[-1]
    raw_today = sent.loc[pd.Timestamp(as_of), "raw"]
    latest = {
        "as_of": as_of.isoformat(),
        "generated_at": deps.now().astimezone(timezone.utc).isoformat(timespec="seconds"),
        "close": round(close, 2),
        "change_pct": round((close / prev_close - 1) * 100, 2),
        "inputs": {
            "news_sentiment": round(float(last["news_sentiment"]), 3),
            "news_sentiment_raw": None if np.isnan(raw_today) else round(float(raw_today), 3),
            "headline_count": int(sent.loc[pd.Timestamp(as_of), "count"]),
            "fear_greed_index": float(last["fear_greed_index"]),
        },
        "horizons": {str(h): {**v, "target_date": (as_of + timedelta(days=h)).isoformat()}
                     for h, v in preds.items()},
    }
    entry = {"date": as_of.isoformat(), "close": round(close, 2),
             "horizons": {str(h): {k: v[k] for k in ("prob", "direction", "threshold")}
                          for h, v in preds.items()}}
    history = upsert_history(read_json(live / "history.json", []), entry)
    history = evaluate_history(history, prices)

    atomic_write_json(live / "chart.json", frame_to_columns(chart_frame(feats)))
    atomic_write_json(live / "history.json", history)
    atomic_write_json(live / "latest.json", latest)  # terakhir: hanya tertulis jika semua langkah sukses
    if deps.explainer is not None:                   # penjelasan opsional dan lambat (LLM): prediksi sudah terbit lebih dulu
        try:
            explained = deps.explainer({"frame": frame, "preds": preds, "as_of": as_of.isoformat(),
                                        "news": read_news_entry(live, as_of)})
            if explained is not None:
                latest["explain"] = explained
                atomic_write_json(live / "latest.json", latest)
        except Exception as e:  # noqa: BLE001 - penjelasan tidak boleh menggagalkan prediksi harian
            print(f"[explain] dilewati: {e}", flush=True)
    return latest


def make_real_deps(patient_mode: bool = False, prices_only: bool = False) -> Deps:
    import anthropic
    import httpx

    from . import sources
    from .inference import Predictor
    from .sentiment import daily_sentiment

    if prices_only:  # hanya perlu sumber harga: tanpa API key, tanpa model
        http = httpx.Client(timeout=30, follow_redirects=True)
        return Deps(live_dir=config.LIVE_DIR, seed_tsv=config.SEED_PRICE_TSV,
                    fetch_prices=lambda start: sources.fetch_prices(http, start),
                    fetch_fear_greed=None, fetch_headlines=None, score=None, predictor=None,
                    now=lambda: datetime.now(timezone.utc))
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY belum diset (environment variable atau .env)")
    http = httpx.Client(timeout=30, follow_redirects=True)
    llm = anthropic.Anthropic(api_key=key)
    from . import explain
    from .sentiment import daily_sentiment_detail
    pred = Predictor.from_artifacts()
    retro = config.CONTENT_DIR / "retro"
    stats, series = read_json(retro / "train_stats.json"), read_json(retro / "series.json")
    explainer = None
    if stats:
        explainer = lambda ctx: explain.build_live_explain(  # noqa: E731
            predictor=pred, frame=ctx["frame"], pred=ctx["preds"][1], news=ctx["news"], as_of=ctx["as_of"],
            stats=stats, series=series, client=llm.with_options(timeout=30.0, max_retries=0))
    fetch_headlines, source_name = make_headline_fetcher(http, patient_mode=patient_mode)
    print(f"sumber berita live: {source_name}", flush=True)
    return Deps(
        live_dir=config.LIVE_DIR, seed_tsv=config.SEED_PRICE_TSV,
        fetch_prices=lambda start: sources.fetch_prices(http, start),
        fetch_fear_greed=lambda: sources.fetch_fear_greed(http, limit=60),
        fetch_headlines=fetch_headlines,
        score=lambda heads: daily_sentiment(llm, heads),
        predictor=pred, now=lambda: datetime.now(timezone.utc),
        score_detail=lambda heads: daily_sentiment_detail(llm, heads), explainer=explainer,
    )


def _load_dotenv():
    for p in (config.WEBAPP / ".env", config.ROOT / ".env", config.ROOT / "scripts" / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


if __name__ == "__main__":
    _load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="hitung ulang walau sudah mutakhir")
    ap.add_argument("--patient", action="store_true",
                    help="bila GDELT memblokir (429), tunggu 15 menit lalu ulangi hari yang sama (untuk backfill pertama)")
    ap.add_argument("--prices-only", action="store_true",
                    help="hanya perbarui harga dan grafik (tanpa API key atau model)")
    args = ap.parse_args()
    if args.prices_only:
        print("harga terakhir:", run_prices_only(make_real_deps(prices_only=True)))
        raise SystemExit(0)
    try:
        deps = make_real_deps(patient_mode=args.patient)
    except RuntimeError as e:
        raise SystemExit(str(e))
    result = run_daily(deps, force=args.force)
    print("sudah mutakhir" if result is None else f"as_of={result['as_of']} horizons={list(result['horizons'])}")
