// Konfigurasi publik (aman di frontend). URL dan anon key Supabase diisi setelah proyek dibuat (lihat supabase/README.md).
// Anon key hanya bisa INSERT ke tabel kuesioner berkat aturan RLS di supabase/schema.sql; jangan pernah isi service_role key di sini.
window.__APP_CONFIG__ = Object.assign({ supabaseUrl: "", supabaseAnonKey: "" }, window.__APP_CONFIG__);
