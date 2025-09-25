/* =========================================================
 * Circuit City · Mobile UX helpers (v3.1)
 * Scope: sidebar drawer, bottom dock sizing, active tab, small iOS fixes
 * Safe to include on every page (idempotent, feature-detected).
 * ========================================================= */

(() => {
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const $ = (sel, root = document) => root.querySelector(sel);

  // -------- Config / selectors (single source of truth) --------
  const SEL = {
    sidebar: '.cc-sidebar',
    openBtn: '#sidebarOpen',
    backdrop: '#ccBackdrop',
    mobileDock: '.cc-bottom-nav, .mobile-tabbar', // supports both class names
    mobileDockTab: '.cc-bottom-nav .tab, .mobile-tabbar .tab',
    page: '.cc-page, main.cc-page'
  };

  // -------- Safe-area & dock height → CSS variable sync --------
  function setDockHeightVar() {
    const dock = $(SEL.mobileDock);
    const root = document.documentElement;
    if (!root) return;
    const h = dock ? dock.getBoundingClientRect().height : 0;
    // Keep CSS var in sync with actual DOM height (overrides default)
    if (h) root.style.setProperty('--cc-nav-h', `${Math.round(h)}px`);
  }

  // -------- Sidebar drawer (collapsible on mobile) -------------
  function setupSidebarDrawer() {
    const sidebar = $(SEL.sidebar);
    const openBtn = $(SEL.openBtn);
    const backdrop = $(SEL.backdrop);
    if (!sidebar || !openBtn || !backdrop) return;

    const body = document.body;
    let savedScrollY = 0;

    const isMobile = () => window.matchMedia('(max-width: 992px)').matches;

    function lockScroll() {
      // Prevent background scroll while drawer is open (iOS friendly)
      savedScrollY = window.scrollY || 0;
      body.style.position = 'fixed';
      body.style.top = `-${savedScrollY}px`;
      body.style.left = '0';
      body.style.right = '0';
      body.style.overflow = 'hidden';
      body.style.width = '100%';
    }
    function unlockScroll() {
      body.style.position = '';
      body.style.top = '';
      body.style.left = '';
      body.style.right = '';
      body.style.overflow = '';
      body.style.width = '';
      window.scrollTo(0, savedScrollY || 0);
    }

    function open() {
      if (!isMobile()) return;
      sidebar.classList.add('open');
      backdrop.classList.add('show');
      lockScroll();
    }
    function close() {
      sidebar.classList.remove('open');
      backdrop.classList.remove('show');
      unlockScroll();
    }
    function toggle() {
      if (sidebar.classList.contains('open')) close(); else open();
    }

    openBtn.addEventListener('click', open);
    backdrop.addEventListener('click', close);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

    // Auto-close drawer after navigating via a sidebar link on mobile
    $$('.cc-sidebar a[href]').forEach(a => {
      a.addEventListener('click', () => { if (isMobile()) close(); }, { passive: true });
    });

    // If we resize to desktop, make sure any mobile state is cleared
    let rAF = 0;
    window.addEventListener('resize', () => {
      cancelAnimationFrame(rAF);
      rAF = requestAnimationFrame(() => {
        if (!isMobile()) close();
        setDockHeightVar();
      });
    }, { passive: true });

    // Expose minimal API for other scripts (optional)
    window.CC_SIDEBAR = { open, close, toggle };
  }

  // -------- Active state for bottom dock tabs ------------------
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

  // -------- iOS viewport & keyboard niceties -------------------
  function setupFocusIntoView() {
    // Keep inputs visible when virtual keyboard opens on very small screens
    document.addEventListener('focusin', (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;
      if (!/^(input|textarea|select)$/i.test(el.tagName)) return;
      // Small delay so keyboard animates first
      setTimeout(() => {
        try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (_) {}
      }, 120);
    });
  }

  // -------- Initialize -----------------------------------------
  function init() {
    // Run as soon as possible (DOM already parsed because script is defer’d)
    setDockHeightVar();
    setupSidebarDrawer();
    setupActiveTabHighlight();
    setupFocusIntoView();

    // Recompute dock height on orientation changes / content shifts
    ['orientationchange', 'load'].forEach(ev =>
      window.addEventListener(ev, setDockHeightVar, { passive: true })
    );

    // Mutation observer: if the dock is rendered later, sync height
    const obs = new MutationObserver(() => setDockHeightVar());
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
