import { $, fmtDate, fmtDateShort, fmtNum, fmtPct, fmtUSD, getJSON, hasWebGL, initTheme, markCapabilities, reducedMotion } from "./common.js";
import { createCharts } from "./chart.js";
import { initSplash } from "./splash.js";
import { renderContrib, renderNarrative, renderNews, renderReliability } from "./panels.js";

initTheme();
markCapabilities();
initSplash();

const state = { demo: false, change: null, close: null, closeDate: null, closeText: "", latest: null, history: [], selected: "1", hero: null, horizon: null, charts: null, interval: "D", range: "1Y" };
const INTERVALS = { D: "Harian (D)", W: "Mingguan (W)", M: "Bulanan (M)" };
const RANGES = ["1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"];
const arrow = (dir) => (dir === "NAIK" ? "▲" : "▼");
const cls = (dir) => (dir === "NAIK" ? "up" : "down");

function showBanner(text, kind = "error") {
  const b = $("#banner");
  b.textContent = text;
  b.className = "banner" + (kind === "demo" ? " demo" : "");
  b.hidden = false;
}

function renderHeader(d) {
  state.demo = !!d.demo;
  if (state.demo) {
    showBanner("DATA DEMO SINTETIS: angka di halaman ini bukan harga atau prediksi asli. Jalankan server tanpa LIVE_DIR demo untuk melihat data asli.", "demo");
  }
  state.close = d.close; state.closeDate = d.as_of;
  $("#price").textContent = fmtUSD(d.close);
  state.closeText = $("#price").textContent;
  const ch = $("#change");
  ch.textContent = `${d.change_pct >= 0 ? "▲" : "▼"} ${fmtPct(d.change_pct)}`;
  ch.className = "chg mono " + (d.change_pct >= 0 ? "up" : "down");
  state.change = { text: ch.textContent, cls: ch.className };
  $("#asof").textContent = `Penutupan ${fmtDate(d.as_of)} (UTC)`;
  $("#stat-sent").textContent = fmtNum(d.inputs.news_sentiment, 2);
  $("#stat-fg").textContent = `${fmtNum(d.inputs.fear_greed_index, 0)}/100`;
  $("#stat-news").textContent = String(d.inputs.headline_count);
  $("#stat-gen").textContent = d.generated_at.replace("T", " ").replace(/\+00:00$/, "");
  if (d.age_days > 2) {
    showBanner(`Data terakhir per ${fmtDate(d.as_of)}, lebih dari 2 hari lalu: pembaruan harian mungkin tertunda.`);
  }
}

function currentVisual() {
  const v = state.latest.horizons[state.selected];
  return { prob: v.prob, threshold: v.threshold, direction: v.direction, sentiment: state.latest.inputs.news_sentiment };
}

function renderPanel() {
  const v = state.latest.horizons[state.selected];
  const dirEl = $("#prediction-direction");
  dirEl.textContent = v.direction;
  dirEl.className = "dir mono " + cls(v.direction);
  const a = $("#prediction-arrow");
  a.textContent = arrow(v.direction);
  a.className = "arrow " + cls(v.direction);
  $("#prediction-prob").textContent = `probabilitas naik ${fmtNum(v.prob * 100, 1)}%`;
  $("#prediction-meta").textContent = `ambang keputusan ${fmtNum(v.threshold, 4)} · target ${fmtDate(v.target_date)}`;

  const badge = $("#evidence-badge");
  badge.hidden = false;
  badge.replaceChildren();
  if (v.evidence) {
    badge.className = "badge warn";
    const ci = `CI95 ${fmtNum(v.evidence.ci_lo, 2)}–${fmtNum(v.evidence.ci_hi, 2)}`;
    badge.textContent = `${v.evidence.label} · AUC ${fmtNum(v.evidence.auc, 3)} (${ci}) · p Holm ${fmtNum(v.evidence.p_holm, 2)}`;
  } else {
    badge.className = "badge warn";
    badge.append("Belum terbukti lebih baik dari tebakan acak (akurasi uji Model F ≈ 50%). Rincian uji ada di ");
    const link = document.createElement("a");
    link.href = "/riset";
    link.textContent = "halaman Riset";
    badge.append(link, ".");
  }
  state.hero?.setState(currentVisual());
  renderHistory();
}

function renderHistory() {
  const rows = state.history.filter((e) => e.horizons[state.selected]).slice(-30).reverse();
  const body = $("#history-body");
  body.replaceChildren();
  let done = 0, ok = 0;
  for (const e of rows) {
    const h = e.horizons[state.selected];
    const tr = document.createElement("tr");
    const cells = [fmtDateShort(e.date), `${arrow(h.direction)} ${h.direction}`, `${fmtNum(h.prob * 100, 1)}%`,
      h.actual ? `${arrow(h.actual)} ${h.actual} ${h.correct ? "✓" : "✗"}` : "menunggu"];
    cells.forEach((t, i) => {
      const td = document.createElement("td");
      td.textContent = t;
      if (i === 2) td.className = "num mono";
      if (i === 1) td.className = cls(h.direction);
      if (i === 3 && h.actual) td.className = h.correct ? "up" : "down";
      tr.append(td);
    });
    if (h.actual) { done++; if (h.correct) ok++; }
    body.append(tr);
  }
  $("#hist-h").textContent = `${state.selected} hari · ` +
    (done ? `${ok}/${done} benar (${fmtNum((ok / done) * 100, 0)}%)` : "belum ada hasil yang jatuh tempo");
}

function select(h) {
  state.selected = String(h);
  document.querySelectorAll("#horizon-tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.h === state.selected)));
  state.horizon?.select(state.selected);
  renderPanel();
}

function buildTabs() {
  const hs = Object.keys(state.latest.horizons).sort((a, b) => a - b);
  if (!hs.includes(state.selected)) state.selected = hs[0];
  const wrap = $("#horizon-tabs");
  wrap.replaceChildren();
  hs.forEach((h) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "tab"; b.setAttribute("role", "tab"); b.dataset.h = h;
    b.textContent = `${h} hari`;
    b.addEventListener("click", () => select(h));
    b.addEventListener("keydown", (e) => {
      const i = hs.indexOf(h), n = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
      if (n !== null && hs[n]) { select(hs[n]); wrap.querySelector(`[data-h="${hs[n]}"]`).focus(); }
    });
    wrap.append(b);
  });
}

function buildRanges() {
  const wrap = $("#ranges");
  RANGES.forEach((r) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "range"; b.textContent = r;
    b.setAttribute("aria-pressed", String(r === state.range));
    b.addEventListener("click", () => {
      state.range = r;
      wrap.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      state.charts.setRange(r);
    });
    wrap.append(b);
  });
}

async function loadPrices(interval) {
  const cols = await getJSON(`/api/prices?interval=${interval}`);
  state.charts.setData(cols);
  state.charts.setRange(state.range);
  state.charts.setMarkers(interval === "D" ? state.history : []);   // penanda prediksi harian hanya pada interval D
  return cols;
}

function buildIntervals() {
  const wrap = $("#intervals");
  Object.keys(INTERVALS).forEach((k) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "range"; b.textContent = k;
    b.setAttribute("aria-pressed", String(k === state.interval));
    b.addEventListener("click", async () => {
      if (k === state.interval) return;
      try {
        await loadPrices(k);
        state.interval = k;
        wrap.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        $("#tf-label").textContent = `Timeframe: ${INTERVALS[k]}`;
      } catch (e) { console.warn("Gagal memuat interval", k, e); }
    });
    wrap.append(b);
  });
}

async function setupCharts() {
  state.charts = createCharts({ priceEl: $("#chart-price"), rsiEl: $("#chart-rsi"), macdEl: $("#chart-macd") });
  buildIntervals();
  buildRanges();
  const cols = await loadPrices("D");
  document.addEventListener("themechange", () => { state.charts.restyle(); if (state.latest) state.hero?.setState(currentVisual()); });
  return cols;
}

function headerFromPrices(cols) {
  const n = cols.close.length, last = cols.close[n - 1], prev = cols.close[n - 2];
  state.close = last; state.closeDate = cols.date[n - 1];
  $("#price").textContent = fmtUSD(last);
  state.closeText = $("#price").textContent;
  const pct = (last / prev - 1) * 100, ch = $("#change");
  ch.textContent = `${pct >= 0 ? "▲" : "▼"} ${fmtPct(pct)}`;
  ch.className = "chg mono " + (pct >= 0 ? "up" : "down");
  state.change = { text: ch.textContent, cls: ch.className };
  $("#asof").textContent = `Penutupan ${fmtDate(cols.date[n - 1])} (UTC) · harga terakhir, belum ada prediksi`;
}

async function start3D() {
  if (!hasWebGL()) return;
  try {
    const { createHero } = await import("./scene.js");
    const { createHorizonScene } = await import("./horizon3d.js");
    const mobile = window.matchMedia("(max-width: 700px)").matches;
    state.hero = createHero($("#hero-canvas"), { reduced: reducedMotion, mobile, onSlow: () => document.body.classList.add("no-webgl") });
    state.horizon = createHorizonScene($("#horizon-canvas"), { reduced: reducedMotion, onSelect: select });
    const hs = Object.entries(state.latest.horizons).sort((a, b) => a[0] - b[0]).map(([h, v]) => ({ h, direction: v.direction }));
    state.horizon.setHorizons(hs);
    state.horizon.select(state.selected);
    renderPanel();
  } catch (e) {
    console.warn("Visual 3D dinonaktifkan:", e);
    document.body.classList.add("no-webgl");
  }
}

async function renderExplain() {
  const ex = state.latest?.explain;
  if (!ex) return;
  $("#sec-explain").hidden = false;
  renderNews($("#live-news"), ex.headlines, ex.sentiment);
  renderContrib($("#live-contrib"), ex.contributions);
  renderNarrative($("#live-narrative"), ex.narrative);
  try {
    if (!(await getJSON("/api/retro/status")).built) throw new Error("belum dibangun");
    const series = await getJSON("/api/retro/series");
    renderReliability($("#live-reliability"), series.reliability, series);
  } catch {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "Keandalan historis belum tersedia: jalankan python -m scripts.build_retro.";
    $("#live-reliability").replaceChildren(p);
  }
}

async function main() {
  try {
    state.latest = await getJSON("/api/prediction/latest");
  } catch (e) {
    // Tanpa prediksi: tetap tampilkan harga dan grafik asli bila ada, tanpa kartu prediksi/riwayat yang kosong.
    $("#asof").textContent = "";
    showBanner(e.status === 404
      ? "Prediksi belum tersedia: job harian belum pernah berhasil dijalankan. Yang tampil hanya harga asli dan grafiknya."
      : "Gagal memuat prediksi. Coba muat ulang halaman.");
    $("#sec-pred").hidden = true;
    $("#sec-hist").hidden = true;
    try { headerFromPrices(await setupCharts()); } catch (err) { console.warn("Grafik harga tidak tersedia:", err); }
    return;
  }
  renderHeader(state.latest);
  buildTabs();
  select(state.selected);
  renderExplain();

  try {
    state.history = await getJSON("/api/prediction/history");
    renderHistory();
  } catch { /* riwayat opsional */ }

  try {
    await setupCharts();
  } catch (e) {
    console.warn("Grafik harga tidak tersedia:", e);
  }
  start3D();
}

// ---- Harga live (hanya tampilan; probabilitas tetap resmi harian dari penutupan lengkap) ----
async function refreshLive() {
  if (document.hidden || state.close == null || state.demo) return;   // demo: jangan campur harga live asli dengan patokan palsu
  const badge = $("#live-badge");
  try {
    const { price } = await getJSON("/api/price/live");
    const pct = (price / state.close - 1) * 100;
    $("#price").textContent = fmtUSD(price);
    const ch = $("#change");
    ch.textContent = `${pct >= 0 ? "▲" : "▼"} ${fmtPct(pct)}`;     // perubahan terhadap penutupan terakhir
    ch.className = "chg mono " + (pct >= 0 ? "up" : "down");
    $("#asof").hidden = true;                                       // baris penutupan ada di #since-close
    badge.hidden = false;
    const since = $("#since-close");
    since.hidden = false;
    since.textContent = `Penutupan ${fmtDate(state.closeDate)}: ${fmtUSD(state.close)} · sejak penutupan ${fmtPct(pct)}`;
    const live = $("#prediction-live");
    if (state.latest) {
      live.hidden = false;
      live.textContent = `patokan penutupan ${fmtUSD(state.close)} · harga live ${fmtUSD(price)} (${fmtPct(pct)}); arah prediksi dinilai dari penutupan hari target`;
    }
  } catch {
    badge.hidden = true;
    $("#since-close").hidden = true;
    $("#prediction-live").hidden = true;
    if (state.closeText) $("#price").textContent = state.closeText;     // kembali ke harga penutupan
    if (state.change) { const ch = $("#change"); ch.textContent = state.change.text; ch.className = state.change.cls; }
    $("#asof").hidden = false;
  }
}

function startLive() {
  refreshLive();
  setInterval(refreshLive, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshLive(); });
}

main().then(startLive);
