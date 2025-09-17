// Fast-tap (modern browsers already do 300ms removal, but ensure no dbl-delay)
document.addEventListener('touchstart', () => {}, {passive:true});

// Soft haptics helper
export function buzz(ms=10){ if (navigator.vibrate) navigator.vibrate(ms); }

// Swipe back (left-edge swipe → history.back)
(function edgeSwipeBack(){
  let startX=null, startY=null;
  window.addEventListener('touchstart',(e)=>{
    const t=e.touches[0];
    if (t.clientX < 18){ startX=t.clientX; startY=t.clientY; }
  },{passive:true});
  window.addEventListener('touchend',(e)=>{
    if(startX===null) return;
    const t=e.changedTouches[0];
    const dx=t.clientX - startX, dy=Math.abs(t.clientY - startY);
    if(dx>60 && dy<40){ history.back(); buzz(8); }
    startX=null; startY=null;
  },{passive:true});
})();

// Pull-to-refresh nudger (visual only; no hijack)
(function pullToRefreshNudge(){
  let y0=0, pulled=false;
  document.addEventListener('touchstart',(e)=>{ y0=e.touches[0].clientY; pulled=false; },{passive:true});
  document.addEventListener('touchmove',(e)=>{
    if (window.scrollY===0){
      const dy=e.touches[0].clientY - y0;
      if(dy>40 && !pulled){ pulled=true; document.body.classList.add('ptr-hint'); setTimeout(()=>document.body.classList.remove('ptr-hint'),700); }
    }
  },{passive:true});
})();

// Auto-focus first input on small screens where safe
(function autoFocusFirst(){
  const el = document.querySelector('[data-autofocus="1"]');
  if(el && window.innerWidth < 600){ setTimeout(()=>el.focus?.(), 150); }
})();
