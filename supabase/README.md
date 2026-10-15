# Kuesioner (Supabase)

1. Buat proyek di https://supabase.com (paket gratis cukup).
2. SQL Editor: tempel isi `schema.sql`, Run. Tabel `feedback_responses` dibuat dengan RLS: pengunjung hanya bisa menambah baris.
3. Project Settings > API: salin **Project URL** dan **anon public key** ke `static/js/app-config.js`
   (`supabaseUrl`, `supabaseAnonKey`). Anon key memang publik; JANGAN pernah memasukkan `service_role` key.
4. Ekspor ulang situs (`python -m scripts.export_static ...`) atau tunggu pembaruan harian.

Membaca hasil: Table Editor atau view `feedback_flat` (hanya pemilik proyek). Unduh CSV dari tombol Export.
Contoh ringkasan: `select g1, count(*) from feedback_flat group by g1;` (ganti kolom sesuai view).
