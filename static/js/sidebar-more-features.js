/**
 * Sidebar "More Features" Collapsible Menu
 * 
 * Features:
 * - Toggle expand/collapse on click
 * - Persist state in localStorage
 * - Mobile-first, touch-friendly
 * - Active link highlighting
 * - Keyboard accessible
 */

(function() {
  'use strict';
  
  const STORAGE_KEY = 'cc.sidebar.moreFeatures.open';
  
  /**
   * Initialize the More Features collapsible menu
   */
  function initMoreFeatures() {
    const toggle = document.getElementById('moreFeaturesToggle');
    const submenu = document.getElementById('moreFeaturesSubmenu');
    
    if (!toggle || !submenu) {
      // Not on a page with More Features menu
      return;
    }
    
    // Load persisted state
    const isOpen = localStorage.getItem(STORAGE_KEY) === '1';
    if (isOpen) {
      openSubmenu(toggle, submenu, false);
    }
    
    // Click handler
    toggle.addEventListener('click', function() {
      toggleSubmenu(toggle, submenu);
    });
    
    // Keyboard handler (Enter/Space)
    toggle.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleSubmenu(toggle, submenu);
      }
    });
    
    // Highlight active submenu item
    highlightActiveSubmenuItem(submenu);
  }
  
  /**
   * Toggle submenu open/closed
   */
  function toggleSubmenu(toggle, submenu) {
    const isOpen = submenu.style.display !== 'none';
    
    if (isOpen) {
      closeSubmenu(toggle, submenu);
    } else {
      openSubmenu(toggle, submenu);
    }
  }
  
  /**
   * Open submenu
   */
  function openSubmenu(toggle, submenu, animate = true) {
    submenu.style.display = 'block';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.classList.add('expanded');
    
    // Smooth animation
    if (animate) {
      submenu.style.maxHeight = '0';
      submenu.style.opacity = '0';
      submenu.style.overflow = 'hidden';
      
      // Force reflow
      submenu.offsetHeight;
      
      submenu.style.transition = 'max-height 0.3s ease, opacity 0.2s ease';
      submenu.style.maxHeight = submenu.scrollHeight + 'px';
      submenu.style.opacity = '1';
      
      setTimeout(() => {
        submenu.style.maxHeight = '';
        submenu.style.overflow = '';
        submenu.style.transition = '';
      }, 300);
    }
    
    // Persist state
    localStorage.setItem(STORAGE_KEY, '1');
  }
  
  /**
   * Close submenu
   */
  function closeSubmenu(toggle, submenu) {
    submenu.style.transition = 'max-height 0.3s ease, opacity 0.2s ease';
    submenu.style.maxHeight = submenu.scrollHeight + 'px';
    submenu.style.overflow = 'hidden';
    
    // Force reflow
    submenu.offsetHeight;
    
    submenu.style.maxHeight = '0';
    submenu.style.opacity = '0';
    
    setTimeout(() => {
      submenu.style.display = 'none';
      submenu.style.maxHeight = '';
      submenu.style.overflow = '';
      submenu.style.opacity = '';
      submenu.style.transition = '';
    }, 300);
    
    toggle.setAttribute('aria-expanded', 'false');
    toggle.classList.remove('expanded');
    
    // Persist state
    localStorage.setItem(STORAGE_KEY, '0');
  }
  
  /**
   * Highlight active submenu item based on current URL
   */
  function highlightActiveSubmenuItem(submenu) {
    const currentPath = window.location.pathname;
    const links = submenu.querySelectorAll('.navlink');
    
    links.forEach(link => {
      const href = link.getAttribute('href');
      if (href && currentPath.startsWith(href)) {
        link.classList.add('active');
      }
    });
  }
  
  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMoreFeatures);
  } else {
    initMoreFeatures();
  }
  
  // Re-initialize on page show (for bfcache)
  window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
      initMoreFeatures();
    }
  });
})();

