import numpy as np
import pandas as pd
import pytest

from scripts.build_retro import (ParityError, assemble_table, check_parity, metrics, predict_split, scaled_matrix,
                                 split_table)
from tests.factories import FakeRetroModel, SENT3_COLS, fit_scaler, synthetic_retro_inputs

IN = synthetic_retro_inputs()
NEWS_DAYS = set(pd.to_datetime(IN["news"]["date"]).dt.normalize())


def table():
    return assemble_table(IN["prices"], IN["sent3"], NEWS_DAYS, IN["fg"])


def test_label_alignment_and_last_row_dropped():
    t = table()
    close = IN["prices"].set_index("date")["close"]
    for d in (t["date"].iloc[10], t["date"].iloc[-1]):
        assert t.loc[t["date"] == d, "label"].iloc[0] == int(close[d + pd.Timedelta(days=1)] > close[d])
    assert t["date"].max() == IN["dates"][-2]                       # hari terakhir tidak punya label


def test_news_sentiment_mean_ffill_two_days_then_zero():
    t = table().set_index("date")
    d = IN["dates"]
    mean = lambda i: IN["sent3"].iloc[i][SENT3_COLS].mean()
    assert t.loc[d[149], "news_sentiment"] == pytest.approx(mean(149))
    assert t.loc[d[150], "news_sentiment"] == pytest.approx(mean(149))      # ffill hari ke-1
    assert t.loc[d[151], "news_sentiment"] == pytest.approx(mean(149))      # ffill hari ke-2
    assert t.loc[d[152], "news_sentiment"] == 0.0                           # lebih dari 2 hari -> 0
    assert not t.loc[d[150], "has_news"] and t.loc[d[149], "has_news"]


def test_fear_greed_scaled_is_plain_division_by_100():
    t = table()
    assert np.allclose(t["fear_greed_index_scaled"] * 100, t["fear_greed_index"])


def test_split_sizes_follow_notebook_rounding():
    t = table()
    tr, va, te = split_table(t, IN["start"], IN["end"])
    n = len(tr) + len(va) + len(te)
    assert len(tr) == round(n * 0.70) and len(tr) + len(va) == round(n * 0.85)
    assert tr["date"].max() < va["date"].min() and va["date"].max() < te["date"].min()


def test_windows_stay_inside_the_test_split():
    t = table()
    tr, va, te = split_table(t, IN["start"], IN["end"])
    sc = fit_scaler(IN)
    rows, prob, W = predict_split(te, sc, FakeRetroModel(), 0.5)
    assert len(rows) == len(te) - 19 == len(prob) == len(W)
    assert rows["date"].iloc[0] == te["date"].iloc[19]                       # prediksi pertama = hari ke-20 split uji
    X = scaled_matrix(te, sc)
    assert np.allclose(W[0], X[:20]) and W.shape[1:] == (20, 13)
    assert rows["date"].min() > va["date"].max()                              # tidak ada jendela yang menyentuh val
    assert (rows["label"].to_numpy() == te["label"].iloc[19:].to_numpy()).all()


def test_scaled_matrix_clips_and_keeps_fear_greed_unscaled():
    t = table()
    t.loc[t.index[-1], "Vol_7"] = 1e9
    X = scaled_matrix(t, fit_scaler(IN))
    assert np.abs(X[:, :12]).max() <= 5.0 + 1e-9
    assert np.allclose(X[:, 12], t["fear_greed_index_scaled"].to_numpy())


def test_parity_pass_and_fail_messages():
    got = {"Accuracy": 0.5012, "F1-Weighted": 0.4994}
    check_parity(got, {"Accuracy": 0.5013, "F1-Weighted": 0.4990})            # dalam 0,002
    with pytest.raises(ParityError) as e:
        check_parity(got, {"Accuracy": 0.5500, "F1-Weighted": 0.4994})
    assert "0.5012" in str(e.value) and "0.5500" in str(e.value) and "Accuracy" in str(e.value)


def test_metrics_values():
    m = metrics(np.array([1, 0, 1, 1]), np.array([1, 0, 0, 1]))
    assert m["Accuracy"] == pytest.approx(0.75) and 0.0 <= m["F1-Weighted"] <= 1.0


import json  # noqa: E402

from scripts.build_retro import build_outputs, fill_narratives, train_stats, write_outputs  # noqa: E402
from tests.test_narrative import FakeLLM  # noqa: E402

THR = 0.5


def outputs(**kw):
    sc = fit_scaler(IN)
    return build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], sc, FakeRetroModel(), THR,
                         start=IN["start"], end=IN["end"], allow_mismatch=True, **kw)


def test_build_outputs_series_days_and_reliability():
    out = outputs()
    s, days = out["series"], out["days"]
    n = len(s["date"])
    assert n == len(days) > 25 and len(s["prob"]) == len(s["pred"]) == len(s["actual"]) == len(s["correct"]) == n
    assert s["threshold"] == THR and 0.0 <= s["auc"] <= 1.0 and len(s["level_cuts"]) == 2
    assert [r["level"] for r in s["reliability"]] == ["rendah", "sedang", "tinggi"]
    assert sum(r["n"] for r in s["reliability"]) == n and s["parity"]["verified"] is False
    d = days[s["date"][5]]
    assert d["direction"] in ("NAIK", "TURUN") and d["actual"] in ("NAIK", "TURUN") and d["correct"] == (d["direction"] == d["actual"])
    assert d["target_date"] == (pd.Timestamp(d["date"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    assert len(d["features"]) == 13 and len(d["contributions"]) == 13 and d["narrative"] is None
    deltas = [abs(c["delta_pp"]) for c in d["contributions"]]
    assert deltas == sorted(deltas, reverse=True)
    firsts = [dd["contributions"][0] for dd in days.values()]                  # model uji hanya bergantung pada Fear & Greed
    assert all(f["feature"] == "fear_greed_index_scaled" or f["delta_pp"] == 0 for f in firsts)
    assert any(f["delta_pp"] != 0 for f in firsts)


def test_headlines_are_first_five_in_file_order_and_missing_news_is_honest():
    out = outputs()
    days = out["days"]
    no_news_dates = {pd.Timestamp(IN["dates"][i]) for i in IN["no_news"]}
    with_news = next(k for k in days if pd.Timestamp(k) not in no_news_dates)
    assert [h["title"] for h in days[with_news]["headlines"]] == \
        IN["news"][IN["news"]["date"] == pd.Timestamp(with_news)]["title"].head(5).tolist()
    assert days[with_news]["sentiment"]["has_news"] is True and days[with_news]["sentiment"]["scores"] is not None
    missing = next(k for k in days if pd.Timestamp(k) in no_news_dates)
    sent = days[missing]["sentiment"]
    assert sent["has_news"] is False and sent["scores"] is None and days[missing]["headlines"] == []


def test_parity_failure_raises_and_writes_nothing(tmp_path):
    sc = fit_scaler(IN)
    with pytest.raises(ParityError):
        build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], sc, FakeRetroModel(), THR,
                      start=IN["start"], end=IN["end"], expected={"Accuracy": 0.99, "F1-Weighted": 0.99})
    with pytest.raises(ParityError):                                          # tanpa tabel notebook juga ditolak
        build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], sc, FakeRetroModel(), THR,
                      start=IN["start"], end=IN["end"], expected=None)
    assert list(tmp_path.iterdir()) == []


def test_parity_verified_when_expected_matches():
    base = outputs()["series"]
    got = base["parity"]["got"]
    sc = fit_scaler(IN)
    out = build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], sc, FakeRetroModel(), THR,
                        start=IN["start"], end=IN["end"], expected={k: round(v, 4) for k, v in got.items()})
    assert out["series"]["parity"]["verified"] is True


def test_train_stats_has_101_quantiles_for_13_features():
    t = table()
    tr, _, _ = split_table(t, IN["start"], IN["end"])
    st = train_stats(tr)
    assert len(st["quantiles"]) == 13 and all(len(v) == 101 for v in st["quantiles"].values())
    assert st["quantiles"]["RSI14"][0] == pytest.approx(tr["RSI14"].min())


def test_write_outputs_and_resumable_narratives(tmp_path):
    out = outputs()
    write_outputs(tmp_path, out)
    assert (tmp_path / "series.json").exists() and (tmp_path / "train_stats.json").exists()
    days = sorted((tmp_path / "days").glob("*.json"))
    assert len(days) == len(out["days"])
    from app.explain import build_facts, template_narrative
    first = json.loads(days[0].read_text())
    good = template_narrative(build_facts(first, auc=out["series"]["auc"]))
    llm = FakeLLM([good] * (3 * len(days)))       # hari selain pertama ditolak validator -> 3 percobaan lalu template
    assert fill_narratives(tmp_path, llm) == len(days)
    again = FakeLLM([])
    assert fill_narratives(tmp_path, again) == 0 and again.calls == []          # dapat dilanjutkan: tidak memanggil ulang
    data = json.loads(days[0].read_text())
    assert data["narrative"]["source"] == "llm" and "bukan saran investasi" in data["narrative"]["text"]


def test_main_reports_missing_artifacts_without_traceback(monkeypatch):
    from app.inference import ArtifactsMissing, Predictor
    from scripts.build_retro import main

    def boom(*a, **k):
        raise ArtifactsMissing("Artefak model belum lengkap di X. Belum ada: threshold_beku.json.")

    monkeypatch.setattr(Predictor, "from_artifacts", classmethod(lambda cls, *a, **k: boom()))
    with pytest.raises(SystemExit) as e:
        main([])
    assert "Artefak model belum lengkap" in str(e.value)


def test_rebuild_keeps_unchanged_narratives_and_removes_stale_day_files(tmp_path):
    from app.store import atomic_write_json
    write_outputs(tmp_path, outputs())
    files = sorted((tmp_path / "days").glob("*.json"))
    rec = json.loads(files[2].read_text())
    rec["narrative"] = {"text": "x", "source": "llm", "attempts": 1, "temperature": 0.1}
    atomic_write_json(files[2], rec)
    (tmp_path / "days" / "2020-01-01.json").write_text("{}")                    # sisa dari build lama
    write_outputs(tmp_path, outputs())                                          # build ulang dengan fakta yang sama
    assert json.loads(files[2].read_text())["narrative"]["text"] == "x"
    assert not (tmp_path / "days" / "2020-01-01.json").exists()
    sc = fit_scaler(IN)
    changed = build_outputs(IN["prices"], IN["sent3"], IN["news"], IN["fg"], sc, FakeRetroModel(), 0.45,
                            start=IN["start"], end=IN["end"], allow_mismatch=True)   # ambang lain -> fakta berubah
    write_outputs(tmp_path, changed)
    assert json.loads(files[2].read_text())["narrative"] is None


def test_fill_narratives_can_redo_template_fallbacks(tmp_path):
    from app.explain import build_facts, template_narrative
    out = outputs()
    write_outputs(tmp_path, out)
    files = sorted((tmp_path / "days").glob("*.json"))
    first = json.loads(files[0].read_text())
    first["narrative"] = {"text": "t", "source": "template", "attempts": 3, "temperature": None}
    second = json.loads(files[1].read_text())
    second["narrative"] = {"text": "l", "source": "llm", "attempts": 1, "temperature": None}
    from app.store import atomic_write_json
    atomic_write_json(files[0], first)
    atomic_write_json(files[1], second)
    good = template_narrative(build_facts(first, auc=out["series"]["auc"]))
    llm = FakeLLM([good] * (3 * len(files)))
    # semua hari kecuali narasi LLM yang sudah ada: yang kosong dan yang berstatus template
    assert fill_narratives(tmp_path, llm, redo_template=True) == len(files) - 1
    assert json.loads(files[0].read_text())["narrative"]["source"] == "llm"
    assert json.loads(files[1].read_text())["narrative"]["text"] == "l"        # narasi LLM tidak disentuh


def test_fill_narratives_stops_on_billing_error_without_writing_templates(tmp_path):
    from app.explain import FatalAPIError
    write_outputs(tmp_path, outputs())
    before = {f.name: f.read_text() for f in (tmp_path / "days").glob("*.json")}
    with pytest.raises(FatalAPIError):
        fill_narratives(tmp_path, FakeLLM([RuntimeError("Your credit balance is too low")]))
    after = {f.name: f.read_text() for f in (tmp_path / "days").glob("*.json")}
    assert after == before                                                     # tidak ada narasi template yang tertulis
