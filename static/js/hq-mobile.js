/**
 * HQ Mobile Navigation
 * Handles expand/collapse of the slim sidebar on mobile.
 * The sidebar is ALWAYS visible (slim 56 px on mobile, full 260 px on desktop).
 * This script only expands the slim sidebar to full-width overlay on mobile.
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

  // Clicking a nav link collapses back to slim (mobile only)
  sidebar.addEventListener('click', function(e) {
    if (window.innerWidth >= 992) return;
    var link = e.target.closest('a');
    if (link && link.href && !link.href.includes('#') && sidebar.classList.contains('hq-expanded')) {
      collapseSidebar();
    }
  });

  // Clicking the slim sidebar icon strip expands it (mobile only)
  sidebar.addEventListener('click', function(e) {
    if (window.innerWidth >= 992) return;
    if (sidebar.classList.contains('hq-expanded')) return;
    // Only expand when clicking the sidebar itself (icons)
    var link = e.target.closest('a');
    var icon = e.target.closest('i');
    if (link || icon) {
      e.preventDefault();
      expandSidebar();
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
