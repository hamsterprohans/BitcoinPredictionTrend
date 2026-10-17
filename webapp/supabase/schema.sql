-- Jalankan sekali di Supabase: SQL Editor > New query > tempel > Run.
create table if not exists public.feedback_responses (
  id             bigint generated always as identity primary key,
  created_at     timestamptz not null default now(),
  survey_version int  not null check (survey_version between 1 and 1000),
  client_id      uuid not null unique,                 -- satu jawaban per peramban; kirim ulang -> 409
  answers        jsonb not null
                 check (jsonb_typeof(answers) = 'object' and pg_column_size(answers) < 30000)
);

alter table public.feedback_responses enable row level security;

-- Pengunjung (anon key) hanya boleh MENAMBAH baris. Tidak ada kebijakan select/update/delete:
-- jawaban orang lain tidak bisa dibaca atau diubah lewat kunci publik.
revoke all on public.feedback_responses from anon, authenticated;
grant insert on public.feedback_responses to anon;
drop policy if exists "anon boleh mengirim" on public.feedback_responses;
create policy "anon boleh mengirim" on public.feedback_responses for insert to anon with check (true);

-- Tampilan datar untuk analisis (hanya terbaca dari dasbor Supabase / service role).
create or replace view public.feedback_flat as
select id, created_at, survey_version, answers->>'a1' as latar_belakang, answers->>'a2' as pernah_kripto, answers->>'a3' as kenal_ml,
       answers->>'b1' as paham_halaman_utama, answers->>'b2' as prediksi_jelas, answers->>'b4' as paham_bukan_acak,
       answers->>'c1' as prediksi_membantu, answers->>'c2' as berita_membantu, answers->>'c3' as fitur_membantu,
       answers->>'c4' as narasi_membantu, answers->>'c5' as retro_membantu, answers->>'d1' as percaya, answers->>'d4' as andalkan_jual_beli,
       answers->>'e1' as tampilan_menarik, answers->>'e2' as navigasi_mudah, answers->>'e6' as ada_kendala,
       answers->>'g1' as membantu_keseluruhan, answers->>'g2' as rekomendasikan, answers->>'f6' as fitur_diminta,
       answers->>'f7' as perlu_ditingkatkan, answers->>'g3' as komentar, answers,
       answers->>'a0' as nama
from public.feedback_responses;
revoke all on public.feedback_flat from anon, authenticated;
