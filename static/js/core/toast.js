window.CCToast = (function(){
  const stack = document.getElementById("toasts");
  function show({title,body,type="info",undo}){
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `<div><div class="title">${title||""}</div><div>${body||""}</div></div>
      <div class="actions">
        ${undo?'<button class="btn btn-ghost btn-sm">Undo</button>':''}
        <button class="btn btn-ghost btn-sm" aria-label="Close">✕</button>
      </div>`;
    stack.appendChild(el);
    const [undoBtn, closeBtn] = el.querySelectorAll(".actions button");
    if (undo && undoBtn) undoBtn.onclick = () => { try{undo();}catch(_){ } el.remove(); };
    closeBtn.onclick = () => el.remove();
    setTimeout(()=> el.remove(), 5000);
  }
  return { show };
})();
