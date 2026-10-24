# Bitcoin Trend

**Sistem Prediksi Tren Harga Bitcoin Berbasis LSTM dengan Integrasi Sentimen Berita Berbasis LLM dan Fear and Greed Index**

Tugas akhir S-1 Sistem Informasi, Institut Teknologi Sepuluh Nopember (ITS), oleh Hans Christian Cakrawangsa.

**Situs:** https://hamsterprohans.github.io/BitcoinPredictionTrend/

> **Bukan saran investasi.** Situs ini adalah hasil penelitian. Pada pengujian, model **belum terbukti lebih akurat daripada tebakan acak**
> (akurasi 50,1% dan AUC 0,487 pada periode uji 433 hari). Situs sengaja menampilkan hal ini apa adanya. Jangan memakainya sebagai dasar keputusan jual atau beli.

## Apa yang dilakukan situs ini

Setiap hari situs memperkirakan **arah** harga Bitcoin (naik atau turun), bukan angka harganya. Prediksi tersedia untuk sembilan horizon:
1, 3, 5, 7, 15, 20, 25, 30, dan 35 hari. Tiap horizon dilatih sebagai model terpisah dengan ambang keputusan sendiri, sehingga arah antarhorizon
boleh berbeda.

- **Prediksi arah** beserta probabilitas naik, ambang keputusan, dan jarak probabilitas ke ambang.
- **Penjelasan prediksi**: berita yang dipakai, skor sentimen, kontribusi tiap fitur, dan narasi singkat.
- **Grafik harga** dengan harga live dari Coinbase, rata-rata bergerak, dan pita Bollinger.
- **Riwayat prediksi vs kenyataan**: prediksi yang sudah terbit tidak pernah ditimpa, dan hasilnya dinilai setelah harga penutupan hari target tersedia.
- **Halaman Riset dan Metodologi**: perbandingan model, uji signifikansi, dan perbandingan strategi dengan beli dan tahan.
- **Glosarium** istilah teknis, serta pengaturan tema dan ukuran teks.
- **Kuesioner** evaluasi pengguna (pemahaman, SUS, kepuasan penjelasan, kepercayaan) yang disimpan di Supabase.

## Cara kerja singkat

1. **Data**: harga harian Bitcoin, Fear and Greed Index (alternative.me), dan berita kripto (CryptoCompare, dengan cadangan RSS beberapa outlet).
2. **Sentimen berita**: judul berita dinilai oleh LLM (Claude Haiku 4.5) menjadi skor sentimen harian.
3. **Model**: LSTM dengan fitur teknikal (rata-rata bergerak, volatilitas, RSI, MACD, lebar Bollinger), sentimen berita, dan Fear and Greed Index.
4. **Pembaruan harian**: GitHub Actions menjalankan pipeline, menyimpan hasilnya, lalu mengekspor situs statis ke GitHub Pages.
5. **Situs**: aplikasi FastAPI diekspor menjadi berkas statis (HTML, JavaScript, dan data JSON), jadi tidak butuh server.

## Struktur repositori

```
.github/workflows/   pembaruan harian dan publikasi ke GitHub Pages
webapp/              seluruh kode situs, pipeline, data, dan tes
  app/               backend FastAPI, pipeline prediksi, dan backtest
  static/            halaman, JavaScript, dan CSS
  scripts/           ekspor statis, ringkasan kuesioner, dan skrip riset
  supabase/          skema database kuesioner dan penghitung kunjungan
  tests/             tes backend dan tes browser (Playwright)
```

Petunjuk teknis lengkap (menyiapkan artefak model, menjalankan lokal, sumber berita, ekspor statis) ada di
[webapp/README.md](webapp/README.md).

## Menjalankan secara lokal

```bash
cd webapp
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements-dev.txt && python -m playwright install chromium
python -m scripts.demo            # tampilan demo dengan data sintetis di http://127.0.0.1:8001
pytest -m "not e2e"               # tes backend
pytest -m e2e                     # tes browser
```

Menjalankan prediksi asli membutuhkan artefak model dari notebook penelitian dan kunci API. Langkahnya ada di [webapp/README.md](webapp/README.md).

## Data dan privasi

- Kuesioner meminta persetujuan terlebih dahulu. Jawaban disimpan di Supabase dengan aturan akses yang hanya mengizinkan penambahan data dari pengunjung.
- Situs mencatat jumlah kunjungan secara anonim (waktu dan nama halaman, tanpa alamat IP atau identitas).
- Kunci API dan kunci rahasia tidak disimpan di repositori. Kunci publik Supabase memang dirancang terbuka dan dibatasi oleh aturan akses database.

## Keterbatasan

- Model belum mengungguli tebakan acak pada periode uji, dan hasil backtest sangat peka terhadap pilihan ambang keputusan.
- Prediksi hanya diperbarui sekali sehari dari harga penutupan, bukan secara real time.
- Sentimen berita bergantung pada ketersediaan sumber berita gratis. Bila sumber utama dibatasi, situs memakai cadangan dan menandainya.

## Penulis

Hans Christian Cakrawangsa, Sistem Informasi, Institut Teknologi Sepuluh Nopember.
