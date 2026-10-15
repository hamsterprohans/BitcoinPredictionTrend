import asyncio
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .store import read_json

NAME_RE = re.compile(r"^[a-z0-9_]+$")


def create_app(live_dir=config.LIVE_DIR, content_dir=config.CONTENT_DIR,
               static_dir=config.STATIC_DIR, now=lambda: datetime.now(timezone.utc)) -> FastAPI:
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
    def prices():
        d = read_json(live_dir / "chart.json")
        if d is None:
            raise HTTPException(404, "Data harga belum tersedia")
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

    for route, fname in (("/", "index.html"), ("/latar-belakang", "latar-belakang.html"), ("/riset", "riset.html"),
                         ("/metodologi", "metodologi.html"), ("/tentang", "tentang.html")):
        app.get(route, include_in_schema=False)(make_page(fname))

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


app = create_app()
