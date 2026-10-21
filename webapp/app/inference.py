import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve

from . import config
from .features import TECH_FEATURES

SENTIMENT_COL = "news_sentiment"
FEATURE_ORDER = TECH_FEATURES + [SENTIMENT_COL, "fear_greed_index_scaled"]


class ArtifactsMissing(RuntimeError):
    """Artefak model dari notebook (10) belum lengkap."""


def youden_threshold(y, p) -> float:
    fpr, tpr, th = roc_curve(y, p)
    fpr, tpr, th = fpr[1:], tpr[1:], th[1:]  # buang titik threshold=inf
    return float(th[np.argmax(tpr - fpr)])


class Predictor:
    def __init__(self, scaler, models: dict, thresholds: dict):
        names = list(getattr(scaler, "feature_names_in_", []))
        expected = TECH_FEATURES + [SENTIMENT_COL]
        if names != expected:
            raise ValueError(
                f"Scaler dilatih dengan kolom {names[-1] if names else '?'} bukan '{SENTIMENT_COL}'. "
                "Ekspor ulang scaler.pkl dan model dari notebook (10) (lihat spec bagian 10).")
        self.scaler = scaler
        self.models = {int(h): list(m) for h, m in models.items()}
        self.thresholds = {int(h): float(t) for h, t in thresholds.items()}

    def build_window(self, frame: pd.DataFrame) -> np.ndarray:
        w = frame.sort_values("date").tail(config.SEQ_LEN)
        if len(w) < config.SEQ_LEN:
            raise ValueError(f"Butuh {config.SEQ_LEN} hari, hanya ada {len(w)}")
        feats = w[FEATURE_ORDER]
        if feats.isna().any().any():
            raise ValueError("Window berisi NaN: " + ", ".join(feats.columns[feats.isna().any()]))
        scaled = np.clip(self.scaler.transform(w[TECH_FEATURES + [SENTIMENT_COL]]),
                         -config.CLIP_VAL, config.CLIP_VAL)
        fg = w[["fear_greed_index_scaled"]].to_numpy()
        return np.hstack([scaled, fg]).astype("float32")[None, :, :]

    def predict(self, frame: pd.DataFrame) -> dict:
        X = self.build_window(frame)
        out = {}
        for h in sorted(self.models):
            prob = float(np.mean([float(m.predict(X, verbose=0).ravel()[0]) for m in self.models[h]]))
            thr = self.thresholds[h]
            out[h] = {"prob": prob, "threshold": thr, "direction": "NAIK" if prob > thr else "TURUN"}
        return out

    @classmethod
    def from_artifacts(cls, path=config.ARTIFACTS) -> "Predictor":
        import keras  # impor lambat; hanya saat benar-benar memuat model

        path = Path(path)
        needed = [path / "scaler.pkl", path / "models" / "model_F.keras", path / "threshold_beku.json"]
        missing = [str(p.relative_to(path)) for p in needed if not p.exists()]
        if missing:
            raise ArtifactsMissing(
                f"Artefak model belum lengkap di {path}. Belum ada: {', '.join(missing)}. "
                "Ekspor dari notebook (10) dengan sel pada README (bagian 'Ekspor artefak dari notebook (10)'), "
                "lalu taruh hasilnya di folder itu (model_F.keras di subfolder models/).")
        scaler = pickle.load(open(path / "scaler.pkl", "rb"))
        load = keras.saving.load_model
        models = {1: [load(path / "models" / "model_F.keras")]}
        thresholds = {1: float(json.load(open(path / "threshold_beku.json"))["THRESHOLD_OPTIMAL"])}
        mh = path / "multihorizon"
        mh_thr_file = mh / "thresholds.json"
        mh_thr = json.load(open(mh_thr_file)) if mh_thr_file.exists() else {}
        for h in config.HORIZONS[1:]:
            files = [mh / f"F_h{h}_s{s}.keras" for s in config.MH_SEEDS]
            if str(h) in mh_thr and all(f.exists() for f in files):
                models[h] = [load(f) for f in files]
                thresholds[h] = float(mh_thr[str(h)])
        return cls(scaler, models, thresholds)
