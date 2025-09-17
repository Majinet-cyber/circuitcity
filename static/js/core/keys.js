document.addEventListener("keydown", (e)=>{
  // Table navigation for any table marked with data-kb-table
  const table = document.querySelector("[data-kb-table]");
  if(!table) return;

  const rows = [...table.querySelectorAll("tbody tr")];
  let i = rows.findIndex(r => r.classList.contains("is-active"));
  const setActive = (n)=>{ rows.forEach(r=>r.classList.remove("is-active")); if(rows[n]){ rows[n].classList.add("is-active"); rows[n].scrollIntoView({block:"nearest"}); } };

  if (e.key==="ArrowDown"){ e.preventDefault(); setActive(Math.min(i+1, rows.length-1)); }
  if (e.key==="ArrowUp"){ e.preventDefault(); setActive(Math.max(i-1, 0)); }
  if (e.key==="Enter" && i>=0){ const link = rows[i].querySelector("a.row-open,[data-row-open]"); if(link) link.click(); }
  if (e.key==="a") { document.querySelector("[data-action='add']")?.click(); }
  if (e.key==="e" && i>=0){ rows[i].querySelector("[data-inline-edit]")?.click(); }
});
