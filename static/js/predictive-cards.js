(async function(){
  const box=document.getElementById("ai-recos-body");
  try{
    const res=await fetch("/api/predictions/");
    const data=await res.json();

    const total = (data.overall||[]).reduce((s,r)=>s+(r.predicted_units||0),0);
    const revenue = (data.overall||[]).reduce((s,r)=>s+(+r.predicted_revenue||0),0);

    let html = `
      <div style="margin-bottom:8px;">
        <div><b>Next 7 days forecast</b></div>
        <div>Units: <b>${total.toLocaleString()}</b> • Revenue: <b>MK ${Math.round(revenue).toLocaleString()}</b></div>
      </div>
    `;

    if ((data.risky||[]).length){
      html += `<div style="margin-top:6px;"><b>Likely Stockouts</b></div>`;
      html += `<ul style="margin:6px 0 0 18px;padding:0;">`;
      for(const r of data.risky){
        html += `<li>${r.product}: stockout by <b>${r.stockout_date}</b> • On-hand: ${r.on_hand} • Restock: <b>${r.suggested_restock}</b> ${r.urgent?'<span style="color:var(--accent)">URGENT</span>':''}</li>`;
      }
      html += `</ul>`;
    }else{
      html += `<div>All good — no stockouts predicted in the next 7 days.</div>`;
    }

    box.innerHTML = html;
  }catch(e){
    console.error(e);
    box.textContent = "Could not load predictions.";
  }
})();
