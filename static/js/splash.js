import { $, fmtDateShort, fmtNum, fmtUSD, getJSON, hasWebGL, reducedMotion } from "./common.js";

/** Ringkasan hari ini dari data yang sama dengan dashboard (tanpa angka karangan); bila gagal dimuat, bagian ini tetap tersembunyi. */
async function loadBrief() {
  const box = $("#splash-brief");
  if (!box) return;
  try {
    const d = await getJSON("/api/prediction/latest");
    const h = d.horizons?.["1"];
    if (!h || d.close == null) return;
    $("#brief-close-l").textContent = `Penutupan ${fmtDateShort(d.as_of)}`;
    $("#brief-close").textContent = fmtUSD(d.close);
    const dir = $("#brief-dir");
    dir.textContent = `${h.direction === "NAIK" ? "▲" : "▼"} ${h.direction}`;
    dir.className = "mono " + (h.direction === "NAIK" ? "up" : "down");
    $("#brief-prob").textContent = `${fmtNum(h.prob * 100, 1)}%`;
    box.hidden = false;
  } catch { /* tanpa ringkasan: splash tetap utuh */ }
}

/** Splash sekali per sesi. Menunggu konfirmasi pengguna (tombol, Enter, atau Esc); data dimuat di belakangnya. */
export function initSplash() {
  const el = $("#splash");
  if (!el) return;
  if (document.documentElement.classList.contains("no-splash")) { el.hidden = true; return; }

  let done = false, scene = null;
  document.body.style.overflow = "hidden";
  $("#splash-enter")?.focus({ preventScroll: true });

  function finish() {
    if (done) return;
    done = true;
    try { sessionStorage.setItem("splash-seen", "1"); } catch { /* abaikan */ }
    el.classList.add("leaving");
    setTimeout(() => {
      el.hidden = true;
      document.body.style.overflow = "";
      scene?.dispose();
      $("main")?.focus({ preventScroll: true });
    }, reducedMotion ? 0 : 450);
  }

  loadBrief();
  $("#splash-enter")?.addEventListener("click", finish);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" || e.key === "Enter") finish(); });

  if (hasWebGL()) {
    import("./splash-scene.js")
      .then((m) => m.createBitcoinMark($("#splash-canvas"), { reduced: reducedMotion }))
      .then((s) => { if (done) s.dispose(); else { scene = s; el.dataset.mark = "bitcoin"; } })
      .catch((e) => { console.warn("Splash 3D dinonaktifkan:", e); document.body.classList.add("no-webgl"); });
  }
}
