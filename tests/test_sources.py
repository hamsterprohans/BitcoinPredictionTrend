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
        return httpx.Response(200, json={"Type": 100, "Data": pages.pop(0) if pages else []})

    out = fetch_headlines_cryptocompare(client(handler), day, "SECRET", sleep=lambda s: None)
    assert out == ["Bitcoin jumps 5%", "BTC holds $100k"]                   # hari itu saja, terbaru dulu, tersaring, unik
    assert seen[0]["lTs"] == str(_ts(2026, 10, 15, 0, 0))                    # mulai dari akhir hari (UTC)
    assert seen[1]["lTs"] == str(_ts(2026, 10, 14, 21, 0))                   # halaman berikut: mundur dari artikel terlama
    assert len(seen) == 2                                                    # berhenti setelah melewati awal hari


def test_cryptocompare_without_valid_key_raises_clear_error():
    from app.sources import fetch_headlines_cryptocompare
    def handler(req):
        return httpx.Response(401, json={"Err": {"message": "API key required"}})
    with pytest.raises(SourceError, match="API key"):
        fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "BAD", sleep=lambda s: None)


def test_cryptocompare_retries_429_then_succeeds_and_gives_up_on_empty_pages():
    from app.sources import fetch_headlines_cryptocompare
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow")
        return httpx.Response(200, json={"Data": []})                         # tidak ada artikel lagi
    waits = []
    assert fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "K", sleep=waits.append) == []
    assert calls["n"] == 2 and waits[0] == 15


def test_cryptocompare_stops_at_max_pages():
    from app.sources import fetch_headlines_cryptocompare
    n = {"i": 0}
    def handler(req):
        n["i"] += 1
        return httpx.Response(200, json={"Data": [_art(_ts(2026, 10, 14, 23, 59) - n["i"], f"Bitcoin {n['i']}")]})
    out = fetch_headlines_cryptocompare(client(handler), date(2026, 10, 14), "K", sleep=lambda s: None, max_pages=5)
    assert n["i"] == 5 and len(out) == 5
