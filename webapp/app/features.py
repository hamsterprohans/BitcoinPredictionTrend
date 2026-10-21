"""Indikator teknikal: disalin identik dari notebook (10), sel 2.1. Jangan ubah rumusnya."""
import numpy as np
import pandas as pd

TECH_FEATURES = [
    "daily_return", "MA7", "MA30", "MA90",
    "Vol_7", "Vol_30", "RSI14",
    "MACD", "MACD_Signal", "MACD_Histogram", "BB_width",
]


def compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["daily_return"] = df["close"].pct_change()
    df["MA7"] = df["close"].rolling(7).mean()
    df["MA30"] = df["close"].rolling(30).mean()
    df["MA90"] = df["close"].rolling(90).mean()
    df["Vol_7"] = df["daily_return"].rolling(7).std()
    df["Vol_30"] = df["daily_return"].rolling(30).std()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=13, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=13, min_periods=14).mean()
    df["RSI14"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]

    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["BB_width"] = (4 * std20) / sma20
    return df


def chart_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "close", "MA7", "MA30", "MA90", "RSI14",
              "MACD", "MACD_Signal", "MACD_Histogram"]].copy()
    sma = df["close"].rolling(20).mean()
    sd = df["close"].rolling(20).std()
    out["BB_mid"] = sma
    out["BB_up"] = sma + 2 * sd
    out["BB_dn"] = sma - 2 * sd
    return out


def assemble_frame(feats: pd.DataFrame, sent_raw: pd.Series, fg: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan news_sentiment (ffill limit=2 lalu 0) dan Fear & Greed (ffill limit=2 lalu 50, /100)."""
    df = feats.copy()
    s = sent_raw.copy()
    s.index = pd.to_datetime(s.index)
    s = s.reindex(pd.date_range(s.index.min(), df["date"].max())).ffill(limit=2).fillna(0.0)
    df["news_sentiment"] = df["date"].map(s)

    g = fg.copy()
    g["date"] = pd.to_datetime(g["date"])
    g = g.set_index("date")["fear_greed_index"]
    full = pd.date_range(min(g.index.min(), df["date"].min()), df["date"].max())
    g = g.reindex(full).ffill(limit=2).fillna(50.0)
    df["fear_greed_index"] = df["date"].map(g)
    df["fear_greed_index_scaled"] = df["fear_greed_index"] / 100.0
    return df


def resample_prices(prices: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Agregasi harga harian ke mingguan (W) atau bulanan (M). Bar diberi tanggal hari terakhir yang ada pada periodenya."""
    rule = {"W": "W-SUN", "M": "ME"}.get(interval)
    if rule is None:
        raise ValueError(f"interval harus 'W' atau 'M', bukan {interval!r}")
    df = prices[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    g = df.sort_values("date").groupby(pd.Grouper(key="date", freq=rule))
    out = pd.DataFrame({"date": g["date"].max(), "close": g["close"].last()}).dropna()
    return out.reset_index(drop=True)
