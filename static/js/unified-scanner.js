/**
 * Unified Scanner Module - Circuit City
 * =====================================
 * 
 * Single reusable scanner for IMEI and Barcodes across the entire app.
 * 
 * Features:
 * - Mode: "imei" or "barcode"
 * - BarcodeDetector API with ZXing fallback for iPhone Safari
 * - Numbered pick-list for multiple IMEIs (no "invalid checksum" errors)
 * - Rear camera by default (facingMode: environment)
 * - Clean modal lifecycle with proper camera cleanup
 * - Auto-fill target input field with event dispatching
 * 
 * Usage:
 * ------
 * const scanner = new UnifiedScanner({
 *   mode: 'imei',  // or 'barcode'
 *   targetInput: '#imei-input',  // element or selector
 *   onSelect: (value) => console.log('Selected:', value)
 * });
 * scanner.open();
 */

(function() {
  'use strict';

  // ZXing library loaded flag
  let zxingLoaded = false;
  let zxingLoadPromise = null;

  /**
   * Dynamically load ZXing library for fallback scanning
   */
  function loadZXing() {
    if (zxingLoaded) return Promise.resolve();
    if (zxingLoadPromise) return zxingLoadPromise;

    zxingLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/@zxing/library@latest/umd/index.min.js';
      script.onload = () => {
        zxingLoaded = true;
        console.log('[UnifiedScanner] ZXing library loaded');
        resolve();
      };
      script.onerror = () => {
        console.error('[UnifiedScanner] Failed to load ZXing library');
        reject(new Error('Failed to load ZXing'));
      };
      document.head.appendChild(script);
    });

    return zxingLoadPromise;
  }

  /**
   * Extract 15-digit IMEI candidates from text
   */
  function extractIMEICandidates(text) {
    if (!text) return [];
    
    // Remove common separators
    const cleaned = text.replace(/[\s\-_./]/g, '');
    
    // Find all 15-digit sequences
    const regex = /\d{15}/g;
    const matches = cleaned.match(regex) || [];
    
    // Deduplicate
    return [...new Set(matches)];
  }

  /**
   * Luhn checksum validation (silent, for sorting only)
   */
  function validateLuhn(imei) {
    if (!imei || imei.length !== 15 || !/^\d{15}$/.test(imei)) {
      return false;
    }
    
    let sum = 0;
    let shouldDouble = false;
    
    // Process from right to left (excluding check digit)
    for (let i = 13; i >= 0; i--) {
      let digit = parseInt(imei[i], 10);
      
      if (shouldDouble) {
        digit *= 2;
        if (digit > 9) digit -= 9;
      }
      
      sum += digit;
      shouldDouble = !shouldDouble;
    }
    
    const checkDigit = parseInt(imei[14], 10);
    const calculatedCheck = (10 - (sum % 10)) % 10;
    
    return checkDigit === calculatedCheck;
  }

  /**
   * UnifiedScanner Class
   */
  class UnifiedScanner {
    constructor(options = {}) {
      this.options = {
        mode: options.mode || 'barcode', // 'imei' or 'barcode'
        targetInput: options.targetInput || null,
        onSelect: options.onSelect || ((value) => console.log('Selected:', value)),
        onClose: options.onClose || (() => {}),
        onError: options.onError || ((error) => console.error('Scanner error:', error)),
        throttleMs: options.throttleMs || 100, // Scan loop throttle (10fps)
        debounceMs: options.debounceMs || 1500
      };

      this.isOpen = false;
      this.videoStream = null;
      this.videoTrack = null;
      this.scanningActive = false;
      this.currentFacingMode = 'environment'; // Default to rear camera
      
      // Detection engines
      this.barcodeDetector = null;
      this.zxingReader = null;
      this.useZXingFallback = false;
      
      // Candidates tracking (for IMEI mode)
      this.candidates = new Map(); // Map<value, {timestamp, valid}>
      this.lastScanTime = 0;
      
      // DOM references
      this.modal = null;
      this.videoElement = null;
      this.statusElement = null;
      this.candidatesListElement = null;
      this.confirmPanel = null;
      this.confirmCodeElement = null;
      
      // Confirmation state
      this.pendingBarcodeValue = null;
      
      this.init();
    }

    init() {
      this.createModal();
      this.attachEventListeners();
      this.checkBarcodeDetectorSupport();
    }

    /**
     * Check BarcodeDetector support, fallback to ZXing if needed
     */
    async checkBarcodeDetectorSupport() {
      if ('BarcodeDetector' in window) {
        try {
          const formats = [
            'code_128', 'code_39', 'code_93',
            'ean_13', 'ean_8', 'upc_a', 'upc_e',
            'itf', 'qr_code', 'data_matrix', 'pdf417'
          ];
          
          this.barcodeDetector = new BarcodeDetector({ formats });
          console.log('[UnifiedScanner] Using BarcodeDetector API');
          this.useZXingFallback = false;
          return;
        } catch (e) {
          console.warn('[UnifiedScanner] BarcodeDetector failed, will use ZXing fallback:', e);
        }
      }
      
      // BarcodeDetector not available, use ZXing
      console.log('[UnifiedScanner] BarcodeDetector not available, will use ZXing fallback');
      this.useZXingFallback = true;
    }

    /**
     * Create modal DOM structure
     */
    createModal() {
      const title = this.options.mode === 'imei' ? 'Scan IMEI' : 'Scan Barcode';
      const icon = this.options.mode === 'imei' ? 'bi-phone' : 'bi-upc-scan';
      
      const candidatesSection = this.options.mode === 'imei' ? `
        <div class="unified-scanner-candidates" id="scannerCandidates">
          <h4>
            <i class="bi bi-list-check"></i> Found IMEIs
            <span class="badge bg-secondary" id="candidateCount">0</span>
          </h4>
          <div class="candidates-list" id="candidatesList">
            <div class="candidates-empty">
              <i class="bi bi-search"></i>
              <p>Scanning for IMEIs...</p>
              <small>Point camera at IMEI barcode or label</small>
            </div>
          </div>
        </div>
      ` : '';
      
      const manualSection = this.options.mode === 'imei' ? `
        <div class="unified-scanner-manual">
          <label for="scannerManualInput" class="form-label">
            <i class="bi bi-keyboard"></i> Manual Entry / Paste
          </label>
          <div class="input-group">
            <input 
              type="text" 
              class="form-control" 
              id="scannerManualInput" 
              placeholder="Type or paste ${this.options.mode === 'imei' ? 'IMEI (15 digits)' : 'barcode'}"
              maxlength="${this.options.mode === 'imei' ? '15' : '50'}"
              inputmode="${this.options.mode === 'imei' ? 'numeric' : 'text'}"
              autocomplete="off"
            >
            <button class="btn btn-outline-primary" type="button" id="addManualBtn">
              <i class="bi bi-plus-circle"></i> ${this.options.mode === 'imei' ? 'Add' : 'Use'}
            </button>
          </div>
        </div>
      ` : '';

      const modalHTML = `
        <div class="unified-scanner-modal" id="unifiedScannerModal">
          <div class="unified-scanner-overlay" data-close-scanner></div>
          <div class="unified-scanner-content">
            <div class="unified-scanner-header">
              <h3>
                <i class="bi ${icon}"></i> ${title}
              </h3>
              <button type="button" class="unified-scanner-close" data-close-scanner aria-label="Close scanner">
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
            
            <div class="unified-scanner-body">
              <!-- Camera Preview -->
              <div class="unified-scanner-video-container">
                <video id="unifiedScannerVideo" autoplay playsinline muted></video>
                <div class="unified-scanner-overlay-ui">
                  <div class="scan-frame"></div>
                  <div class="scan-line"></div>
                </div>
                <div class="unified-scanner-status" id="scannerStatus">
                  Initializing camera...
                </div>
                <!-- Barcode Confirmation Panel -->
                <div class="scan-confirm" id="scanConfirm" hidden>
                  <div class="scan-confirm-code" id="scanConfirmCode"></div>
                  <div class="scan-confirm-actions">
                    <button type="button" class="btn btn-primary scan-use" id="scanUseBtn">
                      <i class="bi bi-check-circle-fill"></i> Use
                    </button>
                    <button type="button" class="btn btn-outline-secondary scan-again" id="scanAgainBtn">
                      <i class="bi bi-arrow-repeat"></i> Scan Again
                    </button>
                  </div>
                  <div class="scan-confirm-hint">
                    Barcode detected and filled. Tap <strong>Use</strong> to continue or <strong>Scan Again</strong> to rescan.
                  </div>
                </div>
              </div>
              
              <!-- Camera Controls -->
              <div class="unified-scanner-controls">
                <button type="button" class="btn btn-sm btn-primary" id="startCameraBtn">
                  <i class="bi bi-camera-video"></i> Start Camera
                </button>
                <button type="button" class="btn btn-sm btn-danger" id="stopCameraBtn" style="display:none;">
                  <i class="bi bi-stop-circle"></i> Stop Camera
                </button>
                <button type="button" class="btn btn-sm btn-secondary" id="switchCameraBtn" style="display:none;">
                  <i class="bi bi-arrow-repeat"></i> Switch Camera
                </button>
              </div>
              
              ${manualSection}
              ${candidatesSection}
            </div>
            
            <div class="unified-scanner-footer">
              <button type="button" class="btn btn-secondary" data-close-scanner>
                <i class="bi bi-x-circle"></i> Cancel
              </button>
            </div>
          </div>
        </div>
      `;
      
      const container = document.createElement('div');
      container.innerHTML = modalHTML;
      this.modal = container.firstElementChild;
      document.body.appendChild(this.modal);
      
      // Cache DOM references
      this.videoElement = this.modal.querySelector('#unifiedScannerVideo');
      this.statusElement = this.modal.querySelector('#scannerStatus');
      this.candidatesListElement = this.modal.querySelector('#candidatesList');
      this.manualInput = this.modal.querySelector('#scannerManualInput');
      this.confirmPanel = this.modal.querySelector('#scanConfirm');
      this.confirmCodeElement = this.modal.querySelector('#scanConfirmCode');
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
      // Close handlers
      this.modal.querySelectorAll('[data-close-scanner]').forEach(el => {
        el.addEventListener('click', () => this.close());
      });
      
      // Camera controls
      const startBtn = this.modal.querySelector('#startCameraBtn');
      const stopBtn = this.modal.querySelector('#stopCameraBtn');
      const switchBtn = this.modal.querySelector('#switchCameraBtn');
      
      if (startBtn) startBtn.addEventListener('click', () => this.startCamera());
      if (stopBtn) stopBtn.addEventListener('click', () => this.stopCamera());
      if (switchBtn) switchBtn.addEventListener('click', () => this.switchCamera());
      
      // Manual input (IMEI mode)
      if (this.options.mode === 'imei' && this.manualInput) {
        const addBtn = this.modal.querySelector('#addManualBtn');
        
        this.manualInput.addEventListener('input', (e) => {
          // Only allow digits
          e.target.value = e.target.value.replace(/\D/g, '');
        });
        
        this.manualInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            this.addManualValue();
          }
        });
        
        if (addBtn) {
          addBtn.addEventListener('click', () => this.addManualValue());
        }
      }
      
      // Manual input (barcode mode)
      if (this.options.mode === 'barcode' && this.manualInput) {
        const useBtn = this.modal.querySelector('#addManualBtn');
        
        this.manualInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            this.useManualBarcode();
          }
        });
        
        if (useBtn) {
          useBtn.addEventListener('click', () => this.useManualBarcode());
        }
      }
      
      // Barcode confirmation buttons
      if (this.confirmPanel) {
        const useBtn = this.modal.querySelector('#scanUseBtn');
        const againBtn = this.modal.querySelector('#scanAgainBtn');
        
        if (useBtn) {
          useBtn.addEventListener('click', () => this.confirmUseBarcode());
        }
        
        if (againBtn) {
          againBtn.addEventListener('click', () => this.confirmScanAgain());
        }
      }
      
      // ESC key to close
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.isOpen) {
          this.close();
        }
      });
    }

    /**
     * Open scanner modal
     */
    async open() {
      // Resolve target input (optional for barcode mode with onSelect callback)
      if (this.options.targetInput) {
        if (typeof this.options.targetInput === 'string') {
          this.targetInput = document.querySelector(this.options.targetInput);
        } else {
          this.targetInput = this.options.targetInput;
        }
        
        if (!this.targetInput) {
          console.error('[UnifiedScanner] Target input not found:', this.options.targetInput);
          return;
        }
      } else if (this.options.mode === 'imei') {
        // IMEI mode requires targetInput
        console.error('[UnifiedScanner] IMEI mode requires targetInput');
        return;
      }
      // Barcode mode can work without targetInput (using onSelect callback)
      
      this.isOpen = true;
      this.modal.classList.add('active');
      document.body.style.overflow = 'hidden';
      
      // Reset state
      this.candidates.clear();
      if (this.candidatesListElement) {
        this.updateCandidatesList();
      }
      if (this.manualInput) {
        this.manualInput.value = '';
      }
      
      // Hide confirmation panel
      this.hideConfirmPanel();
      
      // Try to start camera automatically
      await this.startCamera();
    }

    /**
     * Close scanner modal
     */
    close() {
      this.isOpen = false;
      this.modal.classList.remove('active');
      document.body.style.overflow = '';
      
      // Always stop camera and release tracks
      this.stopCamera();
      
      // Double-check: force stop all video tracks (prevent camera staying active)
      if (this.videoElement && this.videoElement.srcObject) {
        const stream = this.videoElement.srcObject;
        if (stream) {
          stream.getTracks().forEach(track => {
            track.stop();
            track.enabled = false;
          });
        }
        this.videoElement.srcObject = null;
      }
      
      this.candidates.clear();
      if (this.candidatesListElement) {
        this.updateCandidatesList();
      }
      
      this.hideConfirmPanel();
      
      this.options.onClose();
    }

    /**
     * Start camera with rear camera preference
     */
    async startCamera() {
      this.showStatus('Requesting camera access...', 'info');
      
      try {
        // ALWAYS request rear camera first (environment = rear camera)
        const constraints = {
          video: {
            facingMode: { ideal: this.currentFacingMode },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: false
        };
        
        this.videoStream = await navigator.mediaDevices.getUserMedia(constraints);
        this.videoTrack = this.videoStream.getVideoTracks()[0];
        
        this.videoElement.srcObject = this.videoStream;
        await this.videoElement.play();
        
        // Update UI
        this.modal.querySelector('#startCameraBtn').style.display = 'none';
        this.modal.querySelector('#stopCameraBtn').style.display = 'inline-flex';
        this.modal.querySelector('#switchCameraBtn').style.display = 'inline-flex';
        
        const settings = this.videoTrack.getSettings();
        const facingMode = settings.facingMode || 'unknown';
        const facingLabel = facingMode === 'environment' ? 'Rear Camera' : 
                           facingMode === 'user' ? 'Front Camera' : 'Camera';
        
        this.showStatus(`📹 ${facingLabel} Active - Scanning...`, 'success');
        
        // Start scanning
        await this.startScanning();
        
      } catch (error) {
        console.error('[UnifiedScanner] Camera access error:', error);
        
        let message = 'Camera not available. ';
        if (error.name === 'NotAllowedError') {
          message += 'Permission denied. Please allow camera access.';
        } else if (error.name === 'NotFoundError') {
          message += 'No camera found on this device.';
        } else if (error.name === 'NotReadableError') {
          message += 'Camera is in use by another app.';
        } else {
          message += 'Please use manual entry.';
        }
        
        this.showStatus(message, 'error');
        this.modal.querySelector('#startCameraBtn').style.display = 'inline-flex';
        this.options.onError(error);
      }
    }

    /**
     * Stop camera and cleanup
     */
    stopCamera() {
      this.scanningActive = false;
      
      if (this.videoStream) {
        this.videoStream.getTracks().forEach(track => {
          track.stop();
          track.enabled = false;
        });
        this.videoStream = null;
        this.videoTrack = null;
      }
      
      if (this.videoElement) {
        this.videoElement.srcObject = null;
      }
      
      // Update UI
      this.modal.querySelector('#startCameraBtn').style.display = 'inline-flex';
      this.modal.querySelector('#stopCameraBtn').style.display = 'none';
      this.modal.querySelector('#switchCameraBtn').style.display = 'none';
      
      this.showStatus('Camera stopped', 'info');
    }

    /**
     * Switch camera (front <-> rear)
     */
    async switchCamera() {
      if (!this.videoTrack) return;
      
      const currentFacing = this.videoTrack.getSettings().facingMode || 'environment';
      this.currentFacingMode = currentFacing === 'environment' ? 'user' : 'environment';
      
      this.stopCamera();
      await this.startCamera();
    }

    /**
     * Start scanning loop
     */
    async startScanning() {
      // If using ZXing fallback, load the library
      if (this.useZXingFallback && !zxingLoaded) {
        this.showStatus('Loading scanner library...', 'info');
        try {
          await loadZXing();
          // Initialize ZXing reader
          const codeReader = new ZXing.BrowserMultiFormatReader();
          this.zxingReader = codeReader;
          console.log('[UnifiedScanner] ZXing reader initialized');
        } catch (error) {
          console.error('[UnifiedScanner] Failed to initialize ZXing:', error);
          this.showStatus('Scanner library failed to load. Please use manual entry.', 'error');
          return;
        }
      }
      
      this.scanningActive = true;
      this.scanLoop();
    }

    /**
     * Scanning loop (throttled to ~10fps)
     */
    async scanLoop() {
      if (!this.scanningActive) return;
      
      try {
        if (this.videoElement.readyState === this.videoElement.HAVE_ENOUGH_DATA) {
          await this.captureAndDecode();
        }
      } catch (error) {
        // Silent fail during scanning loop
        console.debug('[UnifiedScanner] Scan error:', error);
      }
      
      // Throttle to ~10fps (100ms delay)
      setTimeout(() => {
        if (this.scanningActive) {
          requestAnimationFrame(() => this.scanLoop());
        }
      }, this.options.throttleMs);
    }

    /**
     * Capture frame and decode barcode/IMEI
     */
    async captureAndDecode() {
      let results = [];
      
      // Try BarcodeDetector first
      if (this.barcodeDetector && !this.useZXingFallback) {
        try {
          const barcodes = await this.barcodeDetector.detect(this.videoElement);
          results = barcodes.map(b => b.rawValue);
        } catch (e) {
          console.debug('[UnifiedScanner] BarcodeDetector error:', e);
        }
      }
      
      // Fallback to ZXing
      if (results.length === 0 && this.useZXingFallback && this.zxingReader) {
        try {
          const result = await this.zxingReader.decodeFromVideoElement(this.videoElement);
          if (result && result.text) {
            results = [result.text];
          }
        } catch (e) {
          // ZXing throws when no barcode found, which is normal
          if (e.name !== 'NotFoundException') {
            console.debug('[UnifiedScanner] ZXing error:', e);
          }
        }
      }
      
      // Process results
      if (results.length > 0) {
        for (const rawValue of results) {
          this.processDetection(rawValue);
        }
      }
    }

    /**
     * Process a detected value
     */
    processDetection(rawValue) {
      if (this.options.mode === 'imei') {
        // Extract IMEI candidates
        const candidates = extractIMEICandidates(rawValue);
        candidates.forEach(imei => {
          this.addCandidate(imei);
        });
      } else {
        // Barcode mode - show confirmation instead of auto-closing
        const now = Date.now();
        if (now - this.lastScanTime >= this.options.debounceMs) {
          this.lastScanTime = now;
          this.showBarcodeConfirmation(rawValue);
        }
      }
    }

    /**
     * Add IMEI candidate (IMEI mode only)
     */
    addCandidate(imei) {
      // Debounce: don't re-add if recently added
      if (this.candidates.has(imei)) {
        const existing = this.candidates.get(imei);
        if (Date.now() - existing.timestamp < 1500) {
          return; // Ignore
        }
        existing.timestamp = Date.now();
        return;
      }
      
      // Silently validate Luhn (for sorting only, don't show errors)
      const isValid = validateLuhn(imei);
      
      this.candidates.set(imei, {
        valid: isValid,
        timestamp: Date.now()
      });
      
      this.updateCandidatesList();
      
      // Vibrate feedback
      if (navigator.vibrate) {
        navigator.vibrate(50);
      }
    }

    /**
     * Update candidates list UI (IMEI mode)
     */
    updateCandidatesList() {
      if (!this.candidatesListElement) return;
      
      const count = this.candidates.size;
      const countBadge = this.modal.querySelector('#candidateCount');
      if (countBadge) countBadge.textContent = count;
      
      if (count === 0) {
        this.candidatesListElement.innerHTML = `
          <div class="candidates-empty">
            <i class="bi bi-search"></i>
            <p>Scanning for IMEIs...</p>
            <small>Point camera at IMEI barcode or label</small>
          </div>
        `;
        return;
      }
      
      // Sort: valid IMEIs first, then by timestamp (newest first)
      const sorted = Array.from(this.candidates.entries())
        .sort((a, b) => {
          if (a[1].valid !== b[1].valid) {
            return b[1].valid ? 1 : -1; // Valid first
          }
          return b[1].timestamp - a[1].timestamp; // Newest first
        });
      
      let html = '';
      sorted.forEach(([imei, data], index) => {
        const number = index + 1;
        html += `
          <div class="candidate-item" data-imei="${imei}">
            <div class="candidate-number">${number}</div>
            <div class="candidate-value">${imei}</div>
            <button type="button" class="candidate-select" data-imei="${imei}">
              <i class="bi bi-check2"></i> Use
            </button>
          </div>
        `;
      });
      
      this.candidatesListElement.innerHTML = html;
      
      // Attach click handlers
      this.candidatesListElement.querySelectorAll('.candidate-select').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const imei = e.target.closest('[data-imei]').dataset.imei;
          this.selectValue(imei);
        });
      });
      
      // Also make whole row clickable
      this.candidatesListElement.querySelectorAll('.candidate-item').forEach(item => {
        item.addEventListener('click', (e) => {
          if (!e.target.closest('.candidate-select')) {
            const imei = item.dataset.imei;
            this.selectValue(imei);
          }
        });
      });
    }

    /**
     * Add manual value (IMEI mode)
     */
    addManualValue() {
      if (!this.manualInput) return;
      
      const value = this.manualInput.value.trim();
      if (!value) return;
      
      if (value.length === 15 && /^\d{15}$/.test(value)) {
        this.addCandidate(value);
        this.manualInput.value = '';
      } else {
        this.showStatus('IMEI must be exactly 15 digits', 'error');
      }
    }

    /**
     * Use manual barcode (barcode mode)
     */
    useManualBarcode() {
      if (!this.manualInput) return;
      
      const value = this.manualInput.value.trim();
      if (value) {
        // Show confirmation panel instead of directly closing
        this.showBarcodeConfirmation(value);
      }
    }

    /**
     * Show barcode confirmation panel (barcode mode)
     */
    showBarcodeConfirmation(value) {
      if (!this.confirmPanel || !this.confirmCodeElement) {
        // Fallback: if no confirmation panel, use old behavior
        this.selectValue(value);
        return;
      }
      
      // Pause scanning
      this.scanningActive = false;
      
      // Store the barcode value
      this.pendingBarcodeValue = value;
      
      // Fill the target input (if provided)
      if (this.targetInput) {
        this.targetInput.value = value;
        this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
        this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
      
      // Show confirmation panel
      this.confirmCodeElement.textContent = value;
      this.confirmPanel.hidden = false;
      
      // Vibrate feedback
      if (navigator.vibrate) {
        navigator.vibrate([50, 100, 50]);
      }
      
      console.log('[UnifiedScanner] Barcode detected, showing confirmation:', value);
    }

    /**
     * Hide barcode confirmation panel
     */
    hideConfirmPanel() {
      if (this.confirmPanel) {
        this.confirmPanel.hidden = true;
      }
      this.pendingBarcodeValue = null;
    }

    /**
     * User confirmed to use the scanned barcode
     */
    confirmUseBarcode() {
      console.log('[UnifiedScanner] User confirmed barcode:', this.pendingBarcodeValue);
      
      // Call the onSelect callback
      if (this.pendingBarcodeValue) {
        this.options.onSelect(this.pendingBarcodeValue);
      }
      
      // Close the modal
      this.close();
    }

    /**
     * User wants to scan again
     */
    confirmScanAgain() {
      console.log('[UnifiedScanner] User requested rescan');
      
      // Clear the input if targetInput is provided
      if (this.targetInput) {
        this.targetInput.value = '';
        this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
        this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
      
      // Hide confirmation panel
      this.hideConfirmPanel();
      
      // Resume scanning
      this.scanningActive = true;
      this.scanLoop();
      
      this.showStatus('📹 Scanning resumed...', 'info');
    }

    /**
     * Select a value and fill target input (if provided) or call callback
     */
    selectValue(value) {
      // Fill the input if targetInput is provided
      if (this.targetInput) {
        this.targetInput.value = value;
        
        // Trigger events so existing validation/button-enable logic updates
        setTimeout(() => {
          this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
          this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
          this.targetInput.dispatchEvent(new Event('keyup', { bubbles: true }));
          
          // Focus the input
          this.targetInput.focus();
        }, 50);
      }
      
      // Always call onSelect callback
      this.options.onSelect(value);
      
      // Close modal
      this.close();
      
      // Vibrate confirmation
      if (navigator.vibrate) {
        navigator.vibrate([50, 100, 50]);
      }
    }

    /**
     * Show status message
     */
    showStatus(message, type = 'info') {
      if (!this.statusElement) return;
      
      const icons = {
        info: 'bi-info-circle',
        success: 'bi-check-circle',
        error: 'bi-x-circle',
        warning: 'bi-exclamation-triangle'
      };
      
      this.statusElement.innerHTML = `
        <i class="bi ${icons[type] || icons.info}"></i>
        <p>${message}</p>
      `;
      this.statusElement.className = `unified-scanner-status status-${type}`;
      this.statusElement.style.display = 'flex';
      
      // Auto-hide success/info after 3 seconds
      if (type === 'success' || type === 'info') {
        setTimeout(() => {
          if (this.statusElement && this.statusElement.querySelector('p')?.textContent === message) {
            this.statusElement.style.display = 'none';
          }
        }, 3000);
      }
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

  // Export to global scope
  window.UnifiedScanner = UnifiedScanner;
  
  /**
   * Helper function to initialize scanner from data attributes
   * Usage: <button data-scanner-trigger="imei" data-scanner-target="#imei-input">Scan</button>
   */
  function setupScannerTriggers() {
    document.querySelectorAll('[data-scanner-trigger]').forEach(button => {
      // Skip if already initialized
      if (button.dataset.scannerInitialized === 'true') return;
      button.dataset.scannerInitialized = 'true';
      
      button.addEventListener('click', function(e) {
        e.preventDefault();
        
        const mode = this.dataset.scannerTrigger; // 'imei' or 'barcode'
        const targetInput = this.dataset.scannerTarget;
        
        if (!targetInput) {
          console.error('[UnifiedScanner] data-scanner-target not specified');
          return;
        }
        
        const scanner = new UnifiedScanner({
          mode: mode,
          targetInput: targetInput,
          onSelect: (value) => {
            console.log(`[UnifiedScanner] Selected ${mode}:`, value);
          }
        });
        
        scanner.open();
      });
    });
  }
  
  // Auto-initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupScannerTriggers);
  } else {
    setupScannerTriggers();
  }
  
  // Expose setup function
  window.UnifiedScanner.setup = setupScannerTriggers;

})();

