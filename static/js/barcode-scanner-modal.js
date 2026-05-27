/**
 * Barcode Scanner Modal - Reusable Component
 * 
 * Features:
 * - BarcodeDetector API with fallback to manual input
 * - Front camera only (user preference)
 * - Animated scan line overlay
 * - Multiple barcode formats support
 * - Debouncing and deduplication
 * - Mobile-first, full-screen on mobile
 * - Graceful error handling (no 500s)
 * 
 * Usage:
 *   const scanner = new BarcodeScanner({
 *     onScan: (barcode) => { console.log('Scanned:', barcode); },
 *     onError: (error) => { console.error('Error:', error); }
 *   });
 *   scanner.open();
 */

class BarcodeScanner {
  constructor(options = {}) {
    this.options = {
      onScan: options.onScan || ((barcode) => console.log('Scanned:', barcode)),
      onError: options.onError || ((error) => console.error('Scanner error:', error)),
      onClose: options.onClose || (() => {}),
      debounceMs: options.debounceMs || 1500,
      formats: options.formats || [
        'ean_13', 'ean_8', 'upc_a', 'upc_e',
        'code_128', 'code_39', 'itf', 'qr_code'
      ]
    };
    
    this.videoStream = null;
    this.barcodeDetector = null;
    this.scanningActive = false;
    this.lastScannedBarcode = null;
    this.lastScanTime = 0;
    this.modal = null;
    
    this._createModal();
  }
  
  /**
   * Create modal DOM structure
   */
  _createModal() {
    const modalHTML = `
      <div class="barcode-scanner-modal" id="barcodeScannerModal" style="display:none;">
        <div class="scanner-modal-overlay"></div>
        <div class="scanner-modal-content">
          <div class="scanner-modal-header">
            <h3><i class="bi bi-upc-scan"></i> Scan Barcode</h3>
            <button class="scanner-close-btn" id="scannerCloseBtn" aria-label="Close">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          
          <div class="scanner-modal-body">
            <!-- Camera View -->
            <div class="scanner-video-wrapper">
              <video id="scannerVideo" autoplay playsinline muted></video>
              <div class="scanner-overlay-ui">
                <div class="scan-frame"></div>
                <div class="scan-line"></div>
              </div>
              <div class="scanner-status" id="scannerStatus">
                <i class="bi bi-camera"></i>
                <p>Initializing camera...</p>
              </div>
            </div>
            
            <!-- Manual Input Fallback -->
            <div class="scanner-manual-input">
              <label for="manualBarcodeInput">Or enter manually:</label>
              <div class="input-group">
                <input type="text" 
                       id="manualBarcodeInput" 
                       class="form-control" 
                       placeholder="Type or paste barcode"
                       autocomplete="off">
                <button class="btn btn-primary" id="manualBarcodeSubmit">
                  <i class="bi bi-check-lg"></i> Use
                </button>
              </div>
            </div>
            
            <!-- Instructions -->
            <div class="scanner-instructions">
              <p><i class="bi bi-info-circle"></i> Position the barcode within the frame</p>
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
    const closeBtn = this.modal.querySelector('#scannerCloseBtn');
    closeBtn.addEventListener('click', () => this.close());
    
    // Overlay click to close
    const overlay = this.modal.querySelector('.scanner-modal-overlay');
    overlay.addEventListener('click', () => this.close());
    
    // Manual input submit
    const manualSubmit = this.modal.querySelector('#manualBarcodeSubmit');
    manualSubmit.addEventListener('click', () => this._handleManualInput());
    
    const manualInput = this.modal.querySelector('#manualBarcodeInput');
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
      this._showStatus('Camera unavailable. Use manual input.', 'error');
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
    const manualInput = this.modal.querySelector('#manualBarcodeInput');
    if (manualInput) manualInput.value = '';
    
    this.options.onClose();
  }
  
  /**
   * Start camera and barcode detection
   */
  async _startCamera() {
    try {
      this._showStatus('Requesting camera access...', 'info');
      
      // Request front camera (user preference)
      this.videoStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });
      
      const video = this.modal.querySelector('#scannerVideo');
      video.srcObject = this.videoStream;
      
      // Hide status overlay
      this._hideStatus();
      
      // Initialize BarcodeDetector if available
      if ('BarcodeDetector' in window) {
        try {
          const supportedFormats = await BarcodeDetector.getSupportedFormats();
          const formats = this.options.formats.filter(f => 
            supportedFormats.includes(f)
          );
          
          this.barcodeDetector = new BarcodeDetector({ formats });
          this.scanningActive = true;
          this._scanLoop();
        } catch (err) {
          console.warn('BarcodeDetector initialization failed:', err);
          this._showStatus('Camera active. Use manual input for barcode.', 'warning');
        }
      } else {
        this._showStatus('Camera active. BarcodeDetector not supported - use manual input.', 'warning');
      }
    } catch (error) {
      console.error('Camera access error:', error);
      
      if (error.name === 'NotAllowedError') {
        this._showStatus('Camera permission denied. Please use manual input.', 'error');
      } else if (error.name === 'NotFoundError') {
        this._showStatus('No camera found. Please use manual input.', 'error');
      } else {
        this._showStatus('Camera error. Please use manual input.', 'error');
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
    
    const video = this.modal.querySelector('#scannerVideo');
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
      const video = this.modal.querySelector('#scannerVideo');
      
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        const barcodes = await this.barcodeDetector.detect(video);
        
        if (barcodes.length > 0) {
          const barcode = barcodes[0].rawValue;
          const now = Date.now();
          
          // Debounce: ignore same barcode within debounceMs
          if (barcode !== this.lastScannedBarcode || (now - this.lastScanTime) >= this.options.debounceMs) {
            this.lastScannedBarcode = barcode;
            this.lastScanTime = now;
            
            // Success feedback
            this._showSuccessFeedback();
            
            // Call callback
            this.options.onScan(barcode);
            
            // Auto-close after successful scan
            setTimeout(() => this.close(), 500);
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
   * Handle manual barcode input
   */
  _handleManualInput() {
    const input = this.modal.querySelector('#manualBarcodeInput');
    const barcode = input.value.trim();
    
    if (barcode) {
      this.options.onScan(barcode);
      this.close();
    }
  }
  
  /**
   * Show status message
   */
  _showStatus(message, type = 'info') {
    const statusDiv = this.modal.querySelector('#scannerStatus');
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
    const statusDiv = this.modal.querySelector('#scannerStatus');
    statusDiv.style.display = 'none';
  }
  
  /**
   * Show success feedback animation
   */
  _showSuccessFeedback() {
    const frame = this.modal.querySelector('.scan-frame');
    frame.style.borderColor = '#10b981';
    frame.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.5)';
    
    setTimeout(() => {
      frame.style.borderColor = '';
      frame.style.boxShadow = '';
    }, 500);
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
  module.exports = BarcodeScanner;
}
if (typeof window !== 'undefined') {
  window.BarcodeScanner = BarcodeScanner;
}

