/* =========================================================
 * Circuit City · Mobile UX helpers (v3.2.0)
 * Drawer (single source of truth), dock sizing, active tab,
 * focus/keyboard niceties. Idempotent.
 * ========================================================= */

(() => {
  // ---- Guard against double init ----
  if (window.__CC_MOBILE_INIT__) return;
  window.__CC_MOBILE_INIT__ = true;

  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const $  = (s, r = document) => r.querySelector(s);

  const SEL = {
    sidebar:  '.cc-sidebar',
    openBtn:  '#sidebarOpen',
    backdrop: '#ccBackdrop',
    mobileDock: '.cc-bottom-nav, .mobile-tabbar',
    mobileDockTab: '.cc-bottom-nav .tab, .mobile-tabbar .tab'
  };

  const isMobile = () => matchMedia('(max-width: 992px)').matches;

  // -------- Safe-area & dock height → CSS var --------
  function setDockHeightVar() {
    const dock = $(SEL.mobileDock);
    const root = document.documentElement;
    const h = dock ? Math.round(dock.getBoundingClientRect().height) : 0;
    if (h) root.style.setProperty('--cc-nav-h', `${h}px`);
  }

  // -------- Scroll lock helpers --------
  let savedScrollY = 0;
  function lockScroll() {
    savedScrollY = window.scrollY || 0;
    Object.assign(document.body.style, {
      position: 'fixed', top: `-${savedScrollY}px`, left: '0', right: '0', width: '100%', overflow: 'hidden'
    });
  }
  function unlockScroll() {
    Object.assign(document.body.style, { position: '', top: '', left: '', right: '', width: '', overflow: '' });
    window.scrollTo(0, savedScrollY || 0);
  }

  // -------- Drawer (body[data-drawer] drives CSS) --------
  function setupDrawer() {
    const sidebar  = $(SEL.sidebar);
    const openBtn  = $(SEL.openBtn);
    const backdrop = $(SEL.backdrop);
    if (!sidebar || !openBtn || !backdrop) return;

    // Ensure clean starting state
    document.body.removeAttribute('data-drawer');
    backdrop.classList.remove('show');
    sidebar.classList.remove('open', 'is-open');

    let openedAt = 0; // debounce close-after-open taps

    const open = () => {
      if (!isMobile()) return;
      // hide any old backdrops so they don't eat taps
      $$('.offcanvas-backdrop, [data-legacy-menu]').forEach(n => (n.style.pointerEvents = 'none'));
      document.body.setAttribute('data-drawer', 'open');
      sidebar.classList.add('open', 'is-open');
      backdrop.classList.add('show');
      lockScroll();
      openedAt = Date.now();
    };

    const close = () => {
      document.body.removeAttribute('data-drawer');
      sidebar.classList.remove('open', 'is-open');
      backdrop.classList.remove('show');
      unlockScroll();
    };

    const toggle = (e) => {
      if (e) { e.preventDefault(); e.stopPropagation(); }
      (document.body.getAttribute('data-drawer') === 'open') ? close() : open();
    };

    // Make the hamburger extremely “sticky” to taps
    ['pointerdown', 'touchstart', 'click'].forEach(ev => {
      openBtn.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); toggle(); }, { passive: false });
    });

    // Stop events inside the sidebar from bubbling out and triggering a close
    ['pointerdown', 'touchstart', 'click'].forEach(ev => {
      sidebar.addEventListener(ev, (e) => e.stopPropagation(), { passive: true });
    });

    // Backdrop to close (with tiny debounce so open→blur doesn’t immediately close)
    backdrop.addEventListener('click', () => {
      if (Date.now() - openedAt < 250) return;
      close();
    });

    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); }, { passive: true });

    // Auto-close after navigating from a sidebar link on mobile
    $$('.cc-sidebar a[href]').forEach(a => {
      a.addEventListener('click', () => { if (isMobile()) close(); }, { passive: true });
    });

    // On resize to desktop, clear mobile state
    let rAF = 0;
    window.addEventListener('resize', () => {
      cancelAnimationFrame(rAF);
      rAF = requestAnimationFrame(() => {
        if (!isMobile()) close();
        setDockHeightVar();
      });
    }, { passive: true });

    // Minimal API
    window.CC_SIDEBAR = { open, close, toggle };
  }

  // -------- Active state for bottom dock tabs --------
  function setupActiveTabHighlight() {
    const path = (location.pathname || '/').replace(/\/+$/, '/') || '/';
    $$(SEL.mobileDockTab).forEach(a => {
      const href = (a.getAttribute('href') || '').replace(/\/+$/, '/') || '';
      if (!href) return;
      if (path === href || (href !== '/' && path.startsWith(href))) {
        a.classList.add('active');
        a.setAttribute('aria-current', 'page');
      } else {
        a.classList.remove('active');
        a.removeAttribute('aria-current');
      }
    });
  }

  // -------- Focus into view on mobile keyboards --------
  function setupFocusIntoView() {
    document.addEventListener('focusin', (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;
      if (!/^(input|textarea|select)$/i.test(el.tagName)) return;
      setTimeout(() => {
        try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (_) {}
      }, 120);
    });
  }

  // -------- Init --------
  function init() {
    setDockHeightVar();
    setupDrawer();
    setupActiveTabHighlight();
    setupFocusIntoView();

    ['orientationchange', 'load'].forEach(ev =>
      window.addEventListener(ev, setDockHeightVar, { passive: true })
    );
    new MutationObserver(setDockHeightVar)
      .observe(document.documentElement, { childList: true, subtree: true });
  }

  (document.readyState === 'loading')
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
