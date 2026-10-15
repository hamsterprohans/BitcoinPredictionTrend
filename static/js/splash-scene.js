import * as THREE from "three";
import { cssVar } from "./common.js";

const VERT = `
uniform float uT, uTime, uPx;
attribute vec3 aStart;
attribute float aSeed;
varying float vA;
void main() {
  float e = 1.0 - pow(1.0 - clamp(uT * (0.75 + aSeed * 0.25), 0.0, 1.0), 3.0);   // easing keluar
  vec3 p = mix(aStart, position, e);
  float a = uTime * 0.35 * e;
  p = vec3(p.x * cos(a) + p.z * sin(a), p.y, -p.x * sin(a) + p.z * cos(a));
  vA = 0.35 + 0.65 * e;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = (2.0 + aSeed * 2.0) * (26.0 / -mv.z) * uPx;
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

export function createRing(canvas, { reduced = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: "low-power" });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(dpr);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0.6, 11);
  camera.lookAt(0, 0, 0);

  const N = 5000, R = 3.2;
  const pos = new Float32Array(N * 3), start = new Float32Array(N * 3), seed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const th = Math.random() * Math.PI * 2, r = R + (Math.random() - 0.5) * 0.35, k = i % 2 ? 1 : 0.62;   // dua cincin
    pos.set([Math.cos(th) * r * k, Math.sin(th) * r * k, (Math.random() - 0.5) * 0.5], i * 3);
    start.set([(Math.random() - 0.5) * 28, (Math.random() - 0.5) * 16, (Math.random() - 0.5) * 20], i * 3);
    seed[i] = Math.random();
  }
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
    mat.uniforms.uT.value = Math.min(1, t / 1.6);
    mat.uniforms.uTime.value = t;
    renderer.render(scene, camera);
  }
  if (!reduced) raf = requestAnimationFrame(loop);

  return { dispose() { cancelAnimationFrame(raf); ro.disconnect(); geo.dispose(); mat.dispose(); renderer.dispose(); } };
}
