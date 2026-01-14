// ============================================================================
// PWA Install Prompt Banner
// ============================================================================
// Shows a premium banner prompting users to install the app (when available).
// - Android/Chrome: Uses beforeinstallprompt event
// - iOS: Shows "Add to Home Screen" instructions
// - Respects 7-day dismiss cooldown
// - Never shows again after app is installed
// 
// Implementation: 2025-12-25
// ============================================================================

(function() {
  'use strict';

  // Configuration
  const DISMISS_COOLDOWN_DAYS = 7;
  const STORAGE_KEY_DISMISSED = 'pwa-install-dismissed';
  const STORAGE_KEY_INSTALLED = 'pwa-install-completed';

  // State
  let deferredPrompt = null;
  let bannerElement = null;

  // ============================================================================
  // Detection Functions
  // ============================================================================

  /**
   * Check if app is already installed (PWA standalone mode)
   */
  function isAppInstalled() {
    // Check localStorage flag (set when appinstalled event fires)
    if (localStorage.getItem(STORAGE_KEY_INSTALLED) === 'true') {
      return true;
    }

    // Check if running in standalone mode (PWA installed)
    if (window.matchMedia('(display-mode: standalone)').matches) {
      localStorage.setItem(STORAGE_KEY_INSTALLED, 'true');
      return true;
    }

    // Check iOS standalone mode
    if (window.navigator.standalone === true) {
      localStorage.setItem(STORAGE_KEY_INSTALLED, 'true');
      return true;
    }

    return false;
  }

  /**
   * Check if user is on iOS Safari
   */
  function isIOSSafari() {
    const ua = window.navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(ua);
    const isWebkit = /WebKit/.test(ua);
    const isChrome = /CriOS|Chrome/.test(ua);
    
    return isIOS && isWebkit && !isChrome;
  }

  /**
   * Check if banner was recently dismissed (within cooldown period)
   */
  function isRecentlyDismissed() {
    try {
      const dismissed = localStorage.getItem(STORAGE_KEY_DISMISSED);
      if (!dismissed) return false;

      const dismissedTime = parseInt(dismissed, 10);
      if (isNaN(dismissedTime)) return false;

      const now = Date.now();
      const cooldownMs = DISMISS_COOLDOWN_DAYS * 24 * 60 * 60 * 1000;
      
      return (now - dismissedTime) < cooldownMs;
    } catch (e) {
      return false;
    }
  }

  /**
   * Check if install prompt is available (beforeinstallprompt supported)
   */
  function isInstallPromptAvailable() {
    return deferredPrompt !== null;
  }

  // ============================================================================
  // Banner Management
  // ============================================================================

  /**
   * Show the install banner
   */
  function showBanner(isIOS = false) {
    bannerElement = document.getElementById('pwa-install-banner');
    if (!bannerElement) return;

    // Update content based on platform
    const titleEl = bannerElement.querySelector('.pwa-install-title');
    const subtitleEl = bannerElement.querySelector('.pwa-install-subtitle');
    const installBtn = bannerElement.querySelector('.pwa-install-btn');
    const dismissBtn = bannerElement.querySelector('.pwa-dismiss-btn');

    if (isIOS) {
      // iOS: Show instructions
      if (titleEl) titleEl.textContent = 'Install Emajinet';
      if (subtitleEl) subtitleEl.innerHTML = 'Tap <strong>Share</strong> <svg style="width:14px;height:14px;display:inline;vertical-align:middle;" fill="currentColor"><use xlink:href="#icon-share-ios"/></svg> → <strong>Add to Home Screen</strong>';
      if (installBtn) installBtn.style.display = 'none';
    } else {
      // Android/Chrome: Show install button
      if (titleEl) titleEl.textContent = 'Install Emajinet';
      if (subtitleEl) subtitleEl.textContent = 'Faster access, offline-ready, full-screen experience.';
      if (installBtn) {
        installBtn.style.display = '';
        installBtn.onclick = handleInstallClick;
      }
    }

    if (dismissBtn) {
      dismissBtn.onclick = handleDismissClick;
    }

    // Show banner with fade-in animation
    bannerElement.style.display = 'block';
    setTimeout(() => {
      bannerElement.classList.add('pwa-banner-visible');
    }, 10);
  }

  /**
   * Hide the install banner
   */
  function hideBanner(permanent = false) {
    if (!bannerElement) return;

    bannerElement.classList.remove('pwa-banner-visible');
    setTimeout(() => {
      bannerElement.style.display = 'none';
    }, 300);

    if (permanent) {
      localStorage.setItem(STORAGE_KEY_INSTALLED, 'true');
    }
  }

  // ============================================================================
  // Event Handlers
  // ============================================================================

  /**
   * Handle install button click (Android/Chrome)
   */
  async function handleInstallClick() {
    if (!deferredPrompt) return;

    try {
      // Show the install prompt
      deferredPrompt.prompt();

      // Wait for user response
      const { outcome } = await deferredPrompt.userChoice;
      
      if (outcome === 'accepted') {
        console.log('PWA install accepted');
        hideBanner(true);
      } else {
        console.log('PWA install dismissed');
        // Don't hide banner yet - let user dismiss manually
      }

      // Clear the deferred prompt
      deferredPrompt = null;
    } catch (e) {
      console.error('PWA install error:', e);
    }
  }

  /**
   * Handle dismiss button click
   */
  function handleDismissClick() {
    try {
      // Store dismiss timestamp
      localStorage.setItem(STORAGE_KEY_DISMISSED, Date.now().toString());
    } catch (e) {
      console.error('Failed to store dismiss timestamp:', e);
    }

    hideBanner(false);
  }

  /**
   * Handle app installed event
   */
  function handleAppInstalled() {
    console.log('PWA installed');
    localStorage.setItem(STORAGE_KEY_INSTALLED, 'true');
    hideBanner(true);
  }

  // ============================================================================
  // Initialization
  // ============================================================================

  /**
   * Initialize PWA install prompt
   */
  function init() {
    // Don't show if already installed
    if (isAppInstalled()) {
      console.log('PWA already installed - not showing banner');
      return;
    }

    // Don't show if recently dismissed
    if (isRecentlyDismissed()) {
      console.log('PWA banner recently dismissed - respecting cooldown');
      return;
    }

    // Listen for beforeinstallprompt event (Android/Chrome)
    window.addEventListener('beforeinstallprompt', (e) => {
      console.log('beforeinstallprompt event fired');
      
      // Prevent the default mini-infobar
      e.preventDefault();
      
      // Store the event for later use
      deferredPrompt = e;
      
      // Show our custom banner
      showBanner(false);
    });

    // Listen for appinstalled event
    window.addEventListener('appinstalled', handleAppInstalled);

    // Check if iOS Safari (no beforeinstallprompt support)
    if (isIOSSafari() && !isAppInstalled()) {
      console.log('iOS Safari detected - showing iOS instructions');
      showBanner(true);
    }
  }

  // ============================================================================
  // Start
  // ============================================================================

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

