"""Job harian: harga -> fitur -> sentimen -> prediksi -> snapshot JSON.

Pemakaian: python -m app.jobs [--force]
"""
import argparse
import os
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import numpy as np
import pandas as pd

from . import config
from .sources import SourceError
from .features import TECH_FEATURES, assemble_frame, chart_frame, compute_features
from .store import (append_news, append_sentiment, atomic_write_json, evaluate_history, frame_to_columns, tag_model_version,
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


def with_fallback(primary, secondary):
    """Coba `primary`; bila gagal (SourceError/galat HTTP), coba `secondary`. Bila keduanya gagal, SourceError memuat KEDUA penyebab."""
    def _fetch(day):
        try:
            return primary(day)
        except (SourceError, httpx.HTTPError) as e1:
            print(f"[{day}] sumber utama gagal: {e1}; mencoba sumber cadangan", flush=True)
            try:
                return secondary(day)
            except (SourceError, httpx.HTTPError) as e2:
                raise SourceError(f"{e1} | cadangan: {e2}") from e2
    return _fetch


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
    """Rantai sumber berita live. Dengan API key: CryptoCompare (sumber korpus latih), cadangan RSS outlet kripto.
    Tanpa key: RSS, cadangan GDELT (sering memblokir). Judul membawa `.source` agar asalnya tercatat di news_log."""
    from . import sources
    env = os.environ if env is None else env
    key = env.get("COINDESK_API_KEY") or env.get("CRYPTOCOMPARE_API_KEY")
    rss = lambda day: sources.fetch_headlines_rss(http, day)  # noqa: E731
    if key:
        cc = lambda day: sources.fetch_headlines_cryptocompare(http, day, key)  # noqa: E731
        base, name = with_fallback(cc, rss), "cryptocompare (cadangan: rss)"
    else:
        gdelt = lambda day: sources.fetch_headlines(http, day)  # noqa: E731
        base, name = with_fallback(rss, gdelt), "rss (cadangan: gdelt)"
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
            append_news(live_dir, day, heads[:5], detail, urls=[getattr(h, "url", None) for h in heads[:5]],
                        source=getattr(heads[0], "source", None))
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


def check_fear_greed_fresh(fg: pd.DataFrame, as_of: date, max_lag_days: int = 1) -> None:
    """Hentikan job bila data Fear & Greed tertinggal: assemble_frame akan mengisinya dengan 50, dan prediksi yang salah itu
    terkunci permanen di history.json. Gagal sehari lebih aman (job dijadwalkan ulang beberapa kali per hari)."""
    if fg is None or len(fg) == 0:
        raise RuntimeError("Data Fear & Greed kosong: job dihentikan agar prediksi tidak dihitung dengan nilai bawaan 50")
    last = pd.to_datetime(fg["date"]).max().date()
    if (as_of - last).days > max_lag_days:
        raise RuntimeError(f"Fear & Greed terakhir {last}, tertinggal untuk {as_of}: job dihentikan agar nilai bawaan 50 "
                           "tidak terkunci pada prediksi")


def _compute(deps: Deps, live, prices, as_of):
    """Inti prediksi untuk satu tanggal: fitur, sentimen, Fear & Greed, model. Mengembalikan (feats, frame, preds, latest, entry)."""
    feats = compute_features(prices)
    window_days = [d.date() for d in feats.dropna(subset=TECH_FEATURES)["date"].iloc[-config.SEQ_LEN:]]
    if len(window_days) < config.SEQ_LEN or (window_days[-1] - window_days[0]).days != config.SEQ_LEN - 1:
        raise RuntimeError("Data harga tidak cukup atau berlubang untuk window 20 hari")
    first = window_days[0] - timedelta(days=2)  # 2 hari sebelum window, untuk ffill(limit=2)
    days = [first + timedelta(days=i) for i in range((as_of - first).days + 1)]

    sent = ensure_sentiment(live, days, deps.fetch_headlines, deps.score, deps.score_detail)
    fg = deps.fetch_fear_greed()
    check_fear_greed_fresh(fg, as_of)
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
    entry = {"date": as_of.isoformat(), "close": round(close, 2), "model_version": config.MODEL_VERSION,
             "horizons": {str(h): {k: v[k] for k in ("prob", "direction", "threshold")}
                          for h, v in preds.items()}}
    return feats, frame, preds, latest, entry


def fill_missing_urls(live_dir: Path, day: date, fetch_headlines) -> int:
    """Lengkapi URL artikel untuk berita `day` yang tersimpan tanpa tautan. Mengembalikan jumlah URL yang terisi.

    Hanya memanggil sumber bila ada URL kosong (hemat kuota), mencocokkan menurut JUDUL (bukan urutan), tidak mengubah judul/skor
    yang sudah dinilai, tidak menimpa URL yang ada, dan tidak mengarang URL untuk judul yang tidak ditemukan. Bila sumber gagal,
    tidak ada berkas yang berubah.
    """
    live = Path(live_dir)
    log = read_json(live / "news_log.json", {})
    entry = log.get(day.isoformat())
    if not entry:
        return 0
    titles = entry.get("titles", [])
    urls = list(entry.get("urls") or [None] * len(titles))
    urls += [None] * (len(titles) - len(urls))
    if all(urls):
        return 0
    found = {str(h): getattr(h, "url", None) for h in fetch_headlines(day)}
    filled = 0
    for i, t in enumerate(titles):
        if not urls[i] and found.get(t):
            urls[i] = found[t]
            filled += 1
    if not filled:
        return 0
    entry["urls"] = urls
    atomic_write_json(live / "news_log.json", log)
    latest = read_json(live / "latest.json")
    if latest and latest.get("as_of") == day.isoformat():
        for h, u in zip(latest.get("explain", {}).get("headlines", []), urls):
            if u and "url" not in h:
                h["url"] = u
        atomic_write_json(live / "latest.json", latest)
    return filled


def run_backfill(deps: Deps, as_of):
    """Hitung SUSULAN prediksi satu hari yang terlewat, hanya dari data tersimpan (harga, log sentimen, Fear & Greed).

    Tanpa berita/LLM baru; hanya memakai data sampai `as_of` (tanpa kebocoran). Tidak menyentuh latest.json maupun chart.json,
    tidak menimpa prediksi asli, dan hasilnya ditandai `backfilled`. Mengembalikan entri riwayat, atau None bila sudah ada.
    """
    live = deps.live_dir
    history = read_json(live / "history.json", [])
    if any(e["date"] == as_of.isoformat() for e in history):
        return None
    all_prices = load_prices(live, deps.seed_tsv)
    prices = all_prices[all_prices["date"] <= pd.Timestamp(as_of)]
    if prices.empty or prices["date"].max().date() != as_of:
        raise RuntimeError(f"Harga tersimpan tidak memuat penutupan {as_of}")

    def _no_fetch(day):
        raise RuntimeError(f"Sentimen {day} tidak tersimpan; backfill tidak boleh mengarang atau memanggil berita baru")
    offline = replace(deps, fetch_headlines=_no_fetch, score=None, score_detail=None, explainer=None)
    _, _, _, _, entry = _compute(offline, live, prices, as_of)
    entry["backfilled"] = True
    history = tag_model_version(evaluate_history(upsert_history(history, entry), all_prices), config.MODEL_VERSION)
    atomic_write_json(live / "history.json", history)
    return entry


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

    feats, frame, preds, latest, entry = _compute(deps, live, prices, as_of)
    history = upsert_history(read_json(live / "history.json", []), entry)
    history = tag_model_version(evaluate_history(history, prices), config.MODEL_VERSION)
    issued = next(e for e in history if e["date"] == entry["date"])          # prediksi pertama yang terbit berlaku (terkunci)
    for h, v in latest["horizons"].items():
        kept = issued["horizons"].get(h)
        if kept:
            v.update({k: kept[k] for k in ("prob", "direction", "threshold")})

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
    ap.add_argument("--backfill", metavar="YYYY-MM-DD",
                    help="hitung susulan prediksi hari yang terlewat dari data tersimpan (tanpa API baru)")
    ap.add_argument("--fill-urls", metavar="YYYY-MM-DD",
                    help="lengkapi URL artikel berita tanggal itu yang tersimpan tanpa tautan (satu panggilan sumber berita)")
    ap.add_argument("--prices-only", action="store_true",
                    help="hanya perbarui harga dan grafik (tanpa API key atau model)")
    args = ap.parse_args()
    if args.prices_only:
        print("harga terakhir:", run_prices_only(make_real_deps(prices_only=True)))
        raise SystemExit(0)
    if args.fill_urls:
        from . import sources
        import httpx
        key = os.environ.get("COINDESK_API_KEY") or os.environ.get("CRYPTOCOMPARE_API_KEY")
        if not key:
            raise SystemExit("COINDESK_API_KEY belum diset (environment variable atau .env)")
        http = httpx.Client(timeout=30, follow_redirects=True)
        n = fill_missing_urls(config.LIVE_DIR, date.fromisoformat(args.fill_urls),
                              lambda day: sources.fetch_headlines_cryptocompare(http, day, key))
        raise SystemExit(f"{n} URL berita dilengkapi untuk {args.fill_urls}")
    if args.backfill:
        deps = make_real_deps(patient_mode=False)
        out = run_backfill(deps, date.fromisoformat(args.backfill))
        raise SystemExit("sudah ada prediksi untuk tanggal itu" if out is None else f"backfill {out['date']} selesai")
    try:
        deps = make_real_deps(patient_mode=args.patient)
    except RuntimeError as e:
        raise SystemExit(str(e))
    result = run_daily(deps, force=args.force)
    print("sudah mutakhir" if result is None else f"as_of={result['as_of']} horizons={list(result['horizons'])}")
