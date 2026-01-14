/* static/inventory/app.js
   Polished, mobile-first helpers. Backwards-compatible with your existing IDs.
   - Sidebar toggle (supports #ccBurger/#ccSidebar AND legacy #sidebarToggle/#sidebar)
   - Theme toggle + persistence (data-theme on <html>)
   - CSRF-safe fetch wrapper
   - Inline form validation + accessible errors
   - Auto-hide toasts (+ window.ccToast helper)
   - Bottom mobile tabs + FAB enable on phones
   - Edge-swipe to open sidebar (mobile)
   - Light haptics (if supported)
   - Wallet summary localStorage cache (window.getWalletSummaryCached)
   - Optional filter persistence (data-persist="filters")
   - Count-up utility for KPIs (window.ccCountUp)
   - Service worker registration (if present)
*/
(function () {
  if (window.__ccInit) return; // idempotent
  window.__ccInit = true;

  const d = document;
  const root = d.documentElement;

  /* =========================
     THEME (light/dark)
  ========================== */
  (function themeInit() {
    const KEY = 'cc-theme';
    const saved = localStorage.getItem(KEY);
    const initial = saved || root.getAttribute('data-theme') || 'light';
    const metaTheme = d.querySelector('meta[name="theme-color"]');

    function setTheme(t) {
      root.setAttribute('data-theme', t);
      localStorage.setItem(KEY, t);
      if (metaTheme) metaTheme.setAttribute('content', t === 'dark' ? '#0f172a' : '#0b5bd3');
    }

    // Set once on load (in case base didn't already)
    if (root.getAttribute('data-theme') !== initial) setTheme(initial);

    // Wire any theme toggle buttons that exist
    d.querySelectorAll('#ccTheme,.cc-theme-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
      });
    });
  })();

  /* =========================
     CSRF-SAFE FETCH WRAPPER
  ========================== */
  (function csrfFetch() {
    if (window.__ccPatchedFetch) return;
    window.__ccPatchedFetch = true;

    const csrfEl = d.querySelector('#__csrf__ input[name=csrfmiddlewaretoken]');
    const CSRF = csrfEl ? csrfEl.value : null;
    const SAFE = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE']);
    const orig = window.fetch;

    window.fetch = function (input, init) {
      init = init || {};
      const method = (init.method || 'GET').toUpperCase();
      const url = (typeof input === 'string') ? input : input.url;
      const sameOrigin = url.startsWith('/') || url.startsWith(location.origin);
      if (!SAFE.has(method) && sameOrigin) {
        const headers = new Headers(init.headers || {});
        if (CSRF && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', CSRF);
        init.headers = headers;
      }
      return orig(input, init);
    };
  })();

  /* =========================
     SIDEBAR TOGGLE (mobile)
     - Supports new (#ccBurger/#ccSidebar/#ccOverlay)
       and legacy (#sidebarToggle/#sidebar)
  ========================== */
  (function sidebarInit() {
    const burger = d.getElementById('ccBurger') || d.getElementById('sidebarToggle');
    const sidebar = d.getElementById('ccSidebar') || d.getElementById('sidebar');
    const overlay = d.getElementById('ccOverlay'); // may be null

    function openSidebar() {
      if (!sidebar) return;
      sidebar.classList.add('open');
      if (overlay) { overlay.hidden = false; overlay.setAttribute('aria-hidden', 'false'); }
      d.body.classList.add('no-scroll');
      if (burger) burger.setAttribute('aria-expanded', 'true');
    }
    function closeSidebar() {
      if (!sidebar) return;
      sidebar.classList.remove('open');
      if (overlay) { overlay.hidden = true; overlay.setAttribute('aria-hidden', 'true'); }
      d.body.classList.remove('no-scroll');
      if (burger) burger.setAttribute('aria-expanded', 'false');
    }
    function toggleSidebar() {
      sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
    }

    if (burger && sidebar) {
      burger.addEventListener('click', toggleSidebar);
      if (overlay) overlay.addEventListener('click', closeSidebar);
      // Close on Escape
      d.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSidebar(); });
      // Close if layout switches to desktop
      const mq = window.matchMedia('(min-width: 1025px)');
      mq.addEventListener('change', closeSidebar);
    }

    // Edge-swipe to open (mobile)
    (function swipeToOpen() {
      if (!sidebar) return;
      let startX = null, startY = null, t0 = 0;
      const EDGE = 24, MIN = 60, MAX_ANGLE = 25; // px, px, degrees
      window.addEventListener('touchstart', (e) => {
        const t = e.touches[0]; if (!t) return;
        if (t.clientX <= EDGE) { startX = t.clientX; startY = t.clientY; t0 = Date.now(); }
      }, { passive: true });
      window.addEventListener('touchend', (e) => {
        if (startX == null) return;
        const t = e.changedTouches[0]; if (!t) return;
        const dx = t.clientX - startX, dy = Math.abs(t.clientY - startY);
        const angle = Math.atan2(dy, Math.abs(dx)) * 180 / Math.PI;
        if (dx > MIN && angle < MAX_ANGLE && (Date.now() - t0) < 600) openSidebar();
        startX = startY = null;
      }, { passive: true });
    })();

    // Expose to other scripts if needed
    window.ccOpenSidebar = openSidebar;
    window.ccCloseSidebar = closeSidebar;
  })();

  /* =========================
     INLINE VALIDATION
     - Keep your original behavior
     - Adds aria-invalid and shows .help-error sibling
  ========================== */
  (function inlineValidation() {
    d.querySelectorAll('form[data-validate]').forEach(form => {
      const submitBtn = form.querySelector('button[type="submit"]');
      const validate = () => {
        const valid = form.checkValidity();
        if (submitBtn) submitBtn.disabled = !valid;
        form.querySelectorAll('.help-error').forEach(h => {
          const input = h.previousElementSibling;
          const bad = input && !input.checkValidity();
          h.hidden = !bad;
          if (input) input.setAttribute('aria-invalid', bad ? 'true' : 'false');
        });
      };
      form.addEventListener('input', validate);
      form.addEventListener('change', validate);
      form.addEventListener('submit', (e) => { if (!form.checkValidity()) { e.preventDefault(); validate(); } });
      validate();
    });
  })();

  /* =========================
     TOASTS
     - Auto-hide after ~4s (respect reduced motion)
     - window.ccToast(msg, type) helper (type: info|success|danger)
  ========================== */
  (function toasts() {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    d.querySelectorAll('.toast').forEach(t => {
      if (!prefersReduced) {
        setTimeout(() => {
          t.style.transition = 'opacity .25s';
          t.style.opacity = '0';
          setTimeout(() => t.remove(), 300);
        }, 4000);
      }
    });

    // Create a toast container if needed
    function ensureHost() {
      let host = d.getElementById('toastHost');
      if (!host) {
        host = d.createElement('div');
        host.id = 'toastHost';
        host.style.position = 'fixed';
        host.style.zIndex = '1000';
        host.style.bottom = '16px';
        host.style.right = '16px';
        host.style.display = 'flex';
        host.style.flexDirection = 'column';
        host.style.gap = '8px';
        d.body.appendChild(host);
      }
      return host;
    }

    window.ccToast = (msg, type = 'info') => {
      const host = ensureHost();
      const el = d.createElement('div');
      el.className = 'toast';
      el.setAttribute('role', 'status');
      el.style.padding = '.6rem .8rem';
      el.style.borderRadius = '10px';
      el.style.boxShadow = '0 10px 25px rgba(0,0,0,.15)';
      el.style.color = '#fff';
      el.style.fontWeight = '600';
      el.style.maxWidth = '320px';

      const bgMap = {
        info: '#0b5bd3', success: '#15803d', danger: '#b91c1c', warning: '#b45309'
      };
      el.style.background = bgMap[type] || bgMap.info;

      el.innerHTML = `<div style="display:flex;align-items:center;gap:.6rem">
        <div style="flex:1">${msg}</div>
        <button aria-label="Dismiss" style="border:0;background:transparent;color:#fff;font-size:1.1rem;line-height:1;opacity:.9">×</button>
      </div>`;

      el.querySelector('button').addEventListener('click', () => el.remove());
      host.appendChild(el);

      if (!prefersReduced) {
        setTimeout(() => {
          el.style.transition = 'opacity .25s';
          el.style.opacity = '0';
          setTimeout(() => el.remove(), 300);
        }, 2200);
      }
    };
  })();

  /* =========================
     MOBILE BOTTOM NAV + FAB
     - Shows only on phones (<=1024px) if present in DOM
  ========================== */
  (function mobileNav() {
    const bottomNav = d.getElementById('ccBottomNav');
    const fab = d.getElementById('ccFab');
    const isPhone = matchMedia('(max-width: 1024px)').matches;

    if (bottomNav && isPhone) {
      bottomNav.style.display = 'block';
      d.body.classList.add('has-bottom-nav');
    }
    if (fab && isPhone) {
      fab.style.display = 'inline-block';
      const href = fab.getAttribute('data-href') || '/inventory/scan-sold/';
      fab.addEventListener('click', () => { location.href = href; });
    }

    // Light haptics
    function vibrate(ms = 12) { if ('vibrate' in navigator) { try { navigator.vibrate(ms); } catch {} } }
    [fab, ...d.querySelectorAll('.cc-bottom-tab, .cc-topbtn, .cc-sideitem, .btn')]
      .filter(Boolean).forEach(el => el.addEventListener('click', () => vibrate(8), { passive: true }));
  })();

  /* =========================
     FILTER PERSISTENCE (optional)
     - Add data-persist="filters" on any GET form to enable
  ========================== */
  (function filterPersist() {
    d.querySelectorAll('form[method="get"][data-persist="filters"]').forEach(form => {
      const KEY = 'cc:filters:' + (form.id || location.pathname);
      // restore
      try {
        const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
        for (const [k, v] of Object.entries(saved)) {
          const el = form.querySelector(`[name="${k}"]`); if (el) el.value = v;
        }
      } catch {}
      // save
      form.addEventListener('change', () => {
        const data = Object.fromEntries(new FormData(form).entries());
        localStorage.setItem(KEY, JSON.stringify(data));
      });
    });
  })();

  /* =========================
     WALLET SUMMARY CACHE
     - window.getWalletSummaryCached(userId, year, month)
  ========================== */
  (function walletCache() {
    window.getWalletSummaryCached = async (uid, y = null, m = null) => {
      const key = `wallet:${uid}:${y || ''}:${m || ''}`;
      const hit = localStorage.getItem(key);
      if (hit) {
        try {
          const { at, data } = JSON.parse(hit);
          if (Date.now() - at < 5 * 60 * 1000) return data; // 5 min
        } catch { /* ignore */ }
      }
      const qs = y && m ? `?user_id=${encodeURIComponent(uid)}&year=${y}&month=${m}`
                        : `?user_id=${encodeURIComponent(uid)}`;
      const r = await fetch(`/inventory/api/wallet-summary/${qs}`);
      const data = await r.json();
      localStorage.setItem(key, JSON.stringify({ at: Date.now(), data }));
      return data;
    };
  })();

  /* =========================
     COUNT-UP helper for KPIs
     - window.ccCountUp(el, to, ms)
     - data-countup attribute support
  ========================== */
  (function countUpInit() {
    const nf = new Intl.NumberFormat();
    function ccCountUp(el, to, ms = 600) {
      const start = performance.now();
      const from = 0;
      function step(t) {
        const p = Math.min((t - start) / ms, 1);
        el.textContent = nf.format(Math.floor(from + (to - from) * p));
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }
    window.ccCountUp = ccCountUp;

    d.querySelectorAll('[data-countup]').forEach(el => {
      const to = Number(String(el.textContent).replace(/,/g, '')) || 0;
      ccCountUp(el, to);
    });
  })();

  /* =========================
     AUTO-HIDE ELEMENTS
     - Finds .js-auto-hide elements with data-hide-after-ms attribute
     - Hides them after the specified delay with fade animation
  ========================== */
  (function autoHide() {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    d.querySelectorAll('.js-auto-hide').forEach(el => {
      const delay = parseInt(el.getAttribute('data-hide-after-ms')) || 30000;
      setTimeout(() => {
        if (prefersReduced) {
          el.style.display = 'none';
        } else {
          el.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
          el.style.opacity = '0';
          el.style.transform = 'translateY(-10px)';
          setTimeout(() => {
            el.style.display = 'none';
          }, 500);
        }
      }, delay);
    });
  })();

  /* =========================
     ROTATING DASHBOARD INSIGHTS
     - Rotates between fast products, locations, agents, and payment mix
     - Updates chart every 5 seconds
     - Requires Chart.js to be loaded
  ========================== */
  (function rotatingInsights() {
    const canvas = d.getElementById('rotating-insights-chart');
    if (!canvas || typeof Chart === 'undefined') return;

    const data = window.EmajinetDashboardData;
    if (!data) return;

    const titleEl = d.getElementById('rotating-insights-title');
    const subtitleEl = d.getElementById('rotating-insights-subtitle');
    const indicatorEl = d.getElementById('rotating-insights-indicator');

    // Define states for rotation
    const states = [
      {
        key: 'fastProducts',
        title: 'Fast Moving Stock',
        subtitle: 'Top 5 products by quantity sold (last 30 days)',
        data: data.fastProducts || [],
        colors: ['#6366f1', '#8b5cf6', '#a855f7', '#c084fc', '#d8b4fe']
      },
      {
        key: 'fastLocations',
        title: 'Fast Moving Locations',
        subtitle: 'Top 5 locations by revenue (last 30 days)',
        data: data.fastLocations || [],
        colors: ['#10b981', '#14b8a6', '#06b6d4', '#0ea5e9', '#3b82f6']
      },
      {
        key: 'fastAgents',
        title: 'Top Agents',
        subtitle: 'Top 5 agents by revenue (last 30 days)',
        data: data.fastAgents || [],
        colors: ['#f59e0b', '#f97316', '#ef4444', '#ec4899', '#d946ef']
      },
      {
        key: 'paymentMix',
        title: 'Payment Mix',
        subtitle: 'Revenue by payment method (last 30 days)',
        data: data.paymentMix || [],
        colors: ['#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
      }
    ];

    // Filter out states with no data
    const activeStates = states.filter(s => s.data.length > 0);
    if (activeStates.length === 0) {
      if (titleEl) titleEl.textContent = 'No Data Available';
      if (subtitleEl) subtitleEl.textContent = 'Start making sales to see insights';
      return;
    }

    let currentIndex = 0;

    // Initialize chart with premium AI-generated styling
    const ctx = canvas.getContext('2d');
    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Value',
          data: [],
          backgroundColor: [],
          borderRadius: 12,
          borderSkipped: false,
          barPercentage: 0.7,
          categoryPercentage: 0.8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            top: 10,
            right: 10,
            bottom: 0,
            left: 10
          }
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            padding: 16,
            borderRadius: 12,
            titleFont: {
              size: 15,
              weight: '700',
              family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            bodyFont: {
              size: 14,
              family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
            },
            titleColor: '#ffffff',
            bodyColor: '#e2e8f0',
            borderColor: 'rgba(99, 102, 241, 0.3)',
            borderWidth: 1,
            displayColors: true,
            boxWidth: 12,
            boxHeight: 12,
            boxPadding: 6,
            usePointStyle: true,
            callbacks: {
              label: function(context) {
                const value = context.parsed.y;
                // Format numbers with commas and add currency/unit
                return ' ' + value.toLocaleString('en-US');
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            border: {
              display: false
            },
            grid: {
              color: 'rgba(148, 163, 184, 0.08)',
              lineWidth: 1,
              drawTicks: false
            },
            ticks: {
              padding: 8,
              font: {
                size: 11,
                weight: '600',
                family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
              },
              color: '#64748b',
              callback: function(value) {
                // Format large numbers (e.g., 1000 -> 1K)
                if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
                if (value >= 1000) return (value / 1000).toFixed(0) + 'K';
                return value;
              }
            }
          },
          x: {
            border: {
              display: false
            },
            grid: {
              display: false
            },
            ticks: {
              padding: 8,
              font: {
                size: 11,
                weight: '600',
                family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
              },
              color: '#64748b',
              maxRotation: 0,
              minRotation: 0,
              autoSkip: true,
              autoSkipPadding: 20
            }
          }
        },
        animation: {
          duration: 800,
          easing: 'easeInOutCubic',
          onComplete: function() {
            // Add subtle pulse effect on bars
            const meta = chart.getDatasetMeta(0);
            meta.data.forEach((bar, index) => {
              if (bar) {
                bar.$animations = {};
              }
            });
          }
        }
      }
    });

    // Update chart with current state
    function updateChart() {
      const state = activeStates[currentIndex];

      // Update title and subtitle
      if (titleEl) titleEl.textContent = state.title;
      if (subtitleEl) subtitleEl.textContent = state.subtitle;

      // Update indicator dots
      if (indicatorEl) {
        const dots = indicatorEl.querySelectorAll('.rotating-insights-dot');
        dots.forEach((dot, i) => {
          dot.classList.toggle('active', i === currentIndex);
        });
      }

      // Update chart data
      chart.data.labels = state.data.map(item => item.label);
      chart.data.datasets[0].data = state.data.map(item => item.value);
      chart.data.datasets[0].backgroundColor = state.colors.slice(0, state.data.length);
      chart.update();
    }

    // Initial render
    updateChart();

    // Rotate every 5 seconds
    setInterval(() => {
      currentIndex = (currentIndex + 1) % activeStates.length;
      updateChart();
    }, 5000);
  })();

  /* =========================
     SERVICE WORKER (optional)
  ========================== */
  (function sw() {
    if ('serviceWorker' in navigator) {
      // CRITICAL: Disable service worker on localhost to prevent cache poisoning
      var hostname = window.location.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1') {
        console.log('[DEV] Service worker disabled on localhost to prevent cache issues');
        return;
      }
      navigator.serviceWorker.register('/static/sw.js').catch(() => { /* no-op */ });
    }
  })();

  /* =========================
     LEGACY BLOCKS (kept from your original file)
     - Sidebar toggle (legacy IDs)
     - Auto-hide simple .toast blocks (already enhanced above)
  ========================== */

  // Legacy Sidebar toggle for #sidebarToggle/#sidebar (kept; safe no-op if handled above)
  (function () {
    const toggle = d.getElementById('sidebarToggle');
    const sidebar = d.getElementById('sidebar');
    if (toggle && sidebar) {
      const setState = (open) => { sidebar.classList.toggle('open', open); toggle.setAttribute('aria-expanded', String(open)); };
      toggle.addEventListener('click', () => setState(!sidebar.classList.contains('open')));
      d.addEventListener('keydown', (e) => { if (e.key === 'Escape') setState(false); });
    }
  })();

  // Simple auto-hide toasts after 4s (kept; enhanced version above also handles)
  (function () {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const toasts = d.querySelectorAll('.toast');
    toasts.forEach(t => {
      if (!prefersReduced) {
        setTimeout(() => { t.style.transition = 'opacity .25s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, 4000);
      }
    });
  })();

})();
