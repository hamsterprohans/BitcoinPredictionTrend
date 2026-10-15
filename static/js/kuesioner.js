import { $, initTheme } from "./common.js";
import { SURVEY } from "./kuesioner-schema.js";

const DONE_KEY = `kuesioner-done-v${SURVEY.version}`;
const CLIENT_KEY = "kuesioner-client-id";
const LABEL = { ya: "Ya", netral: "Netral", tidak: "Tidak" };
const OPTIONS = { yn: ["ya", "tidak"], ynn: ["ya", "netral", "tidak"] };
const LIMIT = { short: 200, long: 2000 };

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* penyimpanan diblokir: abaikan */ } },
};
const cfg = () => window.__APP_CONFIG__ || {};
const configured = () => !!(cfg().supabaseUrl && cfg().supabaseAnonKey);

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v; else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  e.append(...kids);
  return e;
}

function renderQuestion(q) {
  const wrap = el("fieldset", { class: "q", "data-qid": q.id });
  if (q.showIf) wrap.hidden = true;
  wrap.append(el("legend", { text: q.text }));
  if (OPTIONS[q.type]) {
    const row = el("div", { class: "choices", role: "radiogroup", "aria-label": q.text });
    for (const v of OPTIONS[q.type]) {
      const input = el("input", { type: "radio", name: q.id, value: v });
      row.append(el("label", { class: "choice" }, input, el("span", { text: LABEL[v] })));
    }
    wrap.append(row);
  } else if (q.type === "short") {
    wrap.append(el("input", { type: "text", name: q.id, maxlength: LIMIT.short, autocomplete: "off", "aria-label": q.text }));
  } else {
    wrap.append(el("textarea", { name: q.id, rows: 4, maxlength: LIMIT.long, "aria-label": q.text }));
  }
  wrap.append(el("p", { class: "q-err", hidden: true, text: "Pertanyaan ini belum dijawab." }));
  return wrap;
}

function render(root) {
  const form = el("form", { id: "survey", novalidate: true });
  for (const s of SURVEY.sections) {
    const sec = el("section", { class: "card survey-section", "aria-labelledby": `h-${s.id}` },
      el("h2", { id: `h-${s.id}`, text: s.title }));
    if (s.intro) sec.append(el("p", { class: "muted", text: s.intro }));
    for (const q of s.questions) sec.append(renderQuestion(q));
    form.append(sec);
  }
  form.append(el("div", { class: "hp", "aria-hidden": "true" },                 // honeypot: manusia tidak melihatnya
    el("label", {}, "Jangan diisi", el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" }))));
  form.append(
    el("p", { id: "survey-error", class: "survey-error", role: "alert", hidden: true }),
    el("p", { id: "survey-status", class: "muted", role: "status" }),
    el("button", { id: "survey-submit", class: "btn-link", type: "submit", text: "Kirim jawaban" }),
    el("p", { class: "muted small", text: "Jawaban disimpan tanpa nama. Isi email hanya bila bersedia diwawancara. Data dipakai untuk pengembangan tugas akhir ini saja." }));
  root.replaceChildren(form);
  return form;
}

const val = (form, q) => {
  if (OPTIONS[q.type]) return form.querySelector(`[name='${q.id}']:checked`)?.value ?? null;
  return form.querySelector(`[name='${q.id}']`).value.trim() || null;
};
const visible = (form, q) => !q.showIf || val(form, SURVEY.sections.flatMap((s) => s.questions).find((x) => x.id === q.showIf.id)) === q.showIf.equals;

function applyConditions(form) {
  for (const q of SURVEY.sections.flatMap((s) => s.questions)) {
    if (q.showIf) form.querySelector(`[data-qid='${q.id}']`).hidden = !visible(form, q);
  }
}

function collect(form) {
  const answers = {}, missing = [];
  for (const q of SURVEY.sections.flatMap((s) => s.questions)) {
    if (!visible(form, q)) continue;
    const v = val(form, q);
    if (v == null) { if (OPTIONS[q.type]) missing.push(q); continue; }
    answers[q.id] = v;
  }
  return { answers, missing };
}

function clientId() {
  let id = store.get(CLIENT_KEY);
  if (!id) { id = crypto.randomUUID(); store.set(CLIENT_KEY, id); }
  return id;
}

async function send(answers) {
  const { supabaseUrl, supabaseAnonKey } = cfg();
  const r = await fetch(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/feedback_responses`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: supabaseAnonKey, Authorization: `Bearer ${supabaseAnonKey}`, Prefer: "return=minimal" },
    body: JSON.stringify({ survey_version: SURVEY.version, client_id: clientId(), answers }),
  });
  if (r.status === 409) return;                       // client_id sudah tercatat: jawaban sebelumnya sudah masuk
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
}

function thanks(root) {
  root.replaceChildren(el("section", { id: "survey-thanks", class: "card", role: "status" },
    el("h2", { text: "Terima kasih!" }),
    el("p", { text: "Jawaban Anda sudah tercatat dan akan dipakai untuk meningkatkan situs ini. Anda hanya perlu mengisi sekali." })));
}

function main() {
  initTheme();
  const root = $("#survey-root");
  if (store.get(DONE_KEY)) return thanks(root);
  const form = render(root);
  const submit = $("#survey-submit"), err = $("#survey-error");
  if (!configured()) {
    submit.disabled = true;
    $("#survey-status").textContent = "Kuesioner belum dikonfigurasi: penyimpanan jawaban (Supabase) belum diatur oleh pengelola situs.";
  }
  form.addEventListener("change", () => applyConditions(form));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!configured()) return;
    form.querySelectorAll(".q-err").forEach((p) => { p.hidden = true; });
    form.querySelectorAll("[aria-invalid]").forEach((n) => n.removeAttribute("aria-invalid"));
    const { answers, missing } = collect(form);
    if (missing.length) {
      err.hidden = false;
      err.textContent = `${missing.length} pertanyaan belum dijawab. Lengkapi pertanyaan yang ditandai.`;
      for (const q of missing) {
        const f = form.querySelector(`[data-qid='${q.id}']`);
        f.querySelector(".q-err").hidden = false;
        f.querySelectorAll("input").forEach((n) => n.setAttribute("aria-invalid", "true"));
      }
      form.querySelector(`[data-qid='${missing[0].id}'] input`).focus();
      return;
    }
    err.hidden = true;
    if (form.querySelector("[name=website]").value) {   // bot: tampak berhasil, tidak ada yang dikirim
      return thanks(root);
    }
    submit.disabled = true;
    try {
      await send(answers);
      store.set(DONE_KEY, "1");
      thanks(root);
    } catch {
      err.hidden = false;
      err.textContent = "Pengiriman gagal. Jawaban Anda masih tersimpan di halaman ini; coba kirim lagi sebentar lagi.";
      submit.disabled = false;
    }
  });
}

main();
