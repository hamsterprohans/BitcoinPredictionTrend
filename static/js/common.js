export const $ = (sel, root = document) => root.querySelector(sel);

const idNum = (d) => new Intl.NumberFormat("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
export const fmtNum = (n, d = 2) => idNum(d).format(n);
export const fmtUSD = (n) => "$" + idNum(2).format(n);
export const fmtPct = (n, d = 2) => (n > 0 ? "+" : "") + idNum(d).format(n) + "%";
export const fmtDate = (iso) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export async function getJSON(url) {
  const r = await fetch(url);
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

export function initTheme() {
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
