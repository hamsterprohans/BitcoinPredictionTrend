// Penghitung kunjungan anonim (hanya waktu dan jalur halaman) dan panel ringkasan tersembunyi untuk pemilik situs.
// Panel muncul bila teks pertama di footer diketuk 5 kali dalam 3 detik, lalu meminta kunci pemilik; kunci diperiksa di database
// (fungsi visit_stats), bukan di peramban. Peramban pemilik tidak ikut dihitung.
const SEEN = "visit-counted";          // sessionStorage: satu kunjungan per sesi peramban
const OWNER = "owner-visit";           // localStorage: peramban pemilik
const KEY = "owner-visit-key";         // sessionStorage: kunci selama sesi
const TAPS = 5, TAP_WINDOW = 3000, DAYS = 30;

const mk = (area) => ({
  get(k) { try { return window[area].getItem(k); } catch { return null; } },
  set(k, v) { try { window[area].setItem(k, v); } catch { /* penyimpanan diblokir: abaikan */ } },
  del(k) { try { window[area].removeItem(k); } catch { /* abaikan */ } },
});
const local = mk("localStorage"), session = mk("sessionStorage");
const cfg = () => window.__APP_CONFIG__ || {};
const configured = () => !!(cfg().supabaseUrl && cfg().supabaseAnonKey);
const endpoint = (p) => `${cfg().supabaseUrl.replace(/\/$/, "")}/rest/v1/${p}`;
const headers = () => ({ "Content-Type": "application/json", apikey: cfg().supabaseAnonKey, Authorization: `Bearer ${cfg().supabaseAnonKey}` });

function pagePath() {
  const base = (window.__STATIC_BASE__ || "").replace(/\/$/, "");
  let p = location.pathname;
  if (base && p.startsWith(base)) p = p.slice(base.length);
  p = p.replace(/\.html$/, "").replace(/\/index$/, "/").toLowerCase() || "/";
  return /^[a-z0-9/_-]{1,60}$/.test(p) ? p : "/";
}

function countVisit() {
  if (!configured() || local.get(OWNER) || session.get(SEEN)) return;
  session.set(SEEN, "1");
  fetch(endpoint("site_visits"), { method: "POST", headers: { ...headers(), Prefer: "return=minimal" }, body: JSON.stringify({ path: pagePath() }), keepalive: true })
    .catch(() => { /* penghitung tidak boleh mengganggu halaman */ });
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v; else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  e.append(...kids);
  return e;
}

const nf = new Intl.NumberFormat("id-ID");
const jakartaDay = (t) => new Date(t + 7 * 3600e3).toISOString().slice(0, 10);

function chart(days) {
  const byDay = new Map(days.map((d) => [d.d, Number(d.n)]));
  const slots = Array.from({ length: DAYS }, (_, i) => jakartaDay(Date.now() - (DAYS - 1 - i) * 864e5));
  const vals = slots.map((s) => byDay.get(s) || 0);
  const max = Math.max(1, ...vals), W = 300, H = 56, bw = W / DAYS;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Kunjungan ${DAYS} hari terakhir, tertinggi ${max} per hari`);
  svg.classList.add("owner-bars");
  vals.forEach((v, i) => {
    const h = Math.max(1, Math.round((v / max) * (H - 2)));
    const r = document.createElementNS(ns, "rect");
    for (const [k, x] of Object.entries({ x: i * bw + 0.5, y: H - h, width: bw - 1, height: h })) r.setAttribute(k, x);
    const t = document.createElementNS(ns, "title");
    t.textContent = `${slots[i]}: ${v}`;
    r.append(t);
    svg.append(r);
  });
  return svg;
}

async function fetchStats(key) {
  const r = await fetch(endpoint("rpc/visit_stats"), { method: "POST", headers: headers(), body: JSON.stringify({ p_key: key }) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function closePanel() {
  document.querySelector("[data-owner-panel]")?.remove();
  document.removeEventListener("keydown", onKey);
}
function onKey(e) { if (e.key === "Escape") closePanel(); }

function showStats(panel, s) {
  const stat = (label, v) => el("div", {}, el("strong", { text: nf.format(v) }), el("span", { text: label }));
  panel.replaceChildren(
    el("div", { class: "owner-stats" }, stat("total dibuka", s.total), stat("hari ini", s.today), stat("7 hari", s.week)),
    chart(s.days || []),
    el("ul", { class: "owner-pages" }, ...(s.pages || []).map((p) => el("li", {}, el("span", { text: p.path }), el("span", { text: nf.format(p.n) })))),
    el("button", { type: "button", "data-logout": "", text: "Keluar" }));
  panel.querySelector("[data-logout]").addEventListener("click", () => { session.del(KEY); closePanel(); });
}

async function unlock(panel, key) {
  const s = await fetchStats(key);
  session.set(KEY, key);
  local.set(OWNER, "1");                                   // peramban ini tidak dihitung lagi
  showStats(panel, s);
}

function openPanel() {
  if (document.querySelector("[data-owner-panel]") || !configured()) return;
  const panel = el("div", { class: "owner-panel", role: "dialog", "aria-modal": "false", "aria-label": "Ringkasan pemilik", "data-owner-panel": "" });
  document.body.append(panel);
  document.addEventListener("keydown", onKey);
  const saved = session.get(KEY);
  if (saved) unlock(panel, saved).catch(() => { session.del(KEY); askKey(panel); });
  else askKey(panel);
}

function askKey(panel) {
  const input = el("input", { type: "password", autocomplete: "off", "aria-label": "Kunci pemilik" });
  const err = el("p", { role: "alert", hidden: true, text: "Ditolak." });
  const form = el("form", {}, input, el("button", { type: "submit", text: "Buka" }), err);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    err.hidden = true;
    try { await unlock(panel, input.value); } catch { err.hidden = false; input.select(); }
  });
  panel.replaceChildren(form);
  input.focus();
}

function armSecret() {
  const target = document.querySelector(".footer p");
  if (!target) return;
  let n = 0, first = 0;
  target.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const now = Date.now();
    if (!n || now - first > TAP_WINDOW) { n = 0; first = now; }
    if (++n >= TAPS) { n = 0; openPanel(); }
  });
}

countVisit();
armSecret();
