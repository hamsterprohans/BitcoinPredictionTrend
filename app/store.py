import csv
import json
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


def atomic_write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _log_path(live_dir) -> Path:
    return Path(live_dir) / "sentiment_log.csv"


def load_sentiment_log(live_dir) -> pd.DataFrame:
    p = _log_path(live_dir)
    if not p.exists():
        return pd.DataFrame({"raw": pd.Series(dtype=float), "count": pd.Series(dtype=int)},
                            index=pd.DatetimeIndex([], name="date"))
    df = pd.read_csv(p, parse_dates=["date"])
    return df.drop_duplicates("date", keep="last").set_index("date").sort_index()


def append_sentiment(live_dir, day: date, raw, count: int) -> None:
    p = _log_path(live_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "raw", "count"])
        w.writerow([day.isoformat(), "" if raw is None else repr(float(raw)), int(count)])


def upsert_history(history: list, entry: dict) -> list:
    out = [e for e in history if e["date"] != entry["date"]] + [entry]
    return sorted(out, key=lambda e: e["date"])


def evaluate_history(history: list, prices: pd.DataFrame) -> list:
    close = prices.assign(date=pd.to_datetime(prices["date"])).set_index("date")["close"]
    for e in history:
        d = pd.Timestamp(e["date"])
        for h, v in e["horizons"].items():
            if "actual" in v:
                continue
            target = d + pd.Timedelta(days=int(h))
            if target in close.index and d in close.index:
                actual = "NAIK" if close[target] > close[d] else "TURUN"
                v["actual"] = actual
                v["correct"] = v["direction"] == actual
    return history


def frame_to_columns(df: pd.DataFrame) -> dict:
    out = {}
    for c in df.columns:
        if c == "date":
            out[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d").tolist()
        else:
            s = df[c].astype(float).round(4)
            out[c] = [None if np.isnan(x) else float(x) for x in s]
    return out


def _news_path(live_dir) -> Path:
    return Path(live_dir) / "news_log.json"


def append_news(live_dir, day: date, titles: list, scores) -> None:
    log = read_json(_news_path(live_dir), {})
    log[day.isoformat()] = {"titles": list(titles), "scores": scores}
    atomic_write_json(_news_path(live_dir), log)


def read_news_entry(live_dir, day: date):
    return read_json(_news_path(live_dir), {}).get(day.isoformat())
