# Bitcoin Trend — website prediksi

## Prasyarat
Taruh artefak hasil ekspor dari notebook (10) di `ARTIFACTS_DIR` (default `../data/model_artifacts`):
`scaler.pkl`, `models/model_F.keras`, `threshold_beku.json`, `preprocessed.pkl` (untuk tes paritas),
dan untuk multi-horizon: `multihorizon/F_h{H}_s{seed}.keras` serta `multihorizon/C_h{H}_s{seed}.npz`
(H = 3,5,7,15,20,25,30,35; seed = 47,123,2024). Lalu: `python -m scripts.compute_mh_thresholds`.
Horizon tanpa berkasnya otomatis tidak ditampilkan.

### Ekspor artefak dari notebook (10)
Tambahkan sel ini di akhir notebook (10) di Colab, jalankan, lalu unduh folder `web_export` dari Drive ke `data/model_artifacts/`:
```python
import pickle, os, json, shutil
OUT = f'{DRIVE_FOLDER}/web_export'; os.makedirs(f'{OUT}/models', exist_ok=True)
results['F']['model_obj'].save(f'{OUT}/models/model_F.keras')
pickle.dump(scaler, open(f'{OUT}/scaler.pkl', 'wb'))
json.dump({'THRESHOLD_OPTIMAL': THRESHOLD_OPTIMAL}, open(f'{OUT}/threshold_beku.json', 'w'))
shutil.copytree(f'{DRIVE_FOLDER}/multihorizon', f'{OUT}/multihorizon', dirs_exist_ok=True)
print(list(scaler.feature_names_in_)[-1])   # harus: news_sentiment
```

## Menjalankan
```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements-dev.txt && python -m playwright install chromium
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env           # tidak ikut git
python -m app.jobs --patient                           # job pertama: mengisi sentimen 22 hari; --patient menunggu bila GDELT memblokir (429)
uvicorn app.main:app --port 8000                       # buka http://127.0.0.1:8000
```
Hanya ingin melihat harga dan grafik asli (tanpa model, tanpa API key): `python -m app.jobs --prices-only`.

Penjadwalan: `RUN_SCHEDULER=1` menjalankan job tiap hari 00.30 UTC di dalam proses web; alternatifnya cron:
`30 0 * * * cd /path/webapp && .venv/bin/python -m app.jobs`.

## Dashboard retrospektif
Setelah artefak notebook (10) terpasang di `data/model_artifacts/` (lihat "Ekspor artefak dari notebook (10)"):
```bash
python -m scripts.build_retro              # hitung ulang prediksi periode uji + cek paritas dengan tabel notebook
python -m scripts.build_retro --narratives # narasi Claude Haiku per hari (butuh ANTHROPIC_API_KEY; dapat dilanjutkan)
```
Skrip berhenti dengan pesan bila akurasi/F1 hasil hitung ulang berbeda lebih dari 0,002 dari baris Model F di `content/ablation.json`
(`--allow-mismatch` tetap menulis, tetapi halaman menandai paritas "belum terverifikasi"). Hasilnya di `content/retro/` dan tampil di `/retrospektif`.
Job harian (`python -m app.jobs`) menyimpan blok `explain` (berita, kontribusi fitur, narasi) pada `latest.json` bila `content/retro/train_stats.json` ada.

## Sumber berita live
Korpus latih (2025–2026) berasal dari **CryptoCompare**, jadi job live memakainya bila ada API key gratis
(buat di https://developers.coindesk.com, lalu tambahkan `COINDESK_API_KEY=...` di `scripts/.env`). Tanpa key, job memakai GDELT,
yang sering membatasi laju (429/balasan kosong) dan dapat menahan job berjam-jam. Sumber tidak dicampur dalam satu jendela 22 hari:
jika berpindah sumber, hapus `data/live/sentiment_log.csv` dan `data/live/news_log.json` lebih dulu.

## Tampilan demo (data sintetis)
`python -m scripts.demo` menjalankan server di http://127.0.0.1:8001 dengan data buatan yang diberi label DEMO.
Jangan memakai `LIVE_DIR=...` manual untuk demo: itu yang membuat angka palsu terlihat seperti data asli.

## Menyegarkan hasil riset
`python -m scripts.export_research "<notebook>.ipynb"` (membaca output sel notebook; notebook tidak diubah).

## Tes
`pytest -m "not e2e"` (backend), `pytest -m e2e` (browser).

## Harga live
`/api/price/live` mengambil harga spot BTC/USD dari Coinbase (cache 20 detik) hanya untuk tampilan; harga ini BUKAN input model.
Probabilitas prediksi tetap resmi harian (dari penutupan hari penuh), tidak diperbarui real-time.

## Publikasi statis (GitHub Pages)

GitHub Pages tidak menjalankan Python, jadi situs diekspor menjadi berkas statis:

```bash
python -m scripts.export_static --base /BitcoinPredictionTugasAkhir --out dist
```

Hasilnya (`dist/`) dipublikasikan pada branch `gh-pages`. Data API dibekukan saat ekspor, sehingga prediksi harian dan
berita baru muncul setelah job harian dan ekspor dijalankan ulang. Harga live diambil browser langsung dari Coinbase.
