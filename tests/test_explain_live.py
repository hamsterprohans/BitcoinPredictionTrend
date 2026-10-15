import numpy as np
import pandas as pd
import pytest

from app.explain import build_live_explain
from app.inference import FEATURE_ORDER
from tests.factories import FakeRetroModel
from tests.test_narrative import FakeLLM


class FakePredictor:
    scaler = None
    models = {1: [FakeRetroModel()]}

    def build_window(self, frame):
        X = np.zeros((1, 20, 13), dtype="float32")
        X[0, :, 12] = 0.7                                       # Fear & Greed terskala 0,7 -> p = 0.3 + 0.28 = 0.58
        return X


def _frame():
    row = {f: 1.0 for f in FEATURE_ORDER}
    row["fear_greed_index_scaled"] = 0.7
    return pd.DataFrame([row])


def _stats():
    q = {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}
    q["fear_greed_index_scaled"] = np.round(np.linspace(0, 1, 101), 6).tolist()      # median 0,5
    return {"quantiles": q}


NEWS = {"titles": ["Bitcoin naik", "ETF masuk"], "scores": {"pemahaman": 3, "detail": 2, "bullbear": 1, "mean": 2.0}}
PRED = {"prob": 0.58, "threshold": 0.4557, "direction": "NAIK"}
SERIES = {"level_cuts": [0.03, 0.08], "auc": 0.52}


def test_live_explain_block_without_llm():
    ex = build_live_explain(predictor=FakePredictor(), frame=_frame(), pred=PRED, news=NEWS, as_of="2026-10-14",
                            stats=_stats(), series=SERIES, client=None)
    assert [h["title"] for h in ex["headlines"]] == NEWS["titles"]
    assert ex["sentiment"] == {"has_news": True, "scores": NEWS["scores"], "used": 1.0}
    assert len(ex["contributions"]) == 13 and len(ex["features"]) == 13
    top = ex["contributions"][0]
    assert top["feature"] == "fear_greed_index_scaled" and top["delta_pp"] == pytest.approx(8.0, abs=1e-3)   # 100*(0.58-0.50)
    assert ex["level"] == "tinggi" and ex["narrative"] is None


def test_live_explain_without_news_and_with_llm_falls_back_to_template():
    ex = build_live_explain(predictor=FakePredictor(), frame=_frame(), pred=PRED, news=None, as_of="2026-10-14",
                            stats=_stats(), series=None, client=FakeLLM(["salah"] * 3))
    assert ex["headlines"] == [] and ex["sentiment"]["has_news"] is False and ex["sentiment"]["scores"] is None
    assert ex["level"] is None
    assert ex["narrative"]["source"] == "template" and "bukan saran investasi" in ex["narrative"]["text"]
