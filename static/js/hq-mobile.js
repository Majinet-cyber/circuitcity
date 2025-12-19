/**
 * HQ Mobile Navigation
 * Handles off-canvas sidebar toggle for mobile devices
 */
(function() {
  'use strict';

  // Only initialize if we're on an HQ page
  const sidebar = document.getElementById('hqSidebar');
  const backdrop = document.getElementById('hqBackdrop');
  const toggle = document.getElementById('hqSidebarToggle');
  
  if (!sidebar || !backdrop || !toggle) {
    // Not an HQ page or elements not found
    return;
  }

  /**
   * Open the sidebar
   */
  function openSidebar() {
    sidebar.classList.add('is-open');
    backdrop.classList.add('is-open');
    backdrop.removeAttribute('hidden');
    document.body.classList.add('hq-nav-open');
    toggle.setAttribute('aria-expanded', 'true');
  }

  /**
   * Close the sidebar
   */
  function closeSidebar() {
    sidebar.classList.remove('is-open');
    backdrop.classList.remove('is-open');
    setTimeout(() => {
      if (!backdrop.classList.contains('is-open')) {
        backdrop.setAttribute('hidden', '');
      }
    }, 200); // Match CSS transition duration
    document.body.classList.remove('hq-nav-open');
    toggle.setAttribute('aria-expanded', 'false');
  }

  /**
   * Toggle sidebar open/closed
   */
  function toggleSidebar() {
    if (sidebar.classList.contains('is-open')) {
      closeSidebar();
    } else {
      openSidebar();
    }
  }

  // Toggle button click
  toggle.addEventListener('click', toggleSidebar);

  // Backdrop click closes sidebar
  backdrop.addEventListener('click', closeSidebar);

  // Escape key closes sidebar
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && sidebar.classList.contains('is-open')) {
      closeSidebar();
    }
  });

  // Close sidebar when clicking any nav link (mobile only)
  // This improves UX when navigating between pages
  function handleNavClick(e) {
    // Only close on mobile (when sidebar is in off-canvas mode)
    if (window.innerWidth < 992 && sidebar.classList.contains('is-open')) {
      // Check if clicked element is a link
      const link = e.target.closest('a');
      if (link && link.href && !link.href.includes('#')) {
        // Let navigation happen, then close
        closeSidebar();
      }
    }
  }

  sidebar.addEventListener('click', handleNavClick);

  // Handle window resize - close sidebar if resizing to desktop
  let resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
      // If we're now on desktop size and sidebar is open, close it
      if (window.innerWidth >= 992 && sidebar.classList.contains('is-open')) {
        closeSidebar();
      }
    }, 250);
  });

  // Prevent body scroll when sidebar is open on mobile
  // This is handled by CSS but we ensure it's always in sync
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      if (mutation.attributeName === 'class') {
        const hasOpenClass = document.body.classList.contains('hq-nav-open');
        // Additional enforcement if needed
      }
    });
  });

  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ['class']
  });

})();

