import * as THREE from "three";
import { cssVar } from "./common.js";

export function createBars(canvas, items, { reduced = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(0, 3.6, 8.2);
  camera.lookAt(0, 1.2, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(4, 8, 6);
  scene.add(key);

  const group = new THREE.Group();
  scene.add(group);
  const gap = 1.5, x0 = -((items.length - 1) * gap) / 2, SCALE = 5;   // skala dari nol: tinggi = nilai × 5
  items.forEach((it, i) => {
    const h = Math.max(0.02, it.value * SCALE);
    const m = new THREE.Mesh(new THREE.BoxGeometry(0.9, h, 0.9),
      new THREE.MeshStandardMaterial({ color: new THREE.Color(cssVar("--gold")), roughness: 0.4, metalness: 0.25 }));
    m.position.set(x0 + i * gap, h / 2, 0);
    group.add(m);
    const c = document.createElement("canvas");
    c.width = 128; c.height = 48;
    const g = c.getContext("2d");
    g.font = '600 28px "Geist Mono", monospace';
    g.fillStyle = cssVar("--text"); g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(it.label, 64, 24);
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true }));
    s.scale.set(1.2, 0.45, 1);
    s.position.set(x0 + i * gap, -0.4, 0.9);
    group.add(s);
  });

  const resize = () => {
    const w = canvas.clientWidth || 600, h = canvas.clientHeight || 240;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  };
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  let raf = 0, visible = true;
  const io = new IntersectionObserver((e) => { visible = e[0].isIntersecting; });
  io.observe(canvas);
  const loop = (t) => {
    raf = requestAnimationFrame(loop);
    if (document.hidden || !visible) return;
    group.rotation.y = Math.sin(t / 3000) * 0.35;
    renderer.render(scene, camera);
  };
  if (!reduced) raf = requestAnimationFrame(loop);
  resize();
  return { dispose() { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); renderer.dispose(); } };
}
