import { $, hasWebGL, reducedMotion } from "./common.js";

/** Splash sekali per sesi. Dapat dilewati (klik, Esc, Enter, tombol); data dimuat di belakangnya. */
export function initSplash() {
  const el = $("#splash");
  if (!el) return;
  if (document.documentElement.classList.contains("no-splash")) { el.hidden = true; return; }

  const webgl = hasWebGL();
  let done = false, scene = null, timer = 0;
  document.body.style.overflow = "hidden";

  function finish() {
    if (done) return;
    done = true;
    clearTimeout(timer);
    try { sessionStorage.setItem("splash-seen", "1"); } catch { /* abaikan */ }
    el.classList.add("leaving");
    setTimeout(() => {
      el.hidden = true;
      document.body.style.overflow = "";
      scene?.dispose();
      $("main")?.focus({ preventScroll: true });
    }, reducedMotion ? 0 : 450);
  }

  el.addEventListener("click", finish);
  $("#splash-enter")?.addEventListener("click", (e) => { e.stopPropagation(); finish(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" || e.key === "Enter") finish(); });
  timer = setTimeout(finish, reducedMotion || !webgl ? 1400 : 2800);

  if (webgl) {
    import("./splash-scene.js")
      .then((m) => { if (!done) scene = m.createRing($("#splash-canvas"), { reduced: reducedMotion }); })
      .catch((e) => console.warn("Splash 3D dinonaktifkan:", e));
  }
}
