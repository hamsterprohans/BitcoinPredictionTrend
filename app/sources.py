"""Pengambil data eksternal. Sumber sama dengan data latih: Coin Metrics, alternative.me, GDELT."""
import re
import time
from datetime import date

import httpx
import pandas as pd

CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
FNG_URL = "https://api.alternative.me/fng/"
COINBASE_SPOT = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
CRYPTOCOMPARE_NEWS = "https://min-api.cryptocompare.com/data/v2/news/"
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


def _cc_page(http, cursor: int, api_key: str, sleep, retries: int, day) -> list:
    """Satu halaman berita CryptoCompare. Balasan kosong/berperingatan/429 = pembatasan laju: ulangi dengan jeda yang naik.

    Paket gratis: 100 panggilan/bulan, 10/menit, 1/detik. Saat dibatasi API tetap membalas HTTP 200 dengan Data kosong,
    sehingga balasan kosong TIDAK boleh dianggap "tidak ada berita".
    """
    for attempt in range(retries + 1):
        r = http.get(CRYPTOCOMPARE_NEWS, params={"lang": "EN", "categories": "BTC", "lTs": cursor},
                     headers={**UA, "authorization": f"Apikey {api_key}"})
        if r.status_code == 429:
            sleep(15 * (2 ** attempt))
            continue
        if r.status_code in (401, 403):
            raise SourceError("CryptoCompare menolak API key (periksa COINDESK_API_KEY di scripts/.env)")
        if r.status_code != 200:
            raise SourceError(f"CryptoCompare HTTP {r.status_code} untuk {day}")
        remaining = r.headers.get("x-ratelimit-remaining")
        if remaining is not None and remaining.strip().lstrip("-").isdigit() and int(remaining) <= 0:
            raise SourceError("kuota CryptoCompare habis (paket gratis: 100 panggilan per bulan)")
        body = r.json()
        data = body.get("Data")
        warned = body.get("HasWarning") in (True, "True", "true") or bool(body.get("RateLimit"))
        if warned or not isinstance(data, list) or not data:
            sleep(60 * (attempt + 1))
            continue
        return data
    raise SourceError(f"CryptoCompare dibatasi atau membalas kosong berulang untuk {day}")


def fetch_headlines_cryptocompare(http: httpx.Client, day: date, api_key: str, sleep=time.sleep,
                                  retries: int = 3, max_pages: int = 3, page_pause: float = 7.0, want: int = 5) -> list:
    """Judul berita BTC satu hari UTC dari CryptoCompare (sumber berita korpus latih), terbaru dulu.

    Satu panggilan per hari biasanya cukup (kuota gratis hanya 100/bulan): halaman diambil mundur dari akhir hari
    lewat `lTs` dan berhenti begitu terkumpul `want` judul atau awal hari terlewati. Judul disaring seperti korpus latih
    (menyebut Bitcoin/BTC, bukan sponsor, unik). Hari tanpa judul = galat (dianggap pembatasan), bukan "tidak ada berita".
    """
    import datetime as dt
    start = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    cursor = start + 86400
    seen, out = set(), []
    for _ in range(max_pages):
        arts = _cc_page(http, cursor, api_key, sleep, retries, day)
        for a in arts:
            ts = int(a.get("published_on", 0))
            title = (a.get("title") or "").strip()
            if ts < start or ts >= start + 86400 or not title or title in seen:
                continue
            if not BTC_RE.search(title) or _is_sponsored(title):
                continue
            seen.add(title)
            out.append(title)
        sleep(page_pause)                                   # <= 10 panggilan/menit
        oldest = min(int(a.get("published_on", cursor)) for a in arts)
        if len(out) >= want or oldest < start or oldest >= cursor:
            break
        cursor = oldest
    if not out:
        raise SourceError(f"CryptoCompare: tidak ada berita BTC untuk {day} (kemungkinan dibatasi); tidak disimpan sebagai 'tanpa berita'")
    return out


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
