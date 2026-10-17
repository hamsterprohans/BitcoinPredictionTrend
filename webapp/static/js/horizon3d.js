import * as THREE from "three";
import { cssVar } from "./common.js";

function label(text, color) {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 72;
  const g = c.getContext("2d");
  g.font = '600 42px "Geist Mono", monospace';
  g.fillStyle = color; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 128, 36);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true }));
  s.scale.set(2.6, 0.74, 1);
  return s;
}

const SPAN = 11;   // lebar deretan simpul (unit dunia)

export function createHorizonScene(canvas, { onSelect = () => {}, reduced = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100);   // ortografik: bola tidak gepeng di kanvas lebar
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(3, 5, 6);
  scene.add(key);

  const group = new THREE.Group();
  scene.add(group);
  let nodes = [], selected = null, visible = true, raf = 0;

  function setHorizons(list) {
    group.clear();
    nodes = [];
    const n = list.length, span = SPAN;
    const gap = span / Math.max(1, n - 1);                      // jarak antar simpul
    const compact = n > 5;                                        // banyak horizon: label ringkas "7h", bukan "7 hari"
    const pts = list.map((_, i) => new THREE.Vector3((i / Math.max(1, n - 1) - 0.5) * span, 0, 0));
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: new THREE.Color(cssVar("--text-2")) })));
    list.forEach((it, i) => {
      const col = new THREE.Color(cssVar(it.direction === "NAIK" ? "--up" : "--down"));
      const m = new THREE.Mesh(new THREE.SphereGeometry(Math.min(0.5, gap * 0.28), 32, 32),
        new THREE.MeshStandardMaterial({ color: col, roughness: 0.35, metalness: 0.2 }));
      m.position.copy(pts[i]);
      m.userData.h = String(it.h);
      group.add(m);
      nodes.push(m);
      const l = label(compact ? `${it.h}h` : `${it.h} hari`, cssVar("--text"));
      l.scale.set(Math.min(2.6, gap * 0.95), 0.74 * Math.min(1, (gap * 0.95) / 2.6), 1);   // label tidak melebihi jarak simpul
      l.position.set(pts[i].x, -1.15, 0);
      group.add(l);
    });
    paint();
  }

  function paint() {
    nodes.forEach((m) => {
      const on = m.userData.h === selected;
      m.scale.setScalar(on ? 1.5 : 1);
      m.material.emissive.set(on ? cssVar("--gold") : "#000000");
      m.material.emissiveIntensity = on ? 0.6 : 0;
    });
    renderOnce();
  }
  function select(h) { selected = String(h); paint(); }

  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  function pick(e) {
    const r = canvas.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    return ray.intersectObjects(nodes)[0]?.object ?? null;
  }
  const onDown = (e) => { const o = pick(e); if (o) onSelect(o.userData.h); };
  const onHover = (e) => { canvas.style.cursor = pick(e) ? "pointer" : "default"; };
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointermove", onHover);

  function renderOnce() { renderer.render(scene, camera); }
  function resize() {
    const w = canvas.clientWidth || 600, h = canvas.clientHeight || 180;
    renderer.setSize(w, h, false);
    // seluruh deretan simpul harus muat (lebar) dan label tidak terpotong (tinggi)
    const halfH = Math.max(2.1, (SPAN + 2.5) / (2 * (w / h)));
    const halfW = halfH * (w / h);
    camera.left = -halfW; camera.right = halfW; camera.top = halfH; camera.bottom = -halfH;
    camera.updateProjectionMatrix();
    renderOnce();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  const io = new IntersectionObserver((e) => { visible = e[0].isIntersecting; });
  io.observe(canvas);

  function loop(t) {
    raf = requestAnimationFrame(loop);
    if (document.hidden || !visible) return;
    group.rotation.y = Math.sin(t / 2400) * 0.12;
    renderOnce();
  }
  if (!reduced) raf = requestAnimationFrame(loop);
  resize();

  return {
    setHorizons, select,
    dispose() {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect();
      canvas.removeEventListener("pointerdown", onDown); canvas.removeEventListener("pointermove", onHover);
      renderer.dispose();
    },
  };
}
