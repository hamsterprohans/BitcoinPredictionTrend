import { $, cssVar, fmtDate, fmtNum, fmtPct, fmtUSD, getJSON, hasWebGL, initTheme, markCapabilities, reducedMotion, textScale } from "./common.js";

initTheme();
markCapabilities();

function el(tag, text, className) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
}

function renderTable(container, rows, spec, { highlight } = {}) {
  const table = el("table");
  const thead = el("thead"), hr = el("tr");
  spec.forEach((c) => hr.append(el("th", c.label, [c.num ? "num" : "", c.cls || ""].join(" ").trim())));
  thead.append(hr);
  const tbody = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr", undefined, highlight && highlight(r) ? "hl" : "");
    spec.forEach((c) => {
      const v = c.get ? c.get(r) : r[c.key];
      tr.append(el("td", v == null ? "—" : typeof v === "number" ? fmtNum(v, c.d ?? 2) : String(v), [c.num ? "num mono" : "", c.cls || ""].join(" ").trim()));
    });
    tbody.append(tr);
  });
  table.append(thead, tbody);
  const wrap = el("div", undefined, "table-wrap");
  wrap.append(table);
  container.append(wrap);
}

function unavailable(container, text = "Data belum tersedia.") {
  container.append(el("p", text, "muted"));
}

async function section(id, name, render) {
  const box = $("#" + id);
  try {
    await render(box, await getJSON("/api/research/" + name));
  } catch (e) {
    unavailable(box, e.status === 404 ? "Data belum tersedia (belum diekspor dari notebook)." : "Gagal memuat data.");
  }
}

section("sec-ablation", "ablation", async (box, rows) => {
  renderTable(box, rows, [
    { key: "Model", label: "Model" }, { key: "Deskripsi", label: "Deskripsi" },
    { key: "N Fitur", label: "Fitur", num: true, d: 0 }, { key: "Accuracy", label: "Accuracy", num: true, d: 4 },
    { key: "Precision", label: "Precision", num: true, d: 4 }, { key: "Recall", label: "Recall", num: true, d: 4 },
    { key: "F1-Weighted", label: "F1-weighted", num: true, d: 4 },
  ], { highlight: (r) => r.Model === "F" });
  if (hasWebGL()) {
    try {
      const { createBars } = await import("./bars3d.js");
      createBars($("#bars3d-canvas"), rows.map((r) => ({ label: r.Model, value: r["F1-Weighted"] })), { reduced: reducedMotion });
    } catch (e) { console.warn("Visual 3D dinonaktifkan:", e); document.body.classList.add("no-webgl"); }
  }
});

const pm = (m, sd, d = 3) => (m == null ? "—" : sd == null ? fmtNum(m, d) : `${fmtNum(m, d)} ± ${fmtNum(sd, d)}`);

section("sec-multiseed", "multiseed", (box, rows) => {
  const n = Math.max(...rows.map((r) => r["N Seed"]));
  box.append(el("p", `Setiap model dilatih ${n} kali dengan seed berbeda: lima seed resmi (47, 123, 2024, 7, 999) ditambah lima seed tambahan ` +
    "(11, 77, 314, 555, 1234) yang ditetapkan sebelum hasil dilihat. Angka = rata-rata ± simpangan baku sampel. Ambang seragam 0,4768 dibekukan dari " +
    "validasi Model C; ambang seimbang (P2) = median probabilitas validasi tiap model, sehingga F1 tidak lagi mencerminkan letak ambang.", "muted"));
  const spec = [
    { key: "Model", label: "Model" }, { key: "Deskripsi", label: "Deskripsi" },
    { label: "AUC uji", num: true, get: (r) => pm(r["AUC Mean"], r["AUC Std"]) },
    { label: "F1-weighted (ambang seragam)", num: true, get: (r) => pm(r["F1 Mean"], r["F1 Std"]) },
    { label: "F1-weighted (ambang seimbang)", num: true, get: (r) => pm(r["F1 P2 Mean"], r["F1 P2 Std"]) },
    { label: "MCC (ambang seimbang)", num: true, get: (r) => pm(r["MCC P2 Mean"], r["MCC P2 Std"]) },
  ];
  renderTable(box, rows.filter((r) => r.Kelompok !== "tambahan"), spec, { highlight: (r) => r.Model === "F" });
  const extra = rows.filter((r) => r.Kelompok === "tambahan");
  if (extra.length) {
    box.append(el("h3", "Eksperimen tambahan"), el("p", "Bx = Model B dengan batas 300 epoch. C2 sampai F2 = fitur rasio menggantikan level harga (rata-rata bergerak dan MACD) " +
      "untuk mengurangi pergeseran distribusi antara data latih dan uji. Tidak ada yang terbukti lebih baik secara signifikan.", "muted"));
    renderTable(box, extra, spec);
  }
});

section("sec-multihorizon", "multihorizon", (box, rows) => {
  renderTable(box, rows, [
    { key: "H", label: "Horizon (hari)", num: true, d: 0 },
    { key: "n_efektif", label: "n efektif", num: true, d: 1 },
    { key: "AUC_F", label: "AUC Model F", num: true, d: 3 },
    { label: "CI95 (blok-bootstrap)", num: true, get: (r) => `${fmtNum(r.CI_lo, 3)} – ${fmtNum(r.CI_hi, 3)}` },
    { key: "p_geser", label: "p geser-sirkular", num: true, d: 4 },
    { key: "p_Holm_m8", label: "p Holm (m=8)", num: true, d: 4 },
    { label: "Kesimpulan", get: (r) => (r.signifikan_Holm_m8 ? "Signifikan setelah koreksi Holm (m=8)" : "Belum terbukti lebih baik dari tebakan acak") },
  ]);
});

section("sec-signif", "significance", (box, d) => {
  box.append(el("h3", "McNemar (data uji)"));
  renderTable(box, d.mcnemar, [
    { get: (r) => `${r.a} vs ${r.b}`, label: "Pasangan" }, { key: "only_a", label: "Hanya model pertama benar", num: true, d: 0 },
    { key: "only_b", label: "Hanya model kedua benar", num: true, d: 0 }, { key: "p", label: "p-value", num: true, d: 4 },
    { key: "verdict", label: "Kesimpulan" }]);
  const w = d.wilcoxon, nPairs = w.metrics[0].pairs.length;
  box.append(el("h3", `Wilcoxon berpasangan per seed (${w.n_seed} seed, ${nPairs} pasangan, koreksi Holm)`),
    el("p", `p minimum yang mungkin dicapai dengan ${w.n_seed} seed: ${fmtNum(w.p_min, 3)}. Hasil dianggap signifikan hanya bila p Holm di bawah 0,05 ` +
      "dan CI 95% selisih tidak memuat 0. Selisih = model kedua dikurangi model pertama.", "muted"));
  w.metrics.forEach((m) => {
    box.append(el("h3", `Metrik: ${m.label}`, "small muted"));
    renderTable(box, m.pairs, [
      { key: "pair", label: "Pasangan" }, { key: "diff", label: "Selisih rata-rata", num: true, d: 4 },
      { label: "CI 95% (bootstrap)", num: true, get: (r) => `${fmtNum(r.ci_lo, 4)} – ${fmtNum(r.ci_hi, 4)}` },
      { key: "p", label: "p mentah", num: true, d: 4 }, { key: "p_holm", label: "p Holm", num: true, d: 4 },
      { label: "Kesimpulan", get: (r) => (r.significant ? "Signifikan setelah Holm" : "Tidak signifikan setelah Holm") }]);
  });
  const raw = [...new Set(w.metrics.flatMap((m) => m.pairs.filter((r) => r.p < 0.05).map((r) => r.pair)))];
  const sig = w.metrics.reduce((n, m) => n + m.pairs.filter((r) => r.significant).length, 0);
  box.append(el("p", `${sig === 0 ? "Tidak ada pasangan" : `${sig} pasangan`} yang signifikan setelah koreksi Holm.` +
    (raw.length ? ` Pasangan dengan p mentah di bawah 0,05 (${raw.join(", ")}) tidak lolos koreksi Holm, sehingga hanya dilaporkan sebagai temuan eksploratif.` : ""), "muted"));
});

section("sec-thresholds", "threshold_rules", (box, rows) => {
  const spread = (r) => Math.max(...Object.values(r.rules).map((x) => x.akurasi)) - Math.min(...Object.values(r.rules).map((x) => x.akurasi));
  const ex = rows.find((r) => r.H === 30) || rows.reduce((a, b) => (spread(b) > spread(a) ? b : a));
  const r3 = ex.rules, f = (x) => `${fmtNum(x, 1)}%`;
  box.append(el("p", `Pada horizon ${ex.H} hari, akurasi uji Model F bisa ${f(r3.c_youden.akurasi)}, ${f(r3.f_youden.akurasi)}, atau ${f(r3.median_f.akurasi)} ` +
    `hanya karena aturan ambang diganti (ambang C-Youden, F-Youden, atau median validasi), sedangkan AUC yang tidak bergantung ambang tetap ${fmtNum(ex.auc_f, 3)} ` +
    "dengan interval kepercayaan yang memuat 0,5 (lihat tabel multi-horizon). Akurasi tinggi pada satu aturan ambang bukan bukti kemampuan prediksi.", "finding"));
  renderTable(box, rows, [
    { key: "H", label: "Horizon (hari)", num: true, d: 0 }, { key: "pct_naik_nyata", label: "% NAIK nyata (uji)", num: true, d: 1 },
    { key: "auc_f", label: "AUC Model F", num: true, d: 3 },
    { label: "Akurasi, ambang C-Youden (dipakai situs)", num: true, get: (r) => `${fmtNum(r.rules.c_youden.akurasi, 1)}% (${fmtNum(r.rules.c_youden.pct_naik_pred, 0)}% NAIK)` },
    { label: "Akurasi, ambang F-Youden", num: true, get: (r) => `${fmtNum(r.rules.f_youden.akurasi, 1)}% (${fmtNum(r.rules.f_youden.pct_naik_pred, 0)}% NAIK)` },
    { label: "Akurasi, ambang median validasi", num: true, get: (r) => `${fmtNum(r.rules.median_f.akurasi, 1)}% (${fmtNum(r.rules.median_f.pct_naik_pred, 0)}% NAIK)` },
  ]);
  box.append(el("p", "Angka dalam kurung = persentase hari uji yang diprediksi NAIK. Nilai yang jauh dari 50% berarti prediktor hampir konstan pada satu arah. " +
    "Situs memakai ambang C-Youden (sama dengan protokol ablation); aturan lain hanya diagnostik, dan ambangnya dipilih dari data validasi, bukan data uji.", "muted small"));
});

section("sec-holding", "holding_period", (box, rows) => renderTable(box, rows, [
  { key: "H", label: "Masa pegang (hari)", num: true, d: 0 }, { key: "subset", label: "Subset" },
  { key: "n_jendela", label: "Jendela", num: true, d: 0 }, { key: "pct_positif", label: "% positif", num: true, d: 1 },
  { key: "median_pct", label: "Median %", num: true, d: 1 }, { key: "p5_pct", label: "P5 %", num: true, d: 1 },
  { key: "p95_pct", label: "P95 %", num: true, d: 1 }, { key: "terburuk_pct", label: "Terburuk %", num: true, d: 1 }]));

section("sec-perm", "permutation_importance", (box, rows) => {
  const key = "Penurunan F1 (Importance)";
  const max = Math.max(...rows.map((r) => r[key]), 1e-9);
  const wrap = el("div", undefined, "bars");
  rows.forEach((r) => {
    const row = el("div", undefined, "bar-row");
    const bar = el("div", undefined, "bar"), fill = el("span");
    fill.style.width = `${Math.max(0, (r[key] / max) * 100)}%`;
    bar.append(fill);
    row.append(el("span", r.Fitur, "mono"), bar, el("span", fmtNum(r[key], 4), "mono"));
    wrap.append(row);
  });
  box.append(wrap);
});

const FIGS = ["ablation_f1_chart", "confusion_matrices", "permutation_importance", "stage1_lr_vs_lstm",
  "learning_curves", "model_C_probability_distribution", "model_C_training_curves"];
const figs = $("#sec-figs .figs");
FIGS.forEach((n) => {
  const img = el("img");
  img.src = `${window.__STATIC_BASE__ ?? ""}/static/research/${n}.png`;
  img.alt = n.replaceAll("_", " ");
  img.loading = "lazy";
  img.addEventListener("error", () => img.remove());
  figs.append(img);
});

// ---- Backtesting: strategi model (long-only) vs buy and hold (proposal Bab 3.1.9) ----
const NA = "—";
const pctOrNA = (v, d = 1) => (v == null ? NA : fmtPct(v, d));
const BT_ROWS = [
  ["Modal akhir (modal awal $1.000)", (m) => fmtUSD(m.final_equity)],
  ["Total return", (m) => fmtPct(m.total_return_pct, 1)],
  ["Maximum drawdown", (m) => fmtPct(m.max_drawdown_pct, 1)],
  ["Sharpe ratio", (m) => (m.sharpe == null ? NA : fmtNum(m.sharpe, 2))],
  ["Win rate (per transaksi)", (m) => (m.win_rate_pct == null ? NA : fmtNum(m.win_rate_pct, 0) + "%")],
  ["Rata-rata untung per transaksi", (m) => pctOrNA(m.avg_win_pct)],
  ["Rata-rata rugi per transaksi", (m) => pctOrNA(m.avg_loss_pct)],
  ["Jumlah transaksi (masuk dan keluar)", (m) => String(m.n_transactions ?? m.n_trades)],
  ["Hari berada di pasar", (m) => fmtNum(m.days_in_market_pct, 0) + "%"],
];

const fmtP = (p) => fmtNum(p, 3);

function btRandom(d) {            // pembanding sinyal acak (digeser sirkular) dan CI selisih Sharpe terhadap buy and hold
  const parts = [];
  if (d.permutation) {
    const p = d.permutation.total.p;
    parts.push(`Dibanding sinyal acak yang digeser sirkular (${d.permutation.n_shifts} geseran; jumlah transaksi dan eksposur sama), ` +
      `model pada ambang klasifikasi ${p >= 0.05 ? "tidak dapat dibedakan dari sinyal acak" : "berbeda dari sinyal acak"}: p = ${fmtP(p)} untuk total return ` +
      `dan p = ${fmtP(d.permutation.sharpe.p)} untuk Sharpe.`);
  }
  if (d.sharpe_diff_ci) {
    const [lo, hi] = d.sharpe_diff_ci;
    parts.push(`CI 95% selisih Sharpe terhadap buy and hold: ${fmtNum(lo, 2)} sampai ${fmtNum(hi, 2)}${lo <= 0 && hi >= 0 ? " (memuat 0, jadi selisihnya belum pasti)" : ""}.`);
  }
  return parts.join(" ");
}

function btFinding(d) {
  const m = d.model, b = d.buy_and_hold, c = d.model_at_classification_threshold, thr = fmtNum(d.trading_threshold.value, 2);
  const tail = " Ini simulasi pada data historis, bukan bukti kinerja di pasar nyata; pembuktian memerlukan forward testing.";
  const cost = d.fee_per_side != null ? `Dengan biaya ${fmtNum(d.fee_per_side * 100, 2)}% per sisi (asumsi), ` : "";
  if (Math.abs(m.final_equity - b.final_equity) < 0.01 && m.days_in_market_pct >= 99.9) {
    return `Dengan ambang trading ${thr} yang dipilih di data validasi, model memberi sinyal beli hampir setiap hari (${fmtNum(m.days_in_market_pct, 0)}% hari), ` +
      `sehingga hasilnya sama dengan buy and hold: ${fmtUSD(m.final_equity)} dari modal $1.000 (${fmtPct(m.total_return_pct, 1)}). ` +
      `${cost ? cost + "v" : "V"}arian dengan ambang klasifikasi ${fmtNum(d.classification_threshold, 4)} berakhir di ${fmtUSD(c.final_equity)} (${fmtPct(c.total_return_pct, 1)}), ` +
      `tetapi hasil itu sangat bergantung pada ambang (lihat tabel kepekaan). ` + btRandom(d) + tail;
  }
  const rel = m.final_equity > b.final_equity ? "lebih tinggi" : "lebih rendah";
  return `${cost}Pada periode uji, strategi model dengan ambang trading ${thr} menghasilkan ${fmtUSD(m.final_equity)} (${fmtPct(m.total_return_pct, 1)}), ` +
    `${rel} daripada buy and hold: ${fmtUSD(b.final_equity)} (${fmtPct(b.total_return_pct, 1)}). ` + btRandom(d) + tail;
}

function btReading(d) {
  const b = d.buy_and_hold, rets = d.sensitivity.map((r) => r.total_return_pct);
  const market = b.total_return_pct < 0
    ? `Harga turun ${fmtPct(b.total_return_pct, 1)} sepanjang periode uji. Pada pasar turun, berada di posisi tunai pada sebagian hari otomatis terlihat lebih baik, apa pun alasannya.`
    : `Harga naik ${fmtPct(b.total_return_pct, 1)} sepanjang periode uji. Pada pasar naik, berada di posisi tunai pada sebagian hari mengurangi keuntungan.`;
  return [
    "Strategi hanya bisa mengungguli buy and hold bila sinyalnya benar-benar memisahkan hari naik dari hari turun. Akurasi uji model hanya sekitar 50% (lihat bagian Ablation), sehingga keunggulan di simulasi mudah terjadi karena kebetulan.",
    market,
    `Hasil berubah drastis menurut ambang: dari ${fmtPct(Math.min(...rets), 1)} sampai ${fmtPct(Math.max(...rets), 1)} (tabel kepekaan). Hasil yang berubah banyak oleh pergeseran kecil ambang bukan tanda sinyal yang stabil.`,
  ];
}

function btTable(d) {
  const cols = [[`Klasifikasi ${fmtNum(d.classification_threshold, 4)}`, d.model_at_classification_threshold]];
  if (d.model_at_half) cols.push(["Ambang 0,5", d.model_at_half, "hide-sm"]);          // disembunyikan di ponsel agar tabel muat
  cols.push([`Trading ${fmtNum(d.trading_threshold.value, 2)}`, d.model], ["Buy and hold", d.buy_and_hold]);
  const table = el("table"), thead = el("thead"), hr = el("tr"), body = el("tbody");
  table.id = "bt-table";
  [["Metrik"], ...cols].forEach(([h, , c], i) => hr.append(el("th", h, [i ? "num" : "", c || ""].join(" ").trim())));
  thead.append(hr);
  table.append(thead);
  const rows = [...BT_ROWS, ["Keterangan", (m) => (m.identical_to_buy_and_hold ? "sama dengan buy and hold" : NA)]];
  rows.forEach(([label, f]) => {
    const tr = el("tr"), th = el("th", label);
    th.scope = "row";
    tr.append(th);
    cols.forEach(([, m, c]) => tr.append(el("td", f(m), `num mono ${c || ""}`.trim())));
    body.append(tr);
  });
  table.append(body);
  const wrap = el("div", undefined, "table-wrap bt-wrap");
  wrap.append(table);
  return wrap;
}

function btChart(box, d) {
  const LC = window.LightweightCharts;
  if (!LC) return;
  const fontSize = () => Math.round(11 * textScale());
  const chart = LC.createChart(box, {
    autoSize: true,
    layout: { background: { type: "solid", color: "transparent" }, textColor: cssVar("--text-2"), fontFamily: cssVar("--mono"), fontSize: fontSize() },
    grid: { vertLines: { color: cssVar("--line") }, horzLines: { color: cssVar("--line") } },
    rightPriceScale: { borderColor: cssVar("--line") }, timeScale: { borderColor: cssVar("--line") },
    handleScroll: false, handleScale: false,
    localization: { priceFormatter: (v) => fmtUSD(v) },
  });
  const line = (color, extra = {}) => chart.addLineSeries({ color, lineWidth: 2, priceLineVisible: false, lastValueVisible: true, ...extra });
  const pts = (key) => d.curve.date.map((time, i) => ({ time, value: d.curve[key][i] }));
  const series = [
    [line(cssVar("--text-2"), { lineStyle: LC.LineStyle.Dashed }), "buy_hold"],          // di bawah: terlihat bila persis tertutup model
    [line(cssVar("--gold")), "model_classification"],
    [line("#7aa7ff"), "model"],
  ];
  series.forEach(([s, key]) => s.setData(pts(key)));
  chart.timeScale().fitContent();
  document.addEventListener("themechange", () => {
    chart.applyOptions({ layout: { textColor: cssVar("--text-2") }, grid: { vertLines: { color: cssVar("--line") }, horzLines: { color: cssVar("--line") } } });
    series[0][0].applyOptions({ color: cssVar("--text-2") });
    series[1][0].applyOptions({ color: cssVar("--gold") });
  });
  document.addEventListener("textscalechange", () => chart.applyOptions({ layout: { fontSize: fontSize() } }));
}

function renderBacktest(box, d) {
  const per = d.period;
  box.append(el("p", `Strategi long-only: beli saat prediksi NAIK, tunai saat TURUN. Modal awal $1.000, ${d.costs}. ` +
    `Periode uji ${fmtDate(per.start)} sampai ${fmtDate(per.end)} (${per.n_days} hari). Ambang trading dipilih dari grid 0,05 sampai 0,90 pada data validasi ` +
    `(${d.trading_threshold.val_n_days} hari), lalu diterapkan ke data uji.`, "muted"));
  const finding = el("p", btFinding(d), "finding");
  finding.id = "bt-finding";
  finding.setAttribute("role", "note");
  box.append(finding);

  const chartBox = el("div", undefined, "chart mid");
  chartBox.id = "bt-chart";
  box.append(el("h3", "Kurva ekuitas (modal awal $1.000)", "small muted"), chartBox);
  const legend = el("p", undefined, "bt-legend mono small");
  [["Model F (ambang klasifikasi)", "--gold"], ["Model F (ambang trading)", "#7aa7ff"], ["Buy and hold (garis putus-putus)", "--text-2"]].forEach(([t, c]) => {
    const item = el("span", t), dot = el("i");
    dot.style.background = c.startsWith("--") ? `var(${c})` : c;
    item.prepend(dot);
    legend.append(item);
  });
  box.append(legend);
  btChart(chartBox, d);

  box.append(el("h3", "Perbandingan metrik", "small muted"),
    el("p", "Kolom = Model F pada tiga ambang (klasifikasi beku dari validasi Model C, 0,5, dan ambang trading yang dipilih dari validasi), lalu buy and hold.", "muted small"),
    btTable(d));
  const reading = el("ul", undefined, "bt-reading");
  reading.id = "bt-reading";
  btReading(d).forEach((t) => reading.append(el("li", t)));
  box.append(el("h3", "Cara membaca hasil ini", "small muted"), reading);

  box.append(el("h3", "Kepekaan terhadap ambang trading (data uji)", "small muted"));
  const sens = el("div", "", "");
  box.append(sens);
  renderTable(sens, d.sensitivity, [
    { label: "Ambang", get: (r) => fmtNum(r.threshold, 2), num: true },
    { label: "Modal akhir", get: (r) => fmtUSD(r.final_equity), num: true },
    { label: "Total return", get: (r) => fmtPct(r.total_return_pct, 1), num: true },
    { label: "Sharpe", get: (r) => (r.sharpe == null ? NA : fmtNum(r.sharpe, 2)), num: true, cls: "hide-sm" },
    { label: "Max drawdown", get: (r) => fmtPct(r.max_drawdown_pct, 1), num: true, cls: "hide-sm" },
    { label: "Transaksi", get: (r) => String(r.n_trades), num: true },
  ], { highlight: (r) => Math.abs(r.threshold - d.trading_threshold.value) < 1e-9 });
  sens.querySelector("table").id = "bt-sensitivity";

  box.append(el("h3", "Catatan dan keterbatasan", "small muted"));
  const cav = el("ul", undefined, "bt-caveats");
  cav.id = "bt-caveats";
  d.caveats.forEach((t) => cav.append(el("li", t)));
  box.append(cav);
}

(async () => {
  const box = $("#sec-backtest");
  try {
    renderBacktest(box, await getJSON("/api/research/backtest"));
  } catch (e) {
    if (e.status !== 404) console.warn("Backtest:", e);                       // galat tampilan/data terlihat di konsol, bukan ditelan
    if (e.status === 404) unavailable(box, "Belum tersedia: hasil backtest belum dibangun (jalankan python -m scripts.build_backtest).");
    else unavailable(box, "Backtest gagal ditampilkan.");
  }
})();
