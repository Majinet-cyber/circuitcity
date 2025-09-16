// Stagger reveal + lightweight ripple on .gbtn
(function(){
  const els = Array.from(document.querySelectorAll("[data-anim]"));
  els.forEach((el, i) => {
    el.style.animationDelay = (i * 60) + "ms";
  });

  // Button ripple
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".gbtn");
    if(!btn) return;
    const r = document.createElement("span");
    r.style.position="absolute";
    r.style.inset="0";
    r.style.borderRadius="inherit";
    r.style.pointerEvents="none";
    r.style.background="radial-gradient(circle at "+(e.offsetX||0)+"px "+(e.offsetY||0)+"px, rgba(255,255,255,.35), transparent 40%)";
    r.style.opacity="0";
    r.style.transition="opacity .5s ease";
    btn.appendChild(r);
    requestAnimationFrame(()=>{ r.style.opacity=".8"; });
    setTimeout(()=>{ r.style.opacity="0"; setTimeout(()=>r.remove(), 350); }, 120);
  });
})();
