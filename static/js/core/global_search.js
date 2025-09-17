(() => {
  const q = document.getElementById("global-q");
  const box = document.getElementById("global-results");
  if (!q || !box) return;

  let inFlight;
  q.addEventListener("input", async e=>{
    const v = e.target.value.trim();
    if(!v){ box.classList.add("hidden"); box.innerHTML=""; return; }
    try{
      if (inFlight) inFlight.abort();
      inFlight = new AbortController();
      const r = await fetch("{% url 'api_global_search' %}?q="+encodeURIComponent(v), {signal: inFlight.signal});
      const data = await r.json();
      box.innerHTML = `
        <div class="pad-sm vstack">
          ${data.skus.map(s=>`<div class="hstack"><span class="badge">SKU</span> <a href="/inventory/sku/${s.id}/">${s.name}</a></div>`).join("")}
          ${data.agents.map(a=>`<div class="hstack"><span class="badge neutral">Agent</span> <a href="/accounts/agent/${a.id}/">${a.full_name}</a></div>`).join("")}
        </div>`;
      box.classList.remove("hidden");
    }catch(_){}
  });

  // `/` focuses search
  document.addEventListener("keydown", e=>{
    if (e.key==="/" && document.activeElement !== q){
      e.preventDefault(); q.focus();
    }
  });

  document.addEventListener("click", e=>{
    if(!box.contains(e.target) && e.target!==q) box.classList.add("hidden");
  });
})();
