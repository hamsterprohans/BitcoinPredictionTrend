import * as THREE from "three";
import { cssVar } from "./common.js";

const VERT = `
uniform float uT, uTime, uPx;
attribute vec3 aStart;
attribute float aSeed;
varying float vA;
void main() {
  float e = 1.0 - pow(1.0 - clamp(uT * (0.7 + aSeed * 0.3), 0.0, 1.0), 3.0);   // easing keluar
  vec3 p = mix(aStart, position, e);
  float a = sin(uTime * 0.7) * 0.4 * e;                                       // ayunan lembut, simbol tetap terbaca
  p = vec3(p.x * cos(a) + p.z * sin(a), p.y, -p.x * sin(a) + p.z * cos(a));
  vA = 0.3 + 0.7 * e;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = (2.2 + aSeed * 2.0) * (26.0 / -mv.z) * uPx;
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = `
uniform vec3 uColor;
varying float vA;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  gl_FragColor = vec4(uColor, smoothstep(0.5, 0.0, d) * vA);
}`;

export const CENTER_Y = 1.7;   // pusat simbol dan cincin pada sumbu y (dunia 3D)

/** Radius cincin: melingkupi seluruh titik simbol dengan sedikit ruang. */
export function ringRadiusFor(pts, cy = CENTER_Y) {
  return Math.max(...pts.map(([x, y]) => Math.hypot(x, y - cy))) * 1.16 + 0.1;
}

/** Titik-titik cincin (pita melingkar setebal `thickness`) seperti lingkaran pada logo Bitcoin. */
export function ringPoints(n, radius, thickness = 0.16, cy = CENTER_Y) {
  return Array.from({ length: n }, () => {
    const th = Math.random() * Math.PI * 2, r = radius + (Math.random() - 0.5) * thickness;
    return [Math.cos(th) * r, Math.sin(th) * r + cy];
  });
}

/** Titik-titik simbol ₿: huruf B ditambah dua garis vertikal di atas dan bawah (tidak bergantung glyph ₿ pada font). */
export async function sampleBitcoin(maxPts, height = 3.6) {
  try { await Promise.race([document.fonts.load('800 200px "Geist"'), new Promise((r) => setTimeout(r, 900))]); } catch { /* pakai font cadangan */ }
  const W = 360, H = 470, size = 300, base = 365;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  g.fillStyle = "#fff";
  g.font = `800 ${size}px Geist, system-ui, sans-serif`;
  g.textAlign = "center";
  g.textBaseline = "alphabetic";
  g.fillText("B", W / 2, base);
  const cap = size * 0.72, bw = size * 0.075, bh = size * 0.15;
  for (const x of [W / 2 - size * 0.1, W / 2 + size * 0.1]) {
    g.fillRect(x - bw / 2, base - cap - bh, bw, bh);   // garis atas
    g.fillRect(x - bw / 2, base, bw, bh);              // garis bawah
  }
  const data = g.getImageData(0, 0, W, H).data, px = [];
  for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) if (data[(y * W + x) * 4 + 3] > 128) px.push([x, y]);
  for (let i = px.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [px[i], px[j]] = [px[j], px[i]]; }
  const scale = height / (cap + 2 * bh), cx = W / 2, cy = base - cap / 2;
  return px.slice(0, maxPts).map(([x, y]) => [(x - cx) * scale, -(y - cy) * scale + CENTER_Y]);
}

export async function createBitcoinMark(canvas, { reduced = false } = {}) {
  const sym = await sampleBitcoin(7000);
  const R = ringRadiusFor(sym);
  const pts = sym.concat(ringPoints(2800, R));      // simbol + cincin
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, CENTER_Y - 0.9, 11);
  camera.lookAt(0, CENTER_Y - 0.9, 0);

  const N = pts.length;
  const pos = new Float32Array(N * 3), start = new Float32Array(N * 3), seed = new Float32Array(N);
  pts.forEach(([x, y], i) => {
    pos.set([x, y, (Math.random() - 0.5) * 0.35], i * 3);
    start.set([(Math.random() - 0.5) * 28, (Math.random() - 0.5) * 16, (Math.random() - 0.5) * 20], i * 3);
    seed[i] = Math.random();
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aStart", new THREE.BufferAttribute(start, 3));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: { uT: { value: reduced ? 1 : 0 }, uTime: { value: 0 }, uPx: { value: dpr }, uColor: { value: new THREE.Color(cssVar("--gold")) } },
    vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  scene.add(new THREE.Points(geo, mat));

  function resize() {
    const w = canvas.clientWidth || window.innerWidth, h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // layar sempit: mundurkan kamera agar cincin tidak terpotong
    camera.position.z = Math.max(11, ((R * 2 + 0.8) / (2 * Math.tan(THREE.MathUtils.degToRad(22.5)) * camera.aspect)));
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  let raf = 0;
  const t0 = performance.now();
  function loop(now) {
    raf = requestAnimationFrame(loop);
    const t = (now - t0) / 1000;
    mat.uniforms.uT.value = Math.min(1, t / 1.8);
    mat.uniforms.uTime.value = t;
    renderer.render(scene, camera);
  }
  if (!reduced) raf = requestAnimationFrame(loop);

  return { ring: true, dispose() { cancelAnimationFrame(raf); ro.disconnect(); geo.dispose(); mat.dispose(); renderer.dispose(); } };
}
