-- Jalankan sekali di Supabase: SQL Editor > New query > tempel > Run.
create table if not exists public.feedback_responses (
  id             bigint generated always as identity primary key,
  created_at     timestamptz not null default now(),
  survey_version int  not null check (survey_version between 1 and 1000),
  client_id      uuid not null unique,                 -- satu jawaban per peramban; kirim ulang -> 409
  answers        jsonb not null
                 check (jsonb_typeof(answers) = 'object' and pg_column_size(answers) < 30000)
);

-- Persetujuan (a0 = 'ya') dan nama wajib: baris BARU tanpa keduanya ditolak di database (pemeriksaan di browser saja bisa dilewati).
-- NOT VALID: hanya berlaku untuk baris baru, jadi jawaban versi 1 (soal dan kunci berbeda) tidak ikut diperiksa ulang.
alter table public.feedback_responses drop constraint if exists feedback_name_required;
alter table public.feedback_responses add constraint feedback_name_required
  check (length(btrim(coalesce(answers->>'nama', ''))) > 0) not valid;
alter table public.feedback_responses drop constraint if exists feedback_consent_required;
alter table public.feedback_responses add constraint feedback_consent_required
  check (answers->>'a0' = 'ya') not valid;

-- Bentuk data dibatasi: hanya ID soal yang dikenal, semua nilai berupa teks, maksimal 2000 karakter per jawaban.
-- Mencegah penyalahgunaan kunci publik untuk menyimpan data sembarang. Daftar ID harus sama dengan static/js/kuesioner-schema.js (dijaga tes).
create or replace function public.feedback_answers_ok(a jsonb) returns boolean
language sql immutable as $$
  select jsonb_typeof(a) = 'object'
     and not exists (
       select 1 from jsonb_each(a) e
       where e.key <> all (array['a0', 'nama', 'a1', 'a2', 'a3', 'a4', 'b1', 'b2', 'b3', 'b4', 'b5', 'b6', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9', 'c10', 'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'd8', 'e1', 'e2', 'e3', 'e4', 'f1', 'f2', 'f3', 'f4'])
          or jsonb_typeof(e.value) <> 'string'
          or length(e.value #>> '{}') > 2000)
$$;
alter table public.feedback_responses drop constraint if exists feedback_answers_shape;
alter table public.feedback_responses add constraint feedback_answers_shape
  check (public.feedback_answers_ok(answers)) not valid;

-- Batas laju global: maksimal 120 kiriman per 10 menit. Menahan banjir data dari penyalahgunaan kunci publik
-- (kuota penyimpanan gratis terbatas). Fungsi berhak 'security definer' agar bisa menghitung baris tanpa memberi anon izin SELECT.
create or replace function public.feedback_rate_limit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from public.feedback_responses where created_at > now() - interval '10 minutes') > 120 then
    raise exception 'terlalu banyak kiriman, coba lagi beberapa menit lagi' using errcode = 'P0001';
  end if;
  return new;
end $$;
revoke all on function public.feedback_rate_limit() from public;
drop trigger if exists feedback_rate_limit on public.feedback_responses;
create trigger feedback_rate_limit before insert on public.feedback_responses
  for each row execute function public.feedback_rate_limit();

alter table public.feedback_responses enable row level security;

-- Pengunjung (anon key) hanya boleh MENAMBAH baris. Tidak ada kebijakan select/update/delete:
-- jawaban orang lain tidak bisa dibaca atau diubah lewat kunci publik.
revoke all on public.feedback_responses from anon, authenticated;
grant insert on public.feedback_responses to anon;
drop policy if exists "anon boleh mengirim" on public.feedback_responses;
create policy "anon boleh mengirim" on public.feedback_responses for insert to anon with check (true);

-- Tampilan datar untuk analisis (hanya terbaca dari dasbor Supabase / service role). Dibuat ulang karena kolom versi 1 sudah tidak berlaku.
-- Penilaian (skor SUS, skor pemahaman) dilakukan oleh scripts/summarize_feedback.py dari kolom answers.
drop view if exists public.feedback_flat;
create view public.feedback_flat as
select id, created_at, survey_version, answers->>'nama' as nama, answers
from public.feedback_responses;
revoke all on public.feedback_flat from anon, authenticated;
