import { $, cssVar, fmtDate, fmtNum, fmtUSD, getJSON, initTheme, markCapabilities } from "./common.js";
import { renderContrib, renderNarrative, renderNews, renderReliability } from "./panels.js";

initTheme();
markCapabilities();

const LC = window.LightweightCharts;
const state = { series: null, idx: 0, cache: new Map(), charts: null };
const nameOf = (v) => (v ? "NAIK" : "TURUN");

function chartOpts() {
  return {
    autoSize: true,
    layout: { background: { type: "solid", color: "transparent" }, textColor: cssVar("--text-2"), fontFamily: cssVar("--mono"), fontSize: 11 },
    grid: { vertLines: { color: cssVar("--line") }, horzLines: { color: cssVar("--line") } },
    rightPriceScale: { borderColor: cssVar("--line") }, timeScale: { borderColor: cssVar("--line"), rightOffset: 4 },
    handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
  };
}

function buildCharts(s) {
  const gold = cssVar("--gold");
  const price = LC.createChart($("#chart-retro-price"), chartOpts());
  const area = price.addAreaSeries({ lineColor: gold, topColor: "rgba(230,192,104,0.25)", bottomColor: "rgba(230,192,104,0)", lineWidth: 2, priceLineVisible: false });
  area.setData(s.date.map((time, i) => ({ time, value: s.close[i] })));
  area.setMarkers(s.date.map((time, i) => ({
    time, position: s.pred[i] ? "belowBar" : "aboveBar", shape: s.pred[i] ? "arrowUp" : "arrowDown",
    color: cssVar(s.correct[i] ? "--up" : "--down"), text: "",
  })));
  const selPrice = price.addLineSeries({ lineVisible: false, lastValueVisible: false, priceLineVisible: false });

  const prob = LC.createChart($("#chart-retro-prob"), chartOpts());
  const line = prob.addLineSeries({ color: gold, lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
  line.setData(s.date.map((time, i) => ({ time, value: s.prob[i] })));
  line.createPriceLine({ price: s.threshold, color: cssVar("--text-2"), lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: "ambang" });
  const selProb = prob.addLineSeries({ lineVisible: false, lastValueVisible: false, priceLineVisible: false });

  let syncing = false;
  [price, prob].forEach((c, k, arr) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (syncing || !r) return;
    syncing = true;
    arr.forEach((o) => { if (o !== c) o.timeScale().setVisibleLogicalRange(r); });
    syncing = false;
  }));
  price.timeScale().fitContent();
  state.charts = { price, prob, selPrice, selProb };
}

function markSelected(i) {
  const s = state.series, time = s.date[i];
  const marker = { time, position: "inBar", shape: "circle", color: cssVar("--gold"), size: 2, text: "" };
  state.charts.selPrice.setData([{ time, value: s.close[i] }]);
  state.charts.selPrice.setMarkers([marker]);
  state.charts.selProb.setData([{ time, value: s.prob[i] }]);
  state.charts.selProb.setMarkers([marker]);
}

async function loadDay(date) {
  if (!state.cache.has(date)) state.cache.set(date, await getJSON(`/api/retro/day/${date}`));
  return state.cache.get(date);
}

async function select(i) {
  const s = state.series;
  i = Math.max(0, Math.min(s.date.length - 1, i));
  state.idx = i;
  $("#day-slider").value = String(i);
  $("#day-picker").value = s.date[i];
  $("#day-date").textContent = fmtDate(s.date[i]);
  $("#day-close").textContent = fmtUSD(s.close[i]);
  $("#day-prob").textContent = fmtNum(s.prob[i], 4);
  const pred = $("#day-pred"), act = $("#day-actual");
  pred.textContent = nameOf(s.pred[i]);
  pred.className = "mono " + (s.pred[i] ? "chg up" : "chg down");
  act.textContent = `${nameOf(s.actual[i])} ${s.correct[i] ? "✓" : "✗"}`;
  act.className = "mono " + (s.correct[i] ? "chg up" : "chg down");
  markSelected(i);
  try {
    const d = await loadDay(s.date[i]);
    if (state.idx !== i) return;                                  // pengguna sudah pindah hari
    renderNews($("#panel-news"), d.headlines, d.sentiment, { approx: true });
    renderContrib($("#panel-contrib"), d.contributions);
    renderNarrative($("#panel-narrative"), d.narrative);
  } catch (e) {
    console.warn("Gagal memuat hari", s.date[i], e);
    if (state.idx !== i) return;
    ["#panel-news", "#panel-contrib", "#panel-narrative"].forEach((sel) => {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "Gagal memuat data hari ini.";
      $(sel).replaceChildren(p);                                  // jangan sisakan panel hari sebelumnya di bawah tanggal baru
    });
  }
}

async function main() {
  let s;
  try {
    s = await getJSON("/api/retro/series");
  } catch (e) {
    $("#retro-empty").hidden = false;
    return;
  }
  state.series = s;
  $("#retro-app").hidden = false;
  const p = s.parity;
  $("#parity-note").textContent = p.verified
    ? `Prediksi dihitung ulang dari model terekspor dan cocok dengan tabel notebook (akurasi ${fmtNum(p.got.Accuracy, 4)} vs ${fmtNum(p.expected.Accuracy, 4)}).`
    : "Paritas dengan tabel notebook belum terverifikasi: angka pada halaman ini belum boleh dianggap sama dengan hasil notebook.";
  const slider = $("#day-slider"), picker = $("#day-picker");
  slider.max = String(s.date.length - 1);
  picker.min = s.date[0];
  picker.max = s.date[s.date.length - 1];
  renderReliability($("#panel-reliability"), s.reliability, s);
  buildCharts(s);
  slider.addEventListener("input", () => select(Number(slider.value)));
  $("#day-prev").addEventListener("click", () => select(state.idx - 1));
  $("#day-next").addEventListener("click", () => select(state.idx + 1));
  picker.addEventListener("change", () => {
    const i = s.date.findIndex((d) => d >= picker.value);
    select(i < 0 ? s.date.length - 1 : i);
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;      // slider dan kalender menangani panah sendiri
    if (e.key === "ArrowLeft") select(state.idx - 1);
    if (e.key === "ArrowRight") select(state.idx + 1);
  });
  document.addEventListener("themechange", () => {
    const o = chartOpts();
    state.charts.price.applyOptions(o);
    state.charts.prob.applyOptions(o);
  });
  select(s.date.length - 1);
}

main();
