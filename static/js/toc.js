// Navigasi dalam halaman (daftar bagian yang menempel), penanda bagian aktif, dan kemunculan kartu saat digulir.
// Semua tautan menuju bagian yang benar-benar ada; bagian tersembunyi (mis. "Alasan" tanpa data) tidak ditautkan.
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const main = document.querySelector("main");

function sections() {
  return [...document.querySelectorAll("main section[data-toc]")];
}

// Halaman prosa (Latar Belakang, Metodologi): daftar isi dari h2, dengan id yang dibuat dari teksnya.
function proseItems() {
  const art = document.querySelector("main article.prose");
  if (!art || sections().length) return [];
  const used = new Set();
  return [...art.querySelectorAll(":scope > h2")].map((h) => {
    if (!h.id) {
      let id = "b-" + h.textContent.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      while (used.has(id) || document.getElementById(id)) id += "-2";
      h.id = id;
    }
    used.add(h.id);
    h.dataset.toc = h.textContent.replace(/\s*\(\d+\)$/, "").replace(/^(Rumusan masalah).*/, "$1").replace(/^Model dan ambang.*/, "Ambang").replace(/^Batasan.*/, "Batasan");
    return h;
  });
}

function buildToc() {
  const prose = proseItems();
  const items = prose.length ? prose : sections().filter((s) => !s.hidden);
  let nav = document.getElementById("toc");
  if (items.length < 3) { nav?.replaceChildren(); return; }
  if (!nav) {
    nav = document.createElement("nav");
    nav.id = "toc"; nav.className = "toc"; nav.setAttribute("aria-label", "Di halaman ini");
    if (prose.length) prose[0].before(nav);
    else (main.querySelector("h1")?.nextElementSibling ?? main.firstElementChild).after(nav);
  }
  const current = nav.querySelector("[aria-current]")?.getAttribute("href");
  nav.replaceChildren(...items.map((s) => {
    const a = document.createElement("a");
    a.href = "#" + s.id;
    a.textContent = s.dataset.toc;
    if (a.getAttribute("href") === current) a.setAttribute("aria-current", "true");
    return a;
  }));
  spy(items);
}

// Tautan panduan baca yang menuju bagian tersembunyi dijadikan teks biasa agar tidak ada tautan mati.
function guardGuideLinks() {
  for (const a of document.querySelectorAll(".guide a[href^='#']")) {
    const t = document.getElementById(a.getAttribute("href").slice(1));
    if (!t || t.hidden) a.removeAttribute("href");
  }
}

let spyIO = null;
function spy(items) {
  spyIO?.disconnect();
  if (!("IntersectionObserver" in window)) return;
  const links = new Map(items.map((s) => [s.id, document.querySelector(`#toc a[href="#${s.id}"]`)]));
  if (!document.querySelector("#toc")) return;
  spyIO = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      for (const l of links.values()) l?.removeAttribute("aria-current");
      links.get(e.target.id)?.setAttribute("aria-current", "true");
    }
  }, { rootMargin: "-20% 0px -65% 0px" });
  items.forEach((s) => spyIO.observe(s));
}

function reveal() {
  if (reduced || !("IntersectionObserver" in window)) return;
  const cards = [...document.querySelectorAll("main .card")].filter((c) => c.getBoundingClientRect().top > innerHeight);
  if (!cards.length) return;
  document.documentElement.classList.add("js-reveal");
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }, { rootMargin: "0px 0px -6% 0px" });
  cards.forEach((c) => { c.classList.add("reveal"); io.observe(c); });
  // Kartu yang dituju lewat tautan #bagian harus langsung terlihat.
  addEventListener("hashchange", () => document.getElementById(location.hash.slice(1))?.classList.add("in"));
}

buildToc();
{ // beri tanda saat bilah menempel di atas layar (latar baru diberi saat konten bergulir di bawahnya)
  const nav = document.getElementById("toc");
  if (nav && "IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => nav.classList.toggle("stuck", e.intersectionRatio < 1), { threshold: [1], rootMargin: "-1px 0px 0px 0px" }).observe(nav);
  }
}
guardGuideLinks();
reveal();
// Bagian "Alasan" baru tampil setelah data prediksi dimuat: bangun ulang saat atribut hidden berubah.
const mo = new MutationObserver(() => { buildToc(); guardGuideLinks(); });
sections().forEach((s) => mo.observe(s, { attributes: true, attributeFilter: ["hidden"] }));
