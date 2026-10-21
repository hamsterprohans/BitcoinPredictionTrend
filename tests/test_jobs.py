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


def test_prices_only_writes_chart_without_prediction_or_keys(tmp_path):
    from app.jobs import run_prices_only
    deps, calls = make_deps(tmp_path)
    as_of = run_prices_only(deps)
    assert as_of == date(2026, 10, 14)                                   # 15 Okt (hari berjalan) dibuang
    chart = read_json(deps.live_dir / "chart.json")
    assert chart["date"][-1] == "2026-10-14" and "BB_up" in chart
    assert not (deps.live_dir / "latest.json").exists()
    assert not (deps.live_dir / "sentiment_log.csv").exists()
    assert calls["score"] == [] and calls["headlines"] == [] and deps.predictor.frames == []


def test_score_detail_logs_titles_and_prompt_scores(tmp_path):
    from app.store import read_news_entry
    deps, calls = make_deps(tmp_path, headlines=lambda d: [f"t{i}" for i in range(7)])
    deps.score_detail = lambda h: {"pemahaman": 4, "detail": 2, "bullbear": 0, "mean": 2.0}
    latest = run_daily(deps)
    e = read_news_entry(deps.live_dir, date(2026, 10, 14))
    assert e["titles"] == ["t0", "t1", "t2", "t3", "t4"] and e["scores"]["mean"] == 2.0   # hanya 5 judul pertama
    assert calls["score"] == []                                                           # score tidak dipanggil bila score_detail ada
    assert latest["inputs"]["news_sentiment_raw"] == 2.0


def test_explainer_result_is_stored_with_context(tmp_path):
    deps, _ = make_deps(tmp_path)
    deps.score_detail = lambda h: {"pemahaman": 1, "detail": 1, "bullbear": 1, "mean": 1.0}
    seen = {}

    def explainer(ctx):
        seen.update(ctx)
        return {"narrative": None, "contributions": []}

    deps.explainer = explainer
    latest = run_daily(deps)
    assert latest["explain"] == {"narrative": None, "contributions": []}
    assert seen["as_of"] == "2026-10-14" and 1 in seen["preds"] and "frame" in seen
    assert seen["news"]["titles"] and seen["news"]["scores"]["mean"] == 1.0
    assert read_json(deps.live_dir / "latest.json")["explain"] == latest["explain"]


def test_explainer_failure_never_blocks_the_prediction(tmp_path):
    deps, _ = make_deps(tmp_path)

    def boom(ctx):
        raise RuntimeError("llm mati")

    deps.explainer = boom
    latest = run_daily(deps)
    assert "explain" not in latest and latest["as_of"] == "2026-10-14"
    assert read_json(deps.live_dir / "latest.json")["as_of"] == "2026-10-14"           # prediksi tetap tertulis


def test_prediction_is_published_before_the_explainer_runs(tmp_path):
    deps, _ = make_deps(tmp_path)
    seen = {}

    def explainer(ctx):
        seen["on_disk"] = read_json(deps.live_dir / "latest.json")
        return {"narrative": None}

    deps.explainer = explainer
    run_daily(deps)
    assert seen["on_disk"]["as_of"] == "2026-10-14" and "explain" not in seen["on_disk"]   # prediksi terbit lebih dulu
    assert read_json(deps.live_dir / "latest.json")["explain"] == {"narrative": None}


def test_headline_source_prefers_cryptocompare_when_key_present():
    from app.jobs import make_headline_fetcher
    fetch, name = make_headline_fetcher(http=object(), env={"COINDESK_API_KEY": "k"})
    assert name.startswith("cryptocompare")
    fetch2, name2 = make_headline_fetcher(http=object(), env={})
    assert name2.startswith("rss")                       # tanpa kunci: RSS lebih andal daripada GDELT (sering memblokir)
    _, name3 = make_headline_fetcher(http=object(), env={"CRYPTOCOMPARE_API_KEY": "k2"})
    assert name3.startswith("cryptocompare")


# ---- backfill: hitung susulan hari yang terlewat dari data yang sudah tersimpan (tanpa API baru) ----
from app.jobs import run_backfill   # noqa: E402

LATER = datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)


def seeded_after_gap(tmp_path):
    deps, calls = make_deps(tmp_path)
    run_daily(deps)                                              # as_of 14 Okt: log sentimen terisi sampai 14 Okt
    deps.now = lambda: LATER
    run_daily(deps)                                              # as_of 15 Okt; lalu entri 14 Okt "hilang" (hari terlewat)
    h = read_json(deps.live_dir / "history.json")
    atomic_write_json(deps.live_dir / "history.json", [e for e in h if e["date"] != "2026-10-14"])
    calls["score"].clear()
    calls["headlines"].clear()
    return deps, calls


def test_backfill_adds_missing_day_flags_it_and_leaves_latest_untouched(tmp_path):
    deps, calls = seeded_after_gap(tmp_path)
    latest_before = (deps.live_dir / "latest.json").read_text()
    entry = run_backfill(deps, date(2026, 10, 14))
    hist = read_json(deps.live_dir / "history.json")
    assert [e["date"] for e in hist] == ["2026-10-14", "2026-10-15"]
    assert hist[0]["backfilled"] is True and "backfilled" not in hist[1]
    assert entry["date"] == "2026-10-14" and "prob" in hist[0]["horizons"]["1"]
    assert (deps.live_dir / "latest.json").read_text() == latest_before          # prediksi terbaru tidak berubah
    assert calls["score"] == [] and calls["headlines"] == []                     # tanpa panggilan berita/LLM


def test_backfill_uses_only_data_up_to_that_day(tmp_path):
    seen = {}

    class Spy(FakePredictor):
        def predict(self, frame):
            seen["last"] = frame["date"].max()
            return super().predict(frame)
    deps, _ = seeded_after_gap(tmp_path)
    deps.predictor = Spy()
    run_backfill(deps, date(2026, 10, 14))
    assert seen["last"] == pd.Timestamp("2026-10-14")                            # tidak ada kebocoran data setelahnya


def test_backfill_evaluates_outcome_when_target_already_known(tmp_path):
    deps, _ = seeded_after_gap(tmp_path)
    run_backfill(deps, date(2026, 10, 14))
    v = read_json(deps.live_dir / "history.json")[0]["horizons"]["1"]
    assert v["actual"] in ("NAIK", "TURUN") and isinstance(v["correct"], bool)


def test_backfill_never_overwrites_a_real_prediction(tmp_path):
    deps, _ = seeded_after_gap(tmp_path)
    before = read_json(deps.live_dir / "history.json")
    assert run_backfill(deps, date(2026, 10, 15)) is None                        # 15 Okt sudah punya prediksi asli
    assert read_json(deps.live_dir / "history.json") == before


def test_backfill_refuses_when_price_or_sentiment_is_missing_and_changes_nothing(tmp_path):
    deps, _ = seeded_after_gap(tmp_path)
    before = (deps.live_dir / "history.json").read_text()
    for bad in (date(2026, 10, 20), date(2026, 8, 1)):                           # di luar harga / di luar log sentimen
        with pytest.raises(RuntimeError):
            run_backfill(deps, bad)
    assert (deps.live_dir / "history.json").read_text() == before


def test_forced_rerun_cannot_change_an_already_issued_prediction(tmp_path):
    class Drifting(FakePredictor):                                # jawabannya berbeda pada tiap panggilan
        n = 0

        def predict(self, frame):
            Drifting.n += 1
            return {h: {"prob": 0.9 if Drifting.n == 1 else 0.1, "threshold": 0.5,
                        "direction": "NAIK" if Drifting.n == 1 else "TURUN"} for h in (1, 3)}
    deps, _ = make_deps(tmp_path, predictor=Drifting())
    run_daily(deps)
    before = read_json(deps.live_dir / "history.json")[-1]["horizons"]["1"].copy()
    assert before["direction"] == "NAIK"
    run_daily(deps, force=True)                                   # hitung ulang: prediksi kini TURUN, tetapi riwayat tidak boleh berubah
    assert read_json(deps.live_dir / "history.json")[-1]["horizons"]["1"] == before
    assert read_json(deps.live_dir / "latest.json")["horizons"]["1"]["direction"] == "NAIK"    # kartu utama pun mengikuti yang sudah terbit


def test_news_log_keeps_the_original_article_urls_next_to_titles(tmp_path):
    from app.sources import Judul
    deps, _ = make_deps(tmp_path, headlines=lambda d: [Judul(f"Bitcoin {i}", f"https://contoh.com/{i}") for i in range(7)])
    run_daily(deps)
    log = read_json(deps.live_dir / "news_log.json")["2026-10-14"]
    assert log["titles"] == [f"Bitcoin {i}" for i in range(5)]                  # lima judul pertama, str biasa (JSON aman)
    assert log["urls"] == [f"https://contoh.com/{i}" for i in range(5)]         # sejajar dengan judul


def test_news_log_without_urls_stays_backward_compatible(tmp_path):
    deps, _ = make_deps(tmp_path)                                               # judul str biasa (tanpa atribut url)
    run_daily(deps)
    assert "urls" not in read_json(deps.live_dir / "news_log.json")["2026-10-14"]


# ---- melengkapi URL berita yang tersimpan tanpa tautan (satu panggilan sumber, hanya mengisi yang kosong) ----
from app.jobs import fill_missing_urls   # noqa: E402
from app.sources import Judul, SourceError   # noqa: E402


def seeded_news(tmp_path, with_urls=False):
    live = tmp_path / "live"
    live.mkdir()
    entry = {"titles": ["Bitcoin A", "Bitcoin B", "Bitcoin C"], "scores": {"mean": 1.0}}
    if with_urls:
        entry["urls"] = ["https://old.com/a", None, None]
    atomic_write_json(live / "news_log.json", {"2026-10-19": entry, "2026-10-18": {"titles": ["X"], "scores": None}})
    atomic_write_json(live / "latest.json", {"as_of": "2026-10-19", "explain": {
        "headlines": [{"title": "Bitcoin A"}, {"title": "Bitcoin B"}, {"title": "Bitcoin C"}]}})
    return live


def test_fill_missing_urls_aligns_by_title_not_by_order(tmp_path):
    live = seeded_news(tmp_path)
    fetched = [Judul("Bitcoin C", "https://c.com/1"), Judul("Bitcoin A", "https://a.com/1"), Judul("Lain", "https://z.com/1")]
    assert fill_missing_urls(live, date(2026, 10, 19), lambda d: fetched) == 2
    log = read_json(live / "news_log.json")["2026-10-19"]
    assert log["titles"] == ["Bitcoin A", "Bitcoin B", "Bitcoin C"]                      # judul yang sudah dinilai tak berubah
    assert log["urls"] == ["https://a.com/1", None, "https://c.com/1"]                    # B tidak ditemukan: tanpa tautan, tidak dikarang
    heads = read_json(live / "latest.json")["explain"]["headlines"]
    assert heads[0]["url"] == "https://a.com/1" and "url" not in heads[1] and heads[2]["url"] == "https://c.com/1"


def test_fill_missing_urls_does_not_call_the_source_when_every_url_exists(tmp_path):
    live = seeded_news(tmp_path)
    log = read_json(live / "news_log.json")
    log["2026-10-19"]["urls"] = ["https://a.com", "https://b.com", "https://c.com"]
    atomic_write_json(live / "news_log.json", log)

    def boom(day):
        raise AssertionError("tidak boleh memanggil sumber (hemat kuota)")
    assert fill_missing_urls(live, date(2026, 10, 19), boom) == 0
    assert read_json(live / "news_log.json")["2026-10-19"]["urls"] == ["https://a.com", "https://b.com", "https://c.com"]


def test_fill_missing_urls_keeps_existing_urls_and_only_fills_blanks(tmp_path):
    live = seeded_news(tmp_path, with_urls=True)
    atomic_write_json(live / "news_log.json", {"2026-10-19": {"titles": ["Bitcoin A", "Bitcoin B"], "scores": None,
                                                              "urls": ["https://old.com/a", None]}})
    fetched = [Judul("Bitcoin A", "https://NEW.com/a"), Judul("Bitcoin B", "https://b.com/1")]
    assert fill_missing_urls(live, date(2026, 10, 19), lambda d: fetched) == 1
    assert read_json(live / "news_log.json")["2026-10-19"]["urls"] == ["https://old.com/a", "https://b.com/1"]


def test_fill_missing_urls_unknown_day_or_source_failure_changes_nothing(tmp_path):
    live = seeded_news(tmp_path)
    before = (live / "news_log.json").read_text(), (live / "latest.json").read_text()
    assert fill_missing_urls(live, date(2026, 10, 1), lambda d: [Judul("Bitcoin A", "https://a.com")]) == 0   # tak ada entri hari itu

    def fail(day):
        raise SourceError("dibatasi")
    with pytest.raises(SourceError):
        fill_missing_urls(live, date(2026, 10, 19), fail)
    assert ((live / "news_log.json").read_text(), (live / "latest.json").read_text()) == before


def test_fill_missing_urls_leaves_latest_alone_when_it_is_another_day(tmp_path):
    live = seeded_news(tmp_path)
    atomic_write_json(live / "latest.json", {"as_of": "2026-10-20", "explain": {"headlines": [{"title": "Bitcoin A"}]}})
    fill_missing_urls(live, date(2026, 10, 19), lambda d: [Judul("Bitcoin A", "https://a.com/1")])
    assert "url" not in read_json(live / "latest.json")["explain"]["headlines"][0]


# ---- rantai sumber berita: CryptoCompare -> RSS (-> GDELT) ----
def test_headline_chain_names_and_order():
    from app.jobs import make_headline_fetcher
    _, with_key = make_headline_fetcher(http=object(), env={"COINDESK_API_KEY": "k"})
    _, no_key = make_headline_fetcher(http=object(), env={})
    assert with_key == "cryptocompare (cadangan: rss)"
    assert no_key == "rss (cadangan: gdelt)"


def test_headline_chain_falls_back_to_rss_when_cryptocompare_is_limited(monkeypatch):
    from app import sources
    from app.jobs import make_headline_fetcher
    calls = []
    def cc(http, day, key, **kw):
        calls.append("cc")
        raise SourceError("CryptoCompare: kuota bulanan habis")
    def rss(http, day, **kw):
        calls.append("rss")
        return [Judul("Bitcoin via rss", "https://x.com/1", "rss")]
    monkeypatch.setattr(sources, "fetch_headlines_cryptocompare", cc)
    monkeypatch.setattr(sources, "fetch_headlines_rss", rss)
    fetch, _ = make_headline_fetcher(http=object(), env={"COINDESK_API_KEY": "k"})
    out = fetch(date(2026, 10, 20))
    assert calls == ["cc", "rss"] and [str(h) for h in out] == ["Bitcoin via rss"] and out[0].source == "rss"


def test_headline_chain_does_not_touch_rss_when_the_primary_works(monkeypatch):
    from app import sources
    from app.jobs import make_headline_fetcher
    monkeypatch.setattr(sources, "fetch_headlines_cryptocompare", lambda http, day, key, **kw: [Judul("Bitcoin cc", None, "cryptocompare")])
    def boom(*a, **k):
        raise AssertionError("RSS tidak boleh dipanggil")
    monkeypatch.setattr(sources, "fetch_headlines_rss", boom)
    fetch, _ = make_headline_fetcher(http=object(), env={"COINDESK_API_KEY": "k"})
    assert [str(h) for h in fetch(date(2026, 10, 20))] == ["Bitcoin cc"]


def test_headline_chain_reports_every_failure_when_all_sources_fail(monkeypatch):
    from app import sources
    from app.jobs import make_headline_fetcher
    def fail(msg):
        def _f(*a, **k):
            raise SourceError(msg)
        return _f
    monkeypatch.setattr(sources, "fetch_headlines_cryptocompare", fail("CC dibatasi"))
    monkeypatch.setattr(sources, "fetch_headlines_rss", fail("RSS kosong"))
    fetch, _ = make_headline_fetcher(http=object(), env={"COINDESK_API_KEY": "k"})
    with pytest.raises(SourceError) as e:
        fetch(date(2026, 10, 20))
    assert "CC dibatasi" in str(e.value) and "RSS kosong" in str(e.value)                    # kedua penyebab terlihat di log


def test_news_log_records_which_source_supplied_the_headlines(tmp_path):
    deps, _ = make_deps(tmp_path, headlines=lambda d: [Judul(f"Bitcoin {i}", f"https://x.com/{i}", "rss") for i in range(3)])
    run_daily(deps)
    assert read_json(deps.live_dir / "news_log.json")["2026-10-14"]["source"] == "rss"


def test_news_log_has_no_source_key_when_headlines_do_not_declare_one(tmp_path):
    deps, _ = make_deps(tmp_path)
    run_daily(deps)
    assert "source" not in read_json(deps.live_dir / "news_log.json")["2026-10-14"]
