from app.prompts import PROMPTS


def test_three_prompts_with_single_placeholder():
    assert set(PROMPTS) == {"pemahaman", "detail", "bullbear"}
    for kind, text in PROMPTS.items():
        assert text.count("{combined}") == 1, kind
        assert "Respond with ONLY a single integer" in text, kind
