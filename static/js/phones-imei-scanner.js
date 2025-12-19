/**
 * Phones IMEI Scanner Modal
 * =========================
 * Premium scanner modal for IMEI detection on Phones Scan IN + Scan & Sell
 * 
 * Features:
 * - Rear camera by default (fallback to front if unavailable)
 * - Animated scan line overlay
 * - IMEI detection from barcodes + manual assist
 * - Luhn checksum validation
 * - Deduped candidate list (newest on top)
 * - Graceful fallbacks if camera not available
 * - Mobile-first responsive design
 */

(function() {
  'use strict';

  // ===== IMEI Validation Helpers =====
  
  /**
   * Extract 15-digit candidates from a string
   */
  function extractIMEICandidates(text) {
    if (!text) return [];
    
    // Remove common separators and spaces
    const cleaned = text.replace(/[\s\-_./]/g, '');
    
    // Find all 15-digit sequences
    const regex = /\d{15}/g;
    const matches = cleaned.match(regex) || [];
    
    return [...new Set(matches)]; // Dedupe
  }
  
  /**
   * Validate IMEI using Luhn algorithm
   * @param {string} imei - 15-digit IMEI string
   * @returns {boolean}
   */
  function validateIMEILuhn(imei) {
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
        if (digit > 9) {
          digit -= 9;
        }
      }
      
      sum += digit;
      shouldDouble = !shouldDouble;
    }
    
    const checkDigit = parseInt(imei[14], 10);
    const calculatedCheck = (10 - (sum % 10)) % 10;
    
    return checkDigit === calculatedCheck;
  }
  
  /**
   * Normalize IMEI string
   */
  function normalizeIMEI(text) {
    return text.replace(/\D/g, '').slice(0, 15);
  }

  // ===== Scanner Modal Class =====
  
  class IMEIScannerModal {
    constructor() {
      this.isOpen = false;
      this.targetInput = null;
      this.videoStream = null;
      this.videoTrack = null;
      this.scanInterval = null;
      this.barcodeDetector = null;
      this.candidates = new Map(); // Map<imei, {valid, timestamp}>
      
      this.modal = null;
      this.videoElement = null;
      this.candidatesList = null;
      this.manualInput = null;
      
      this.init();
    }
    
    init() {
      this.createModal();
      this.attachEventListeners();
      this.checkBarcodeDetectorSupport();
    }
    
    checkBarcodeDetectorSupport() {
      if ('BarcodeDetector' in window) {
        try {
          // Support ALL major barcode formats for maximum IMEI detection
          this.barcodeDetector = new BarcodeDetector({
            formats: [
              'code_128',
              'code_39', 
              'code_93',
              'ean_13', 
              'ean_8', 
              'upc_a', 
              'upc_e', 
              'itf',
              'qr_code',
              'data_matrix',
              'pdf417'
            ]
          });
        } catch (e) {
          console.warn('BarcodeDetector not fully supported, using fallback formats:', e);
          // Fallback to basic formats if advanced ones fail
          try {
            this.barcodeDetector = new BarcodeDetector({
              formats: ['code_128', 'code_39', 'ean_13', 'qr_code']
            });
          } catch (e2) {
            console.warn('BarcodeDetector not supported at all:', e2);
          }
        }
      }
    }
    
    createModal() {
      const modalHTML = `
        <div class="imei-scanner-modal" id="imeiScannerModal" role="dialog" aria-modal="true" aria-labelledby="scannerModalTitle">
          <div class="imei-scanner-overlay" data-close-modal></div>
          <div class="imei-scanner-content">
            <div class="imei-scanner-header">
              <h3 id="scannerModalTitle">
                <i class="bi bi-upc-scan"></i> Scan IMEI
              </h3>
              <button type="button" class="imei-scanner-close" data-close-modal aria-label="Close scanner">
                <i class="bi bi-x-lg"></i>
              </button>
            </div>
            
            <div class="imei-scanner-body">
              <!-- Camera Preview -->
              <div class="imei-scanner-video-container" id="videoContainer">
                <video id="scannerVideo" autoplay playsinline muted></video>
                <div class="imei-scanner-scan-overlay">
                  <div class="imei-scanner-scan-frame"></div>
                  <div class="imei-scanner-scan-line"></div>
                </div>
                <div class="imei-scanner-status" id="scannerStatus">
                  Initializing camera...
                </div>
              </div>
              
              <!-- Camera Controls -->
              <div class="imei-scanner-controls">
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
              
              <!-- Manual Assist Mode -->
              <div class="imei-scanner-manual">
                <label for="manualIMEIInput" class="form-label">
                  <i class="bi bi-keyboard"></i> Manual Entry / Paste
                </label>
                <div class="input-group">
                  <input 
                    type="text" 
                    class="form-control" 
                    id="manualIMEIInput" 
                    placeholder="Type or paste IMEI (15 digits)"
                    maxlength="15"
                    inputmode="numeric"
                    autocomplete="off"
                  >
                  <button class="btn btn-outline-primary" type="button" id="addManualBtn">
                    <i class="bi bi-plus-circle"></i> Add
                  </button>
                </div>
              </div>
              
              <!-- Found IMEIs -->
              <div class="imei-scanner-candidates">
                <h4>
                  <i class="bi bi-list-check"></i> Found IMEIs
                  <span class="badge bg-secondary" id="candidateCount">0</span>
                </h4>
                <div class="imei-candidates-list" id="candidatesList">
                  <div class="imei-candidates-empty">
                    <i class="bi bi-search"></i>
                    <p>Scanning for IMEIs...</p>
                    <small>Point camera at IMEI barcode or enter manually</small>
                  </div>
                </div>
              </div>
            </div>
            
            <div class="imei-scanner-footer">
              <button type="button" class="btn btn-secondary" data-close-modal>
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
      this.videoElement = this.modal.querySelector('#scannerVideo');
      this.candidatesList = this.modal.querySelector('#candidatesList');
      this.manualInput = this.modal.querySelector('#manualIMEIInput');
      this.statusElement = this.modal.querySelector('#scannerStatus');
      this.videoContainer = this.modal.querySelector('#videoContainer');
    }
    
    attachEventListeners() {
      // Close modal handlers
      this.modal.querySelectorAll('[data-close-modal]').forEach(el => {
        el.addEventListener('click', () => this.close());
      });
      
      // Camera controls
      this.modal.querySelector('#startCameraBtn').addEventListener('click', () => this.startCamera());
      this.modal.querySelector('#stopCameraBtn').addEventListener('click', () => this.stopCamera());
      this.modal.querySelector('#switchCameraBtn').addEventListener('click', () => this.switchCamera());
      
      // Manual input
      this.modal.querySelector('#addManualBtn').addEventListener('click', () => this.addManualIMEI());
      this.manualInput.addEventListener('input', (e) => {
        e.target.value = normalizeIMEI(e.target.value);
      });
      this.manualInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.addManualIMEI();
        }
      });
      
      // ESC key to close
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.isOpen) {
          this.close();
        }
      });
    }
    
    async open(targetInputId) {
      this.targetInput = document.getElementById(targetInputId);
      if (!this.targetInput) {
        console.error('Target input not found:', targetInputId);
        return;
      }
      
      this.isOpen = true;
      this.modal.classList.add('active');
      document.body.style.overflow = 'hidden';
      
      // Reset state
      this.candidates.clear();
      this.updateCandidatesList();
      this.manualInput.value = '';
      
      // Try to start camera automatically
      await this.startCamera();
    }
    
    close() {
      this.isOpen = false;
      this.modal.classList.remove('active');
      document.body.style.overflow = '';
      
      // Always stop camera and release tracks (camera light off)
      this.stopCamera();
      
      // Double-check: force stop all video tracks
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
      this.updateCandidatesList();
    }
    
    async startCamera() {
      this.showStatus('Requesting camera access...');
      
      try {
        // Step 1: Check for cached rear camera deviceId
        const cachedRearId = localStorage.getItem('preferredRearCamId');
        let initialStream = null;
        
        if (cachedRearId) {
          console.log('[IMEI Scanner] Trying cached rear camera:', cachedRearId);
          try {
            initialStream = await navigator.mediaDevices.getUserMedia({
              video: { deviceId: { exact: cachedRearId } },
              audio: false
            });
            console.log('[IMEI Scanner] Cached rear camera successful');
          } catch (e) {
            console.warn('[IMEI Scanner] Cached camera failed, will enumerate:', e);
            localStorage.removeItem('preferredRearCamId');
          }
        }
        
        // Step 2: If no cached camera or cache failed, request with facingMode
        if (!initialStream) {
          const constraints = {
            video: {
              facingMode: { ideal: 'environment' },
              width: { ideal: 1920 },
              height: { ideal: 1080 }
            },
            audio: false
          };
          
          initialStream = await navigator.mediaDevices.getUserMedia(constraints);
          console.log('[IMEI Scanner] Initial camera permission granted');
        }
        
        // Step 3: Enumerate devices (labels now available after permission)
        const rearCameraInfo = await this.pickRearCameraDeviceId();
        
        if (rearCameraInfo) {
          const initialTrack = initialStream.getVideoTracks()[0];
          const initialSettings = initialTrack.getSettings();
          const initialLabel = initialTrack.label || '';
          const isFront = /front|user|selfie/i.test(initialLabel) || initialSettings.facingMode === 'user';
          
          console.log('[IMEI Scanner] Initial camera:', { 
            label: initialLabel, 
            facingMode: initialSettings.facingMode,
            isFront 
          });
          
          // Step 4: If we got front camera OR deviceId doesn't match best rear, switch
          if (isFront || initialSettings.deviceId !== rearCameraInfo.deviceId) {
            console.log('[IMEI Scanner] Switching to rear camera:', rearCameraInfo.label);
            this.showStatus('Switching to rear camera...');
            
            // Stop initial stream
            initialStream.getTracks().forEach(track => track.stop());
            
            // Request exact rear camera
            this.videoStream = await navigator.mediaDevices.getUserMedia({
              video: { 
                deviceId: { exact: rearCameraInfo.deviceId },
                width: { ideal: 1920 },
                height: { ideal: 1080 }
              },
              audio: false
            });
            
            // Cache the successful rear camera
            localStorage.setItem('preferredRearCamId', rearCameraInfo.deviceId);
            console.log('[IMEI Scanner] Rear camera set, cached deviceId');
          } else {
            // Already on rear camera
            this.videoStream = initialStream;
            localStorage.setItem('preferredRearCamId', rearCameraInfo.deviceId);
          }
        } else {
          // No rear camera identified, use whatever we got
          console.warn('[IMEI Scanner] Could not identify rear camera, using initial stream');
          this.videoStream = initialStream;
        }
        
        this.videoTrack = this.videoStream.getVideoTracks()[0];
        
        // Try to apply advanced camera settings (autofocus)
        try {
          const capabilities = this.videoTrack.getCapabilities();
          if (capabilities.focusMode && capabilities.focusMode.includes('continuous')) {
            await this.videoTrack.applyConstraints({
              advanced: [{ focusMode: 'continuous' }]
            });
          }
        } catch (e) {
          console.log('[IMEI Scanner] Advanced focus not supported:', e);
        }
        
        this.videoElement.srcObject = this.videoStream;
        await this.videoElement.play();
        
        // Update UI
        this.modal.querySelector('#startCameraBtn').style.display = 'none';
        this.modal.querySelector('#stopCameraBtn').style.display = 'inline-flex';
        this.modal.querySelector('#switchCameraBtn').style.display = 'inline-flex';
        
        const finalSettings = this.videoTrack.getSettings();
        const finalLabel = this.videoTrack.label || '';
        const finalFacingMode = finalSettings.facingMode || 'unknown';
        const isRearCamera = finalFacingMode === 'environment' || /back|rear|environment/i.test(finalLabel);
        const facingLabel = isRearCamera ? '📹 Rear Camera Active' : '📹 Front Camera Active';
        
        console.log('[IMEI Scanner] Final camera active:', { 
          label: finalLabel, 
          facingMode: finalFacingMode,
          deviceId: finalSettings.deviceId
        });
        
        this.showStatus(`${facingLabel} - Point at IMEI barcode`);
        
        // Start scanning
        this.startScanning();
        
      } catch (error) {
        console.error('Camera access error:', error);
        
        let message = 'Camera not available. ';
        if (error.name === 'NotAllowedError') {
          message += 'Permission denied. Please allow camera access and try again.';
        } else if (error.name === 'NotFoundError') {
          message += 'No camera found on this device.';
        } else if (error.name === 'NotReadableError') {
          message += 'Camera is in use by another app. Please close other apps and try again.';
        } else {
          message += 'Please use manual entry below.';
        }
        
        this.showStatus(message, 'error');
        this.modal.querySelector('#startCameraBtn').style.display = 'inline-flex';
      }
    }
    
    /**
     * Pick the best rear camera deviceId from enumerated devices
     * Returns: { deviceId, label } or null
     */
    async pickRearCameraDeviceId() {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = devices.filter(d => d.kind === 'videoinput');
        
        console.log('[IMEI Scanner] Available cameras:', videoInputs.map(d => ({ 
          label: d.label, 
          deviceId: d.deviceId.slice(0, 20) + '...' 
        })));
        
        if (videoInputs.length === 0) {
          console.warn('[IMEI Scanner] No video inputs found');
          return null;
        }
        
        // Priority 1: Explicit rear/back/environment label (MOST reliable)
        let rearCamera = videoInputs.find(d => 
          /back|rear|environment/i.test(d.label)
        );
        
        if (rearCamera) {
          console.log('[IMEI Scanner] Found rear camera by label:', rearCamera.label);
          return { deviceId: rearCamera.deviceId, label: rearCamera.label };
        }
        
        // Priority 2: Avoid front/user/selfie (find first that doesn't match)
        rearCamera = videoInputs.find(d => 
          !/front|user|selfie/i.test(d.label) && d.label.trim() !== ''
        );
        
        if (rearCamera) {
          console.log('[IMEI Scanner] Found non-front camera:', rearCamera.label);
          return { deviceId: rearCamera.deviceId, label: rearCamera.label };
        }
        
        // Priority 3: Pick last device (often rear on Android)
        if (videoInputs.length > 1) {
          rearCamera = videoInputs[videoInputs.length - 1];
          console.log('[IMEI Scanner] Using last camera (Android heuristic):', rearCamera.label);
          return { deviceId: rearCamera.deviceId, label: rearCamera.label };
        }
        
        // Fallback: Use any available camera
        rearCamera = videoInputs[0];
        console.log('[IMEI Scanner] Using fallback camera:', rearCamera.label);
        return { deviceId: rearCamera.deviceId, label: rearCamera.label };
        
      } catch (error) {
        console.error('[IMEI Scanner] Failed to enumerate devices:', error);
        return null;
      }
    }
    
    stopCamera() {
      if (this.scanInterval) {
        clearInterval(this.scanInterval);
        this.scanInterval = null;
      }
      
      if (this.videoStream) {
        this.videoStream.getTracks().forEach(track => track.stop());
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
      
      this.showStatus('Camera stopped');
    }
    
    async switchCamera() {
      if (!this.videoTrack) return;
      
      const currentSettings = this.videoTrack.getSettings();
      const currentDeviceId = currentSettings.deviceId;
      
      this.stopCamera();
      
      try {
        // Enumerate all cameras
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = devices.filter(d => d.kind === 'videoinput');
        
        if (videoInputs.length < 2) {
          this.showStatus('Only one camera available', 'info');
          await this.startCamera(); // Restart same camera
          return;
        }
        
        // Find the other camera (not the current one)
        const otherCamera = videoInputs.find(d => d.deviceId !== currentDeviceId);
        
        if (!otherCamera) {
          this.showStatus('Could not find alternate camera', 'error');
          return;
        }
        
        console.log('[IMEI Scanner] Switching to:', otherCamera.label);
        
        this.videoStream = await navigator.mediaDevices.getUserMedia({
          video: { 
            deviceId: { exact: otherCamera.deviceId },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: false
        });
        
        this.videoTrack = this.videoStream.getVideoTracks()[0];
        this.videoElement.srcObject = this.videoStream;
        await this.videoElement.play();
        
        this.modal.querySelector('#stopCameraBtn').style.display = 'inline-flex';
        this.modal.querySelector('#switchCameraBtn').style.display = 'inline-flex';
        
        const newLabel = this.videoTrack.label || '';
        const isRear = /back|rear|environment/i.test(newLabel);
        this.showStatus(`📹 ${isRear ? 'Rear' : 'Front'} Camera Active`);
        
        this.startScanning();
        
      } catch (error) {
        console.error('Camera switch error:', error);
        this.showStatus('Could not switch camera', 'error');
        this.modal.querySelector('#startCameraBtn').style.display = 'inline-flex';
      }
    }
    
    startScanning() {
      if (this.scanInterval) return;
      
      // Scan more frequently for better detection (every 300ms)
      this.scanInterval = setInterval(() => {
        this.captureAndScan();
      }, 300);
    }
    
    async captureAndScan() {
      if (!this.videoElement || this.videoElement.readyState !== 4) return;
      
      try {
        // Try BarcodeDetector API if available
        if (this.barcodeDetector) {
          const barcodes = await this.barcodeDetector.detect(this.videoElement);
          
          if (barcodes.length > 0) {
            const streamLabel = this.videoTrack?.label || '';
            console.log('[IMEI Scanner] Stream active:', streamLabel);
            
            // Multiple barcodes detected - process all of them
            for (const barcode of barcodes) {
              const candidates = extractIMEICandidates(barcode.rawValue);
              candidates.forEach(imei => {
                console.log('[IMEI Scanner] Detected:', imei, 'from', barcode.format);
                this.addCandidate(imei);
              });
            }
            
            // Show multi-detection feedback
            if (barcodes.length > 1) {
              this.showStatus(`🎯 Detected ${barcodes.length} codes - processing...`, 'info');
            }
          }
        }
        
        // Note: We're not implementing full OCR here to keep it lightweight
        // Users can use manual input or barcode scanning
        
      } catch (error) {
        // Silent fail during scanning (don't spam console)
      }
    }
    
    addManualIMEI() {
      const value = this.manualInput.value.trim();
      if (!value) return;
      
      const imei = normalizeIMEI(value);
      if (imei.length === 15) {
        this.addCandidate(imei);
        this.manualInput.value = '';
      } else {
        // ⚡ Show clear message, keep scanner open for retry
        this.showStatus('Invalid IMEI. IMEI must be 15 digits.', 'error');
      }
    }
    
    addCandidate(imei) {
      // Debounce: don't add same IMEI if added within last 1.5 seconds
      if (this.candidates.has(imei)) {
        const existing = this.candidates.get(imei);
        if (Date.now() - existing.timestamp < 1500) {
          return; // Ignore to reduce flicker
        }
        // Update timestamp
        existing.timestamp = Date.now();
        return;
      }
      
      // ⚡ ACCEPT ANY 15-DIGIT NUMERIC STRING (No Luhn validation required)
      // Business logic: If it's 15 digits, it's valid for scanning
      const isValid = (imei.length === 15 && /^\d{15}$/.test(imei));
      
      this.candidates.set(imei, {
        valid: isValid,
        timestamp: Date.now()
      });
      
      this.updateCandidatesList();
      
      if (isValid) {
        this.showStatus(`✅ IMEI detected: ${imei}`, 'success');
        
        // Vibrate if supported
        if (navigator.vibrate) {
          navigator.vibrate(50);
        }
      } else {
        // Should not reach here if extractIMEICandidates works correctly
        console.log(`Invalid IMEI format: ${imei}`);
      }
    }
    
    updateCandidatesList() {
      const count = this.candidates.size;
      this.modal.querySelector('#candidateCount').textContent = count;
      
      if (count === 0) {
        this.candidatesList.innerHTML = `
          <div class="imei-candidates-empty">
            <i class="bi bi-search"></i>
            <p>Scanning for IMEIs...</p>
            <small>Point camera at IMEI barcode or enter manually</small>
          </div>
        `;
        return;
      }
      
      // Sort by timestamp (newest first)
      const sorted = Array.from(this.candidates.entries())
        .sort((a, b) => b[1].timestamp - a[1].timestamp);
      
      let html = '';
      sorted.forEach(([imei, data]) => {
        const statusClass = data.valid ? 'valid' : 'invalid';
        const statusIcon = data.valid ? 'bi-check-circle-fill' : 'bi-x-circle-fill';
        const statusText = data.valid ? '15 digits' : 'Invalid';
        
        html += `
          <div class="imei-candidate-item ${statusClass}" data-imei="${imei}">
            <div class="imei-candidate-value">${imei}</div>
            <div class="imei-candidate-status">
              <i class="bi ${statusIcon}"></i> ${statusText}
            </div>
            ${data.valid ? '<button type="button" class="imei-candidate-select"><i class="bi bi-check2"></i> Use</button>' : ''}
          </div>
        `;
      });
      
      this.candidatesList.innerHTML = html;
      
      // Attach click handlers
      this.candidatesList.querySelectorAll('.imei-candidate-select').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const item = e.target.closest('.imei-candidate-item');
          const imei = item.dataset.imei;
          this.selectIMEI(imei);
        });
      });
    }
    
    selectIMEI(imei) {
      if (!this.targetInput) return;
      
      // Fill the input
      this.targetInput.value = imei;
      
      // Trigger input and change events so existing validation/lookup logic runs
      // Use setTimeout to ensure the value is set before events fire
      setTimeout(() => {
        this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
        this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Also trigger any keyup/blur listeners that might exist
        this.targetInput.dispatchEvent(new Event('keyup', { bubbles: true }));
        this.targetInput.dispatchEvent(new Event('blur', { bubbles: true }));
        
        // Focus the input to show visual feedback
        this.targetInput.focus();
      }, 50);
      
      // Close modal
      this.close();
      
      // Show success feedback
      if (navigator.vibrate) {
        navigator.vibrate([50, 100, 50]);
      }
    }
    
    showStatus(message, type = 'info') {
      if (!this.statusElement) return;
      
      this.statusElement.textContent = message;
      this.statusElement.className = 'imei-scanner-status';
      
      if (type === 'error') {
        this.statusElement.classList.add('error');
      } else if (type === 'success') {
        this.statusElement.classList.add('success');
      }
      
      // Auto-hide after 3 seconds for non-errors
      if (type !== 'error') {
        setTimeout(() => {
          if (this.statusElement.textContent === message) {
            this.statusElement.textContent = '';
          }
        }, 3000);
      }
    }
  }

  // ===== Initialize Scanner =====
  
  let scannerInstance = null;
  
  function initScanner() {
    if (scannerInstance) return scannerInstance;
    scannerInstance = new IMEIScannerModal();
    return scannerInstance;
  }
  
  // ===== Setup Scan Buttons =====
  
  function setupScanButtons() {
    document.querySelectorAll('[data-imei-scan-trigger]').forEach(button => {
      button.addEventListener('click', function(e) {
        e.preventDefault();
        
        const targetInputId = this.dataset.imeiScanTrigger;
        const targetElement = document.getElementById(targetInputId);
        
        console.log('[IMEI Scanner] Bind OK - trigger:', this, 'target:', targetInputId, 'element:', targetElement);
        
        const scanner = initScanner();
        scanner.open(targetInputId);
      });
    });
  }
  
  // ===== Auto-initialize on DOM ready =====
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupScanButtons);
  } else {
    setupScanButtons();
  }
  
  // Expose for manual initialization if needed
  window.IMEIScannerModal = {
    init: initScanner,
    setup: setupScanButtons
  };
  
})();

