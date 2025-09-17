(() => {
  const overlay = document.getElementById("cmdk-overlay");
  const input = document.getElementById("cmdk-input");
  const list  = document.getElementById("cmdk-list");
  const trigger = document.getElementById("open-cmdk");
  if (!overlay || !input || !list) return;

  const actions = [
    {label:"Scan In", hint:"Inventory",   run:()=>location.href="{% url 'inventory:scan_in' %}"},
    {label:"Issue Payout", hint:"Wallet", run:()=>location.href="{% url 'wallet:admin_issue' %}"},
    {label:"Agents", hint:"People",       run:()=>location.href="{% url 'accounts:agents' %}"},
    {label:"Low Stock", hint:"Saved view",run:()=>location.href="{% url 'inventory:stock_list' %}?view=low"},
  ];

  function render(q=""){
    const r = q ? actions.filter(a => (a.label+a.hint).toLowerCase().includes(q.toLowerCase())) : actions;
    list.innerHTML = r.map((a,i)=>`
      <div class="cmdk-item" data-i="${i}" role="button" tabindex="0">
        <div class="label"><strong>${a.label}</strong><span class="cmdk-item__hint">${a.hint}</span></div>
        <div class="cmdk-kbd">↵</div>
      </div>`).join("") || `<div class="cmdk-item">No results</div>`;
    list.querySelectorAll(".cmdk-item").forEach(el=>{
      el.onclick = () => r[+el.dataset.i]?.run();
      el.onkeydown = (e)=>{ if(e.key==="Enter") r[+el.dataset.i]?.run(); };
    });
  }

  const open = () => { overlay.classList.remove("hidden"); input.value=""; render(); input.focus(); };
  const close= () => overlay.classList.add("hidden");

  trigger?.addEventListener("click", open);
  document.addEventListener("keydown", e=>{
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==="k"){ e.preventDefault(); open(); }
    if (e.key==="Escape") close();
  });
  overlay.addEventListener("click", e=>{ if(e.target===overlay) close(); });
  input.addEventListener("input", e=> render(e.target.value));
})();
