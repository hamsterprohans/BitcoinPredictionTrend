from datetime import datetime, timezone

from app.scheduler import next_run_after


def test_next_run_same_day_before_and_next_day_after():
    before = datetime(2026, 10, 15, 0, 10, tzinfo=timezone.utc)
    after = datetime(2026, 10, 15, 0, 31, tzinfo=timezone.utc)
    assert next_run_after(before) == datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)
    assert next_run_after(after) == datetime(2026, 10, 16, 0, 30, tzinfo=timezone.utc)
