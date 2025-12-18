/**
 * Rear Camera Barcode Scanner Modal - For Fast Sell
 * 
 * Features:
 * - REAR camera ONLY (facingMode: "environment")
 * - Strict fallback: NO silent switch to front camera
 * - Animated scan line overlay
 * - Multiple barcode formats support (EAN-13, UPC, Code-128, QR, etc.)
 * - Debouncing and deduplication
 * - Scan history (last 10 scans with timestamps)
 * - Mobile-first, full-screen on mobile
 * - Graceful error handling (manual input fallback)
 * 
 * Usage:
 *   const scanner = new RearCameraBarcodeScanner({
 *     onScan: (barcode) => { console.log('Scanned:', barcode); },
 *     onError: (error) => { console.error('Error:', error); }
 *   });
 *   scanner.open();
 */

class RearCameraBarcodeScanner {
  constructor(options = {}) {
    this.options = {
      onScan: options.onScan || ((barcode) => console.log('Scanned:', barcode)),
      onError: options.onError || ((error) => console.error('Scanner error:', error)),
      onClose: options.onClose || (() => {}),
      debounceMs: options.debounceMs || 1500,
      formats: options.formats || [
        'ean_13', 'ean_8', 'upc_a', 'upc_e',
        'code_128', 'code_39', 'code_93', 'codabar',
        'itf', 'qr_code', 'data_matrix', 'pdf417'
      ],
      historySize: options.historySize || 10
    };
    
    this.videoStream = null;
    this.barcodeDetector = null;
    this.scanningActive = false;
    this.lastScannedBarcode = null;
    this.lastScanTime = 0;
    this.modal = null;
    this.scanHistory = [];
    
    this._createModal();
  }
  
  /**
   * Create modal DOM structure
   */
  _createModal() {
    const modalHTML = `
      <div class="rear-barcode-scanner-modal" id="rearBarcodeScannerModal" style="display:none;">
        <div class="scanner-modal-overlay"></div>
        <div class="scanner-modal-content">
          <div class="scanner-modal-header">
            <h3><i class="bi bi-upc-scan"></i> Scan Barcode</h3>
            <button class="scanner-close-btn" id="rearScannerCloseBtn" aria-label="Close">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          
          <div class="scanner-modal-body">
            <!-- Camera View -->
            <div class="scanner-video-wrapper">
              <video id="rearScannerVideo" autoplay playsinline muted></video>
              <div class="scanner-overlay-ui">
                <div class="scan-frame"></div>
                <div class="scan-line"></div>
              </div>
              <div class="scanner-status" id="rearScannerStatus">
                <i class="bi bi-camera"></i>
                <p>Initializing rear camera...</p>
              </div>
            </div>
            
            <!-- Scan History -->
            <div class="scan-history-panel" id="scanHistoryPanel" style="display:none;">
              <div class="history-header">
                <i class="bi bi-clock-history"></i>
                <span>Recent Scans</span>
              </div>
              <ul class="history-list" id="scanHistoryList"></ul>
            </div>
            
            <!-- Manual Input Fallback -->
            <div class="scanner-manual-input">
              <label for="rearManualBarcodeInput">Or enter manually:</label>
              <div class="input-group">
                <input type="text" 
                       id="rearManualBarcodeInput" 
                       class="form-control" 
                       placeholder="Type or paste barcode"
                       autocomplete="off">
                <button class="btn btn-primary" id="rearManualBarcodeSubmit">
                  <i class="bi bi-check-lg"></i> Use
                </button>
              </div>
            </div>
            
            <!-- Instructions -->
            <div class="scanner-instructions">
              <p><i class="bi bi-info-circle"></i> Point rear camera at barcode within the frame</p>
              <p class="text-muted small">Supports: EAN-13, UPC, Code-128, QR, and more</p>
            </div>
          </div>
        </div>
      </div>
    `;
    
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = modalHTML.trim();
    this.modal = tempDiv.firstChild;
    document.body.appendChild(this.modal);
    
    // Bind events
    this._bindEvents();
  }
  
  /**
   * Bind event listeners
   */
  _bindEvents() {
    // Close button
    const closeBtn = this.modal.querySelector('#rearScannerCloseBtn');
    closeBtn.addEventListener('click', () => this.close());
    
    // Overlay click to close
    const overlay = this.modal.querySelector('.scanner-modal-overlay');
    overlay.addEventListener('click', () => this.close());
    
    // Manual input submit
    const manualSubmit = this.modal.querySelector('#rearManualBarcodeSubmit');
    manualSubmit.addEventListener('click', () => this._handleManualInput());
    
    const manualInput = this.modal.querySelector('#rearManualBarcodeInput');
    manualInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        this._handleManualInput();
      }
    });
    
    // Escape key to close
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modal.style.display !== 'none') {
        this.close();
      }
    });
  }
  
  /**
   * Open scanner modal
   */
  async open() {
    this.modal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scroll
    
    try {
      await this._startCamera();
    } catch (error) {
      this._showStatus('Rear camera unavailable. Use manual input below.', 'error');
      this.options.onError(error);
    }
  }
  
  /**
   * Close scanner modal
   */
  close() {
    this._stopCamera();
    this.modal.style.display = 'none';
    document.body.style.overflow = '';
    
    // Clear manual input
    const manualInput = this.modal.querySelector('#rearManualBarcodeInput');
    if (manualInput) manualInput.value = '';
    
    this.options.onClose();
  }
  
  /**
   * Start camera with STRICT rear camera enforcement
   */
  async _startCamera() {
    try {
      this._showStatus('Requesting rear camera access...', 'info');
      
      let stream = null;
      
      // Try exact "environment" first
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { exact: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: false
        });
      } catch (exactError) {
        console.warn('Exact rear camera not available, trying fallback...', exactError);
        
        // Fallback to non-exact "environment"
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: "environment",
              width: { ideal: 1280 },
              height: { ideal: 720 }
            },
            audio: false
          });
        } catch (fallbackError) {
          console.error('Rear camera fallback failed:', fallbackError);
          throw new Error('REAR_CAMERA_NOT_AVAILABLE');
        }
      }
      
      // Verify we got the correct camera (if possible)
      const tracks = stream.getVideoTracks();
      if (tracks.length > 0) {
        const settings = tracks[0].getSettings();
        console.log('Camera settings:', settings);
        
        // If we can detect front camera, reject it
        if (settings.facingMode && settings.facingMode === 'user') {
          stream.getTracks().forEach(track => track.stop());
          throw new Error('FRONT_CAMERA_DETECTED');
        }
      }
      
      this.videoStream = stream;
      const video = this.modal.querySelector('#rearScannerVideo');
      video.srcObject = this.videoStream;
      
      // Hide status overlay
      this._hideStatus();
      
      // Initialize BarcodeDetector if available
      if ('BarcodeDetector' in window) {
        try {
          const supportedFormats = await BarcodeDetector.getSupportedFormats();
          console.log('BarcodeDetector supported formats:', supportedFormats);
          
          const formats = this.options.formats.filter(f => 
            supportedFormats.includes(f)
          );
          
          if (formats.length === 0) {
            throw new Error('No compatible barcode formats');
          }
          
          this.barcodeDetector = new BarcodeDetector({ formats });
          this.scanningActive = true;
          this._scanLoop();
          
          // Show scan history panel
          this._updateScanHistory();
        } catch (err) {
          console.warn('BarcodeDetector initialization failed:', err);
          this._showStatus('Camera active but barcode detection unavailable. Use manual input.', 'warning');
        }
      } else {
        console.warn('BarcodeDetector API not supported in this browser');
        this._showStatus('Rear camera active. BarcodeDetector not supported - use manual input.', 'warning');
      }
    } catch (error) {
      console.error('Camera access error:', error);
      
      if (error.message === 'REAR_CAMERA_NOT_AVAILABLE') {
        this._showStatus('❌ Rear camera not available on this device. Use manual input.', 'error');
      } else if (error.message === 'FRONT_CAMERA_DETECTED') {
        this._showStatus('❌ Only front camera available. Rear camera required. Use manual input.', 'error');
      } else if (error.name === 'NotAllowedError') {
        this._showStatus('❌ Camera permission denied. Please allow camera access or use manual input.', 'error');
      } else if (error.name === 'NotFoundError') {
        this._showStatus('❌ No camera found. Use manual input.', 'error');
      } else {
        this._showStatus('❌ Camera error. Use manual input.', 'error');
      }
      
      throw error;
    }
  }
  
  /**
   * Stop camera and cleanup
   */
  _stopCamera() {
    this.scanningActive = false;
    
    if (this.videoStream) {
      this.videoStream.getTracks().forEach(track => track.stop());
      this.videoStream = null;
    }
    
    const video = this.modal.querySelector('#rearScannerVideo');
    if (video) {
      video.srcObject = null;
    }
    
    this.barcodeDetector = null;
  }
  
  /**
   * Barcode scanning loop with debouncing
   */
  async _scanLoop() {
    if (!this.scanningActive || !this.barcodeDetector) return;
    
    try {
      const video = this.modal.querySelector('#rearScannerVideo');
      
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        const barcodes = await this.barcodeDetector.detect(video);
        
        if (barcodes.length > 0) {
          const barcode = barcodes[0].rawValue;
          const format = barcodes[0].format;
          const now = Date.now();
          
          // Debounce: ignore same barcode within debounceMs
          if (barcode !== this.lastScannedBarcode || (now - this.lastScanTime) >= this.options.debounceMs) {
            this.lastScannedBarcode = barcode;
            this.lastScanTime = now;
            
            // Add to history
            this._addToHistory(barcode, format);
            
            // Success feedback
            this._showSuccessFeedback();
            
            // Call callback
            this.options.onScan(barcode);
            
            // Auto-close after successful scan
            setTimeout(() => this.close(), 600);
            return;
          }
        }
      }
    } catch (error) {
      console.error('Scan loop error:', error);
    }
    
    // Continue scanning
    requestAnimationFrame(() => this._scanLoop());
  }
  
  /**
   * Add barcode to scan history
   */
  _addToHistory(barcode, format) {
    const timestamp = new Date().toLocaleTimeString();
    this.scanHistory.unshift({ barcode, format, timestamp });
    
    // Keep only last N scans
    if (this.scanHistory.length > this.options.historySize) {
      this.scanHistory.pop();
    }
    
    this._updateScanHistory();
  }
  
  /**
   * Update scan history UI
   */
  _updateScanHistory() {
    const historyPanel = this.modal.querySelector('#scanHistoryPanel');
    const historyList = this.modal.querySelector('#scanHistoryList');
    
    if (!historyList) return;
    
    if (this.scanHistory.length === 0) {
      historyPanel.style.display = 'none';
      return;
    }
    
    historyPanel.style.display = 'block';
    historyList.innerHTML = this.scanHistory.map(item => `
      <li class="history-item">
        <span class="history-barcode">${this._escapeHtml(item.barcode)}</span>
        <span class="history-meta">
          <span class="history-format">${item.format}</span>
          <span class="history-time">${item.timestamp}</span>
        </span>
      </li>
    `).join('');
  }
  
  /**
   * Handle manual barcode input
   */
  _handleManualInput() {
    const input = this.modal.querySelector('#rearManualBarcodeInput');
    const barcode = input.value.trim();
    
    if (barcode) {
      this._addToHistory(barcode, 'manual');
      this.options.onScan(barcode);
      this.close();
    }
  }
  
  /**
   * Show status message
   */
  _showStatus(message, type = 'info') {
    const statusDiv = this.modal.querySelector('#rearScannerStatus');
    const icons = {
      info: 'bi-info-circle',
      warning: 'bi-exclamation-triangle',
      error: 'bi-x-circle',
      success: 'bi-check-circle'
    };
    
    statusDiv.innerHTML = `
      <i class="bi ${icons[type] || icons.info}"></i>
      <p>${message}</p>
    `;
    statusDiv.style.display = 'flex';
    statusDiv.className = `scanner-status status-${type}`;
  }
  
  /**
   * Hide status overlay
   */
  _hideStatus() {
    const statusDiv = this.modal.querySelector('#rearScannerStatus');
    statusDiv.style.display = 'none';
  }
  
  /**
   * Show success feedback animation
   */
  _showSuccessFeedback() {
    const frame = this.modal.querySelector('.scan-frame');
    if (!frame) return;
    
    frame.style.borderColor = '#10b981';
    frame.style.boxShadow = '0 0 30px rgba(16, 185, 129, 0.6)';
    
    // Play success sound (if available)
    try {
      const audio = new Audio('data:audio/wav;base64,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');
      audio.volume = 0.3;
      audio.play().catch(() => {});
    } catch (e) {}
    
    setTimeout(() => {
      frame.style.borderColor = '';
      frame.style.boxShadow = '';
    }, 600);
  }
  
  /**
   * Escape HTML to prevent XSS
   */
  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  /**
   * Destroy scanner instance
   */
  destroy() {
    this.close();
    if (this.modal && this.modal.parentNode) {
      this.modal.parentNode.removeChild(this.modal);
    }
  }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = RearCameraBarcodeScanner;
}
if (typeof window !== 'undefined') {
  window.RearCameraBarcodeScanner = RearCameraBarcodeScanner;
}

