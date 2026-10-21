import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("scheduler")


def next_run_after(now: datetime, hour: int = 0, minute: int = 30) -> datetime:
    run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


def _run_once() -> bool:
    """Jalankan job sekali. True bila sukses; kegagalan apa pun dicatat dan snapshot lama dipertahankan."""
    from . import jobs
    jobs._load_dotenv()
    try:
        result = jobs.run_daily(jobs.make_real_deps())
        log.info("job harian selesai: %s", "mutakhir" if result is None else result["as_of"])
        return True
    except Exception:  # noqa: BLE001 - termasuk RuntimeError kunci API hilang; server web tidak boleh mati
        log.exception("job harian gagal; snapshot lama dipertahankan")
        return False


def run_with_retries(run, sleep=time.sleep, max_retries: int = 6, delay: int = 3600) -> bool:
    """Ulangi job per jam (mis. GDELT 429, Coin Metrics belum terbit) sampai berhasil atau habis percobaan."""
    for attempt in range(max_retries + 1):
        if run():
            return True
        if attempt < max_retries:
            sleep(delay)
    return False


async def run_forever():
    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep((next_run_after(now) - now).total_seconds())
        await asyncio.to_thread(run_with_retries, _run_once)
