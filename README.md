# Bitcoin Trend — website prediksi

## Prasyarat
Taruh artefak hasil ekspor dari notebook (10) di `ARTIFACTS_DIR` (default `../data/model_artifacts`):
`scaler.pkl`, `models/model_F.keras`, `threshold_beku.json`, `preprocessed.pkl` (untuk tes paritas),
dan untuk multi-horizon: `multihorizon/F_h{H}_s{seed}.keras` serta `multihorizon/C_h{H}_s{seed}.npz`
(H = 3,5,7,15,20,25,30,35; seed = 47,123,2024). Lalu: `python -m scripts.compute_mh_thresholds`.
Horizon tanpa berkasnya otomatis tidak ditampilkan.

## Menjalankan
```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements-dev.txt && python -m playwright install chromium
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env           # tidak ikut git
python -m app.jobs --patient                           # job pertama: mengisi sentimen 22 hari; --patient menunggu bila GDELT memblokir (429)
uvicorn app.main:app --port 8000                       # buka http://127.0.0.1:8000
```
Penjadwalan: `RUN_SCHEDULER=1` menjalankan job tiap hari 00.30 UTC di dalam proses web; alternatifnya cron:
`30 0 * * * cd /path/webapp && .venv/bin/python -m app.jobs`.

## Menyegarkan hasil riset
`python -m scripts.export_research "<notebook>.ipynb"` (membaca output sel notebook; notebook tidak diubah).

## Tes
`pytest -m "not e2e"` (backend), `pytest -m e2e` (browser).
