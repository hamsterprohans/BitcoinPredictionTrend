import asyncio
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger("scheduler")


def next_run_after(now: datetime, hour: int = 0, minute: int = 30) -> datetime:
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


def _run_once():
    from . import jobs
    jobs._load_dotenv()
    try:
        result = jobs.run_daily(jobs.make_real_deps())
        log.info("job harian selesai: %s", "mutakhir" if result is None else result["as_of"])
    except Exception:  # noqa: BLE001 - kegagalan dicatat; snapshot lama tetap dipakai
        log.exception("job harian gagal; snapshot lama dipertahankan")


async def run_forever():
    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep((next_run_after(now) - now).total_seconds())
        await asyncio.to_thread(_run_once)
