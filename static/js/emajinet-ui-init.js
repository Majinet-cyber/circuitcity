/**
 * Emajinet UI Initialization System (Feb 2026)
 * ============================================
 * 
 * PROBLEM SOLVED:
 * - Warped dashboards after vertical navigation (BFCache restoration)
 * - Dropdowns/notifications not working until refresh
 * - Stale DOM fragments (wrong vertical banners)
 * 
 * ROOT CAUSE:
 * - Browsers use BFCache to restore pages instantly when navigating back/forward
 * - BFCache restores full DOM state including open dropdowns, attached event listeners
 * - Bootstrap dropdown instances get stale/disconnected after BFCache restore
 * 
 * SOLUTION:
 * - Single init function that is IDEMPOTENT (safe to run multiple times)
 * - Re-initializes Bootstrap dropdowns with proper event delegation
 * - Clears ALL transient UI state (modals, backdrops, overlays)
 * - Runs on: DOMContentLoaded, pageshow (BFCache), popstate
 */

(function () {
  'use strict';

  // Prevent double initialization
  if (window.EmajinetUI && window.EmajinetUI.__initialized) {
    console.log('[EmajinetUI] Already initialized, skipping duplicate init');
    return;
  }

  const EmajinetUI = {
    __initialized: false,
    __version: '2.0.0',

    /**
     * Master init function - IDEMPOTENT and safe to call multiple times
     * Called on: DOMContentLoaded, pageshow (BFCache), popstate, manual refresh
     */
    init: function () {
      console.log('[EmajinetUI] Initializing UI system v' + this.__version);

      // 1. Clean up stale UI state first
      this.resetTransientUI();

      // 2. Wait for Bootstrap to be available before initializing dropdowns
      this._waitForBootstrap(function () {
        EmajinetUI.initDropdowns();
        EmajinetUI.initMobileDrawer();
        EmajinetUI.initTenantMenu();
        EmajinetUI.initBottomNav();
        EmajinetUI.__initialized = true;
        console.log('[EmajinetUI] Initialization complete');
      });
    },

    /**
     * Reset all transient UI state (dropdowns, modals, overlays, backdrops)
     * CRITICAL for BFCache: ensures restored pages start with clean slate
     */
    resetTransientUI: function () {
      console.log('[EmajinetUI] Resetting transient UI state');

      // 1. Force close all dropdowns
      var dropdowns = document.querySelectorAll('[data-bs-toggle="dropdown"]');
      dropdowns.forEach(function (btn) {
        btn.setAttribute('aria-expanded', 'false');
        var menuId = btn.getAttribute('aria-controls');
        if (menuId) {
          var menu = document.getElementById(menuId);
          if (menu) {
            menu.classList.remove('show');
            menu.setAttribute('hidden', '');
            menu.style.display = '';
            menu.style.position = '';
            menu.style.inset = '';
            menu.style.transform = '';
          }
        }
      });

      // 2. Force close all Bootstrap modals
      var modals = document.querySelectorAll('.modal.show');
      modals.forEach(function (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
      });

      // 3. Force close all offcanvas
      var offcanvas = document.querySelectorAll('.offcanvas.show');
      offcanvas.forEach(function (oc) {
        oc.classList.remove('show');
      });

      // 4. Remove all orphaned backdrops
      var backdrops = document.querySelectorAll('.modal-backdrop, .offcanvas-backdrop');
      backdrops.forEach(function (backdrop) {
        backdrop.remove();
      });

      // 5. Clean body classes
      document.body.classList.remove('modal-open', 'offcanvas-open');

      // 6. Reset body scroll-lock styles (only if drawer isn't open)
      var drawerOpen = document.body.getAttribute('data-drawer') === 'open';
      if (!drawerOpen) {
        document.body.style.position = '';
        document.body.style.top = '';
        document.body.style.left = '';
        document.body.style.right = '';
        document.body.style.width = '';
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
      }

      // 7. Close custom tenant menu
      var tenantMenu = document.getElementById('tenantMenu');
      if (tenantMenu) {
        tenantMenu.style.display = 'none';
      }

      // 8. Remove any filter overlays
      var filterOverlays = document.querySelectorAll('.filter-backdrop, .cc-filter-backdrop');
      filterOverlays.forEach(function (el) {
        el.classList.remove('show', 'open');
      });

      console.log('[EmajinetUI] Transient UI reset complete');
    },

    /**
     * Initialize Bootstrap dropdowns with proper event delegation
     * CRITICAL: Destroys old instances before creating new ones (prevents memory leaks)
     */
    initDropdowns: function () {
      console.log('[EmajinetUI] Initializing dropdowns');

      var notifBtn = document.getElementById('ccNotifBtn');
      var userBtn = document.getElementById('userMenuBtn');
      var notifMenu = document.getElementById('ccNotifMenu');
      var userMenu = document.getElementById('userMenu');

      // Initialize notification dropdown
      if (notifBtn && notifMenu) {
        // Destroy old instance if exists
        var existingNotif = bootstrap.Dropdown.getInstance(notifBtn);
        if (existingNotif) {
          try {
            existingNotif.dispose();
          } catch (e) {}
        }

        // Remove hidden attribute so Bootstrap can initialize
        notifMenu.removeAttribute('hidden');

        // Create new dropdown instance
        try {
          var notifDropdown = new bootstrap.Dropdown(notifBtn, {
            autoClose: true,
            boundary: 'viewport',
          });
          console.log('[EmajinetUI] Notification dropdown initialized');

          // Re-hide after initialization
          setTimeout(function () {
            if (!notifMenu.classList.contains('show')) {
              notifMenu.setAttribute('hidden', '');
            }
          }, 0);

          // Handle show event: remove hidden, close other dropdown
          notifBtn.addEventListener(
            'show.bs.dropdown',
            function () {
              notifMenu.removeAttribute('hidden');
              if (userBtn && userMenu) {
                EmajinetUI._forceCloseDropdown(userBtn);
              }
            },
            { once: false }
          );

          // Handle hidden event: restore hidden attribute
          notifBtn.addEventListener(
            'hidden.bs.dropdown',
            function () {
              notifMenu.setAttribute('hidden', '');
            },
            { once: false }
          );
        } catch (e) {
          console.warn('[EmajinetUI] Failed to initialize notification dropdown:', e);
        }
      }

      // Initialize user dropdown
      if (userBtn && userMenu) {
        // Destroy old instance if exists
        var existingUser = bootstrap.Dropdown.getInstance(userBtn);
        if (existingUser) {
          try {
            existingUser.dispose();
          } catch (e) {}
        }

        // Remove hidden attribute so Bootstrap can initialize
        userMenu.removeAttribute('hidden');

        // Create new dropdown instance
        try {
          var userDropdown = new bootstrap.Dropdown(userBtn, {
            autoClose: true,
            boundary: 'viewport',
          });
          console.log('[EmajinetUI] User dropdown initialized');

          // Re-hide after initialization
          setTimeout(function () {
            if (!userMenu.classList.contains('show')) {
              userMenu.setAttribute('hidden', '');
            }
          }, 0);

          // Handle show event: remove hidden, close other dropdown
          userBtn.addEventListener(
            'show.bs.dropdown',
            function () {
              userMenu.removeAttribute('hidden');
              if (notifBtn && notifMenu) {
                EmajinetUI._forceCloseDropdown(notifBtn);
              }
            },
            { once: false }
          );

          // Handle hidden event: restore hidden attribute
          userBtn.addEventListener(
            'hidden.bs.dropdown',
            function () {
              userMenu.setAttribute('hidden', '');
            },
            { once: false }
          );
        } catch (e) {
          console.warn('[EmajinetUI] Failed to initialize user dropdown:', e);
        }
      }
    },

    /**
     * Initialize mobile sidebar drawer (if not already bound)
     */
    initMobileDrawer: function () {
      // Check if already bound by CC Drawer Hotfix v4
      if (window.__CC_DRAWER_V4__) {
        console.log('[EmajinetUI] Mobile drawer already initialized by CC Drawer Hotfix v4');
        return;
      }

      console.log('[EmajinetUI] Mobile drawer initialization skipped (handled by CC Drawer Hotfix v4)');
    },

    /**
     * Initialize tenant menu dropdown
     */
    initTenantMenu: function () {
      var btn = document.getElementById('tenantBtn');
      var menu = document.getElementById('tenantMenu');

      if (!btn || !menu) return;

      // Check if already bound
      if (btn.getAttribute('data-emajinet-bound') === 'true') {
        console.log('[EmajinetUI] Tenant menu already bound');
        return;
      }

      var open = false;

      function set(state) {
        open = state;
        menu.style.display = open ? 'block' : 'none';
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }

      function toggle(e) {
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }
        set(!open);
      }

      function close() {
        if (open) set(false);
      }

      // Initialize closed
      set(false);

      // Bind events
      btn.addEventListener('click', toggle, { passive: false });
      menu.addEventListener('click', function (e) {
        e.stopPropagation();
      });
      document.addEventListener('click', close, { passive: true });
      document.addEventListener(
        'keydown',
        function (e) {
          if (e.key === 'Escape') close();
        },
        { passive: true }
      );

      // Mark as bound
      btn.setAttribute('data-emajinet-bound', 'true');
      console.log('[EmajinetUI] Tenant menu initialized');
    },

    /**
     * Initialize bottom navigation active states
     */
    initBottomNav: function () {
      var tabs = document.querySelectorAll('.mobile-tabbar .tab');
      if (tabs.length === 0) return;

      var currentPath = window.location.pathname.replace(/\/+$/, '/') || '/';

      tabs.forEach(function (tab) {
        var href = (tab.getAttribute('href') || '').replace(/\/+$/, '/') || '/';
        var activePrefix = tab.getAttribute('data-active-prefix') || '';

        // Remove previous active state
        tab.classList.remove('active');

        // Check for exact match or prefix match
        var isActive =
          currentPath === href ||
          (href !== '/' && currentPath.startsWith(href)) ||
          (activePrefix && currentPath.startsWith(activePrefix));

        if (isActive) {
          tab.classList.add('active');
          tab.setAttribute('aria-current', 'page');
        }
      });

      console.log('[EmajinetUI] Bottom nav active states updated');
    },

    /**
     * Helper: Force close a Bootstrap dropdown
     */
    _forceCloseDropdown: function (btn) {
      if (!btn) return;

      var instance = bootstrap.Dropdown.getInstance(btn);
      if (instance) {
        try {
          instance.hide();
        } catch (e) {}
      }

      btn.setAttribute('aria-expanded', 'false');
      var menuId = btn.getAttribute('aria-controls');
      if (menuId) {
        var menu = document.getElementById(menuId);
        if (menu) {
          menu.classList.remove('show');
          menu.setAttribute('hidden', '');
        }
      }
    },

    /**
     * Helper: Wait for Bootstrap to be available
     */
    _waitForBootstrap: function (callback) {
      if (typeof bootstrap !== 'undefined' && bootstrap.Dropdown) {
        callback();
      } else {
        setTimeout(function () {
          EmajinetUI._waitForBootstrap(callback);
        }, 50);
      }
    },
  };

  // Expose globally
  window.EmajinetUI = EmajinetUI;

  // Auto-initialize on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      EmajinetUI.init();
    });
  } else {
    // DOM already loaded
    EmajinetUI.init();
  }

  // CRITICAL: Re-initialize on pageshow (BFCache restoration)
  window.addEventListener('pageshow', function (event) {
    // event.persisted is true when page is restored from BFCache
    if (event.persisted) {
      console.log('[EmajinetUI] Page restored from BFCache, reinitializing UI');
    }
    // Always reinitialize to be safe
    EmajinetUI.init();
  });

  // Re-initialize on popstate (browser back/forward without BFCache)
  window.addEventListener('popstate', function () {
    console.log('[EmajinetUI] Popstate event, reinitializing UI');
    EmajinetUI.init();
  });

  // Re-initialize when tab becomes visible (handles background tab restores)
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      console.log('[EmajinetUI] Tab became visible, reinitializing UI');
      EmajinetUI.init();
    }
  });

  console.log('[EmajinetUI] Module loaded and event listeners registered');
})();

