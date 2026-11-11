import { fmtNum } from "./common.js";

const el = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};

const TONE_LABEL = { bearish: "bernada turun", netral: "netral", bullish: "bernada naik" };

function renderNewsView(root, view, hasTones) {
  if (!view) return;
  if (view.role) root.append(el("p", view.role, "news-role"));
  if (view.summary) {
    const p = el("p", undefined, "news-summary");
    p.append(el("strong", "Rangkuman berita bernada turun: "), document.createTextNode(view.summary.text));
    root.append(p);
  }
  if (hasTones) {
    root.append(el("p", "Nada tiap judul dinilai terpisah oleh LLM untuk tampilan ini. Itu bukan input model (model hanya memakai skor rata-rata harian) " +
      "dan bukan penyebab prediksi.", "muted small tone-note"));
  }
}

export function renderNews(root, headlines, sentiment, opts = {}) {
  root.replaceChildren();
  if (headlines?.length) {
    const ul = el("ul", undefined, "news-list");
    headlines.forEach((h) => {
      const li = el("li");
      if (/^https?:\/\//.test(h.url || "")) {
        const a = el("a", h.title);
        a.href = h.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.append(a);
      } else {
        li.textContent = h.title;
      }
      if (h.tone) li.append(" ", el("span", TONE_LABEL[h.tone] || h.tone, `tone tone-${h.tone}`));
      ul.append(li);
    });
    root.append(ul);
    renderNewsView(root, opts.view, headlines.some((h) => h.tone));
    if (opts.source && opts.source !== "cryptocompare") {      // jujur: sumber cadangan bisa sedikit berbeda dari data latih
      const label = { rss: "RSS CoinDesk, Cointelegraph, Decrypt, dll.", gdelt: "GDELT" }[opts.source] || opts.source;
      root.append(el("p", `Sumber berita cadangan (${label}): outlet sejenis dengan sumber utama, tetapi cakupannya bisa sedikit berbeda dari data latih.`, "muted small source-note"));
    }
    if (opts.approx) {
      root.append(el("p", "Contoh judul berita hari itu: belum tentu sama dengan lima judul yang dinilai " +
        "(urutan data scrap tidak dapat direproduksi persis).", "muted small"));
    }
  } else {
    root.append(el("p", sentiment?.has_news === false
      ? "Tidak ada berita bersih pada hari ini: sentimen diisi dari forward-fill maksimal 2 hari, lalu 0."
      : "Tidak ada judul berita tersimpan untuk hari ini.", "muted"));
  }
  const s = sentiment?.scores;
  if (s) {
    root.append(el("p", `Skor prompt (−10…+10): pemahaman ${fmtNum(s.pemahaman, 0)} · detail ${fmtNum(s.detail, 0)} · ` +
      `bullbear ${fmtNum(s.bullbear, 0)} · rata-rata ${fmtNum(s.mean, 2)}`, "mono muted small"));
  }
  if (sentiment?.used != null) {
    root.append(el("p", `Nilai sentimen yang dipakai model: ${fmtNum(sentiment.used, 2)}`, "mono muted small"));
  }
}

export function renderContrib(root, contributions) {
  root.replaceChildren();
  const max = Math.max(...contributions.map((c) => Math.abs(c.delta_pp)), 1e-9);
  const wrap = el("div", undefined, "bars");
  contributions.forEach((c) => {
    const row = el("div", undefined, "bar-row");
    const bar = el("div", undefined, "dv");
    const fill = el("span", undefined, c.delta_pp >= 0 ? "pos" : "neg");
    fill.style.width = `${(Math.abs(c.delta_pp) / max) * 50}%`;
    bar.append(fill);
    row.append(el("span", c.label), bar, el("span", `${c.delta_pp >= 0 ? "+" : ""}${fmtNum(c.delta_pp, 1)}`, "mono"));
    wrap.append(row);
  });
  root.append(wrap, el("p", "Poin persentase perubahan probabilitas bila fitur itu diganti median data latih. Bukan sebab-akibat.",
    "muted small"));
}

export function renderReliability(root, reliability, series) {
  root.replaceChildren();
  if (series?.parity && !series.parity.verified) {
    root.append(el("p", "Paritas dengan tabel notebook belum terverifikasi: angka keandalan ini belum boleh dianggap " +
      "sama dengan hasil notebook.", "banner"));
  }
  const table = el("table"), head = el("tr");
  ["Tingkat keyakinan", "Hari", "Akurasi", "CI 95% (Wilson)", "Kesimpulan"].forEach((h, i) =>
    head.append(el("th", h, i >= 1 && i <= 3 ? "num" : "")));
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  reliability.forEach((r) => {
    const tr = el("tr");
    tr.append(el("td", r.level), el("td", String(r.n), "num mono"),
      el("td", r.accuracy == null ? "—" : `${fmtNum(r.accuracy * 100, 1)}%`, "num mono"),
      el("td", `${fmtNum(r.ci_lo * 100, 1)}–${fmtNum(r.ci_hi * 100, 1)}%`, "num mono"),
      el("td", r.includes_chance ? "memuat 50%: belum terbukti lebih baik dari tebakan acak" : "tidak memuat 50%"));
    tbody.append(tr);
  });
  table.append(thead, tbody);
  const wrap = el("div", undefined, "table-wrap");
  wrap.append(table);
  root.append(wrap);
  if (series) {
    root.append(el("p", `Periode uji: ${series.n} hari, akurasi ${fmtNum(series.accuracy * 100, 1)}%` +
      (series.auc != null ? `, AUC ${fmtNum(series.auc, 3)}` : "") +
      ". Interval yang memuat 50% berarti belum terbukti lebih baik dari tebakan acak.", "muted small"));
  }
}

export function renderNarrative(root, narrative, digest) {
  root.replaceChildren();
  if (!narrative) {
    root.append(el("p", "Narasi belum dibuat untuk hari ini.", "muted"));
    return;
  }
  root.append(el("p", narrative.text.replace(/^\s*#+[^\n]*\n+/, ""), "narr"));       // sisa judul markdown dari LLM tidak ditampilkan
  root.append(el("p", narrative.source === "llm"
    ? "Ditulis oleh LLM dan lolos pemeriksaan otomatis atas angka, arah prediksi, dan disclaimer; ini bukan jaminan penjelasannya benar."
    : "Narasi template: keluaran LLM tidak lolos pemeriksaan otomatis, sehingga memakai template berbasis fakta.",
    "muted small"));
  if (digest?.text) {
    const p = el("p", undefined, "narr-digest");
    p.append(el("strong", "Rangkuman berita hari ini: "), document.createTextNode(digest.text));
    root.append(p);
    root.append(el("p", "Rangkuman ditulis oleh LLM dari judul-judul berita hari itu. Ini bukan penyebab prediksi, dan model hanya memakai skor sentimen rata-rata.", "muted small"));
  }
}
