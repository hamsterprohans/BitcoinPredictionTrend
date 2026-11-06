import pytest

from app.explain import bearish_summary, news_role
from tests.test_narrative import FakeLLM

CONTRIB = [
    {"feature": "MA90", "label": "Rata-rata harga 90 hari", "delta_pp": -14.098},
    {"feature": "MA7", "label": "Rata-rata harga 7 hari", "delta_pp": -10.762},
    {"feature": "Vol_30", "label": "Volatilitas 30 hari", "delta_pp": -6.4},
    {"feature": "MA30", "label": "Rata-rata harga 30 hari", "delta_pp": -4.931},
    {"feature": "news_sentiment", "label": "Sentimen berita", "delta_pp": 2.414},
    {"feature": "RSI14", "label": "RSI 14 hari", "delta_pp": 0.3},
]


def test_news_role_when_news_pushes_against_a_down_prediction():
    s = news_role(CONTRIB, "TURUN")
    assert "+2,4 poin persentase" in s and "ke arah naik" in s
    assert "urutan ke-5 dari 6" in s and "tidak terutama dibentuk oleh berita" in s


def test_news_role_when_news_is_a_top_driver_in_the_same_direction():
    top = [{"feature": "news_sentiment", "label": "Sentimen berita", "delta_pp": -9.0}] + CONTRIB[:3]
    s = news_role(top, "TURUN")
    assert "-9,0 poin persentase" in s and "ke arah turun" in s and "tiga fitur" in s


def test_news_role_near_zero_effect():
    c = [{"feature": "news_sentiment", "label": "Sentimen berita", "delta_pp": 0.02}] + CONTRIB[:2]
    assert "hampir tidak memengaruhi" in news_role(c, "TURUN")


def test_news_role_is_none_without_the_feature_or_without_news():
    assert news_role(CONTRIB[:4], "TURUN") is None
    assert news_role(CONTRIB, "TURUN", has_news=False) is None


def test_summary_without_bearish_headlines_makes_no_llm_call():
    llm = FakeLLM([])
    out = bearish_summary(llm, [])
    assert out["source"] == "template" and "tidak ada" in out["text"].lower() and llm.calls == []


GOOD_SUMMARY = "Satu judul menyoroti arus keluar dana dari ETF Bitcoin dan Ethereum, yang bernada bearish bagi harga."


def test_summary_accepts_a_clean_llm_text_and_sends_only_the_bearish_titles():
    llm = FakeLLM([GOOD_SUMMARY])
    out = bearish_summary(llm, ["Bitcoin and Ethereum ETFs shed $1.8B"])
    assert out == {"text": GOOD_SUMMARY, "source": "llm"}
    assert "ETFs shed" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("bad", [
    "Dana ETF keluar 1,8 miliar dolar, bernada bearish.",                 # angka baru
    "Harga turun karena arus keluar dana ETF, bernada bearish.",           # sebab-akibat
    "# Ringkasan\nArus keluar dana ETF bernada bearish.",                  # markdown
    "Sebaiknya jual Bitcoin sekarang.",                                    # ajakan
])
def test_summary_rejects_invalid_text_and_falls_back_to_listing_titles(bad):
    llm = FakeLLM([bad, bad])
    out = bearish_summary(llm, ["ETFs shed money"])
    assert out["source"] == "template" and "«ETFs shed money»" in out["text"]
