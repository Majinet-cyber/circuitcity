/**
 * IMEI Smart Scanner Module
 * Circuit City / Emajinet
 * 
 * Handles smart IMEI validation and lookup for Scan IN and Scan & Sell pages.
 * 
 * Usage:
 * <div class="cc-imei-scanner" data-cc-imei-mode="scan_in">
 *   <input data-cc-imei-input type="text" maxlength="15" />
 *   <button data-cc-imei-scan>Scan IMEI</button>
 *   <div data-cc-imei-message></div>
 * </div>
 * 
 * Then in your page:
 * <script src="/static/js/imei_scanner.js"></script>
 * <script>
 *   ImeiScanner.init({
 *     onSuccess: function(data) { ... },
 *     onError: function(msg) { ... }
 *   });
 * </script>
 */

(function(window) {
  'use strict';

  // API endpoint
  const API_ENDPOINT = '/inventory/api/imei-lookup/';
  
  // IMEI validation regex (exactly 15 digits)
  const IMEI_REGEX = /^\d{15}$/;

  /**
   * Normalize IMEI: strip spaces, keep only digits
   */
  function normalizeImei(value) {
    return (value || '').replace(/\s+/g, '').replace(/\D/g, '');
  }

  /**
   * Validate IMEI format (exactly 15 digits)
   */
  function validateImeiFormat(imei) {
    const clean = normalizeImei(imei);
    return IMEI_REGEX.test(clean);
  }

  /**
   * Display message in the message container
   */
  function showMessage(container, message, type) {
    if (!container) return;
    
    container.textContent = message;
    container.className = 'cc-imei-message';
    
    // Add type-specific class
    if (type === 'error') {
      container.classList.add('cc-imei-message--error');
    } else if (type === 'success') {
      container.classList.add('cc-imei-message--success');
    } else if (type === 'info') {
      container.classList.add('cc-imei-message--info');
    }
    
    container.style.display = 'block';
  }

  /**
   * Clear message
   */
  function clearMessage(container) {
    if (!container) return;
    container.textContent = '';
    container.style.display = 'none';
  }

  /**
   * Call the backend IMEI lookup API
   */
  function lookupImei(imei, mode) {
    const url = new URL(API_ENDPOINT, window.location.origin);
    url.searchParams.set('imei', imei);
    url.searchParams.set('mode', mode);
    
    return fetch(url.toString(), {
      method: 'GET',
      credentials: 'same-origin',
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.error || `HTTP ${response.status}`);
        });
      }
      return response.json();
    });
  }

  /**
   * Initialize scanner for a container
   */
  function initScanner(container, options) {
    const mode = container.getAttribute('data-cc-imei-mode') || 'scan_in';
    const input = container.querySelector('[data-cc-imei-input]');
    const scanBtn = container.querySelector('[data-cc-imei-scan]');
    const messageEl = container.querySelector('[data-cc-imei-message]');
    
    if (!input || !scanBtn) {
      console.error('IMEI Scanner: Required elements not found');
      return;
    }

    // Validation function
    function validateAndLookup() {
      const rawValue = input.value || '';
      const imei = normalizeImei(rawValue);
      
      // Clear previous messages
      clearMessage(messageEl);
      
      // Validate format
      if (!validateImeiFormat(imei)) {
        const errorMsg = 'IMEI must be exactly 15 digits (numbers only).';
        showMessage(messageEl, errorMsg, 'error');
        if (options.onError) {
          options.onError(errorMsg);
        }
        return;
      }
      
      // Show loading state
      if (scanBtn) {
        scanBtn.disabled = true;
        scanBtn.textContent = 'Checking...';
      }
      
      // Call API
      lookupImei(imei, mode)
        .then(data => {
          if (data.ok === false) {
            // API returned error
            const errorMsg = data.error || 'IMEI lookup failed';
            showMessage(messageEl, errorMsg, 'error');
            if (options.onError) {
              options.onError(errorMsg, data);
            }
          } else if (data.data) {
            // Success
            const result = data.data;
            
            if (mode === 'scan_in') {
              if (result.status === 'available') {
                showMessage(messageEl, '✓ IMEI available for scan in', 'success');
                if (options.onSuccess) {
                  options.onSuccess(result);
                }
              }
            } else if (mode === 'scan_sell') {
              if (result.status === 'in_stock') {
                const productName = result.product_name || 'Product';
                showMessage(messageEl, `✓ ${productName} ready to sell`, 'success');
                if (options.onSuccess) {
                  options.onSuccess(result);
                }
              }
            }
          }
        })
        .catch(error => {
          const errorMsg = error.message || 'Network error. Please try again.';
          showMessage(messageEl, errorMsg, 'error');
          if (options.onError) {
            options.onError(errorMsg);
          }
        })
        .finally(() => {
          // Restore button state
          if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan IMEI';
          }
        });
    }

    // Bind scan button
    scanBtn.addEventListener('click', function(e) {
      e.preventDefault();
      validateAndLookup();
    });

    // Bind Enter key on input
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        validateAndLookup();
      }
    });

    // Auto-validate on input (optional, for real-time feedback)
    if (options.autoValidate) {
      input.addEventListener('input', function() {
        const imei = normalizeImei(input.value);
        if (imei.length === 15) {
          // Auto-trigger validation when 15 digits entered
          setTimeout(validateAndLookup, 100);
        } else if (imei.length > 0 && messageEl) {
          clearMessage(messageEl);
        }
      });
    }
  }

  /**
   * Public API
   */
  const ImeiScanner = {
    /**
     * Initialize all IMEI scanners on the page
     * @param {Object} options - Configuration options
     * @param {Function} options.onSuccess - Called when IMEI lookup succeeds
     * @param {Function} options.onError - Called when IMEI lookup fails
     * @param {Boolean} options.autoValidate - Auto-validate when 15 digits entered
     */
    init: function(options) {
      options = options || {};
      
      const containers = document.querySelectorAll('[data-cc-imei-mode]');
      containers.forEach(function(container) {
        initScanner(container, options);
      });
    },
    
    /**
     * Validate IMEI format (utility)
     */
    validate: validateImeiFormat,
    
    /**
     * Normalize IMEI (utility)
     */
    normalize: normalizeImei
  };

  // Export to global scope
  window.ImeiScanner = ImeiScanner;

})(window);

