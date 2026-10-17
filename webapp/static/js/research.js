import { $, fmtNum, getJSON, hasWebGL, initTheme, markCapabilities, reducedMotion } from "./common.js";

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
  spec.forEach((c) => hr.append(el("th", c.label, c.num ? "num" : "")));
  thead.append(hr);
  const tbody = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr", undefined, highlight && highlight(r) ? "hl" : "");
    spec.forEach((c) => {
      const v = c.get ? c.get(r) : r[c.key];
      tr.append(el("td", v == null ? "—" : typeof v === "number" ? fmtNum(v, c.d ?? 2) : String(v), c.num ? "num mono" : ""));
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

section("sec-multiseed", "multiseed", (box, rows) => renderTable(box, rows, [
  { key: "Model", label: "Model" }, { key: "F1 Mean", label: "F1 rata-rata (5 seed)", num: true, d: 4 },
  { key: "F1 Std", label: "Simpangan baku", num: true, d: 4 }]));

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
  box.append(el("h3", "Wilcoxon berpasangan per seed"));
  renderTable(box, d.wilcoxon, [
    { get: (r) => `${r.a} vs ${r.b}`, label: "Pasangan" }, { key: "statistic", label: "Statistik", num: true, d: 1 },
    { key: "p", label: "p-value", num: true, d: 4 }, { key: "mean_a", label: "Rata-rata pertama", num: true, d: 4 },
    { key: "mean_b", label: "Rata-rata kedua", num: true, d: 4 }, { key: "verdict", label: "Kesimpulan" }]);
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

const FIGS = ["ablation_f1_chart", "multiseed_f1", "confusion_matrices", "permutation_importance", "stage1_lr_vs_lstm",
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

(async () => {
  const box = $("#sec-backtest");
  try {
    const d = await getJSON("/api/research/backtest");
    box.append(el("pre", JSON.stringify(d, null, 1), "mono"));
  } catch {
    unavailable(box, "Belum tersedia: output sel backtest pada notebook belum diekspor.");
  }
})();
