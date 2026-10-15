from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.jobs import Deps, run_daily
from app.sentiment import SentimentError
from app.store import atomic_write_json, load_sentiment_log, read_json
from tests.factories import FakePredictor, synthetic_prices

NOW = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)


def make_deps(tmp_path, *, seed_end=date(2026, 10, 12), api_days=(13, 14, 15),
              headlines=None, score=None, predictor=None):
    live = tmp_path / "live"
    live.mkdir()
    synthetic_prices(seed_end).to_csv(live / "prices.csv", index=False)
    last = float(pd.read_csv(live / "prices.csv")["close"].iloc[-1])
    calls = {"score": [], "headlines": []}

    def fetch_prices(start):
        rows = [(pd.Timestamp(2026, 10, d), last * (1 + 0.01 * i)) for i, d in enumerate(api_days, 1)
                if pd.Timestamp(2026, 10, d) >= pd.Timestamp(start)]
        return pd.DataFrame(rows, columns=["date", "close"])

    def fetch_headlines(day):
        calls["headlines"].append(day)
        return (headlines or (lambda d: ["Bitcoin up"]))(day)

    def _score(h):
        calls["score"].append(h)
        return (score or (lambda h: 2.0))(h)

    deps = Deps(live_dir=live, seed_tsv=tmp_path / "none.tsv", fetch_prices=fetch_prices,
                fetch_fear_greed=lambda: pd.DataFrame({"date": pd.date_range("2026-08-01", "2026-10-14"),
                                                       "fear_greed_index": 55.0}),
                fetch_headlines=fetch_headlines, score=_score,
                predictor=predictor or FakePredictor(), now=lambda: NOW)
    return deps, calls


def test_run_writes_snapshot_and_drops_incomplete_today(tmp_path):
    deps, calls = make_deps(tmp_path)
    latest = run_daily(deps)
    assert latest["as_of"] == "2026-10-14"                      # 15 Okt (hari berjalan) dibuang
    assert "2026-10-15" not in (deps.live_dir / "prices.csv").read_text()
    assert set(latest["horizons"]) == {"1", "3"}
    assert latest["horizons"]["1"]["target_date"] == "2026-10-15"
    assert latest["inputs"]["fear_greed_index"] == 55.0
    log = load_sentiment_log(deps.live_dir)
    assert len(log) >= 22                                        # window 20 hari + 2 hari untuk ffill
    hist = read_json(deps.live_dir / "history.json")
    assert hist[-1]["date"] == "2026-10-14" and "prob" in hist[-1]["horizons"]["1"]
    chart = read_json(deps.live_dir / "chart.json")
    assert chart["date"][-1] == "2026-10-14" and "RSI14" in chart


def test_idempotent_second_run(tmp_path):
    deps, calls = make_deps(tmp_path)
    run_daily(deps)
    n = len(calls["score"])
    assert run_daily(deps) is None
    assert len(calls["score"]) == n
    assert run_daily(deps, force=True) is not None


def test_no_news_today_uses_ffill_not_error(tmp_path):
    def headlines(day):
        return [] if day == date(2026, 10, 14) else ["Bitcoin up"]
    deps, _ = make_deps(tmp_path, headlines=headlines, score=lambda h: 4.0)
    fp = deps.predictor
    latest = run_daily(deps)
    last = fp.frames[-1].iloc[-1]
    assert last["news_sentiment"] == 4.0                         # ffill dari 13 Okt
    assert latest["inputs"]["news_sentiment_raw"] is None
    assert latest["inputs"]["headline_count"] == 0


def test_sentiment_failure_keeps_previous_latest(tmp_path):
    def boom(h):
        raise SentimentError("api mati")
    deps, _ = make_deps(tmp_path, score=boom)
    atomic_write_json(deps.live_dir / "latest.json", {"as_of": "2026-10-12", "sentinel": True, "horizons": {}})
    with pytest.raises(SentimentError):
        run_daily(deps)
    assert read_json(deps.live_dir / "latest.json")["sentinel"] is True


def test_history_gets_outcome_when_matured(tmp_path):
    deps, _ = make_deps(tmp_path, seed_end=date(2026, 10, 12), api_days=(13, 14))
    atomic_write_json(deps.live_dir / "history.json", [
        {"date": "2026-10-12", "close": 1.0,
         "horizons": {"1": {"prob": 0.6, "direction": "NAIK", "threshold": 0.4557}}}])
    run_daily(deps)
    hist = read_json(deps.live_dir / "history.json")
    assert hist[0]["horizons"]["1"]["actual"] == "NAIK"          # close 13 Okt > 12 Okt (harga sintetis naik)
    assert hist[0]["horizons"]["1"]["correct"] is True
    assert "actual" not in hist[-1]["horizons"]["1"]            # entri 14 Okt: target 15 Okt belum ada


def test_patient_fetch_waits_and_retries_same_day_after_block():
    from app.jobs import patient
    from app.sources import SourceError
    calls, waits = [], []

    def flaky(day):
        calls.append(day)
        if len(calls) < 3:
            raise SourceError("429")
        return ["Bitcoin up"]

    out = patient(flaky, cooldown=900, max_waits=5, sleep=waits.append)(date(2026, 9, 26))
    assert out == ["Bitcoin up"] and calls == [date(2026, 9, 26)] * 3 and waits == [900, 900]


def test_patient_fetch_gives_up_after_max_waits():
    from app.jobs import patient
    from app.sources import SourceError

    def always(day):
        raise SourceError("429")

    with pytest.raises(SourceError):
        patient(always, cooldown=1, max_waits=2, sleep=lambda s: None)(date(2026, 9, 26))
