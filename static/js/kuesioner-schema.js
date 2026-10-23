// Definisi kuesioner (data murni), mengikuti dokumen "Referensi Kuesioner TA Hans".
// Tipe: yn = Ya/Tidak, choice = pilihan tunggal (options), scale = skala 1-5 (labels = ujung bawah dan atas),
// tf = Benar/Salah/Tidak tahu, short = teks pendek, long = teks panjang.
// SEMUA soal yang tampil wajib dijawab. showIf = soal hanya tampil (dan wajib) bila soal lain berjawaban tertentu.
// `consent` = soal persetujuan: soal lain baru tampil setelah dijawab Ya. Kunci jawaban bagian B sengaja TIDAK ada di sini (publik):
// penilaian dilakukan di scripts/summarize_feedback.py. Ubah isi => naikkan `version` (dan daftar kunci di supabase/schema.sql).
const AGREE = ["Sangat tidak setuju", "Sangat setuju"];
const D = { id: "d0", equals: "ya" };
export const SURVEY = {
  version: 2,
  consent: "a0",
  sections: [
    { id: "a", title: "A. Persetujuan dan profil",
      intro: "Jawaban dipakai untuk penelitian tugas akhir ini saja.",
      questions: [
        { id: "a0", type: "yn", text: "Saya berusia 18 tahun atau lebih dan bersedia berpartisipasi." },
        { id: "nama", type: "short", text: "Nama Anda:", autocomplete: "name" },
        { id: "a1", type: "choice", text: "Pengalaman Anda dengan aset kripto:", options: [
          { value: "belum", label: "Belum pernah" },
          { value: "berita", label: "Pernah membaca atau mengikuti beritanya" },
          { value: "trading_baru", label: "Pernah trading kurang dari 1 tahun" },
          { value: "trading_lama", label: "Pernah trading 1 tahun atau lebih" }] },
        { id: "a2", type: "scale", text: "Seberapa familiar Anda dengan machine learning atau prediksi berbasis data?", labels: ["Tidak familiar", "Sangat familiar"] },
        { id: "a3", type: "choice", text: "Seberapa sering Anda memakai indikator teknikal (RSI, MACD, moving average)?", options: [
          { value: "tidak_pernah", label: "Tidak pernah" },
          { value: "pernah_lihat", label: "Pernah melihat" },
          { value: "kadang", label: "Kadang memakai" },
          { value: "rutin", label: "Rutin memakai" }] },
        { id: "a4", type: "choice", text: "Anda mengakses situs ini lewat:", options: [
          { value: "ponsel", label: "Ponsel" },
          { value: "laptop", label: "Laptop atau komputer" },
          { value: "tablet", label: "Tablet" }] },
      ] },
    { id: "b", title: "B. Pemahaman",
      intro: "Pilih Benar, Salah, atau Tidak tahu untuk tiap pernyataan. Tidak apa-apa bila Anda tidak tahu.",
      questions: [
        { id: "b1", type: "tf", text: "Situs ini memprediksi angka harga Bitcoin besok." },
        { id: "b2", type: "tf", text: "Probabilitas naik 60% berarti harga pasti naik dengan peluang 60%." },
        { id: "b3", type: "tf", text: "Pada pengujian, model terbukti lebih akurat daripada tebakan acak." },
        { id: "b4", type: "tf", text: "Prediksi NAIK bisa muncul walaupun probabilitasnya di bawah 50%." },
        { id: "b5", type: "tf", text: "Batang hijau pada kontribusi fitur berarti fitur itu menyebabkan harga naik di pasar." },
        { id: "b6", type: "tf", text: "Prediksi dengan tingkat keyakinan tinggi sudah terbukti lebih akurat daripada yang rendah." },
      ] },
    { id: "c", title: "C. Kemudahan penggunaan",
      intro: "Seberapa setuju Anda dengan pernyataan berikut? (1 = sangat tidak setuju, 5 = sangat setuju)",
      questions: [
        { id: "c1", type: "scale", labels: AGREE, text: "Saya pikir saya akan sering menggunakan situs ini." },
        { id: "c2", type: "scale", labels: AGREE, text: "Saya merasa situs ini terlalu rumit tanpa perlu." },
        { id: "c3", type: "scale", labels: AGREE, text: "Saya pikir situs ini mudah digunakan." },
        { id: "c4", type: "scale", labels: AGREE, text: "Saya pikir saya membutuhkan bantuan orang teknis untuk dapat menggunakan situs ini." },
        { id: "c5", type: "scale", labels: AGREE, text: "Saya merasa fungsi-fungsi dalam situs ini terintegrasi dengan baik." },
        { id: "c6", type: "scale", labels: AGREE, text: "Saya pikir ada terlalu banyak ketidakkonsistenan dalam situs ini." },
        { id: "c7", type: "scale", labels: AGREE, text: "Saya membayangkan kebanyakan orang akan belajar menggunakan situs ini dengan sangat cepat." },
        { id: "c8", type: "scale", labels: AGREE, text: "Saya merasa situs ini sangat merepotkan untuk digunakan." },
        { id: "c9", type: "scale", labels: AGREE, text: "Saya merasa sangat percaya diri menggunakan situs ini." },
        { id: "c10", type: "scale", labels: AGREE, text: "Saya perlu mempelajari banyak hal sebelum dapat menggunakan situs ini." },
      ] },
    { id: "d", title: "D. Kepuasan terhadap penjelasan",
      intro: "Bagian ini tentang panel penjelasan prediksi (\"Dari mana prediksi ini datang\"). 1 = sangat tidak setuju, 5 = sangat setuju.",
      questions: [
        { id: "d0", type: "yn", text: "Apakah Anda membuka dan membaca panel penjelasan prediksi di halaman utama?" },
        { id: "d1", type: "scale", labels: AGREE, showIf: D, text: "Dari penjelasan ini, saya memahami cara kerja prediksi situs ini." },
        { id: "d2", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan tentang cara kerja prediksi ini memuaskan." },
        { id: "d3", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini memiliki detail yang cukup." },
        { id: "d4", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini terasa lengkap." },
        { id: "d5", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini memberi tahu saya cara menggunakan prediksi tersebut." },
        { id: "d6", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini berguna untuk tujuan saya." },
        { id: "d7", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini menunjukkan seberapa akurat prediksi tersebut." },
        { id: "d8", type: "scale", labels: AGREE, showIf: D, text: "Penjelasan ini memungkinkan saya menilai kapan saya sebaiknya percaya dan tidak percaya pada prediksi tersebut." },
      ] },
    { id: "e", title: "E. Kepercayaan dan niat bergantung",
      intro: "1 = sangat tidak setuju, 5 = sangat setuju.",
      questions: [
        { id: "e1", type: "scale", labels: AGREE, text: "Saya percaya pada probabilitas naik dan turun yang ditampilkan situs ini." },
        { id: "e2", type: "scale", labels: AGREE, text: "Saya akan mengikuti prediksi situs ini saat mengambil keputusan jual atau beli." },
        { id: "e3", type: "scale", labels: AGREE, text: "Situs ini membuat saya tahu batas keandalan prediksinya." },
        { id: "e4", type: "scale", labels: AGREE, text: "Setelah menjelajahi situs ini, saya lebih berhati-hati dalam memakai prediksi tersebut." },
      ] },
    { id: "f", title: "F. Pertanyaan terbuka",
      questions: [
        { id: "f1", type: "long", text: "Bagian situs mana yang paling membantu Anda memahami prediksi, dan mengapa?" },
        { id: "f2", type: "long", text: "Bagian atau istilah mana yang membingungkan?" },
        { id: "f3", type: "long", text: "Fitur atau perubahan apa yang Anda harapkan berikutnya?" },
        { id: "f4", type: "long", text: "Dengan kata-kata Anda sendiri, seberapa layak prediksi situs ini dijadikan dasar keputusan?" },
      ] },
  ],
};
