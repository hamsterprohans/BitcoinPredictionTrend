"""Skor sentimen berita harian: rata-rata 3 prompt Claude Haiku (sama dengan notebook (10))."""
import re
import time

from .prompts import PROMPTS

MODEL = "claude-haiku-4-5"
KINDS = ("pemahaman", "detail", "bullbear")


class SentimentError(RuntimeError):
    pass


def parse_score(text: str):
    m = re.search(r"-?\d+", text.strip())
    if not m:
        return None
    return max(-10, min(10, int(m.group(0))))


def score_one(client, kind: str, headlines: list, sleep=time.sleep, retries: int = 3) -> int:
    combined = " | ".join(headlines[:5])
    prompt = PROMPTS[kind].replace("{combined}", combined)
    last = None
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=5,
                messages=[{"role": "user", "content": prompt}])
            score = parse_score(resp.content[0].text)
            if score is not None:
                return score
            last = f"balasan tidak berisi angka: {resp.content[0].text!r}"
        except Exception as e:  # noqa: BLE001 - jaringan/API apa pun diulang
            last = e
        sleep(2 ** attempt)
    raise SentimentError(f"{kind}: gagal setelah {retries} percobaan ({last})")


def daily_sentiment_detail(client, headlines: list, sleep=time.sleep):
    if not headlines:
        return None
    scores = {k: score_one(client, k, headlines, sleep) for k in KINDS}
    return {**scores, "mean": sum(scores.values()) / len(KINDS)}


def daily_sentiment(client, headlines: list, sleep=time.sleep):
    d = daily_sentiment_detail(client, headlines, sleep)
    return None if d is None else d["mean"]
