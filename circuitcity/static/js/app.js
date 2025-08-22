// Sidebar toggle for mobile
(function(){
  const toggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if(toggle && sidebar){
    const setState = (open)=>{ sidebar.classList.toggle('open', open); toggle.setAttribute('aria-expanded', String(open)); }
    toggle.addEventListener('click', ()=> setState(!sidebar.classList.contains('open')));
    // Close on Escape
    document.addEventListener('keydown', (e)=>{ if(e.key==='Escape') setState(false); });
  }
})();

// Inline validation (disable submit until valid; show hints)
(function(){
  document.querySelectorAll('form[data-validate]').forEach(form=>{
    const submitBtn = form.querySelector('button[type="submit"]');
    const validate = ()=>{
      const valid = form.checkValidity();
      if(submitBtn) submitBtn.disabled = !valid;
      form.querySelectorAll('.help-error').forEach(h=>{
        const input = h.previousElementSibling;
        if(input && !input.checkValidity()){ h.hidden = false; } else { h.hidden = true; }
      });
    };
    form.addEventListener('input', validate);
    form.addEventListener('change', validate);
    form.addEventListener('submit', (e)=>{ if(!form.checkValidity()){ e.preventDefault(); validate(); }});
    validate();
  });
})();

// Auto-hide toasts after 4s (respect reduced motion)
(function(){
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const toasts = document.querySelectorAll('.toast');
  toasts.forEach(t=>{
    if(!prefersReduced){
      setTimeout(()=>{ t.style.transition='opacity .25s'; t.style.opacity='0'; setTimeout(()=>t.remove(), 300); }, 4000);
    }
  });
})();
