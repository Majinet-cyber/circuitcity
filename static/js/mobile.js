/* =========================================================
 * Circuit City · Mobile UX helpers (v3.3.0)
 * Dock sizing, active tab, focus/keyboard niceties.
 * Drawer logic is handled by base.html CC Drawer Hotfix v4.
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

  // -------- Drawer (SKIP if already bound by base.html) --------
  function setupDrawer() {
    const sidebar  = $(SEL.sidebar);
    const openBtn  = $(SEL.openBtn);
    const backdrop = $(SEL.backdrop);
    if (!sidebar || !openBtn || !backdrop) return;

    // CRITICAL: Check if already handled by base.html CC Drawer Hotfix
    // If data-bound="1" is set, another script has already configured these elements
    if (openBtn.getAttribute('data-bound') === '1') {
      // Already bound — just ensure CC_SIDEBAR is exposed
      if (!window.CC_SIDEBAR && window.ccDrawer) {
        window.CC_SIDEBAR = window.ccDrawer;
      }
      return;
    }

    // Mark as bound to prevent future duplicate handlers
    openBtn.setAttribute('data-bound', '1');
    backdrop.setAttribute('data-bound', '1');
    sidebar.setAttribute('data-bound', '1');

    // Ensure clean starting state
    document.body.removeAttribute('data-drawer');
    backdrop.classList.remove('show');
    sidebar.classList.remove('open', 'is-open');

    let savedScrollY = 0;
    let openedAt = 0; // debounce close-after-open taps

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

    // Single event type to prevent double-toggle (pointerup only)
    openBtn.addEventListener('pointerup', (e) => { e.preventDefault(); e.stopPropagation(); toggle(); }, { passive: false });

    // Stop events inside the sidebar from bubbling out and triggering a close
    ['pointerdown', 'touchstart', 'click'].forEach(ev => {
      sidebar.addEventListener(ev, (e) => e.stopPropagation(), { passive: true });
    });

    // Backdrop to close (with tiny debounce so open→blur doesn't immediately close)
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
    window.ccDrawer = window.CC_SIDEBAR; // Compatibility
  }

  // -------- Active state for bottom dock tabs --------
  function setupActiveTabHighlight() {
    const path = (location.pathname || '/').replace(/\/+$/, '/') || '/';
    $$(SEL.mobileDockTab).forEach(a => {
      const href = (a.getAttribute('href') || '').replace(/\/+$/, '/') || '';
      if (!href || href === '#') return;
      
      // Check if there's a data-active-prefix attribute (vertical-aware matching)
      const activePrefix = a.getAttribute('data-active-prefix');
      let isActive = false;
      
      if (activePrefix && activePrefix.trim()) {
        // Use active prefix if provided
        isActive = path.startsWith(activePrefix);
      } else {
        // Fallback to href matching
        isActive = path === href || (href !== '/' && path.startsWith(href));
      }
      
      if (isActive) {
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
