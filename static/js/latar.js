import { $, fmtNum, getJSON, initTheme } from "./common.js";

initTheme();

const fill = (key, text) => { const e = $(`[data-fill="${key}"]`); if (e) e.textContent = text; };
const p = (v, d = 4) => fmtNum(v, d);

async function load(name) {
  try { return await getJSON("/api/research/" + name); } catch { return null; }
}

(async () => {
  const [ablation, signif, evidence] = await Promise.all([load("ablation"), load("significance"), load("multihorizon_evidence")]);

  if (ablation?.length) {
    const acc = ablation.map((r) => r.Accuracy);
    fill("accuracy", `${p(Math.min(...acc))} – ${p(Math.max(...acc))} (tebakan acak ≈ 0,5000)`);
  } else fill("accuracy", "belum tersedia");

  if (signif?.mcnemar?.length) {
    const rows = signif.mcnemar, sig = rows.filter((r) => r.p < 0.05).length;
    const min = rows.reduce((a, b) => (b.p < a.p ? b : a));
    fill("mcnemar", `${sig} dari ${rows.length} pasangan signifikan; p terkecil ${min.a} vs ${min.b} = ${p(min.p)}`);
  } else fill("mcnemar", "belum tersedia");

  if (signif?.wilcoxon?.length) {
    const rows = signif.wilcoxon, sig = rows.filter((r) => r.p < 0.05).length;
    const min = rows.reduce((a, b) => (b.p < a.p ? b : a));
    fill("wilcoxon", `${sig} dari ${rows.length} pasangan signifikan; p terkecil ${min.a} vs ${min.b} = ${p(min.p)}`);
  } else fill("wilcoxon", "belum tersedia");

  if (evidence && Object.keys(evidence).length) {
    const all = Object.values(evidence), sig = all.filter((e) => e.significant).length;
    fill("horizons", `${sig} dari ${all.length} horizon terbukti lebih baik dari tebakan acak (koreksi Holm)`);
  } else fill("horizons", "belum tersedia");
})();
