// Konfigurasi publik (aman di frontend). Kunci "publishable" Supabase memang dirancang publik: berkat RLS di
// supabase/schema.sql ia hanya bisa INSERT ke feedback_responses (tidak bisa membaca). Jangan pernah mengisi kunci rahasia (secret) di sini.
window.__APP_CONFIG__ = Object.assign({
  supabaseUrl: "https://pzpldabfnatehnsjqxqw.supabase.co",
  supabaseAnonKey: "sb_publishable_YWVmhKGEErq6GQU63A4yuA_8gVDXsES",
}, window.__APP_CONFIG__);
