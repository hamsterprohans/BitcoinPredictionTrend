import * as THREE from "../vendor/three.module.min.js";
import { cssVar } from "./common.js";

// aKind: 0 = simbol ₿, 3 = debu emas yang melayang pelan (kedalaman). Warna bergradasi emas dalam (bawah) ke emas terang (atas); satu keluarga warna.
const VERT = `
uniform float uT, uTime, uPx, uCy, uSweep;
uniform vec2 uPtr;
uniform vec3 uDeep, uLight;
attribute vec3 aStart;
attribute float aSeed, aKind;
varying float vA;
varying vec3 vCol;
mat3 rotY(float a) { float c = cos(a), s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a), s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }
void main() {
  float e = 1.0 - pow(1.0 - clamp(uT * (0.7 + aSeed * 0.3), 0.0, 1.0), 3.0);   // easing keluar: partikel berkumpul membentuk simbol
  vec3 p = mix(aStart, position, e);
  vec3 c0 = vec3(0.0, uCy, 0.0);
  float dust = step(2.5, aKind);
  if (dust > 0.5) {                                                           // debu: naik pelan, memudar di tepi atas dan bawah
    float y = mod(position.y - uCy + uTime * (0.10 + aSeed * 0.14) + 6.0, 12.0) - 6.0;
    p = vec3(position.x, uCy + y, position.z);
  }
  p = c0 + rotY(sin(uTime * 0.6) * 0.22 + uPtr.x * 0.35) * rotX(uPtr.y * 0.2) * (p - c0);   // ayunan lembut + parallax pointer
  float h = smoothstep(uCy - 2.0, uCy + 2.0, p.y);
  vec3 base = mix(uDeep, uLight, h);
  float sweep = exp(-pow((p.y - uSweep) / 0.38, 2.0)) * step(0.0, uSweep - (uCy - 3.0)) * e * (1.0 - dust);   // sapuan cahaya menyorot simbol
  vCol = base * (dust > 0.5 ? 0.85 : 1.0) + uLight * sweep * 0.9;
  vA = (0.25 + 0.75 * e) * (dust > 0.5 ? 0.45 * (1.0 - smoothstep(3.5, 6.0, abs(p.y - uCy))) : 1.0);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = (dust > 0.5 ? 0.9 + aSeed * 1.1 : 1.15 + aSeed * 1.5) * (26.0 / -mv.z) * uPx;
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = `
varying float vA;
varying vec3 vCol;
void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  gl_FragColor = vec4(vCol, smoothstep(0.5, 0.05, d) * vA);
}`;

export const CENTER_Y = 1.7;   // pusat simbol dan cincin pada sumbu y (dunia 3D)

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
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (data[(y * W + x) * 4 + 3] > 128) px.push([x, y]);
  for (let i = px.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [px[i], px[j]] = [px[j], px[i]]; }
  const scale = height / (cap + 2 * bh), cx = W / 2, cy = base - cap / 2;
  return px.slice(0, maxPts).map(([x, y]) => [(x - cx) * scale, -(y - cy) * scale + CENTER_Y]);
}

export async function createBitcoinMark(canvas, { reduced = false } = {}) {
  const sym = await sampleBitcoin(14000);
  const extent = Math.max(...sym.map(([x, y]) => Math.hypot(x, y - CENTER_Y)));          // jari-jari simbol, untuk pembingkaian kamera
  const dust = Array.from({ length: 900 }, () => [(Math.random() - 0.5) * 20, CENTER_Y + (Math.random() - 0.5) * 12, (Math.random() - 0.5) * 8 - 1]);
  const pts = [...sym.map(([x, y]) => [x, y, (Math.random() - 0.5) * 0.18, 0]), ...dust.map(([x, y, z]) => [x, y, z, 3])];
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, CENTER_Y - 1.5, 11);
  camera.lookAt(0, CENTER_Y - 1.5, 0);

  const N = pts.length;
  const pos = new Float32Array(N * 3), start = new Float32Array(N * 3), seed = new Float32Array(N), kind = new Float32Array(N);
  pts.forEach(([x, y, z, k], i) => {
    pos.set([x, y, z], i * 3);
    start.set([(Math.random() - 0.5) * 28, (Math.random() - 0.5) * 16, (Math.random() - 0.5) * 20], i * 3);
    seed[i] = Math.random();
    kind[i] = k;
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aStart", new THREE.BufferAttribute(start, 3));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  geo.setAttribute("aKind", new THREE.BufferAttribute(kind, 1));
  const light = document.documentElement.dataset.theme === "light";
  const gold = new THREE.Color(cssVar("--gold")), deep = new THREE.Color(cssVar("--gold-dim"));
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uT: { value: reduced ? 1 : 0 }, uTime: { value: 0 }, uPx: { value: dpr }, uCy: { value: CENTER_Y }, uSweep: { value: -10 },
      uPtr: { value: new THREE.Vector2() },
      uDeep: { value: deep }, uLight: { value: light ? gold : gold.clone().lerp(new THREE.Color("#ffffff"), 0.35) },
    },
    vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false,
    blending: light ? THREE.NormalBlending : THREE.AdditiveBlending,       // di latar terang, tambahan cahaya tidak terlihat
  });
  const points = new THREE.Points(geo, mat);
  scene.add(points);

  function resize() {
    const w = canvas.clientWidth || window.innerWidth, h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const tanH = Math.tan(THREE.MathUtils.degToRad(22.5));
    // layar sempit: mundurkan kamera agar simbol termuat; layar lebar: simbol bergeser ke kanan (teks di kiri)
    const fit = (extent * 2 + 1.2) / (2 * tanH * camera.aspect);
    const wide = w >= 900;
    camera.position.z = wide ? Math.max(9, fit) : Math.max(13, fit);          // desktop: simbol besar; ponsel: lebih kecil agar tidak menabrak judul
    camera.position.y = wide ? CENTER_Y : CENTER_Y - 2.6;                    // desktop: sejajar tengah teks; ponsel: simbol naik, teks di bawah
    camera.lookAt(0, camera.position.y, 0);
    points.position.x = wide ? 0.44 * tanH * camera.position.z * camera.aspect : 0;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
  const onMove = (e) => { ptr.tx = (e.clientX / window.innerWidth - 0.5) * 2; ptr.ty = (e.clientY / window.innerHeight - 0.5) * 2; };
  let raf = 0;
  const t0 = performance.now();
  function loop(now) {
    raf = requestAnimationFrame(loop);
    const t = (now - t0) / 1000;
    ptr.x += (ptr.tx - ptr.x) * 0.05; ptr.y += (ptr.ty - ptr.y) * 0.05;
    mat.uniforms.uT.value = Math.min(1, t / 1.8);
    mat.uniforms.uTime.value = t;
    mat.uniforms.uPtr.value.set(ptr.x, ptr.y);
    const k = (t - 2.2) / 5.5;                                              // sapuan cahaya: sekali per 5,5 detik, mulai setelah simbol terbentuk
    mat.uniforms.uSweep.value = k < 0 ? -10 : CENTER_Y - 2.4 + (k % 1) * 4.8;
    renderer.render(scene, camera);
  }
  if (!reduced) { window.addEventListener("pointermove", onMove, { passive: true }); raf = requestAnimationFrame(loop); }

  return { dispose() { cancelAnimationFrame(raf); window.removeEventListener("pointermove", onMove); ro.disconnect(); geo.dispose(); mat.dispose(); renderer.dispose(); } };
}
