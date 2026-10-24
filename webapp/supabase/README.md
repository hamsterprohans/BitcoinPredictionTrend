# Kuesioner (Supabase)

1. Buat proyek di https://supabase.com (paket gratis cukup).
2. SQL Editor: tempel isi `schema.sql`, Run. Tabel `feedback_responses` dibuat dengan RLS: pengunjung hanya bisa menambah baris.
3. Project Settings > API: salin **Project URL** dan **anon public key** ke `static/js/app-config.js`
   (`supabaseUrl`, `supabaseAnonKey`). Anon key memang publik; JANGAN pernah memasukkan `service_role` key.
4. Ekspor ulang situs (`python -m scripts.export_static ...`) atau tunggu pembaruan harian.

Membaca hasil per soal: Table Editor > `feedback_flat` (satu kolom per pertanyaan dengan nama berupa ringkasan pertanyaan, mis. `sus_mudah_digunakan`, plus `skor_sus` dan `skor_pemahaman`; hanya jawaban versi 2). Tabel `feedback_responses` menyimpan JSON mentah. Unduh CSV dari tombol Export, lalu rangkum dengan
`python -m scripts.summarize_feedback hasil.csv` (skor SUS dan pemahaman dihitung di sana, dari kolom `answers`).

Catatan: setiap kali soal berubah, jalankan ulang `schema.sql` (aman diulang). Versi 2 (kuesioner sesuai dokumen referensi) mengganti
daftar kunci jawaban yang diizinkan, mengganti syarat nama (kini `answers->>'nama'`), mewajibkan persetujuan (`a0 = 'ya'`), dan membuat
ulang view `feedback_flat`. Jawaban versi 1 tetap tersimpan (kolom `survey_version` = 1) dan tidak ikut dihitung oleh skrip ringkasan.

## Penghitung kunjungan dan panel pemilik

`schema.sql` juga membuat `site_visits` (satu baris per kunjungan: waktu dan jalur halaman, tanpa IP atau identitas; satu kunjungan per sesi
peramban) dan fungsi `visit_stats`. Pengunjung biasa hanya bisa menambah baris. Ringkasan hanya terbaca dengan kunci pemilik.

Atur kuncimu sendiri SEKALI di SQL Editor (ganti teks di antara tanda kutip dengan kalimat sandi panjang yang tidak dipakai di tempat lain;
yang tersimpan hanya hash SHA-256-nya, kuncinya tidak pernah ada di repo):

```sql
insert into public.site_secret (id, key_hash)
values (1, encode(sha256(convert_to('GANTI-DENGAN-KALIMAT-SANDI-PANJANGMU', 'utf8')), 'hex'))
on conflict (id) do update set key_hash = excluded.key_hash;
```

Membukanya: di halaman mana pun, ketuk teks pertama di footer ("Bukan saran investasi.") 5 kali dalam 3 detik, lalu masukkan kunci.
Panel samar di pojok kanan bawah menampilkan total dibuka, hari ini, 7 hari, grafik 30 hari, dan halaman terbanyak. Peramban yang pernah
membuka panel tidak ikut dihitung lagi. Esc menutup panel; tombol Keluar melupakan kunci di sesi itu.
