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


def test_fetch_headlines_empty_body_means_no_news():
    def handler(req):
        return httpx.Response(200, text="")
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
