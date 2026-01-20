/**
 * SHARED NAVBAR INITIALIZATION (SSOT)
 * 
 * PART 3 FIX: Navbar dropdowns + notifications must work in production
 * without hard refresh, including after HTMX navigation.
 * 
 * This script handles:
 * - Avatar dropdown toggle (Profile/Settings/Logout)
 * - Notifications panel
 * - Re-initialization after HTMX swaps
 * - Mutual exclusion (opening one closes the other)
 * 
 * CRITICAL: This file is included ONCE in base.html and handles
 * all navbar interactions across all verticals.
 */
(function() {
  'use strict';

  // Guard against double initialization
  if (window.__CC_NAVBAR_INITIALIZED__) {
    return;
  }
  window.__CC_NAVBAR_INITIALIZED__ = true;

  // Track open dropdowns for mutual exclusion
  var openDropdowns = new Set();

  /**
   * Initialize navbar dropdowns.
   * Called on DOMContentLoaded and after HTMX swaps.
   */
  function initNavbarDropdowns() {
    // ========================================
    // Avatar/User Dropdown
    // ========================================
    var avatarBtn = document.getElementById('ccUserBtn');
    var avatarMenu = document.getElementById('ccUserMenu');

    if (avatarBtn && avatarMenu) {
      // Remove existing listeners (prevent duplicates on HTMX swap)
      var newAvatarBtn = avatarBtn.cloneNode(true);
      avatarBtn.parentNode.replaceChild(newAvatarBtn, avatarBtn);
      avatarBtn = newAvatarBtn;

      avatarBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        toggleDropdown('avatar', avatarMenu, avatarBtn);
      });
    }

    // ========================================
    // Notifications Bell
    // ========================================
    var bellBtn = document.getElementById('cc-bell');
    var notifPanel = document.getElementById('cc-notifications-panel');

    if (bellBtn) {
      // Remove existing listeners
      var newBellBtn = bellBtn.cloneNode(true);
      bellBtn.parentNode.replaceChild(newBellBtn, bellBtn);
      bellBtn = newBellBtn;

      bellBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (notifPanel) {
          toggleDropdown('notifications', notifPanel, bellBtn);
        } else {
          // Fallback: Simple alert if no panel exists
          showNotificationsToast();
        }
      });
    }

    // ========================================
    // Global click-outside handler
    // ========================================
    // Use capture phase to catch events before they bubble
    document.removeEventListener('click', handleOutsideClick, true);
    document.addEventListener('click', handleOutsideClick, true);

    // ========================================
    // Escape key handler
    // ========================================
    document.removeEventListener('keydown', handleEscapeKey);
    document.addEventListener('keydown', handleEscapeKey, { passive: true });

    console.log('[Navbar] Dropdowns initialized');
  }

  /**
   * Toggle a dropdown open/closed with mutual exclusion.
   */
  function toggleDropdown(id, menuEl, btnEl) {
    var isOpen = menuEl.classList.contains('open');

    // Close all other dropdowns first
    closeAllDropdowns();

    if (!isOpen) {
      // Open this dropdown
      menuEl.classList.add('open');
      if (btnEl) {
        btnEl.setAttribute('aria-expanded', 'true');
      }
      openDropdowns.add(id);
    }
  }

  /**
   * Close all open dropdowns.
   */
  function closeAllDropdowns() {
    var avatarMenu = document.getElementById('ccUserMenu');
    var avatarBtn = document.getElementById('ccUserBtn');
    var notifPanel = document.getElementById('cc-notifications-panel');
    var bellBtn = document.getElementById('cc-bell');

    if (avatarMenu) {
      avatarMenu.classList.remove('open');
    }
    if (avatarBtn) {
      avatarBtn.setAttribute('aria-expanded', 'false');
    }
    if (notifPanel) {
      notifPanel.classList.remove('open');
    }
    if (bellBtn) {
      bellBtn.setAttribute('aria-expanded', 'false');
    }

    openDropdowns.clear();
  }

  /**
   * Handle clicks outside dropdowns.
   */
  function handleOutsideClick(e) {
    if (openDropdowns.size === 0) return;

    var avatarBtn = document.getElementById('ccUserBtn');
    var avatarMenu = document.getElementById('ccUserMenu');
    var bellBtn = document.getElementById('cc-bell');
    var notifPanel = document.getElementById('cc-notifications-panel');

    // Check if click is inside any dropdown or trigger
    var isInsideAvatar = (
      (avatarBtn && avatarBtn.contains(e.target)) ||
      (avatarMenu && avatarMenu.contains(e.target))
    );
    var isInsideNotif = (
      (bellBtn && bellBtn.contains(e.target)) ||
      (notifPanel && notifPanel.contains(e.target))
    );

    if (!isInsideAvatar && !isInsideNotif) {
      closeAllDropdowns();
    }
  }

  /**
   * Handle Escape key to close dropdowns.
   */
  function handleEscapeKey(e) {
    if (e.key === 'Escape') {
      closeAllDropdowns();
    }
  }

  /**
   * Show a toast for notifications (fallback when no panel exists).
   */
  function showNotificationsToast() {
    // Check for existing toast system
    if (typeof window.showToast === 'function') {
      window.showToast('No new notifications', 'info');
    } else {
      // Simple inline toast
      var existingToast = document.getElementById('cc-notif-toast');
      if (existingToast) {
        existingToast.remove();
      }

      var toast = document.createElement('div');
      toast.id = 'cc-notif-toast';
      toast.style.cssText = [
        'position: fixed',
        'top: 80px',
        'right: 20px',
        'padding: 12px 20px',
        'background: #1e293b',
        'color: #fff',
        'border-radius: 10px',
        'box-shadow: 0 4px 20px rgba(0,0,0,0.2)',
        'z-index: 9999',
        'font-size: 14px',
        'font-weight: 600',
        'animation: fadeIn 0.2s ease'
      ].join(';');
      toast.textContent = 'No new notifications';
      document.body.appendChild(toast);

      setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(function() { toast.remove(); }, 300);
      }, 2000);
    }
  }

  // ========================================
  // Initial setup
  // ========================================
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavbarDropdowns);
  } else {
    initNavbarDropdowns();
  }

  // ========================================
  // HTMX integration: Re-init after swaps
  // ========================================
  document.addEventListener('htmx:afterSwap', function(e) {
    // Only re-init if the swap affected the navbar area
    var target = e.detail.target;
    if (target && (
      target.querySelector('#ccUserBtn') ||
      target.querySelector('#cc-bell') ||
      target.id === 'main-content' ||
      target.tagName === 'BODY'
    )) {
      console.log('[Navbar] Re-initializing after HTMX swap');
      initNavbarDropdowns();
    }
  });

  // Also handle htmx:afterSettle for safety
  document.addEventListener('htmx:afterSettle', function(e) {
    // Re-init navbar elements if they exist in the settled content
    var target = e.detail.target;
    if (target && target.querySelector && target.querySelector('[data-testid="nav-avatar"]')) {
      initNavbarDropdowns();
    }
  });

  // Expose for debugging/manual re-init
  window.ccNavbarInit = initNavbarDropdowns;
  window.ccNavbarCloseAll = closeAllDropdowns;

  console.log('[Navbar] Shared navbar init loaded');
})();

