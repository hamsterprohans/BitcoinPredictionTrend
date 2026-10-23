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

-- Tampilan datar untuk dibaca per soal (Table Editor > feedback_flat): satu kolom per pertanyaan, kolom = ringkasan pertanyaan
-- (profil, paham_*, sus_* = 10 butir SUS, penjelasan_*, percaya/kepercayaan, jawaban terbuka) ditambah skor_sus (0-100) dan skor_pemahaman (benar dari 6).
-- Hanya jawaban versi 2: jawaban versi 1 punya soal berbeda dan tetap ada di tabel feedback_responses. Hanya terbaca dari dasbor / service role.
-- Nilai di luar 1-5 (kunci publik bisa mengirim teks apa pun) diabaikan oleh rumus agar view tidak error.
drop view if exists public.feedback_flat;
create view public.feedback_flat as
with r as (select id, created_at, survey_version, answers as a from public.feedback_responses where survey_version = 2)
select id, created_at, survey_version,
       a->>'a0' as setuju_ikut,
       a->>'nama' as nama,
       a->>'a1' as pengalaman_kripto,
       a->>'a2' as familiar_ml,
       a->>'a3' as pakai_indikator_teknikal,
       a->>'a4' as akses_lewat,
       a->>'b1' as paham_prediksi_angka_harga,
       a->>'b2' as paham_probabilitas_60_persen,
       a->>'b3' as paham_lebih_akurat_dari_acak,
       a->>'b4' as paham_naik_di_bawah_50,
       a->>'b5' as paham_batang_hijau_sebab,
       a->>'b6' as paham_keyakinan_tinggi_akurat,
       a->>'c1' as sus_sering_pakai,
       a->>'c2' as sus_terlalu_rumit,
       a->>'c3' as sus_mudah_digunakan,
       a->>'c4' as sus_butuh_bantuan_teknis,
       a->>'c5' as sus_fungsi_terintegrasi,
       a->>'c6' as sus_tidak_konsisten,
       a->>'c7' as sus_cepat_dipelajari,
       a->>'c8' as sus_merepotkan,
       a->>'c9' as sus_percaya_diri,
       a->>'c10' as sus_banyak_dipelajari,
       a->>'d0' as lihat_panel_penjelasan,
       a->>'d1' as penjelasan_paham_cara_kerja,
       a->>'d2' as penjelasan_memuaskan,
       a->>'d3' as penjelasan_detail_cukup,
       a->>'d4' as penjelasan_lengkap,
       a->>'d5' as penjelasan_cara_pakai,
       a->>'d6' as penjelasan_berguna,
       a->>'d7' as penjelasan_tunjukkan_akurasi,
       a->>'d8' as penjelasan_kapan_percaya,
       a->>'e1' as percaya_probabilitas,
       a->>'e2' as akan_ikuti_prediksi,
       a->>'e3' as tahu_batas_keandalan,
       a->>'e4' as lebih_berhati_hati,
       a->>'f1' as bagian_paling_membantu,
       a->>'f2' as bagian_membingungkan,
       a->>'f3' as harapan_fitur,
       a->>'f4' as layak_jadi_dasar_keputusan,
       case when a->>'c1' ~ '^[1-5]$' and a->>'c2' ~ '^[1-5]$' and a->>'c3' ~ '^[1-5]$' and a->>'c4' ~ '^[1-5]$' and a->>'c5' ~ '^[1-5]$' and a->>'c6' ~ '^[1-5]$' and a->>'c7' ~ '^[1-5]$' and a->>'c8' ~ '^[1-5]$' and a->>'c9' ~ '^[1-5]$' and a->>'c10' ~ '^[1-5]$'
            then (((a->>'c1')::int - 1)+(5 - (a->>'c2')::int)+((a->>'c3')::int - 1)+(5 - (a->>'c4')::int)+((a->>'c5')::int - 1)+(5 - (a->>'c6')::int)+((a->>'c7')::int - 1)+(5 - (a->>'c8')::int)+((a->>'c9')::int - 1)+(5 - (a->>'c10')::int)) * 2.5 end as skor_sus,
       case when a->>'b1' in ('benar', 'salah', 'tidak_tahu') and a->>'b2' in ('benar', 'salah', 'tidak_tahu') and a->>'b3' in ('benar', 'salah', 'tidak_tahu') and a->>'b4' in ('benar', 'salah', 'tidak_tahu') and a->>'b5' in ('benar', 'salah', 'tidak_tahu') and a->>'b6' in ('benar', 'salah', 'tidak_tahu')
            then (a->>'b1' = 'salah')::int + (a->>'b2' = 'salah')::int + (a->>'b3' = 'salah')::int + (a->>'b4' = 'benar')::int + (a->>'b5' = 'salah')::int + (a->>'b6' = 'salah')::int end as skor_pemahaman
from r;
revoke all on public.feedback_flat from anon, authenticated;
