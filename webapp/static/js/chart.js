import { cssVar, fmtPct, textScale } from "./common.js";

const LC = window.LightweightCharts;
const RANGE_DAYS = { "1M": 30, "3M": 90, "6M": 182, "1Y": 365, "5Y": 1826 };

function hexA(hex, a) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

const ID_NUM = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usd = (v) => "$" + ID_NUM.format(v);
const toIso = (t) => (typeof t === "string" ? t : `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`);
const longDate = (iso, month = "long") =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month, year: "numeric", timeZone: "UTC" });
const fontPx = () => Math.round(11 * textScale());

export function createCharts({ priceEl, rsiEl, macdEl }) {
  const base = () => ({
    autoSize: true,
    layout: { background: { type: "solid", color: "transparent" }, textColor: cssVar("--text-2"), fontFamily: cssVar("--mono"), fontSize: fontPx() },
    localization: { timeFormatter: (t) => longDate(toIso(t), "short") },          // label tanggal pada sumbu saat hover
    grid: { vertLines: { color: cssVar("--line") }, horzLines: { color: cssVar("--line") } },
    rightPriceScale: { borderColor: cssVar("--line") },
    timeScale: { borderColor: cssVar("--line"), rightOffset: 4 },
    crosshair: { mode: LC.CrosshairMode.Normal },
    handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
  });
  const line = (chart, color, w = 1, extra = {}) =>
    chart.addLineSeries({ color, lineWidth: w, priceLineVisible: false, lastValueVisible: false, ...extra });

  const price = LC.createChart(priceEl, base());
  const gold = cssVar("--gold");
  const area = price.addAreaSeries({ lineColor: gold, topColor: hexA(gold, 0.28), bottomColor: hexA(gold, 0), lineWidth: 2, priceLineColor: gold });
  const ma = { MA7: line(price, "#f3d98b"), MA30: line(price, "#7aa7ff"), MA90: line(price, "#b58cff") };
  const dashed = { lineStyle: LC.LineStyle.Dashed };
  const bb = { BB_up: line(price, cssVar("--text-2"), 1, dashed), BB_mid: line(price, cssVar("--text-2"), 1, { lineStyle: LC.LineStyle.Dotted }), BB_dn: line(price, cssVar("--text-2"), 1, dashed) };

  const rsiChart = LC.createChart(rsiEl, base());
  const rsi = line(rsiChart, gold, 2);
  [70, 30].forEach((p) => rsi.createPriceLine({ price: p, color: cssVar("--line"), lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: "" }));

  const macdChart = LC.createChart(macdEl, base());
  const hist = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
  const macd = line(macdChart, "#7aa7ff", 2);
  const sig = line(macdChart, gold, 1);

  const charts = [price, rsiChart, macdChart];
  let syncing = false;
  charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (syncing || !r) return;
    syncing = true;
    charts.forEach((o) => { if (o !== c) o.timeScale().setVisibleLogicalRange(r); });
    syncing = false;
  }));

  let cols = null;
  let liveDay = null;
  // Titik tanpa nilai menjadi "whitespace" agar semua grafik punya indeks logis yang sejajar.
  const series = (key, map = (v) => ({ value: v })) =>
    cols.date.map((time, i) => (cols[key][i] == null ? { time } : { time, ...map(cols[key][i]) }));

  function setData(c) {
    cols = c;
    liveDay = null;
    area.setData(series("close"));
    Object.entries(ma).forEach(([k, s]) => s.setData(series(k)));
    Object.entries(bb).forEach(([k, s]) => s.setData(series(k)));
    rsi.setData(series("RSI14"));
    macd.setData(series("MACD"));
    sig.setData(series("MACD_Signal"));
    hist.setData(series("MACD_Histogram", (v) => ({ value: v, color: v >= 0 ? hexA(cssVar("--up"), 0.7) : hexA(cssVar("--down"), 0.7) })));
  }

  function setRange(key) {
    if (!cols) return;
    const last = cols.date[cols.date.length - 1];
    if (key === "MAX") { price.timeScale().fitContent(); return; }
    let from;
    if (key === "YTD") from = last.slice(0, 4) + "-01-01";
    else {
      const d = new Date(last + "T00:00:00Z");
      d.setUTCDate(d.getUTCDate() - RANGE_DAYS[key]);
      from = d.toISOString().slice(0, 10);
    }
    price.timeScale().setVisibleRange({ from, to: last });
  }

  function setMarkers(history) {
    const have = new Set(cols?.date ?? []);
    const ms = history.filter((e) => e.horizons["1"] && have.has(e.date)).map((e) => {
      const up = e.horizons["1"].direction === "NAIK";
      return { time: e.date, position: up ? "belowBar" : "aboveBar", color: cssVar(up ? "--up" : "--down"), shape: up ? "arrowUp" : "arrowDown", text: "" };
    });
    area.setMarkers(ms);
  }

  function restyle() {
    charts.forEach((c) => c.applyOptions(base()));
    const g = cssVar("--gold");
    area.applyOptions({ lineColor: g, topColor: hexA(g, 0.28), bottomColor: hexA(g, 0), priceLineColor: g });
    rsi.applyOptions({ color: g });
    sig.applyOptions({ color: g });
    Object.values(bb).forEach((s) => s.applyOptions({ color: cssVar("--text-2") }));
  }

  // Titik "hari ini" dari harga live: hanya SETELAH penutupan terakhir (update() menolak waktu lampau). Bukan penutupan resmi.
  function setLive(price, day) {
    const last = cols?.date[cols.date.length - 1];
    if (last == null || day <= last) return false;
    area.update({ time: day, value: price });
    liveDay = day;
    return true;
  }

  function clearLive() { liveDay = null; if (cols) area.setData(series("close")); }

  // Tooltip hover: tanggal lengkap + harga + perubahan dari titik sebelumnya (seperti grafik harga pada umumnya).
  const tip = document.createElement("div");
  tip.id = "chart-tooltip"; tip.className = "chart-tip"; tip.hidden = true;
  priceEl.style.position = "relative";
  priceEl.append(tip);
  price.subscribeCrosshairMove((p) => {
    const v = p.seriesData?.get(area);
    if (!p.point || !p.time || !v || v.value == null) { tip.hidden = true; return; }
    const iso = toIso(p.time), i = cols ? cols.date.indexOf(iso) : -1;
    const isLive = i < 0 && liveDay === iso;
    const prev = isLive ? cols.close[cols.close.length - 1] : (i > 0 ? cols.close[i - 1] : null);
    tip.dataset.date = iso;
    const row = document.createElement("div");
    row.className = "tip-row";
    const dot = document.createElement("span"); dot.className = "tip-dot";
    const label = document.createElement("span"); label.textContent = isLive ? "Harga live:" : "Harga:";
    const val = document.createElement("span"); val.className = "tip-price"; val.textContent = usd(v.value);
    row.append(dot, label, val);
    const date = document.createElement("div"); date.className = "tip-date"; date.textContent = longDate(iso);
    const kids = [date, row];
    if (prev) {
      const pct = (v.value / prev - 1) * 100, chg = document.createElement("div");
      chg.className = "tip-chg " + (pct >= 0 ? "up" : "down");
      chg.textContent = `${pct >= 0 ? "▲" : "▼"} ${fmtPct(pct)} dari ${isLive ? "penutupan terakhir" : "hari sebelumnya"}`;
      kids.push(chg);
    }
    tip.replaceChildren(...kids);
    tip.hidden = false;
    const W = priceEl.clientWidth, H = priceEl.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = p.point.x + 16;
    if (x + tw > W - 4) x = p.point.x - tw - 16;                     // balik ke kiri titik bila mepet tepi kanan
    let y = p.point.y - th - 12;
    if (y < 4) y = p.point.y + 16;                                    // balik ke bawah titik bila mepet atas
    tip.style.left = Math.max(4, Math.min(x, W - tw - 4)) + "px";
    tip.style.top = Math.max(4, Math.min(y, H - th - 4)) + "px";
  });
  priceEl.addEventListener("mouseleave", () => { tip.hidden = true; });
  document.addEventListener("textscalechange", () => charts.forEach((c) => c.applyOptions({ layout: { fontSize: fontPx() } })));

  return { setData, setLive, clearLive, setRange, setMarkers, restyle, dispose: () => charts.forEach((c) => c.remove()) };
}
