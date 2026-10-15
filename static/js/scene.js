import * as THREE from "three";
import { cssVar } from "./common.js";

const VERT = `
uniform float uTime, uAmp, uDir, uSpeed, uPx;
attribute float aSeed;
varying float vH;
void main() {
  vec3 p = position;
  float flow = uTime * uSpeed;
  float w = sin(p.x * 0.35 + flow + p.z * 0.2) * 0.6 + sin(p.z * 0.5 - flow * 0.7) * 0.4;
  p.y += w * uAmp + uDir * p.x * 0.12;
  vH = w;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = (1.6 + aSeed * 1.6) * (38.0 / -mv.z) * uPx;
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = `
uniform vec3 uBase, uTint;
uniform float uTintAmt, uGlow;
varying float vH;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = length(c);
  if (d > 0.5) discard;
  float a = smoothstep(0.5, 0.0, d) * (0.3 + 0.7 * uGlow);
  vec3 col = mix(uBase, uTint, uTintAmt) * (0.65 + 0.7 * (vH * 0.5 + 0.5));
  gl_FragColor = vec4(col, a);
}`;

export function createHero(canvas, { reduced = false, mobile = false, onSlow = () => {} } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  const dpr = Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2);
  renderer.setPixelRatio(dpr);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 5, 14);
  camera.lookAt(0, 0, 0);

  const N = mobile ? 64 : 128;
  const pos = new Float32Array(N * N * 3), seed = new Float32Array(N * N);
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
    const k = i * N + j;
    pos.set([(i / (N - 1) - 0.5) * 40, 0, (j / (N - 1) - 0.5) * 24], k * 3);
    seed[k] = Math.random();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 }, uAmp: { value: 0.25 }, uDir: { value: 0 }, uSpeed: { value: 0.5 }, uPx: { value: dpr },
      uBase: { value: new THREE.Color(cssVar("--gold")) }, uTint: { value: new THREE.Color(cssVar("--gold")) },
      uTintAmt: { value: 0 }, uGlow: { value: 0.35 },
    },
    vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  scene.add(new THREE.Points(geo, mat));

  const target = { amp: 0.25, dir: 0, glow: 0.35, tint: 0, tintColor: new THREE.Color(cssVar("--gold")) };
  const u = mat.uniforms;
  const pointer = { x: 0 };

  function setState({ prob, threshold, direction, sentiment }) {
    const conf = Math.min(1, Math.abs(prob - threshold) * 4);   // 0 di ambang keputusan -> adegan tenang dan netral
    target.amp = 0.25 + 0.9 * conf;
    target.dir = (direction === "NAIK" ? 1 : -1) * conf * 0.5;
    target.glow = 0.35 + 0.65 * conf;
    const s = Math.max(-1, Math.min(1, (sentiment || 0) / 10));
    target.tint = Math.abs(s) * 0.6;
    target.tintColor.set(cssVar(s >= 0 ? "--up" : "--down"));
    u.uBase.value.set(cssVar("--gold"));
    if (reduced) renderOnce();
  }

  function resize() {
    const w = canvas.clientWidth || window.innerWidth, h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    if (reduced) renderOnce();
  }
  const lerp = (a, b, t) => a + (b - a) * t;
  function applyTargets(k) {
    u.uAmp.value = lerp(u.uAmp.value, target.amp, k);
    u.uDir.value = lerp(u.uDir.value, target.dir, k);
    u.uGlow.value = lerp(u.uGlow.value, target.glow, k);
    u.uTintAmt.value = lerp(u.uTintAmt.value, target.tint, k);
    u.uTint.value.lerp(target.tintColor, k);
  }

  function renderOnce() {
    applyTargets(1);
    renderer.render(scene, camera);
  }

  // resize() memanggil renderOnce() (mode reduced): harus setelah lerp/applyTargets/renderOnce terdefinisi.
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  let raf = 0, last = performance.now(), visible = true, frames = 0, ema = 16, stage = 0;
  function loop(now) {
    raf = requestAnimationFrame(loop);
    if (document.hidden || !visible) { last = now; return; }
    const dt = now - last;
    last = now;
    ema = ema * 0.95 + dt * 0.05;
    u.uTime.value += dt / 1000;
    applyTargets(0.04);
    camera.position.x += (pointer.x * 1.5 - camera.position.x) * 0.03;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    if (++frames % 90 === 0 && ema > 45) {          // penjaga performa: turunkan jumlah partikel, lalu menyerah
      if (stage === 0) { geo.setDrawRange(0, (N * N) / 4); stage = 1; }
      else if (stage === 1) { cancelAnimationFrame(raf); onSlow(); }
    }
  }
  const io = new IntersectionObserver((e) => { visible = e[0].isIntersecting; });
  io.observe(canvas);
  const onMove = (e) => { pointer.x = (e.clientX / window.innerWidth - 0.5) * 2; };

  if (reduced) renderOnce();
  else { window.addEventListener("pointermove", onMove, { passive: true }); raf = requestAnimationFrame(loop); }

  return {
    setState,
    dispose() {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect();
      window.removeEventListener("pointermove", onMove);
      geo.dispose(); mat.dispose(); renderer.dispose();
    },
  };
}
