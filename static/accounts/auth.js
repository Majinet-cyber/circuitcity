/* Small enhancements: follow-cursor light on buttons + show/hide password */

(function(){
  // Cursor-reactive buttons
  const reactives = document.querySelectorAll('.cursor-react');
  reactives.forEach(btn => {
    const setPos = (e) => {
      const r = btn.getBoundingClientRect();
      const mx = ((e.clientX - r.left) / r.width) * 100;
      const my = ((e.clientY - r.top) / r.height) * 100;
      btn.style.setProperty('--mx', `${mx}%`);
      btn.style.setProperty('--my', `${my}%`);
    };
    btn.addEventListener('mousemove', setPos);
    btn.addEventListener('touchmove', (e) => {
      if (!e.touches?.[0]) return;
      setPos({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY });
    }, { passive: true });
  });

  // Show/hide password
  const eye = document.querySelector('.password-wrap .reveal');
  const input = document.getElementById('id_password');
  if (eye && input){
    eye.addEventListener('click', () => {
      const isPw = input.getAttribute('type') === 'password';
      input.setAttribute('type', isPw ? 'text' : 'password');
    });
  }
})();
