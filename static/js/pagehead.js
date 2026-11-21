// Kepala halaman isi: judul di atas bentangan partikel 3D yang tenang (bingkai banner, tanpa data).
// Dimatikan bila WebGL tidak ada atau gerak dikurangi; bila lambat, hanya kanvas ini yang dilepas.
import { hasWebGL, reducedMotion } from "./common.js";

const h1 = document.querySelector("main h1");
if (h1 && hasWebGL() && !reducedMotion) {
  const head = document.createElement("div");
  head.className = "page-head";
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  h1.before(head);
  head.append(canvas);
  const body = document.createElement("div");
  body.className = "page-head-body";
  head.append(body);
  body.append(h1);
  if (head.nextElementSibling?.matches("p.muted")) body.append(head.nextElementSibling);
  import("./scene.js").then(({ createHero }) => {
    const mobile = matchMedia("(max-width: 700px)").matches;
    const hero = createHero(canvas, { banner: true, mobile, onSlow: () => canvas.remove() });
    hero.setState({ prob: 0.5, threshold: 0.5, direction: "NAIK", sentiment: 0 });
  }).catch((e) => { console.warn("Kepala 3D dinonaktifkan:", e); canvas.remove(); });
}
