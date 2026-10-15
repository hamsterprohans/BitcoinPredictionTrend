from datetime import datetime, timezone

from app.scheduler import next_run_after


def test_next_run_same_day_before_and_next_day_after():
    before = datetime(2026, 10, 15, 0, 10, tzinfo=timezone.utc)
    after = datetime(2026, 10, 15, 0, 31, tzinfo=timezone.utc)
    assert next_run_after(before) == datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)
    assert next_run_after(after) == datetime(2026, 10, 16, 0, 30, tzinfo=timezone.utc)


def test_run_once_survives_missing_api_key(monkeypatch):
    import app.jobs as jobs
    from app import scheduler
    monkeypatch.setattr(jobs, "_load_dotenv", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert scheduler._run_once() is False          # tidak melempar SystemExit


def test_retry_until_success_with_backoff():
    from app.scheduler import run_with_retries
    outcomes, waits = [False, False, True], []
    assert run_with_retries(lambda: outcomes.pop(0), sleep=waits.append, max_retries=5, delay=3600) is True
    assert waits == [3600, 3600]


def test_retry_gives_up_after_max_retries():
    from app.scheduler import run_with_retries
    waits = []
    assert run_with_retries(lambda: False, sleep=waits.append, max_retries=3, delay=60) is False
    assert waits == [60, 60, 60]
