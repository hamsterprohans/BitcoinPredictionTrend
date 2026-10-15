import asyncio
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, sources
import pandas as pd

from .features import chart_frame, compute_features, resample_prices
from .store import frame_to_columns, read_json

NAME_RE = re.compile(r"^[a-z0-9_]+$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


LIVE_TTL = 20.0   # detik: cache harga live di server agar upstream tidak dibanjiri


def _default_fetch_live() -> float:
    import httpx
    with httpx.Client(timeout=5, follow_redirects=True) as c:
        return sources.fetch_spot(c)


def create_app(live_dir=config.LIVE_DIR, content_dir=config.CONTENT_DIR,
               static_dir=config.STATIC_DIR, now=lambda: datetime.now(timezone.utc),
               fetch_live=_default_fetch_live, monotonic=time.monotonic) -> FastAPI:
    live_dir, content_dir, static_dir = Path(live_dir), Path(content_dir), Path(static_dir)

    @asynccontextmanager
    async def lifespan(_app):
        task = None
        if os.environ.get("RUN_SCHEDULER") == "1":
            from .scheduler import run_forever
            task = asyncio.create_task(run_forever())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Prediksi Tren Bitcoin", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/api/prediction/latest")
    def latest():
        d = read_json(live_dir / "latest.json")
        if d is None:
            raise HTTPException(404, "Prediksi belum tersedia")
        evidence = read_json(content_dir / "multihorizon_evidence.json", {})
        for h, v in d["horizons"].items():
            v["evidence"] = evidence.get(h)
        d["age_days"] = (now().astimezone(timezone.utc).date()
                         - datetime.fromisoformat(d["as_of"]).date()).days
        return d

    @app.get("/api/prediction/history")
    def history():
        return read_json(live_dir / "history.json", [])

    @app.get("/api/prices")
    def prices(interval: Literal["D", "W", "M"] = "D"):
        if interval == "D":
            d = read_json(live_dir / "chart.json")
            if d is None:
                raise HTTPException(404, "Data harga belum tersedia")
            return d
        csv = live_dir / "prices.csv"
        if not csv.exists():
            raise HTTPException(404, "Data harga belum tersedia")
        agg = resample_prices(pd.read_csv(csv, parse_dates=["date"]), interval)
        return frame_to_columns(chart_frame(compute_features(agg)))

    live_cache = {"t": None, "v": None}
    live_lock = threading.Lock()

    @app.get("/api/price/live")
    def live_price():
        with live_lock:
            t = monotonic()
            if live_cache["v"] is not None and t - live_cache["t"] < LIVE_TTL:
                return live_cache["v"]
            try:
                price = float(fetch_live())
            except Exception:  # noqa: BLE001 - upstream apa pun gagal: jangan kirim angka lama sebagai "live"
                raise HTTPException(503, "Harga live tidak tersedia")
            v = {"price": round(price, 2), "source": "Coinbase",
                 "fetched_at": now().astimezone(timezone.utc).isoformat(timespec="seconds")}
            live_cache.update(t=t, v=v)
            return v

    retro_dir = content_dir / "retro"

    @app.get("/api/retro/status")
    def retro_status():
        d = read_json(retro_dir / "series.json")
        return {"built": d is not None, "n": None if d is None else d["n"]}

    @app.get("/api/retro/series")
    def retro_series():
        d = read_json(retro_dir / "series.json")
        if d is None:
            raise HTTPException(404, "Data retrospektif belum dibangun")
        return d

    @app.get("/api/retro/day/{day}")
    def retro_day(day: str):
        if not DAY_RE.match(day):
            raise HTTPException(404, "Tidak ditemukan")
        d = read_json(retro_dir / "days" / f"{day}.json")
        if d is None:
            raise HTTPException(404, "Tidak ditemukan")
        return d

    @app.get("/api/research/{name}")
    def research(name: str):
        if not NAME_RE.match(name):
            raise HTTPException(404, "Tidak ditemukan")
        d = read_json(content_dir / f"{name}.json")
        if d is None:
            raise HTTPException(404, "Tidak ditemukan")
        return d

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    def make_page(fname: str):
        def page():            # tanpa parameter: FastAPI tidak boleh menjadikannya query param
            f = static_dir / fname
            if not f.exists():
                raise HTTPException(404, "Halaman belum ada")
            return FileResponse(f)
        return page

    for route, fname in (("/", "index.html"), ("/latar-belakang", "latar-belakang.html"), ("/retrospektif", "retrospektif.html"),
                         ("/riset", "riset.html"),
                         ("/metodologi", "metodologi.html"), ("/tentang", "tentang.html")):
        app.get(route, include_in_schema=False)(make_page(fname))

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


app = create_app()
