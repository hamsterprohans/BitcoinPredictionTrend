// Pencarian di glosarium: semua kata kunci harus ada (di istilah, alias, atau definisi); tanpa memperhatikan huruf besar-kecil dan aksen.
import { $ } from "./common.js";

const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const input = $("#gloss-search"), count = $("#gloss-count");
const items = [...document.querySelectorAll("#sec-glossary .gl")];

if (input && count && items.length) {
  const text = items.map((it) => norm(`${it.querySelector("dt").textContent} ${it.dataset.alias || ""} ${it.querySelector("dd").textContent}`));
  const groups = [...document.querySelectorAll("#sec-glossary .gloss-group")];
  const update = () => {
    const tokens = norm(input.value).split(/\s+/).filter(Boolean);
    let shown = 0;
    items.forEach((it, i) => {
      const ok = tokens.every((t) => text[i].includes(t));
      it.hidden = !ok;
      if (ok) shown++;
    });
    groups.forEach((g) => { g.hidden = !g.querySelector(".gl:not([hidden])"); });
    count.textContent = !tokens.length ? `${items.length} istilah`
      : shown ? `Menampilkan ${shown} dari ${items.length} istilah` : "Tidak ada istilah yang cocok dengan pencarian Anda.";
  };
  input.addEventListener("input", update);
  update();
}
