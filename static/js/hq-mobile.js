/**
 * HQ Mobile Navigation
 * Handles expand/collapse of the slim sidebar on mobile.
 * The sidebar is ALWAYS visible (slim 56 px on mobile, full 260 px on desktop).
 * This script only expands the slim sidebar to full-width overlay on mobile.
 *
 * FIX (2026-04-29): Replaced two separate click listeners with a single unified
 * handler. The old dual-listener pattern had a race condition: the first listener
 * removed the 'hq-expanded' class, then the second listener saw it was gone and
 * called e.preventDefault() + expandSidebar() again — preventing navigation.
 */
(function() {
  'use strict';

  var sidebar  = document.getElementById('hqSidebar');
  var backdrop = document.getElementById('hqBackdrop');
  var toggle   = document.getElementById('hqSidebarToggle');
  var closeBtn = document.getElementById('hqSidebarClose');

  if (!sidebar) return; // Not an HQ page

  /** Expand sidebar (mobile overlay) */
  function expandSidebar() {
    sidebar.classList.add('hq-expanded');
    if (backdrop) {
      backdrop.classList.add('is-open');
      backdrop.removeAttribute('hidden');
    }
    document.body.classList.add('hq-nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
  }

  /** Collapse sidebar back to slim strip */
  function collapseSidebar() {
    sidebar.classList.remove('hq-expanded');
    if (backdrop) {
      backdrop.classList.remove('is-open');
      setTimeout(function() {
        if (!backdrop.classList.contains('is-open')) {
          backdrop.setAttribute('hidden', '');
        }
      }, 220);
    }
    document.body.classList.remove('hq-nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  /** Toggle */
  function toggleSidebar() {
    if (sidebar.classList.contains('hq-expanded')) {
      collapseSidebar();
    } else {
      expandSidebar();
    }
  }

  // Topbar hamburger button
  if (toggle) toggle.addEventListener('click', toggleSidebar);

  // Close button inside expanded sidebar
  if (closeBtn) closeBtn.addEventListener('click', collapseSidebar);

  // Backdrop click
  if (backdrop) backdrop.addEventListener('click', collapseSidebar);

  // Escape key
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && sidebar.classList.contains('hq-expanded')) {
      collapseSidebar();
    }
  });

  /**
   * UNIFIED sidebar click handler (replaces the old dual-listener pattern).
   *
   * Old bug: Two separate listeners fired in sequence. The first collapsed the
   * sidebar (removed hq-expanded), then the second saw the class was gone and
   * prevented navigation + re-expanded — creating an infinite toggle loop that
   * made all nav links unclickable.
   *
   * Fix: Capture the expanded state BEFORE any mutation, then decide once:
   *  - If sidebar WAS expanded → let the link navigate (no preventDefault);
   *    collapse after the navigation starts.
   *  - If sidebar WAS slim (not expanded) → prevent navigation and expand it so
   *    the user can see the full labels, then click the link again.
   */
  sidebar.addEventListener('click', function(e) {
    if (window.innerWidth >= 992) return; // Desktop: no-op

    var wasExpanded = sidebar.classList.contains('hq-expanded');
    var link = e.target.closest('a');
    var icon = e.target.closest('i');

    if (wasExpanded) {
      // Sidebar was open when clicked.
      // If a real navigation link was clicked: collapse the sidebar and let
      // the browser follow the link (do NOT call preventDefault).
      if (link && link.href && !link.href.endsWith('#') && link.href !== window.location.href + '#') {
        collapseSidebar();
        // href navigation proceeds normally (no preventDefault)
      }
      // If a non-link area (icon only) was clicked, just collapse.
      else if (!link && icon) {
        collapseSidebar();
      }
    } else {
      // Sidebar is slim. Expand it on any icon or link click so the user
      // can see the full labels before navigating.
      if (link || icon) {
        e.preventDefault();
        expandSidebar();
      }
    }
  });

  // On resize to desktop, collapse overlay state
  var resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
      if (window.innerWidth >= 992 && sidebar.classList.contains('hq-expanded')) {
        collapseSidebar();
      }
    }, 250);
  });

})();
