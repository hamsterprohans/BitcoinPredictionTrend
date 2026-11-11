// Glosarium dilipat: tampil sekitar satu layar lebih dulu, sisanya dibuka lewat tombol.
// Isi tetap ada di halaman (bisa dibaca pembaca layar dan dicari); terbuka otomatis saat mencari atau menuju istilah dari tautan.
const sec = document.getElementById("sec-glossary");
const groups = sec ? [...sec.querySelectorAll(":scope > .gloss-group")] : [];
if (sec && groups.length) {
  const fold = document.createElement("div");
  fold.id = "gloss-fold"; fold.className = "fold";
  groups[0].before(fold);
  fold.append(...groups);

  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "fold-btn";
  btn.setAttribute("aria-controls", "gloss-fold");
  fold.after(btn);

  const total = () => sec.querySelectorAll(".gl").length;
  const label = (open) => { btn.textContent = open ? "Ciutkan daftar istilah" : `Tampilkan semua ${total()} istilah`; btn.setAttribute("aria-expanded", String(open)); };
  const setOpen = (open) => { fold.classList.toggle("open", open); label(open); };
  setOpen(false);

  btn.addEventListener("click", () => {
    const open = !fold.classList.contains("open");
    setOpen(open);
    if (!open) sec.scrollIntoView({ block: "start" });
  });
  document.getElementById("gloss-search")?.addEventListener("input", (e) => { if (e.target.value.trim()) setOpen(true); });

  const toTarget = () => {
    const t = location.hash.startsWith("#g-") ? document.getElementById(location.hash.slice(1)) : null;
    if (t && sec.contains(t)) { setOpen(true); t.scrollIntoView({ block: "center" }); }
  };
  addEventListener("hashchange", toTarget);
  document.addEventListener("click", (e) => {            // tautan istilah yang hash-nya sama dengan sebelumnya tidak memicu hashchange
    const a = e.target.closest?.("a[href^='#g-']");
    if (a) { setOpen(true); }
  });
  toTarget();
}
