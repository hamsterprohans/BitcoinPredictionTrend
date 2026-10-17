"""Server demo dengan data SINTETIS (berlabel DEMO di halaman), di folder sementara.

Tidak menyentuh webapp/data/live. Pemakaian: python -m scripts.demo   (Ctrl+C untuk berhenti)
"""
import tempfile
from pathlib import Path

import uvicorn

from app import config
from app.main import create_app
from tests.factories import seed_live_dir

if __name__ == "__main__":
    base = Path(tempfile.mkdtemp(prefix="btc-demo-"))
    live, junk = base / "live", base / "junk"
    live.mkdir()
    junk.mkdir()
    seed_live_dir(live, junk, demo=True)
    print("DATA DEMO SINTETIS di", live, "- bukan harga atau prediksi asli. http://127.0.0.1:8001")
    uvicorn.run(create_app(live, config.CONTENT_DIR, config.STATIC_DIR), host="127.0.0.1", port=8001)
