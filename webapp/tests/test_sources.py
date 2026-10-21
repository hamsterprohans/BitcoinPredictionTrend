from datetime import date

import httpx
import pandas as pd
import pytest

from app.sources import (SourceError, fetch_fear_greed, fetch_headlines,
                         fetch_prices, read_price_tsv)


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_read_price_tsv_utf16(tmp_path):
    p = tmp_path / "p.tsv"
    p.write_text('"Time"\t"BTC / USD Denominated Closing Price"\n"2026-04-29"\t75795.0\n"2026-04-30"\t76299.6\n',
                 encoding="utf-16")
    df = read_price_tsv(p)
    assert list(df.columns) == ["date", "close"]
    assert df["date"].iloc[-1] == pd.Timestamp("2026-04-30")
    assert df["close"].iloc[-1] == pytest.approx(76299.6)


def test_fetch_prices_parses_and_drops_missing():
    def handler(req):
        assert req.url.params["metrics"] == "PriceUSD"
        assert req.url.params["start_time"] == "2026-10-12"
        return httpx.Response(200, json={"data": [
            {"asset": "btc", "time": "2026-10-12T00:00:00.000000000Z", "PriceUSD": "100.5"},
            {"asset": "btc", "time": "2026-10-13T00:00:00.000000000Z", "PriceUSD": None},
            {"asset": "btc", "time": "2026-10-14T00:00:00.000000000Z", "PriceUSD": "102"},
        ]})
    df = fetch_prices(client(handler), date(2026, 10, 12))
    assert df["date"].tolist() == [pd.Timestamp("2026-10-12"), pd.Timestamp("2026-10-14")]
    assert df["close"].tolist() == [100.5, 102.0]


def test_fetch_fear_greed():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"value": "40", "timestamp": "1760400000"},  # 2025-10-14 00:00 UTC
            {"value": "45", "timestamp": "1760486400"},
        ]})
    df = fetch_fear_greed(client(handler), limit=2)
    assert df["fear_greed_index"].tolist() == [40.0, 45.0]
    assert df["date"].is_monotonic_increasing


def test_fetch_headlines_filters_btc_sponsor_and_dupes():
    arts = [
        {"title": "Bitcoin jumps 5%"}, {"title": "Bitcoin jumps 5%"},
        {"title": "Ethereum rallies"},
        {"title": "Best crypto to buy: Bitcoin presale"},
        {"title": "BTC holds $100k"},
    ]
    def handler(req):
        assert req.url.params["startdatetime"] == "20261014000000"
        assert req.url.params["enddatetime"] == "20261014235959"
        return httpx.Response(200, json={"articles": arts})
    assert fetch_headlines(client(handler), date(2026, 10, 14), sleep=lambda s: None) == [
        "Bitcoin jumps 5%", "BTC holds $100k"]


def test_fetch_headlines_empty_body_is_throttling_and_is_retried():
    # Bukti dari run nyata: GDELT membalas badan KOSONG (200) saat dibatasi, bukan karena tidak ada berita Bitcoin.
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(200, text="")
        return httpx.Response(200, json={"articles": [{"title": "Bitcoin up"}]})
    waits = []
    out = fetch_headlines(client(handler), date(2026, 10, 14), sleep=waits.append)
    assert out == ["Bitcoin up"] and calls["n"] == 3
    assert waits[:2] == [15, 30]                                   # jeda naik seperti pada 429


def test_fetch_headlines_persistent_empty_body_raises_instead_of_caching_no_news():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, text="")
    with pytest.raises(SourceError, match="kosong"):
        fetch_headlines(client(handler), date(2026, 10, 14), sleep=lambda s: None)
    assert calls["n"] == 4                                          # 1 + 3 ulang


def test_fetch_headlines_valid_json_with_no_articles_is_no_news():
    def handler(req):
        return httpx.Response(200, json={"articles": []})
    assert fetch_headlines(client(handler), date(2026, 10, 14), sleep=lambda s: None) == []


def test_fetch_headlines_retries_429_then_raises():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, text="slow down")
    with pytest.raises(SourceError):
        fetch_headlines(client(handler), date(2026, 10, 14), sleep=lambda s: None)
    assert calls["n"] == 4  # 1 + 3 ulang


def test_fetch_spot_parses_coinbase_amount():
    from app.sources import fetch_spot
    def handler(req):
        assert req.url.host == "api.coinbase.com" and req.url.path.endswith("/BTC-USD/spot")
        return httpx.Response(200, json={"data": {"base": "BTC", "currency": "USD", "amount": "81131.45"}})
    assert fetch_spot(client(handler)) == pytest.approx(81131.45)


def test_fetch_spot_retries_once_on_transient_error():
    from app.sources import fetch_spot
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("sesaat")
        return httpx.Response(200, json={"data": {"amount": "81000.5"}})
    assert fetch_spot(client(handler)) == pytest.approx(81000.5) and calls["n"] == 2


def test_fetch_spot_gives_up_after_second_failure():
    from app.sources import fetch_spot
    def handler(req):
        raise httpx.ConnectError("mati")
    with pytest.raises(httpx.HTTPError):
        fetch_spot(client(handler))


# ---- CryptoCompare (sumber berita korpus latih; butuh API key) ----
import datetime as _dt  # noqa: E402


def _ts(y, m, d, h=0, mi=0):
    return int(_dt.datetime(y, m, d, h, mi, tzinfo=_dt.timezone.utc).timestamp())


def _art(ts, title):
    return {"published_on": ts, "title": title, "url": "https://x/" + str(ts)}


def test_cryptocompare_collects_one_utc_day_newest_first_with_filters_and_paging():
    from app.sources import fetch_headlines_cryptocompare
    day = date(2026, 10, 14)
    pages = [
        [_art(_ts(2026, 10, 15, 0, 5), "Bitcoin besok"), _art(_ts(2026, 10, 14, 23, 0), "Bitcoin jumps 5%"),
         _art(_ts(2026, 10, 14, 22, 0), "Ethereum rallies"), _art(_ts(2026, 10, 14, 21, 0), "Best crypto to buy: Bitcoin presale")],
        [_art(_ts(2026, 10, 14, 12, 0), "BTC holds $100k"), _art(_ts(2026, 10, 14, 11, 0), "Bitcoin jumps 5%"),
         _art(_ts(2026, 10, 13, 23, 59), "Bitcoin kemarin")],
    ]
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        assert req.headers["authorization"] == "Apikey SECRET"
        return httpx.Response(200, json={"Type": 100, "Data": pages.pop(0)})

    out = fetch_headlines_cryptocompare(client(handler), day, "SECRET", sleep=lambda s: None, want=50)
    assert out == ["Bitcoin jumps 5%", "BTC holds $100k"]                   # hari itu saja, terbaru dulu, tersaring, unik
    assert seen[0]["lTs"] == str(_ts(2026, 10, 15, 0, 0)) and seen[0]["categories"] == "BTC"
    assert seen[1]["lTs"] == str(_ts(2026, 10, 14, 21, 0))                   # halaman berikut: mundur dari artikel terlama
    assert len(seen) == 2                                                    # berhenti setelah melewati awal hari


def test_cryptocompare_stops_after_one_page_when_enough_headlines_and_respects_rate_limit():
    from app.sources import fetch_headlines_cryptocompare
    page = [_art(_ts(2026, 10, 14, 23, 59) - i * 60, f"Bitcoin berita {i}") for i in range(8)]
    calls, waits = {"n": 0}, []

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"Type": 100, "Data": page})

    out = fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "K", sleep=waits.append)
    assert len(out) == 8 and calls["n"] == 1                                 # satu panggilan per hari (kuota gratis 100/bulan)
    assert waits and waits[-1] >= 6                                          # jeda >= 6 dtk (batas 10 panggilan/menit)


def test_cryptocompare_without_valid_key_raises_clear_error():
    from app.sources import fetch_headlines_cryptocompare
    def handler(req):
        return httpx.Response(401, json={"Err": {"message": "API key required"}})
    with pytest.raises(SourceError, match="API key"):
        fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "BAD", sleep=lambda s: None)


def test_cryptocompare_throttled_replies_are_retried_never_treated_as_no_news():
    from app.sources import fetch_headlines_cryptocompare
    day_page = [_art(_ts(2026, 10, 14, 20, 0) - i * 60, f"Bitcoin x{i}") for i in range(6)]
    replies = [httpx.Response(200, json={"Type": 100, "Data": [], "HasWarning": False, "RateLimit": {}}),          # kosong
               httpx.Response(200, json={"Type": 100, "Data": day_page, "HasWarning": True, "RateLimit": {"x": 1}}),  # peringatan
               httpx.Response(429, text="slow"),
               httpx.Response(200, json={"Type": 100, "Data": day_page, "HasWarning": False, "RateLimit": {}})]
    waits = []
    out = fetch_headlines_cryptocompare(client(lambda req: replies.pop(0)), date(2026, 10, 14), "K", sleep=waits.append)
    assert len(out) == 6 and not replies and 60 in waits and 120 in waits    # backoff 60 dtk (kosong), 120 dtk (peringatan), 60 dtk (429)


def test_cryptocompare_persistent_throttle_or_empty_day_raises():
    from app.sources import fetch_headlines_cryptocompare
    def empty(req):
        return httpx.Response(200, json={"Type": 100, "Data": []})
    with pytest.raises(SourceError, match="dibatasi|kosong"):
        fetch_headlines_cryptocompare(client(empty), date(2026, 10, 14), "K", sleep=lambda s: None)
    def no_btc_in_day(req):
        return httpx.Response(200, json={"Type": 100, "Data": [_art(_ts(2026, 10, 13, 12, 0), "Bitcoin kemarin")]})
    with pytest.raises(SourceError, match="tidak ada berita"):
        fetch_headlines_cryptocompare(client(no_btc_in_day), date(2026, 10, 14), "K", sleep=lambda s: None)


def test_cryptocompare_monthly_quota_exhausted_is_reported():
    from app.sources import fetch_headlines_cryptocompare
    def handler(req):
        return httpx.Response(200, json={"Type": 100, "Data": [_art(_ts(2026, 10, 14, 12, 0), "Bitcoin ok")]},
                              headers={"x-ratelimit-remaining": "0"})
    with pytest.raises(SourceError, match="kuota"):
        fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "K", sleep=lambda s: None)


def test_judul_membawa_url_dan_tetap_sama_dengan_str():
    from app.sources import Judul
    j = Judul("Bitcoin naik", "https://contoh.com/a")
    assert j == "Bitcoin naik" and j.url == "https://contoh.com/a"
    assert Judul("x", "javascript:alert(1)").url is None and Judul("x").url is None


# ---- sumber cadangan: RSS outlet kripto (gratis, tanpa kunci) ----
from app.sources import Judul, fetch_headlines_rss   # noqa: E402

DAY = date(2026, 10, 20)


def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate></item>" for t, l, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


def rss_client(by_host, status=None):
    def handler(req):
        if status and req.url.host in status:
            return httpx.Response(status[req.url.host])
        return httpx.Response(200, content=by_host.get(req.url.host, rss()))
    return client(handler)


def test_rss_returns_btc_headlines_of_the_utc_day_newest_first_with_urls():
    feeds = {"a.example": "https://a.example/rss", "b.example": "https://b.example/rss"}
    http = rss_client({
        "a.example": rss(("Bitcoin falls", "https://a.example/1", "Tue, 20 Oct 2026 08:00:00 +0000"),
                         ("Ethereum only", "https://a.example/2", "Tue, 20 Oct 2026 09:00:00 +0000")),
        "b.example": rss(("BTC rallies", "https://b.example/1", "Tue, 20 Oct 2026 12:30:00 +0000"))})
    out = fetch_headlines_rss(http, DAY, feeds=feeds)
    assert [str(h) for h in out] == ["BTC rallies", "Bitcoin falls"]                   # terbaru dulu; non-BTC dibuang
    assert [h.url for h in out] == ["https://b.example/1", "https://a.example/1"]
    assert all(isinstance(h, Judul) and h.source == "rss" for h in out)


def test_rss_day_boundaries_are_utc_regardless_of_feed_timezone():
    feeds = {"a.example": "https://a.example/rss"}
    http = rss_client({"a.example": rss(
        ("Bitcoin late", "https://a.example/1", "Tue, 20 Oct 2026 23:59:59 +0000"),
        ("Bitcoin next day", "https://a.example/2", "Wed, 21 Oct 2026 00:00:00 +0000"),
        ("Bitcoin prev day", "https://a.example/3", "Mon, 19 Oct 2026 23:59:59 +0000"),
        ("Bitcoin tz shifted", "https://a.example/4", "Wed, 21 Oct 2026 05:00:00 +0700"))})            # = 20 Okt 22:00 UTC
    assert [str(h) for h in fetch_headlines_rss(http, DAY, feeds=feeds)] == ["Bitcoin late", "Bitcoin tz shifted"]


def test_rss_dedupes_across_feeds_and_keeps_at_most_five():
    feeds = {f"f{i}.example": f"https://f{i}.example/rss" for i in range(3)}
    items = [(f"Bitcoin story {i}", f"https://x/{i}", f"Tue, 20 Oct 2026 {10 + i:02d}:00:00 +0000") for i in range(5)]
    http = rss_client({"f0.example": rss(*items[:4]), "f1.example": rss(*items[2:]),
                       "f2.example": rss(("BITCOIN STORY 0", "https://dup", "Tue, 20 Oct 2026 20:00:00 +0000"), items[0])})
    out = fetch_headlines_rss(http, DAY, feeds=feeds)
    titles = [str(h).lower() for h in out]
    assert len(out) == 5 and len(set(titles)) == 5                                  # tanpa duplikat (huruf besar/kecil sama)


def test_rss_filters_sponsored_and_drops_unsafe_links_but_keeps_the_headline():
    feeds = {"a.example": "https://a.example/rss"}
    http = rss_client({"a.example": rss(
        ("Best crypto to buy now: Bitcoin presale", "https://a.example/ad", "Tue, 20 Oct 2026 08:00:00 +0000"),
        ("Bitcoin news with bad link", "javascript:alert(1)", "Tue, 20 Oct 2026 09:00:00 +0000"))})
    out = fetch_headlines_rss(http, DAY, feeds=feeds)
    assert [str(h) for h in out] == ["Bitcoin news with bad link"] and out[0].url is None


def test_rss_one_broken_feed_does_not_stop_the_others_and_all_broken_is_an_error():
    feeds = {"ok.example": "https://ok.example/rss", "bad.example": "https://bad.example/rss", "xml.example": "https://xml.example/rss"}
    good = rss(("Bitcoin ok", "https://ok.example/1", "Tue, 20 Oct 2026 08:00:00 +0000"))
    def handler(req):
        if req.url.host == "ok.example":
            return httpx.Response(200, content=good)
        if req.url.host == "bad.example":
            return httpx.Response(503)
        return httpx.Response(200, content=b"<rss><channel><item>rusak")
    assert [str(h) for h in fetch_headlines_rss(client(handler), DAY, feeds=feeds)] == ["Bitcoin ok"]
    all_bad = client(lambda req: httpx.Response(500))
    with pytest.raises(SourceError, match="RSS"):
        fetch_headlines_rss(all_bad, DAY, feeds=feeds)


def test_rss_empty_day_is_an_error_not_no_news():
    http = rss_client({"a.example": rss(("Bitcoin old", "https://a.example/1", "Sun, 18 Oct 2026 08:00:00 +0000"))})
    with pytest.raises(SourceError, match="tidak ada berita"):
        fetch_headlines_rss(http, DAY, feeds={"a.example": "https://a.example/rss"})


def test_rss_oversized_response_is_ignored():
    feeds = {"big.example": "https://big.example/rss", "ok.example": "https://ok.example/rss"}
    huge = rss(("Bitcoin huge", "https://big.example/1", "Tue, 20 Oct 2026 08:00:00 +0000")) + b" " * 3_000_000
    def handler(req):
        if req.url.host == "big.example":
            return httpx.Response(200, content=huge)
        return httpx.Response(200, content=rss(("Bitcoin small", "https://ok.example/1", "Tue, 20 Oct 2026 09:00:00 +0000")))
    assert [str(h) for h in fetch_headlines_rss(client(handler), DAY, feeds=feeds)] == ["Bitcoin small"]


def test_judul_defaults_have_no_source_and_keep_it_when_given():
    assert Judul("x").source is None and Judul("x", None, "rss").source == "rss"
