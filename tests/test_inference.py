import pickle

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import RobustScaler

from app import config
from app.features import TECH_FEATURES
from app.inference import Predictor


def make_frame(n=30, seed=0):
    rng = np.random.default_rng(seed)
    d = {"date": pd.date_range("2026-09-01", periods=n)}
    for f in TECH_FEATURES + ["news_sentiment"]:
        d[f] = rng.normal(size=n)
    d["fear_greed_index_scaled"] = rng.uniform(0, 1, n)
    return pd.DataFrame(d)


def make_scaler(frame, sentiment_col="news_sentiment"):
    cols = TECH_FEATURES + [sentiment_col]
    return RobustScaler().fit(frame.rename(columns={"news_sentiment": sentiment_col})[cols])


class ConstModel:
    def __init__(self, p):
        self.p = p
        self.seen = None

    def predict(self, X, verbose=0):
        self.seen = X
        return np.full((len(X), 1), self.p, dtype="float32")


def test_window_shape_scaling_and_clip():
    f = make_frame()
    f.loc[f.index[-1], "Vol_7"] = 1e6  # outlier harus terpotong CLIP_VAL
    p = Predictor(make_scaler(f), {1: [ConstModel(0.6)]}, {1: 0.5})
    X = p.build_window(f)
    assert X.shape == (1, config.SEQ_LEN, 13) and X.dtype == np.float32
    assert np.abs(X[0, :, :12]).max() <= config.CLIP_VAL + 1e-6
    assert X[0, -1, 12] == pytest.approx(f["fear_greed_index_scaled"].iloc[-1], rel=1e-6)  # F&G tidak di-scale


def test_predict_direction_uses_threshold_and_ensemble_mean():
    f = make_frame()
    m = {1: [ConstModel(0.46)], 3: [ConstModel(0.2), ConstModel(0.6)]}
    p = Predictor(make_scaler(f), m, {1: 0.4557, 3: 0.5})
    out = p.predict(f)
    assert list(out) == [1, 3]
    assert out[1]["direction"] == "NAIK" and out[1]["prob"] == pytest.approx(0.46)
    assert out[3]["prob"] == pytest.approx(0.4) and out[3]["direction"] == "TURUN"
    assert out[3]["threshold"] == 0.5


def test_nan_in_window_rejected():
    f = make_frame()
    f.loc[f.index[-3], "MA30"] = np.nan
    p = Predictor(make_scaler(f), {1: [ConstModel(0.5)]}, {1: 0.5})
    with pytest.raises(ValueError, match="NaN"):
        p.build_window(f)


def test_scaler_trained_with_other_sentiment_column_fails_loudly():
    f = make_frame()
    with pytest.raises(ValueError, match="news_sentiment_detail"):
        Predictor(make_scaler(f, "news_sentiment_detail"), {1: [ConstModel(0.5)]}, {1: 0.5})


def test_real_artifacts_load_and_predict():
    path = config.ARTIFACTS
    needed = [path / "scaler.pkl", path / "models" / "model_F.keras", path / "threshold_beku.json"]
    if not all(p.exists() for p in needed):
        pytest.skip("artefak dari notebook (10) belum ada di " + str(path))
    pred = Predictor.from_artifacts(path)
    frame = pickle.load(open(path / "preprocessed.pkl", "rb"))["test_df"].tail(40)
    frame = frame.assign(news_sentiment=frame.get("news_sentiment", 0.0))
    out = pred.predict(frame)
    assert 0.0 <= out[1]["prob"] <= 1.0


def test_from_artifacts_lists_missing_files_with_guidance(tmp_path):
    from app.inference import ArtifactsMissing
    with pytest.raises(ArtifactsMissing) as e:
        Predictor.from_artifacts(tmp_path)
    msg = str(e.value)
    for name in ("scaler.pkl", "model_F.keras", "threshold_beku.json", "README"):
        assert name in msg, name
    assert isinstance(e.value, RuntimeError)                  # CLI dan penjadwal menangani sebagai kegagalan biasa
