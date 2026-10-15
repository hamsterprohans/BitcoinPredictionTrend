"""Pengambil data eksternal. Sumber sama dengan data latih: Coin Metrics, alternative.me, GDELT."""
import re
import time
from datetime import date

import httpx
import pandas as pd

CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
FNG_URL = "https://api.alternative.me/fng/"
COINBASE_SPOT = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) BitcoinTrendWeb/1.0"}

BTC_RE = re.compile(r"bitcoin|btc\b", re.IGNORECASE)
SPONSOR_KEYWORDS = ["presale", "sponsored", "roi", "magacoin", "airdrop", "token sale",
                    "% climb", "% roi", "best crypto to buy", "x return", "x gains"]


class SourceError(RuntimeError):
    pass


def read_price_tsv(path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, sep="\t", encoding="utf-16")
    except UnicodeDecodeError:
        df = pd.read_csv(path, sep="\t")
    df.columns = ["date", "close"]
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)


def fetch_prices(http: httpx.Client, start: date) -> pd.DataFrame:
    r = http.get(CM_URL, params={"assets": "btc", "metrics": "PriceUSD", "frequency": "1d",
                                 "start_time": start.isoformat(), "page_size": 10000},
                 headers=UA)
    r.raise_for_status()
    rows = []
    for x in r.json()["data"]:
        if x.get("PriceUSD") in (None, ""):
            continue
        d = pd.to_datetime(x["time"], utc=True).tz_localize(None).normalize()
        rows.append((d, float(x["PriceUSD"])))
    return pd.DataFrame(rows, columns=["date", "close"]).sort_values("date").reset_index(drop=True)


def fetch_fear_greed(http: httpx.Client, limit: int = 60) -> pd.DataFrame:
    r = http.get(FNG_URL, params={"limit": limit, "format": "json"}, headers=UA)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["data"])
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    df["fear_greed_index"] = df["value"].astype(float)
    return df[["date", "fear_greed_index"]].sort_values("date").reset_index(drop=True)


def fetch_spot(http: httpx.Client) -> float:
    """Harga spot BTC/USD saat ini (hanya untuk tampilan; BUKAN input model). Satu kali ulang untuk gangguan sesaat."""
    for attempt in range(2):
        try:
            r = http.get(COINBASE_SPOT, headers=UA, timeout=5)
            r.raise_for_status()
            return float(r.json()["data"]["amount"])
        except httpx.HTTPError:
            if attempt == 1:
                raise


def _is_sponsored(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in SPONSOR_KEYWORDS)


def fetch_headlines(http: httpx.Client, day: date, sleep=time.sleep,
                    retries: int = 3, min_interval: float = 10.0) -> list:
    params = {"query": "bitcoin sourcelang:english", "mode": "artlist", "format": "json",
              "maxrecords": "250",
              "startdatetime": day.strftime("%Y%m%d000000"),
              "enddatetime": day.strftime("%Y%m%d235959")}
    for attempt in range(retries + 1):
        r = http.get(GDELT_URL, params=params, headers=UA)
        if r.status_code == 429:
            sleep(15 * (2 ** attempt))
            continue
        if r.status_code != 200:
            raise SourceError(f"GDELT HTTP {r.status_code} untuk {day}")
        if not r.text.strip():
            # Badan kosong = GDELT sedang membatasi (bukan "tidak ada berita Bitcoin"): ulangi dengan jeda yang naik.
            sleep(15 * (2 ** attempt))
            continue
        try:
            arts = r.json().get("articles", [])
        except ValueError as e:
            raise SourceError(f"GDELT bukan JSON untuk {day}") from e
        seen, out = set(), []
        for a in arts:
            title = (a.get("title") or "").strip()
            if not title or title in seen or not BTC_RE.search(title) or _is_sponsored(title):
                continue
            seen.add(title)
            out.append(title)
        sleep(min_interval)  # GDELT: >= 5 detik antar permintaan
        return out
    raise SourceError(f"GDELT 429/balasan kosong berulang untuk {day}")
