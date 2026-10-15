import pytest

from app.sentiment import SentimentError, daily_sentiment, parse_score, score_one


class _Resp:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class FakeClient:
    """Balasan berurutan; Exception di dalam daftar akan dilempar."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.messages = self

    def create(self, model, max_tokens, messages):
        assert model == "claude-haiku-4-5" and max_tokens == 5
        self.prompts.append(messages[0]["content"])
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


def no_sleep(_):
    pass


def test_parse_and_clip():
    assert parse_score("  +3 ") == 3
    assert parse_score("-4") == -4
    assert parse_score("15") == 10
    assert parse_score("-99") == -10
    assert parse_score("tidak ada angka") is None


def test_daily_is_mean_of_three_prompts():
    c = FakeClient(["6", "3", "0"])
    assert daily_sentiment(c, ["Bitcoin rises"], sleep=no_sleep) == pytest.approx(3.0)
    assert len(c.prompts) == 3


def test_empty_headlines_returns_none_without_calls():
    c = FakeClient([])
    assert daily_sentiment(c, [], sleep=no_sleep) is None
    assert c.prompts == []


def test_uses_only_first_five_headlines():
    c = FakeClient(["1"])
    score_one(c, "detail", [f"h{i}" for i in range(1, 8)], sleep=no_sleep)
    assert "h5" in c.prompts[0] and "h6" not in c.prompts[0]


def test_retries_then_succeeds():
    c = FakeClient([RuntimeError("429"), "2"])
    assert score_one(c, "detail", ["x"], sleep=no_sleep) == 2


def test_raises_after_three_failures():
    c = FakeClient([RuntimeError("a"), RuntimeError("b"), "bukan angka"])
    with pytest.raises(SentimentError):
        score_one(c, "detail", ["x"], sleep=no_sleep)


def test_daily_detail_returns_scores_and_mean():
    from app.sentiment import daily_sentiment_detail
    c = FakeClient(["6", "3", "0"])
    d = daily_sentiment_detail(c, ["Bitcoin rises"], sleep=no_sleep)
    assert d == {"pemahaman": 6, "detail": 3, "bullbear": 0, "mean": pytest.approx(3.0)}


def test_daily_detail_none_for_empty_headlines():
    from app.sentiment import daily_sentiment_detail
    c = FakeClient([])
    assert daily_sentiment_detail(c, [], sleep=no_sleep) is None and c.prompts == []
