// Banner himbauan: di layar sempit teks berjalan satu baris. Ketuk banner untuk menjeda atau melanjutkan (juga berhenti saat ditahan atau disorot).
const bar = document.querySelector(".notice-bar");
if (bar) {
  bar.tabIndex = 0;
  bar.setAttribute("title", "Ketuk untuk menjeda atau melanjutkan teks berjalan");
  const toggle = () => bar.classList.toggle("paused");
  bar.addEventListener("click", toggle);
  bar.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
}
