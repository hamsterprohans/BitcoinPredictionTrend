"""Bangun data dashboard retrospektif dari data scrap lokal + model F terekspor.

Pemakaian: python -m scripts.build_retro [--allow-mismatch] [--narratives]
Meniru notebook (10): sel 2.1-2.3, 3.3, 4.1-4.4 (tabel, split 70/15/15, jendela 20 hari di dalam split).
"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

from app import config
from app.features import TECH_FEATURES, compute_features

SENT3 = ["news_sentiment_pemahaman", "news_sentiment_detail", "news_sentiment_bullbear"]
NB_START, NB_END = "2018-02-01", "2026-04-30"


class ParityError(RuntimeError):
    pass


def assemble_table(prices, sent3, news_days, fg) -> pd.DataFrame:
    df = compute_features(prices)
    df["next_return"] = df["close"].pct_change().shift(-1)
    df["label"] = (df["next_return"] > 0).astype(int)
    df = df.dropna(subset=TECH_FEATURES + ["next_return"]).reset_index(drop=True)

    g = fg.copy()
    g["date"] = pd.to_datetime(g["date"])
    df = df.merge(g[["date", "fear_greed_index"]], on="date", how="left")
    df["fear_greed_index"] = df["fear_greed_index"].ffill(limit=2).fillna(50)
    df["fear_greed_index_scaled"] = df["fear_greed_index"] / 100.0

    s = sent3.copy()
    s["date"] = pd.to_datetime(s["date"])
    df = df.merge(s[["date"] + SENT3], on="date", how="left")
    has_news = df["date"].isin(news_days).to_numpy()
    tmp = df[SENT3].copy()
    tmp.loc[~has_news, :] = np.nan                                  # hari tanpa berita bersih -> NaN (bukan 0)
    df["news_sentiment"] = tmp.mean(axis=1).ffill(limit=2).fillna(0)
    df["has_news"] = has_news
    return df


def split_table(df, start=NB_START, end=NB_END):
    d = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].reset_index(drop=True)
    n = len(d)
    n_train, n_val_end = int(round(n * 0.70)), int(round(n * 0.85))
    return d.iloc[:n_train].copy(), d.iloc[n_train:n_val_end].copy(), d.iloc[n_val_end:].copy()


def scaled_matrix(df, scaler) -> np.ndarray:
    cols = TECH_FEATURES + ["news_sentiment"]
    scaled = np.clip(scaler.transform(df[cols]), -config.CLIP_VAL, config.CLIP_VAL)
    return np.hstack([scaled, df[["fear_greed_index_scaled"]].to_numpy()])


def predict_split(df_split, scaler, model, threshold, seq_len=config.SEQ_LEN):
    X = scaled_matrix(df_split, scaler)
    W = np.stack([X[i:i + seq_len] for i in range(len(X) - seq_len + 1)]).astype("float32")
    prob = np.asarray(model.predict(W, verbose=0)).ravel()
    return df_split.iloc[seq_len - 1:].reset_index(drop=True), prob, W


def metrics(actual, pred) -> dict:
    return {"Accuracy": float(accuracy_score(actual, pred)),
            "F1-Weighted": float(f1_score(actual, pred, average="weighted", zero_division=0))}


def check_parity(got: dict, expected: dict, tol: float = 0.002) -> None:
    bad = {k: (got[k], expected[k]) for k in ("Accuracy", "F1-Weighted") if abs(got[k] - expected[k]) > tol}
    if bad:
        raise ParityError("Hasil hitung ulang berbeda dari tabel notebook (toleransi %.3f): " % tol +
                          "; ".join(f"{k}: hitung ulang {a:.4f} vs notebook {b:.4f}" for k, (a, b) in bad.items()))
