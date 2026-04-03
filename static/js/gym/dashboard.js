/**
 * Gym Dashboard – Premium Interactions v3
 *
 * What this file does (and deliberately does NOT do):
 *
 * DOES:
 *  - Animate payment-mix progress bars (start 0 → target, inside faded-in cards)
 *  - Animate count-up numbers for KPI elements that are BELOW the fold on load
 *    (skip in-viewport elements — server-rendered value is already correct)
 *  - Animate the health bar fill (one-time grow on first paint)
 *  - Init Bootstrap tooltips
 *  - Scroll-in animation for below-fold .recent-block sections (opacity toggle only)
 *  - Smooth-scroll anchor links
 *
 * DOES NOT:
 *  - Override CSS transitions with inline `transition: all` (removed initCardInteractions)
 *  - Hide or move any element that was already visible on initial paint
 *  - Rely on JS for the hero, KPI cards, or health bar to render correctly
 *  - Cause any CLS (Cumulative Layout Shift) or FOIC (Flash of Invisible Content)
 */

(function () {
  'use strict';

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ------------------------------------------------------------------
     COUNT-UP ANIMATION
     Only animates elements that are below the fold at page-load time.
     Elements already visible keep their server-rendered value untouched.
     ------------------------------------------------------------------ */

  function animateCountUp(element, target, duration) {
    if (prefersReducedMotion) {
      element.textContent = target;
      return;
    }

    const hasKSuffix  = target.toString().includes('K');
    const isMoney     = target.toString().includes('MWK') ||
                        target.toString().includes(',') ||
                        element.textContent.includes('K');
    const isDecimal   = !hasKSuffix && target.toString().includes('.');

    const numericTarget = parseFloat(target.toString().replace(/[^0-9.-]/g, ''));
    if (isNaN(numericTarget)) return;

    const startTime = performance.now();

    function easeOutCubic(t) {
      return 1 - Math.pow(1 - t, 3);
    }

    function tick(now) {
      const elapsed  = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const current  = numericTarget * easeOutCubic(progress);

      let formatted;
      if (hasKSuffix) {
        formatted = current.toFixed(1) + 'K';
      } else if (isMoney) {
        formatted = Math.round(current).toLocaleString();
      } else if (isDecimal) {
        formatted = current.toFixed(1);
      } else {
        formatted = Math.round(current).toLocaleString();
      }
      element.textContent = formatted;

      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        element.textContent = target; // Snap to exact final value
      }
    }

    requestAnimationFrame(tick);
  }

  function initCountUpAnimations() {
    if (prefersReducedMotion) return;

    const vh       = window.innerHeight || document.documentElement.clientHeight;
    const elements = document.querySelectorAll('[data-count]');

    elements.forEach(function (el, i) {
      const target = el.getAttribute('data-count');
      if (!target || target === '0' || target === '—' || target === '-') return;

      const rect              = el.getBoundingClientRect();
      const inInitialViewport = rect.top < vh && rect.bottom > 0;

      if (inInitialViewport) {
        /* Server-rendered value is correct — skip animation to avoid flash */
        return;
      }

      /* Off-screen: animate immediately (runs invisibly, done before user scrolls) */
      var delay = i * 80;
      setTimeout(function () { animateCountUp(el, target, 1100); }, delay);
    });
  }

  /* ------------------------------------------------------------------
     PAYMENT-MIX PROGRESS BARS
     Bars start at width:0 (CSS default).  Once the parent metric-card
     has faded into view the bars grow to their target widths, giving a
     satisfying fill effect.  Cards are invisible during their stagger
     delay so the 0-start is never visible.
     ------------------------------------------------------------------ */

  function animatePaymentBars() {
    var bars = document.querySelectorAll('.payment-bar');

    bars.forEach(function (bar, i) {
      var target = bar.getAttribute('data-width');
      if (!target) return;

      if (prefersReducedMotion) {
        bar.style.width = target + '%';
        return;
      }

      /* Stagger each bar slightly so they grow sequentially */
      setTimeout(function () {
        bar.style.width = target + '%';
      }, 120 + (i * 70));
    });
  }

  /* ------------------------------------------------------------------
     HEALTH BAR — one-time grow on initial render
     The bar width is already set server-side via inline style.
     We override to 0 first, then restore the server value so the
     CSS transition fires as a genuine change.  The bar is inside a
     .recent-block that fades in, so the 0-start is never visible.
     ------------------------------------------------------------------ */

  function initHealthBar() {
    if (prefersReducedMotion) return;

    var fill = document.querySelector('.gym-health-bar-fill');
    if (!fill) return;

    var targetWidth = fill.style.width || '0%';
    /* Temporarily reset to 0 so the CSS transition triggers on re-set */
    fill.style.transition = 'none';
    fill.style.width      = '0%';

    /* Single rAF to flush the no-transition style, then restore */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        fill.style.transition = '';   /* Restore CSS-defined transition */
        fill.style.width      = targetWidth;
      });
    });
  }

  /* ------------------------------------------------------------------
     BOOTSTRAP TOOLTIPS
     ------------------------------------------------------------------ */

  function initTooltips() {
    if (typeof bootstrap === 'undefined' || !bootstrap.Tooltip) return;
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      new bootstrap.Tooltip(el);
    });
  }

  /* ------------------------------------------------------------------
     SCROLL-IN FOR BELOW-FOLD SECTIONS
     Only hides sections that are genuinely below the initial viewport.
     Never hides anything that was already visible — that causes FOIC.
     ------------------------------------------------------------------ */

  function initScrollIn() {
    if (!('IntersectionObserver' in window) || prefersReducedMotion) return;

    var vh = window.innerHeight || document.documentElement.clientHeight;

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.style.opacity   = '1';
          entry.target.style.transform = 'translateY(0)';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    var blocks = document.querySelectorAll('.recent-block');
    blocks.forEach(function (block, idx) {
      /* Always leave the first 3 blocks untouched (typically in-viewport) */
      if (idx <= 2) return;

      var rect      = block.getBoundingClientRect();
      var belowFold = rect.top >= vh;
      if (belowFold) {
        block.style.opacity   = '0';
        block.style.transform = 'translateY(14px)';
        block.style.transition = 'opacity 0.42s ease, transform 0.42s ease';
        observer.observe(block);
      }
    });
  }

  /* ------------------------------------------------------------------
     SMOOTH SCROLL
     ------------------------------------------------------------------ */

  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = this.getAttribute('href');
        if (id === '#') return;
        var target = document.querySelector(id);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({
            behavior: prefersReducedMotion ? 'auto' : 'smooth',
            block: 'start',
          });
        }
      });
    });
  }

  /* ------------------------------------------------------------------
     BOOT
     ------------------------------------------------------------------ */

  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
      return;
    }

    initTooltips();
    initCountUpAnimations();
    animatePaymentBars();
    initHealthBar();
    initScrollIn();
    initSmoothScroll();

    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
      console.log('[gym-dashboard] Initialized');
    }
  }

  init();

  /* Public API for HTMX / turbo partial updates */
  window.gymDashboard = {
    refresh: function () {
      initCountUpAnimations();
      animatePaymentBars();
      initHealthBar();
      initTooltips();
    },
  };
})();
