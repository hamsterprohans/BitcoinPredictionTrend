export const $ = (sel, root = document) => root.querySelector(sel);

const idNum = (d) => new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtNum = (n, d = 2) => idNum(d).format(n);
export const fmtUSD = (n) => "$" + idNum(2).format(n);
export const fmtPct = (n, d = 2) => (n > 0 ? "+" : "") + idNum(d).format(n) + "%";
export const fmtDate = (iso) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export const fmtDateShort = (iso) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

// Situs statis (GitHub Pages): ekspor menyuntikkan window.__STATIC_BASE__; API dibaca dari berkas api/*.json.
const STATIC_BASE = window.__STATIC_BASE__;

async function staticJSON(url) {
  if (url === "/api/price/live") {                 // satu-satunya data live: langsung dari Coinbase
    const r = await fetch("https://api.coinbase.com/v2/prices/BTC-USD/spot");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { price: parseFloat((await r.json()).data.amount) };
  }
  const path = url.replace(/\?interval=(\w)$/, "__$1") + ".json";
  const d = await rawJSON(STATIC_BASE + path);
  if (url === "/api/prediction/latest") {          // umur data dihitung di browser, bukan saat ekspor
    d.age_days = Math.floor((Date.now() - Date.parse(d.as_of + "T00:00:00Z")) / 864e5);
  }
  return d;
}

export function getJSON(url) {
  return STATIC_BASE === undefined ? rawJSON(url) : staticJSON(url);
}

async function rawJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });          // selalu validasi ke server (304 bila tak berubah)
  if (!r.ok) { const e = new Error(`HTTP ${r.status}`); e.status = r.status; throw e; }
  return r.json();
}

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

export function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

export function markCapabilities() {
  document.body.classList.toggle("no-webgl", !hasWebGL());
  document.body.dataset.motion = reducedMotion ? "reduced" : "full";
}

// Ukuran teks: 4 tingkat (skala terhadap 16px), disimpan di peramban. Bawaan sudah lebih besar (115%) agar ramah banyak kalangan.
export const TEXT_LEVELS = [1, 1.15, 1.3, 1.5];
const DEFAULT_LEVEL = 1;

function storedLevel() {
  try {
    const n = Number(localStorage.getItem("text-level"));
    return Number.isInteger(n) && n >= 0 && n < TEXT_LEVELS.length && localStorage.getItem("text-level") !== null ? n : DEFAULT_LEVEL;
  } catch { return DEFAULT_LEVEL; }
}

export function textScale() { return Number(getComputedStyle(document.documentElement).getPropertyValue("--text-scale")) || TEXT_LEVELS[DEFAULT_LEVEL]; }

function applyTextLevel(n) {
  document.documentElement.style.setProperty("--text-scale", String(TEXT_LEVELS[n]));
  document.documentElement.dataset.textLevel = String(n);
  const dec = document.querySelector("#font-dec"), inc = document.querySelector("#font-inc");
  if (dec) dec.disabled = n <= 0;
  if (inc) inc.disabled = n >= TEXT_LEVELS.length - 1;
  document.dispatchEvent(new CustomEvent("textscalechange"));
}

applyTextLevel(storedLevel());      // sedini mungkin, sebelum render pertama

function initTextSize() {
  const dec = $("#font-dec"), inc = $("#font-inc");
  if (!dec || !inc) return;
  const step = (d) => {
    const n = Math.min(TEXT_LEVELS.length - 1, Math.max(0, Number(document.documentElement.dataset.textLevel) + d));
    try { localStorage.setItem("text-level", String(n)); } catch { /* abaikan */ }
    applyTextLevel(n);
  };
  dec.addEventListener("click", () => step(-1));
  inc.addEventListener("click", () => step(1));
  applyTextLevel(storedLevel());    // sinkronkan keadaan tombol setelah DOM siap
}

// Menu hamburger (layar sempit): buka/tutup dengan tombol, Escape, atau klik di luar menu.
function initNav() {
  const btn = $("#nav-toggle"), bar = $(".topbar");
  if (!btn || !bar) return;
  const set = (open) => {
    bar.classList.toggle("nav-open", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.setAttribute("aria-label", open ? "Tutup menu navigasi" : "Buka menu navigasi");
  };
  btn.addEventListener("click", () => set(btn.getAttribute("aria-expanded") !== "true"));
  // Bila tautan tidak muat sebaris (teks diperbesar / layar sedang), beralih ke hamburger; kembali bila sudah muat.
  const fit = () => {
    bar.classList.remove("compact");
    if (!matchMedia("(max-width: 760px)").matches && bar.scrollWidth > bar.clientWidth + 1) bar.classList.add("compact");
    if (!bar.classList.contains("compact") && !matchMedia("(max-width: 760px)").matches) set(false);
  };
  fit();
  addEventListener("resize", fit);
  document.addEventListener("textscalechange", fit);
  document.fonts?.ready.then(fit);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && btn.getAttribute("aria-expanded") === "true") { set(false); btn.focus(); }
  });
  document.addEventListener("click", (e) => {
    if (btn.getAttribute("aria-expanded") === "true" && !bar.contains(e.target)) set(false);
  });
}

export function initTheme() {
  initNav();
  initTextSize();
  let t = "dark";
  try { t = localStorage.getItem("theme") || "dark"; } catch { /* penyimpanan diblokir: abaikan */ }
  document.documentElement.dataset.theme = t;
  const btn = $("#theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* abaikan */ }
    document.dispatchEvent(new CustomEvent("themechange"));
  });
}

// Interval kepercayaan Wilson 95% untuk proporsi k dari n (dalam persen). Dipakai pada ringkasan riwayat prediksi.
export function wilson(k, n, z = 1.96) {
  if (!n) return [0, 100];
  const p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h) * 100, Math.min(1, c + h) * 100];
}
