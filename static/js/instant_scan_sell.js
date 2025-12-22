// static/js/instant_scan_sell.js
/**
 * Instant Scan-to-Sell Engine for Clothing + Pharmacy Fast Sell
 * 
 * NON-NEGOTIABLE PRINCIPLE: FASTER THAN WRITING IN A BOOK
 * 
 * Features:
 * - Auto-complete sale immediately on barcode scan (no confirm button)
 * - Keep camera open for rapid consecutive scans
 * - Show non-blocking toast with undo option
 * - Handle unknown barcodes with quick-create modal
 * - Handle missing prices with inline price-set modal
 * - Rear camera only (no front camera)
 * - BarcodeDetector API with ZXing fallback
 */

(() => {
  'use strict';

  // ========== Configuration ==========
  const CONFIG = {
    API_LOOKUP: '/inventory/api/barcode/lookup/',
    API_QUICK_CREATE: '/inventory/api/barcode/quick-create/',
    UNDO_TIMEOUT_MS: 10000, // 10 seconds to undo
    SCAN_COOLDOWN_MS: 500,  // Prevent duplicate scans
    BEEP_ENABLED: true,
    TOAST_DURATION_MS: 3000,
  };

  // ========== State ==========
  let state = {
    scanning: false,
    lastScanTime: 0,
    lastScanCode: null,
    pendingSale: null,  // For undo functionality
    videoStream: null,
    detector: null,
    rafId: null,
    vertical: null,  // 'clothing' or 'pharmacy'
    business: null,
  };

  // ========== DOM Elements ==========
  let elements = {
    video: null,
    statusText: null,
    startBtn: null,
    stopBtn: null,
    manualBtn: null,
    toastContainer: null,
    quickCreateModal: null,
    setPriceModal: null,
  };

  // ========== Initialization ==========
  function init(options = {}) {
    state.vertical = options.vertical || 'clothing';
    state.business = options.business || null;

    // Get DOM elements
    elements.video = document.getElementById(options.videoId || 'scannerVideo');
    elements.statusText = document.getElementById(options.statusId || 'scannerStatus');
    elements.startBtn = document.getElementById(options.startBtnId || 'btnStartScan');
    elements.stopBtn = document.getElementById(options.stopBtnId || 'btnStopScan');
    elements.manualBtn = document.getElementById(options.manualBtnId || 'btnManualEntry');
    elements.toastContainer = document.getElementById(options.toastContainerId || 'toastContainer');

    // Bind events
    if (elements.startBtn) {
      elements.startBtn.addEventListener('click', startScanning);
    }
    if (elements.stopBtn) {
      elements.stopBtn.addEventListener('click', stopScanning);
    }
    if (elements.manualBtn) {
      elements.manualBtn.addEventListener('click', showManualEntry);
    }

    // Create modals if they don't exist
    createModals();

    console.log('[InstantScanSell] Initialized for', state.vertical);
  }

  // ========== Camera Control ==========
  async function startScanning() {
    if (state.scanning) return;

    try {
      updateStatus('Starting camera...', 'info');

      // Request rear camera
      const constraints = {
        video: {
          facingMode: { ideal: 'environment' },  // Rear camera
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      };

      state.videoStream = await navigator.mediaDevices.getUserMedia(constraints);
      elements.video.srcObject = state.videoStream;
      await elements.video.play();

      state.scanning = true;
      updateButtons();
      updateStatus('Point camera at barcode...', 'success');

      // Start detection loop
      await initDetector();
      scanLoop();

    } catch (err) {
      console.error('[InstantScanSell] Camera error:', err);
      updateStatus('Camera access denied or unavailable', 'error');
      showToast('❌ Camera access denied. Please enable camera permissions.', 'error');
    }
  }

  function stopScanning() {
    if (!state.scanning) return;

    state.scanning = false;

    // Stop video stream
    if (state.videoStream) {
      state.videoStream.getTracks().forEach(track => track.stop());
      state.videoStream = null;
    }

    // Cancel animation frame
    if (state.rafId) {
      cancelAnimationFrame(state.rafId);
      state.rafId = null;
    }

    // Clear video
    if (elements.video) {
      elements.video.srcObject = null;
    }

    updateButtons();
    updateStatus('Scanner stopped', 'info');
  }

  // ========== Barcode Detection ==========
  async function initDetector() {
    // Try native BarcodeDetector first
    if ('BarcodeDetector' in window) {
      try {
        const formats = [
          'qr_code', 'ean_13', 'ean_8', 'code_128', 'code_39', 'code_93',
          'upc_a', 'upc_e', 'itf', 'codabar', 'aztec', 'data_matrix', 'pdf417'
        ];
        state.detector = new window.BarcodeDetector({ formats });
        console.log('[InstantScanSell] Using native BarcodeDetector');
        return;
      } catch (err) {
        console.warn('[InstantScanSell] BarcodeDetector failed, falling back to ZXing');
      }
    }

    // Fallback: Load ZXing
    if (!window.ZXingBrowser) {
      await loadScript('https://unpkg.com/@zxing/browser@latest');
    }
    console.log('[InstantScanSell] Using ZXing fallback');
  }

  function scanLoop() {
    if (!state.scanning) return;

    state.rafId = requestAnimationFrame(async () => {
      if (elements.video.readyState === elements.video.HAVE_ENOUGH_DATA) {
        await detectBarcode();
      }
      scanLoop();
    });
  }

  async function detectBarcode() {
    try {
      if (state.detector) {
        // Native BarcodeDetector
        const barcodes = await state.detector.detect(elements.video);
        if (barcodes && barcodes.length > 0) {
          const code = barcodes[0].rawValue;
          if (code) {
            handleBarcodeDetected(code);
          }
        }
      } else if (window.ZXingBrowser) {
        // ZXing fallback (not implemented in loop - would need separate approach)
        // For now, native detector is primary
      }
    } catch (err) {
      // Ignore detection errors (common when frame not ready)
    }
  }

  // ========== Barcode Processing ==========
  function handleBarcodeDetected(code) {
    const now = Date.now();

    // Cooldown check (prevent duplicate scans)
    if (code === state.lastScanCode && (now - state.lastScanTime) < CONFIG.SCAN_COOLDOWN_MS) {
      return;
    }

    state.lastScanCode = code;
    state.lastScanTime = now;

    console.log('[InstantScanSell] Barcode detected:', code);
    beep();
    updateStatus(`Scanned: ${code}`, 'success');

    // Lookup and auto-sell
    lookupAndSell(code);
  }

  async function lookupAndSell(barcode) {
    try {
      // Step 1: Lookup barcode
      const response = await fetch(`${CONFIG.API_LOOKUP}?code=${encodeURIComponent(barcode)}`, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin'
      });

      if (!response.ok) {
        throw new Error(`Lookup failed: ${response.status}`);
      }

      const data = await response.json();

      if (!data.found) {
        // Unknown barcode → Quick Create
        showQuickCreateModal(barcode);
        return;
      }

      // Check stock
      if (data.stock_available <= 0) {
        showToast(`❌ OUT OF STOCK: ${data.product_name}`, 'error');
        updateStatus('Out of stock', 'error');
        return;
      }

      // Check if price is missing
      if (data.needs_price) {
        showSetPriceModal(barcode, data);
        return;
      }

      // Step 2: Auto-complete sale immediately
      await completeSale(barcode, data);

    } catch (err) {
      console.error('[InstantScanSell] Lookup error:', err);
      showToast('❌ Lookup failed. Please try again.', 'error');
      updateStatus('Lookup failed', 'error');
    }
  }

  async function completeSale(barcode, productData) {
    try {
      updateStatus('Processing sale...', 'info');

      // Get CSRF token
      const csrfToken = getCsrfToken();

      // Call fast sell API (from existing fast_sell.py service)
      const vertical = state.vertical;
      const response = await fetch(`/verticals/${vertical}/api/fast-sell/create/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          barcode: barcode,
          quantity: 1,
          payment_method: 'cash',  // Default
          selling_price: productData.selling_price
        })
      });

      if (!response.ok) {
        throw new Error(`Sale failed: ${response.status}`);
      }

      const result = await response.json();

      if (!result.ok) {
        showToast(`❌ ${result.error || 'Sale failed'}`, 'error');
        updateStatus('Sale failed', 'error');
        return;
      }

      // Success! Show toast with undo option
      const stockRemaining = (productData.stock_available || 1) - 1;
      showSaleSuccessToast(
        productData.product_name,
        productData.selling_price,
        stockRemaining,
        result.sale_id
      );

      updateStatus('Sale completed! Scan next item...', 'success');

      // Store for undo
      state.pendingSale = {
        saleId: result.sale_id,
        barcode: barcode,
        productName: productData.product_name,
        timestamp: Date.now()
      };

      // Update KPIs if callback exists
      if (window.updateFastSellKPIs) {
        window.updateFastSellKPIs();
      }

    } catch (err) {
      console.error('[InstantScanSell] Sale error:', err);
      showToast('❌ Sale failed. Please try again.', 'error');
      updateStatus('Sale failed', 'error');
    }
  }

  // ========== Quick Create Modal ==========
  function createModals() {
    // Quick Create Modal
    if (!document.getElementById('quickCreateModal')) {
      const modal = document.createElement('div');
      modal.id = 'quickCreateModal';
      modal.className = 'modal-overlay hidden';
      modal.innerHTML = `
        <div class="modal-content">
          <h3>Unknown Barcode - Quick Create</h3>
          <p class="text-sm text-gray-600 mb-4">This barcode is not in the system. Create it now:</p>
          
          <div class="form-group">
            <label>Barcode</label>
            <input type="text" id="qcBarcode" readonly class="form-control">
          </div>
          
          <div class="form-group">
            <label>Product Type *</label>
            <div id="qcCategoryCards" class="category-cards"></div>
          </div>
          
          <div class="form-group">
            <label>Product Name *</label>
            <input type="text" id="qcProductName" class="form-control" placeholder="e.g., T-Shirt Red XL">
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Order Price (Cost) *</label>
              <input type="number" id="qcOrderPrice" class="form-control" placeholder="0.00" step="0.01" min="0">
            </div>
            <div class="form-group">
              <label>Selling Price *</label>
              <input type="number" id="qcSellingPrice" class="form-control" placeholder="0.00" step="0.01" min="0">
            </div>
          </div>
          
          <div class="form-group">
            <label>Quantity *</label>
            <input type="number" id="qcQuantity" class="form-control" value="1" min="1">
          </div>
          
          <div id="qcClothingFields" class="hidden">
            <div class="form-row">
              <div class="form-group">
                <label>Size</label>
                <input type="text" id="qcSize" class="form-control" placeholder="e.g., XL">
              </div>
              <div class="form-group">
                <label>Color</label>
                <input type="text" id="qcColor" class="form-control" placeholder="e.g., Red">
              </div>
            </div>
          </div>
          
          <div id="qcPharmacyFields" class="hidden">
            <div class="form-row">
              <div class="form-group">
                <label>Batch Number</label>
                <input type="text" id="qcBatchNumber" class="form-control" placeholder="Auto-generated if empty">
              </div>
              <div class="form-group">
                <label>Expiry Date</label>
                <input type="date" id="qcExpiryDate" class="form-control">
              </div>
            </div>
          </div>
          
          <div class="modal-actions">
            <button type="button" id="btnQcCancel" class="btn btn-secondary">Cancel</button>
            <button type="button" id="btnQcSave" class="btn btn-primary">Save & Sell</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      // Bind events
      document.getElementById('btnQcCancel').addEventListener('click', hideQuickCreateModal);
      document.getElementById('btnQcSave').addEventListener('click', handleQuickCreateSave);
    }

    // Set Price Modal
    if (!document.getElementById('setPriceModal')) {
      const modal = document.createElement('div');
      modal.id = 'setPriceModal';
      modal.className = 'modal-overlay hidden';
      modal.innerHTML = `
        <div class="modal-content modal-sm">
          <h3>Set Selling Price</h3>
          <p class="text-sm text-gray-600 mb-4">Product: <strong id="spProductName"></strong></p>
          
          <div class="form-group">
            <label>Selling Price *</label>
            <input type="number" id="spSellingPrice" class="form-control" placeholder="0.00" step="0.01" min="0" autofocus>
          </div>
          
          <div class="modal-actions">
            <button type="button" id="btnSpCancel" class="btn btn-secondary">Cancel</button>
            <button type="button" id="btnSpSave" class="btn btn-primary">Save & Sell</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      // Bind events
      document.getElementById('btnSpCancel').addEventListener('click', hideSetPriceModal);
      document.getElementById('btnSpSave').addEventListener('click', handleSetPriceSave);
    }
  }

  function showQuickCreateModal(barcode) {
    const modal = document.getElementById('quickCreateModal');
    if (!modal) return;

    // Populate barcode
    document.getElementById('qcBarcode').value = barcode;

    // Reset form
    document.getElementById('qcProductName').value = '';
    document.getElementById('qcOrderPrice').value = '';
    document.getElementById('qcSellingPrice').value = '';
    document.getElementById('qcQuantity').value = '1';

    // Show/hide vertical-specific fields
    const clothingFields = document.getElementById('qcClothingFields');
    const pharmacyFields = document.getElementById('qcPharmacyFields');
    
    if (state.vertical === 'clothing') {
      clothingFields.classList.remove('hidden');
      pharmacyFields.classList.add('hidden');
      populateClothingCategories();
    } else if (state.vertical === 'pharmacy') {
      clothingFields.classList.add('hidden');
      pharmacyFields.classList.remove('hidden');
      populatePharmacyCategories();
    }

    modal.classList.remove('hidden');
    document.getElementById('qcProductName').focus();
  }

  function hideQuickCreateModal() {
    const modal = document.getElementById('quickCreateModal');
    if (modal) {
      modal.classList.add('hidden');
    }
  }

  function populateClothingCategories() {
    const container = document.getElementById('qcCategoryCards');
    const categories = ['shirt', 'jacket', 'trousers', 'shoes', 'dress', 'skirt', 'other'];
    
    container.innerHTML = categories.map(cat => `
      <button type="button" class="category-card" data-category="${cat}">
        ${cat.charAt(0).toUpperCase() + cat.slice(1)}
      </button>
    `).join('');

    // Bind category selection
    container.querySelectorAll('.category-card').forEach(btn => {
      btn.addEventListener('click', (e) => {
        container.querySelectorAll('.category-card').forEach(b => b.classList.remove('selected'));
        e.target.classList.add('selected');
      });
    });
  }

  function populatePharmacyCategories() {
    const container = document.getElementById('qcCategoryCards');
    const categories = ['medicine', 'cosmetics', 'supplement', 'other'];
    
    container.innerHTML = categories.map(cat => `
      <button type="button" class="category-card" data-category="${cat}">
        ${cat.charAt(0).toUpperCase() + cat.slice(1)}
      </button>
    `).join('');

    // Bind category selection
    container.querySelectorAll('.category-card').forEach(btn => {
      btn.addEventListener('click', (e) => {
        container.querySelectorAll('.category-card').forEach(b => b.classList.remove('selected'));
        e.target.classList.add('selected');
      });
    });
  }

  async function handleQuickCreateSave() {
    const barcode = document.getElementById('qcBarcode').value;
    const productName = document.getElementById('qcProductName').value.trim();
    const orderPrice = document.getElementById('qcOrderPrice').value;
    const sellingPrice = document.getElementById('qcSellingPrice').value;
    const quantity = document.getElementById('qcQuantity').value;
    
    const selectedCategory = document.querySelector('#qcCategoryCards .category-card.selected');
    const category = selectedCategory ? selectedCategory.dataset.category : '';

    // Validation
    const errors = [];
    if (!productName) errors.push('Product name is required');
    if (!category) errors.push('Please select a category');
    if (!orderPrice || parseFloat(orderPrice) < 0) errors.push('Valid order price is required');
    if (!sellingPrice || parseFloat(sellingPrice) < 0) errors.push('Valid selling price is required');
    if (!quantity || parseInt(quantity) < 1) errors.push('Quantity must be at least 1');

    if (errors.length > 0) {
      showToast('❌ ' + errors.join('; '), 'error');
      return;
    }

    // Build payload
    const payload = {
      barcode,
      vertical: state.vertical,
      product_name: productName,
      category,
      selling_price: parseFloat(sellingPrice),
      order_price: parseFloat(orderPrice),
      quantity: parseInt(quantity)
    };

    // Add vertical-specific fields
    if (state.vertical === 'clothing') {
      payload.size = document.getElementById('qcSize').value.trim();
      payload.color = document.getElementById('qcColor').value.trim();
    } else if (state.vertical === 'pharmacy') {
      payload.batch_number = document.getElementById('qcBatchNumber').value.trim();
      const expiryDate = document.getElementById('qcExpiryDate').value;
      if (expiryDate) {
        payload.expiry_date = expiryDate;
      }
    }

    // Submit
    try {
      const csrfToken = getCsrfToken();
      const response = await fetch(CONFIG.API_QUICK_CREATE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`Quick create failed: ${response.status}`);
      }

      const result = await response.json();

      if (!result.ok) {
        showToast(`❌ ${result.error || 'Failed to create product'}`, 'error');
        return;
      }

      // Success!
      hideQuickCreateModal();
      showToast(`✅ Created: ${productName}`, 'success');

      // Now auto-sell it
      lookupAndSell(barcode);

    } catch (err) {
      console.error('[InstantScanSell] Quick create error:', err);
      showToast('❌ Failed to create product', 'error');
    }
  }

  function showSetPriceModal(barcode, productData) {
    const modal = document.getElementById('setPriceModal');
    if (!modal) return;

    document.getElementById('spProductName').textContent = productData.product_name;
    document.getElementById('spSellingPrice').value = '';

    // Store data for later
    modal.dataset.barcode = barcode;
    modal.dataset.productData = JSON.stringify(productData);

    modal.classList.remove('hidden');
    document.getElementById('spSellingPrice').focus();
  }

  function hideSetPriceModal() {
    const modal = document.getElementById('setPriceModal');
    if (modal) {
      modal.classList.add('hidden');
    }
  }

  async function handleSetPriceSave() {
    const modal = document.getElementById('setPriceModal');
    const barcode = modal.dataset.barcode;
    const productData = JSON.parse(modal.dataset.productData);
    const sellingPrice = parseFloat(document.getElementById('spSellingPrice').value);

    if (!sellingPrice || sellingPrice < 0) {
      showToast('❌ Please enter a valid selling price', 'error');
      return;
    }

    // Update product data
    productData.selling_price = sellingPrice;

    hideSetPriceModal();

    // Now complete the sale
    await completeSale(barcode, productData);
  }

  // ========== Toast Notifications ==========
  function showToast(message, type = 'info') {
    const container = elements.toastContainer || document.body;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
      toast.classList.add('show');
    }, 10);
    
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION_MS);
  }

  function showSaleSuccessToast(productName, price, stockRemaining, saleId) {
    const container = elements.toastContainer || document.body;
    
    const toast = document.createElement('div');
    toast.className = 'toast toast-success toast-sale';
    toast.innerHTML = `
      <div class="toast-content">
        <div class="toast-title">✅ SOLD: ${productName}</div>
        <div class="toast-details">MK ${price.toFixed(2)} • Stock: ${stockRemaining}</div>
      </div>
      <button class="toast-undo" data-sale-id="${saleId}">UNDO</button>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
      toast.classList.add('show');
    }, 10);

    // Bind undo button
    const undoBtn = toast.querySelector('.toast-undo');
    undoBtn.addEventListener('click', () => handleUndo(saleId, toast));
    
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, CONFIG.UNDO_TIMEOUT_MS);
  }

  async function handleUndo(saleId, toastElement) {
    try {
      // TODO: Implement undo API endpoint
      // For now, just show message
      showToast('⚠️ Undo functionality coming soon', 'warning');
      
      if (toastElement) {
        toastElement.remove();
      }
    } catch (err) {
      console.error('[InstantScanSell] Undo error:', err);
      showToast('❌ Undo failed', 'error');
    }
  }

  // ========== Manual Entry ==========
  function showManualEntry() {
    const barcode = prompt('Enter barcode manually:');
    if (barcode && barcode.trim()) {
      handleBarcodeDetected(barcode.trim());
    }
  }

  // ========== Utilities ==========
  function updateStatus(message, type = 'info') {
    if (elements.statusText) {
      elements.statusText.textContent = message;
      elements.statusText.className = `status status-${type}`;
    }
  }

  function updateButtons() {
    if (elements.startBtn) {
      elements.startBtn.disabled = state.scanning;
    }
    if (elements.stopBtn) {
      elements.stopBtn.disabled = !state.scanning;
    }
  }

  function beep() {
    if (!CONFIG.BEEP_ENABLED) return;
    
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.frequency.value = 800;
      oscillator.type = 'sine';
      gainNode.gain.value = 0.3;
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.1);
    } catch (err) {
      // Ignore beep errors
    }
  }

  function getCsrfToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'csrftoken') {
        return value;
      }
    }
    return '';
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  // ========== Public API ==========
  window.InstantScanSell = {
    init,
    startScanning,
    stopScanning,
    getState: () => ({ ...state })
  };

})();

