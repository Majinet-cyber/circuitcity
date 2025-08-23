(function(){
  const THEMES=["style-1","style-2","style-3"];
  const KEY="cc-theme", ROTATE_KEY="cc-theme-rotate", INTERVAL=10000;
  const root=document.documentElement;
  const btnPrev=document.getElementById("theme-prev");
  const btnNext=document.getElementById("theme-next");
  const btnAuto=document.getElementById("theme-toggle-rotate");
  const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let current=localStorage.getItem(KEY)||root.getAttribute("data-theme")||THEMES[0];
  let auto=JSON.parse(localStorage.getItem(ROTATE_KEY)||"false");
  function apply(t){ current=t; root.setAttribute("data-theme",t); localStorage.setItem(KEY,t);
    window.dispatchEvent(new CustomEvent("theme:changed",{detail:{theme:t}})); }
  function next(){ apply(THEMES[(THEMES.indexOf(current)+1)%THEMES.length]); }
  function prev(){ apply(THEMES[(THEMES.indexOf(current)-1+THEMES.length)%THEMES.length]); }
  apply(current);

  function setAuto(v){ auto=v; localStorage.setItem(ROTATE_KEY,JSON.stringify(v)); updateBtn(); if(v) start(); else stop(); }
  function updateBtn(){ if(btnAuto) btnAuto.textContent=`Auto: ${auto?"On":"Off"}`; }

  btnNext && btnNext.addEventListener("click",()=>setAuto(false)||next());
  btnPrev && btnPrev.addEventListener("click",()=>setAuto(false)||prev());
  btnAuto && btnAuto.addEventListener("click",()=>setAuto(!auto));
  updateBtn();

  let timer=null;
  function start(){ if(reduced||!auto) return; stop(); timer=setInterval(next,INTERVAL); }
  function stop(){ if(timer) clearInterval(timer); timer=null; }
  document.addEventListener("visibilitychange",()=>document.hidden?stop():start());
  window.addEventListener("load",start);
})();
