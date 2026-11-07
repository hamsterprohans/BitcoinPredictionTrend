import { $, hasWebGL, reducedMotion } from "./common.js";

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

  $("#splash-enter")?.addEventListener("click", finish);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" || e.key === "Enter") finish(); });

  if (hasWebGL()) {
    import("./splash-scene.js")
      .then((m) => m.createBitcoinMark($("#splash-canvas"), { reduced: reducedMotion }))
      .then((s) => { if (done) s.dispose(); else { scene = s; el.dataset.mark = "bitcoin"; if (s.ring) el.dataset.ring = "1"; } })
      .catch((e) => { console.warn("Splash 3D dinonaktifkan:", e); document.body.classList.add("no-webgl"); });
  }
}
