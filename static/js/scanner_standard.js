/**
 * STANDARD SCANNER MODULE - CIRCUIT CITY SaaS
 * ============================================
 * Single source of truth for scanner logic across all verticals.
 * 
 * FEATURES:
 * - Back camera ONLY (no front camera, no switch option)
 * - BarcodeDetector → ZXing → Quagga fallback chain
 * - Use/Scan Again UX (matches Fast Sell)
 * - Phone-specific validation (15-digit IMEI, in-stock checks)
 * - Multi-code picker
 * - Proper aspect ratio (no warped preview)
 * - Torch support (when available)
 * 
 * USAGE:
 * StandardScanner.init('id_imei', {
 *   mode: 'phone_scan_sell',
 *   validateFn: validatePhoneIMEI,
 *   onSuccess: function(value) { console.log('Scanned:', value); }
 * });
 */

(function() {
  'use strict';

  // Global registry of scanner instances
  const scanners = {};

  /**
   * Initialize a scanner for a specific input field
   * @param {string} inputId - ID of the input field to fill
   * @param {object} options - Configuration options
   *   - mode: 'phone_scan_sell' | 'phone_scan_in' | 'general' (default: 'general')
   *   - validateFn: Function to validate scanned value (optional)
   *   - onSuccess: Callback after successful scan (optional)
   *   - onError: Callback on error (optional)
   */
  function init(inputId, options = {}) {
    if (scanners[inputId]) {
      console.warn(`Scanner already initialized for ${inputId}`);
      return scanners[inputId];
    }

    const scanner = new Scanner(inputId, options);
    scanners[inputId] = scanner;
    return scanner;
  }

  /**
   * Scanner class
   */
  class Scanner {
    constructor(inputId, options) {
      this.inputId = inputId;
      this.mode = options.mode || 'general';
      this.validateFn = options.validateFn;
      this.onSuccess = options.onSuccess;
      this.onError = options.onError;

      // DOM elements
      this.inputEl = document.getElementById(inputId);
      this.modalEl = document.getElementById(`scanner_modal_${inputId}`);
      this.videoEl = document.getElementById(`scanner_video_${inputId}`);
      this.scanlineEl = document.getElementById(`scanner_scanline_${inputId}`);
      this.resultBoxEl = document.getElementById(`scanner_result_box_${inputId}`);
      this.resultValueEl = document.getElementById(`scanner_result_value_${inputId}`);
      this.statusEl = document.getElementById(`scanner_status_${inputId}`);
      this.torchBtnEl = document.getElementById(`scanner_torch_btn_${inputId}`);
      this.pickerEl = document.getElementById(`scanner_picker_${inputId}`);
      this.pickerListEl = document.getElementById(`scanner_picker_list_${inputId}`);

      // Scanner state
      this.stream = null;
      this.track = null;
      this.scanning = false;
      this.torchOn = false;
      this.detector = null;
      this.rafId = null;
      this.quaggaHandler = null;
      this.zxingReader = null;
      this.lastDetectedValue = null;
      this.lastPickerAt = 0;

      // Bind events
      this.bindEvents();

      // Validate required elements
      if (!this.inputEl || !this.modalEl || !this.videoEl) {
        console.error(`Scanner initialization failed: missing elements for ${inputId}`);
      }
    }

    bindEvents() {
      // Open scanner button
      const openBtn = document.getElementById(`btn_open_scanner_${this.inputId}`);
      if (openBtn) {
        openBtn.addEventListener('click', () => this.open());
      }

      // Close scanner button
      const closeBtn = document.getElementById(`scanner_close_btn_${this.inputId}`);
      if (closeBtn) {
        closeBtn.addEventListener('click', () => this.close());
      }

      // Use button
      const useBtn = document.getElementById(`scanner_use_btn_${this.inputId}`);
      if (useBtn) {
        useBtn.addEventListener('click', () => this.useDetectedValue());
      }

      // Scan Again button
      const rescanBtn = document.getElementById(`scanner_rescan_btn_${this.inputId}`);
      if (rescanBtn) {
        rescanBtn.addEventListener('click', () => this.resumeScanning());
      }

      // Torch button
      if (this.torchBtnEl) {
        this.torchBtnEl.addEventListener('click', () => this.toggleTorch());
      }

      // Picker cancel button
      const pickerCancelBtn = document.getElementById(`scanner_picker_cancel_${this.inputId}`);
      if (pickerCancelBtn) {
        pickerCancelBtn.addEventListener('click', () => this.closePicker());
      }

      // Close on ESC key
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.modalEl && this.modalEl.style.display !== 'none') {
          this.close();
        }
      });
    }

    async open() {
      this.modalEl.style.display = 'flex';
      this.hideResultBox();
      await this.startCamera();
    }

    close() {
      this.stopScanning();
      this.stopCamera();
      this.modalEl.style.display = 'none';
      this.closePicker();
    }

    async startCamera() {
      if (this.stream) return;

      this.setStatus('Starting camera...');

      try {
        // ALWAYS request back camera (environment)
        // Try with facingMode first
        const constraints = {
          audio: false,
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30, max: 30 }
          }
        };

        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (e1) {
        // Fallback: enumerate devices and pick back camera by deviceId
        try {
          const devices = await navigator.mediaDevices.enumerateDevices();
          const cameras = devices.filter(d => d.kind === 'videoinput');
          
          if (cameras.length === 0) {
            throw new Error('No camera found');
          }

          // Find back camera
          const backCamera = cameras.find(c => /back|rear|environment/i.test(c.label));
          const deviceId = (backCamera || cameras[cameras.length - 1]).deviceId;

          this.stream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              deviceId: { exact: deviceId },
              width: { ideal: 1280 },
              height: { ideal: 720 },
              frameRate: { ideal: 30, max: 30 }
            }
          });
        } catch (e2) {
          // Last resort: any video
          try {
            this.stream = await navigator.mediaDevices.getUserMedia({
              audio: false,
              video: { width: { ideal: 1280 }, height: { ideal: 720 } }
            });
          } catch (e3) {
            this.setStatus('Camera access denied. Please allow camera permission.');
            this.onError?.('Camera access denied');
            return;
          }
        }
      }

      this.videoEl.srcObject = this.stream;
      await this.videoEl.play();
      this.track = this.stream.getVideoTracks()[0];

      // Check torch capability
      const caps = this.track.getCapabilities?.() || {};
      if (caps.torch) {
        this.torchBtnEl.style.display = 'inline-flex';
      }

      this.setStatus('Point camera at barcode...');
      await this.startScanning();
    }

    stopCamera() {
      if (this.track) {
        this.track.stop();
        this.track = null;
      }
      if (this.stream) {
        this.stream.getTracks().forEach(t => t.stop());
        this.stream = null;
      }
      if (this.videoEl) {
        this.videoEl.srcObject = null;
      }
    }

    async startScanning() {
      this.scanning = true;
      this.lastDetectedValue = null;

      // Try BarcodeDetector (native, fastest)
      if ('BarcodeDetector' in window) {
        try {
          this.detector = new window.BarcodeDetector({
            formats: [
              'qr_code', 'aztec', 'code_128', 'code_39', 'code_93',
              'data_matrix', 'ean_13', 'ean_8', 'itf', 'pdf417',
              'upc_a', 'upc_e'
            ]
          });
          this.startBarcodeDetectorLoop();
          return;
        } catch (e) {
          console.warn('BarcodeDetector init failed, trying ZXing...');
        }
      }

      // Fallback: ZXing
      if (window.ZXing && window.ZXing.BrowserMultiFormatReader) {
        try {
          await this.startZXing();
          return;
        } catch (e) {
          console.warn('ZXing init failed, trying Quagga...');
        }
      }

      // Fallback: Quagga
      if (window.Quagga) {
        await this.startQuagga();
      } else {
        this.setStatus('No barcode library available.');
        this.onError?.('No barcode library available');
      }
    }

    startBarcodeDetectorLoop() {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      let lastTick = 0;
      const tickEveryMs = 140; // ~7 fps

      const loop = async () => {
        if (!this.scanning) return;
        this.rafId = requestAnimationFrame(loop);

        if (this.videoEl.readyState < 2) return;

        const now = performance.now();
        if (now - lastTick < tickEveryMs) return;
        lastTick = now;

        canvas.width = this.videoEl.videoWidth;
        canvas.height = this.videoEl.videoHeight;
        ctx.drawImage(this.videoEl, 0, 0, canvas.width, canvas.height);

        try {
          const codes = await this.detector.detect(canvas);
          if (codes && codes.length) {
            const values = codes.map(c => (c.rawValue || c.rawValueText || '').trim()).filter(Boolean);
            if (values.length) {
              this.handleDetectedCodes(values);
            }
          }
        } catch (e) {
          // Ignore frame errors
        }
      };

      loop();
    }

    async startZXing() {
      this.zxingReader = new window.ZXing.BrowserMultiFormatReader();
      
      const devices = await this.zxingReader.listVideoInputDevices();
      let deviceId = null;
      if (devices.length) {
        const back = devices.find(d => /back|rear|environment/i.test(d.label));
        deviceId = (back || devices[devices.length - 1]).deviceId;
      }

      await this.zxingReader.decodeFromVideoDevice(
        deviceId,
        this.videoEl,
        (result, err) => {
          if (!this.scanning) return;
          if (result) {
            this.handleDetectedCodes([result.getText()]);
          }
        }
      );
    }

    async startQuagga() {
      const deviceId = this.track?.getSettings?.().deviceId;

      return new Promise((resolve, reject) => {
        window.Quagga.init({
          inputStream: {
            type: 'LiveStream',
            target: this.videoEl,
            constraints: {
              facingMode: deviceId ? undefined : 'environment',
              deviceId: deviceId ? { exact: deviceId } : undefined,
              width: { ideal: 1280 },
              height: { ideal: 720 }
            }
          },
          decoder: {
            readers: [
              'code_128_reader', 'ean_reader', 'ean_8_reader',
              'code_39_reader', 'upc_reader', 'upc_e_reader',
              'itf_reader', 'codabar_reader'
            ]
          },
          locate: true,
          numOfWorkers: navigator.hardwareConcurrency ? Math.min(4, navigator.hardwareConcurrency) : 2
        }, (err) => {
          if (err) {
            reject(err);
            return;
          }

          window.Quagga.start();
          resolve();
        });

        // Ensure only one handler
        if (this.quaggaHandler) {
          try {
            window.Quagga.offDetected(this.quaggaHandler);
          } catch (e) {}
        }

        this.quaggaHandler = (result) => {
          if (!this.scanning) return;
          const code = (result && result.codeResult && result.codeResult.code) || '';
          if (code) {
            this.handleDetectedCodes([code]);
          }
        };

        window.Quagga.onDetected(this.quaggaHandler);
      });
    }

    stopScanning() {
      this.scanning = false;

      // Stop RAF loop
      if (this.rafId) {
        cancelAnimationFrame(this.rafId);
        this.rafId = null;
      }

      // Stop ZXing
      if (this.zxingReader) {
        try {
          this.zxingReader.reset?.();
        } catch (e) {}
        this.zxingReader = null;
      }

      // Stop Quagga
      if (window.Quagga && this.quaggaHandler) {
        try {
          window.Quagga.offDetected(this.quaggaHandler);
          window.Quagga.stop();
        } catch (e) {}
        this.quaggaHandler = null;
      }

      this.detector = null;
    }

    handleDetectedCodes(values) {
      const unique = [...new Set(values)];

      // Phone-specific: extract 15-digit IMEI candidates
      if (this.mode.startsWith('phone_')) {
        const imeiCandidates = this.extractIMEICandidates(unique);
        if (imeiCandidates.length === 1) {
          this.showDetectedValue(imeiCandidates[0]);
        } else if (imeiCandidates.length > 1) {
          this.showPicker(imeiCandidates);
        } else {
          // No valid IMEI found, try raw value
          if (unique.length === 1) {
            this.showDetectedValue(unique[0]);
          }
        }
      } else {
        // General mode: show first value or picker
        if (unique.length === 1) {
          this.showDetectedValue(unique[0]);
        } else if (unique.length > 1) {
          this.showPicker(unique);
        }
      }
    }

    extractIMEICandidates(values) {
      const candidates = [];
      const imeiRegex = /\b\d{15}\b/g;

      values.forEach(val => {
        const matches = val.match(imeiRegex);
        if (matches) {
          matches.forEach(m => {
            if (!candidates.includes(m)) {
              candidates.push(m);
            }
          });
        }
      });

      return candidates;
    }

    showDetectedValue(value) {
      this.lastDetectedValue = value;
      this.resultValueEl.textContent = value;
      this.resultBoxEl.style.display = 'block';
      this.pauseScanline();
      this.stopScanning(); // Pause detection while showing result

      // Vibrate
      try {
        navigator.vibrate?.(30);
      } catch (e) {}
    }

    hideResultBox() {
      this.resultBoxEl.style.display = 'none';
      this.lastDetectedValue = null;
    }

    async useDetectedValue() {
      const value = this.lastDetectedValue;
      if (!value) return;

      // Phone-specific validation
      if (this.mode === 'phone_scan_sell') {
        // Validate 15 digits
        if (!/^\d{15}$/.test(value)) {
          this.showError('IMEI must be exactly 15 digits');
          return;
        }

        // Check if in stock (via API)
        const inStock = await this.checkPhoneInStock(value);
        if (!inStock) {
          this.showError('IMEI not in stock');
          return;
        }
      } else if (this.mode === 'phone_scan_in') {
        // Validate 15 digits
        if (!/^\d{15}$/.test(value)) {
          this.showError('IMEI must be exactly 15 digits');
          return;
        }

        // Check if already exists (via API)
        const exists = await this.checkPhoneExists(value);
        if (exists) {
          this.showError('IMEI already exists in system');
          return;
        }
      }

      // Custom validation function
      if (this.validateFn) {
        const valid = await this.validateFn(value, this.mode);
        if (!valid) {
          return; // Validation function should show its own error
        }
      }

      // Fill input and close
      if (this.inputEl) {
        this.inputEl.value = value;
        this.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        this.inputEl.dispatchEvent(new Event('change', { bubbles: true }));
      }

      this.onSuccess?.(value);
      this.close();
    }

    resumeScanning() {
      this.hideResultBox();
      this.resumeScanline();
      this.startScanning();
    }

    showPicker(values) {
      // Prevent picker spam
      const now = Date.now();
      if (now - this.lastPickerAt < 600) return;
      this.lastPickerAt = now;

      this.pickerListEl.innerHTML = '';
      values.forEach(val => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cc-scanner-picker-item';
        btn.textContent = val;
        btn.onclick = () => {
          this.closePicker();
          this.showDetectedValue(val);
        };
        this.pickerListEl.appendChild(btn);
      });

      this.pickerEl.style.display = 'flex';
      this.pauseScanline();
      this.stopScanning();
    }

    closePicker() {
      this.pickerEl.style.display = 'none';
    }

    async checkPhoneInStock(imei) {
      // Call your stock check API
      try {
        const response = await fetch(`/inventory/api/stock-status/?code=${encodeURIComponent(imei)}`, {
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
          cache: 'no-store'
        });

        if (!response.ok) return false;

        const data = await response.json();
        return !!(data && data.in_stock);
      } catch (e) {
        console.error('Stock check failed:', e);
        return false;
      }
    }

    async checkPhoneExists(imei) {
      // Call your existence check API
      try {
        const response = await fetch(`/inventory/api/imei-exists/?imei=${encodeURIComponent(imei)}`, {
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
          cache: 'no-store'
        });

        if (!response.ok) return false;

        const data = await response.json();
        return !!(data && data.exists);
      } catch (e) {
        console.error('IMEI existence check failed:', e);
        return false;
      }
    }

    showError(message) {
      this.setStatus(`❌ ${message}`);
      this.hideResultBox();
      setTimeout(() => {
        this.setStatus('Point camera at barcode...');
        this.resumeScanning();
      }, 2500);
    }

    async toggleTorch() {
      if (!this.track) return;

      const caps = this.track.getCapabilities?.() || {};
      if (!caps.torch) return;

      this.torchOn = !this.torchOn;

      try {
        await this.track.applyConstraints({
          advanced: [{ torch: this.torchOn }]
        });
        this.torchBtnEl.textContent = this.torchOn ? '🔦 Torch ON' : '🔦 Torch';
      } catch (e) {
        console.warn('Torch toggle failed:', e);
      }
    }

    pauseScanline() {
      if (this.scanlineEl) {
        this.scanlineEl.classList.add('paused');
      }
    }

    resumeScanline() {
      if (this.scanlineEl) {
        this.scanlineEl.classList.remove('paused');
      }
    }

    setStatus(message) {
      if (this.statusEl) {
        this.statusEl.textContent = message;
      }
    }
  }

  // Export to global scope
  window.StandardScanner = { init };
})();

