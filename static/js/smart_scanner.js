/**
 * Smart Scanner Module
 * ====================
 * Unified intelligent scanner for CircuitCity - works across all verticals
 * 
 * Features:
 * - Multi-barcode detection (shows numbered list when multiple codes found)
 * - Animated scan line overlay
 * - BarcodeDetector API with ZXing and Quagga fallbacks
 * - Camera selection and torch control
 * - Supports IMEI, SKU, barcode input modes
 * - Zero regressions - safe integration with existing forms
 * 
 * Usage:
 *   SmartScanner.init({
 *     videoElementId: 'scannerVideo',
 *     targetInputId: 'id_imei',
 *     scanMode: 'imei',  // 'imei', 'sku', or 'barcode'
 *     onDetect: function(value) { console.log('Scanned:', value); }
 *   });
 */

(function(window) {
  'use strict';

  // ====== Helper Functions ======
  
  const digitsOnly = (s) => (s || '').replace(/\D/g, '');
  
  /**
   * Extract 15-digit IMEI candidates from a string (for QR codes with multiple IMEIs)
   */
  function imeiCandidatesFromString(s) {
    const d = digitsOnly(s || '');
    const cands = new Set();
    // Slide a window to capture any 15-digit sequences
    for (let i = 0; i + 15 <= d.length; i++) {
      const chunk = d.slice(i, i + 15);
      if (chunk.length === 15) cands.add(chunk);
    }
    return Array.from(cands);
  }

  /**
   * Normalize candidate based on scan mode
   */
  function normalizeCandidate(raw, mode) {
    const trimmed = (raw || '').trim();
    if (mode === 'imei') {
      // Keep last 15 digits for IMEI
      const d = digitsOnly(trimmed);
      return d.length >= 15 ? d.slice(-15) : d;
    }
    // For SKU/barcode, keep as-is (trimmed)
    return trimmed;
  }

  /**
   * Build picker modal for multiple detected codes
   */
  function buildPicker(values, onPick, title = 'Multiple codes found — pick one') {
    // Remove any existing picker
    document.getElementById('ccscan-picker')?.remove();
    
    const wrap = document.createElement('div');
    wrap.id = 'ccscan-picker';
    wrap.style.cssText = 'position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);z-index:9999';
    
    const card = document.createElement('div');
    card.style.cssText = 'background:#fff;max-width:90vw;width:520px;padding:20px;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.35);font-family:system-ui,sans-serif';
    
    const h = document.createElement('div');
    h.style.cssText = 'font-weight:700;margin-bottom:12px;font-size:1.1rem;color:#0f172a';
    h.textContent = title;
    
    const list = document.createElement('div');
    list.style.cssText = 'max-height:55vh;overflow:auto;display:flex;flex-direction:column;gap:8px';
    
    values.forEach((v, idx) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = 'text-align:left;padding:12px 14px;border-radius:10px;border:1px solid #e5e7eb;background:#f9fafb;cursor:pointer;transition:all .2s;word-break:break-all';
      
      const main = (v.label ?? v.value ?? '').toString();
      const number = `<strong style="display:inline-block;min-width:28px;color:#10b981">${idx + 1}.</strong>`;
      const text = main.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const meta = v.meta ? `<small style="display:block;color:#6b7280;margin-top:4px">${v.meta}</small>` : '';
      
      btn.innerHTML = `${number} ${text}${meta}`;
      
      btn.onmouseover = () => {
        btn.style.background = '#f0fdf4';
        btn.style.borderColor = '#10b981';
      };
      btn.onmouseout = () => {
        btn.style.background = '#f9fafb';
        btn.style.borderColor = '#e5e7eb';
      };
      btn.onclick = () => {
        wrap.remove();
        onPick(v.value ?? main);
      };
      
      list.appendChild(btn);
    });
    
    const actions = document.createElement('div');
    actions.style.cssText = 'margin-top:14px;display:flex;justify-content:flex-end;gap:10px';
    
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = 'Cancel';
    cancel.style.cssText = 'padding:10px 16px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;font-weight:600';
    cancel.onclick = () => wrap.remove();
    
    actions.appendChild(cancel);
    card.append(h, list, actions);
    wrap.appendChild(card);
    document.body.appendChild(wrap);
    
    // ESC key to close
    const escHandler = (e) => {
      if (e.key === 'Escape') {
        wrap.remove();
        document.removeEventListener('keydown', escHandler);
      }
    };
    document.addEventListener('keydown', escHandler);
  }

  /**
   * Pause scan line animation briefly (visual feedback on detection)
   */
  function pauseScanline(scanLineElement, ms = 900) {
    if (!scanLineElement) return;
    scanLineElement.classList.add('paused');
    setTimeout(() => scanLineElement.classList.remove('paused'), ms);
  }

  // ====== SmartScanner Class ======
  
  class SmartScanner {
    constructor(config) {
      this.config = {
        videoElementId: config.videoElementId || 'camera',
        targetInputId: config.targetInputId,
        scanMode: config.scanMode || 'barcode', // 'imei', 'sku', 'barcode'
        scanLineElementId: config.scanLineElementId || 'scanline',
        onDetect: config.onDetect || null,
        onError: config.onError || null,
        autoSubmit: config.autoSubmit || false,
        showToast: config.showToast || null,
      };
      
      this.mediaStream = null;
      this.videoTrack = null;
      this.detector = null;
      this.isScanning = false;
      this.lastPickerAt = 0;
      
      this.videoElement = document.getElementById(this.config.videoElementId);
      this.targetInput = document.getElementById(this.config.targetInputId);
      this.scanLineElement = document.getElementById(this.config.scanLineElementId);
      
      if (!this.videoElement) {
        console.error('[SmartScanner] Video element not found:', this.config.videoElementId);
      }
      if (!this.targetInput) {
        console.error('[SmartScanner] Target input not found:', this.config.targetInputId);
      }
    }

    /**
     * Start media stream and scanning
     */
    async start(deviceId) {
      if (this.isScanning) return;
      
      try {
        const constraints = {
          audio: false,
          video: {
            facingMode: deviceId ? undefined : { ideal: 'environment' },
            deviceId: deviceId ? { exact: deviceId } : undefined,
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30 }
          }
        };
        
        this.mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        this.videoElement.srcObject = this.mediaStream;
        await this.videoElement.play();
        this.videoTrack = this.mediaStream.getVideoTracks()[0];
        
        this.isScanning = true;
        this._startNativeDetector();
        
      } catch (error) {
        console.error('[SmartScanner] Camera start error:', error);
        if (this.config.onError) {
          this.config.onError(error);
        }
        throw error;
      }
    }

    /**
     * Stop media stream and scanning
     */
    stop() {
      this.isScanning = false;
      
      // Stop ZXing session if any
      if (this._startZXing && this._startZXing._stop) {
        try { this._startZXing._stop(); } catch (_) {}
      }
      
      // Stop Quagga
      if (window.Quagga) {
        try { 
          Quagga.offDetected && Quagga.offDetected(() => {});
          Quagga.stop(); 
        } catch (_) {}
      }
      
      // Stop native stream
      if (this.mediaStream) {
        this.mediaStream.getTracks().forEach(t => t.stop());
      }
      
      this.mediaStream = null;
      this.videoTrack = null;
    }

    /**
     * Enable/disable torch (flash)
     */
    async enableTorch(desired) {
      if (!this.videoTrack) return;
      const caps = this.videoTrack.getCapabilities?.() || {};
      if (!('torch' in caps)) {
        if (this.config.showToast) {
          this.config.showToast('Torch not supported on this camera.', false);
        }
        return;
      }
      try {
        await this.videoTrack.applyConstraints({ advanced: [{ torch: desired }] });
      } catch (_) {}
    }

    /**
     * Start BarcodeDetector-based scanning (with fallbacks)
     */
    async _startNativeDetector() {
      // Try native BarcodeDetector first
      if (!('BarcodeDetector' in window)) {
        // Fallback to ZXing
        return this._startZXing(null).catch(() => this._startQuagga(null));
      }
      
      try {
        this.detector = new window.BarcodeDetector({
          formats: [
            "qr_code", "aztec", "code_128", "code_39", "code_93",
            "data_matrix", "ean_13", "ean_8", "itf", "pdf417", "upc_a", "upc_e"
          ]
        });
      } catch (e) {
        console.warn('[SmartScanner] BarcodeDetector init failed:', e);
        return this._startZXing(null).catch(() => this._startQuagga(null));
      }
      
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      
      const loop = async () => {
        if (!this.isScanning || !this.mediaStream) return;
        requestAnimationFrame(loop);
        
        if (this.videoElement.readyState < 2) return;
        
        canvas.width = this.videoElement.videoWidth;
        canvas.height = this.videoElement.videoHeight;
        ctx.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);
        
        try {
          const detections = await this.detector.detect(canvas);
          if (!detections || !detections.length) return;
          
          // Prefer QR codes (may contain multiple IMEIs)
          const qrs = detections.filter(c => (c.format || c.type) === 'qr_code');
          
          if (qrs.length > 0 && this.config.scanMode === 'imei') {
            // QR-specific handling for IMEI mode
            const choices = [];
            qrs.forEach((c) => {
              const raw = (c.rawValue || c.rawValueText || '').trim();
              if (!raw) return;
              const imeis = imeiCandidatesFromString(raw);
              const label = raw.length > 120 ? (raw.slice(0, 120) + '…') : raw;
              choices.push({
                label,
                value: raw,
                meta: imeis.length ? `IMEI candidates: ${imeis.join(', ')}` : 'QR'
              });
            });
            
            if (choices.length === 1) {
              const raw = choices[0].value;
              const imeis = imeiCandidatesFromString(raw);
              this._handleDetection(imeis[0] || raw);
            } else if (choices.length > 1) {
              this._showPicker(choices);
            }
            return;
          }
          
          // Generic handling: collect all unique values
          const vals = [...new Set(detections.map(c => (c.rawValue || c.rawValueText || "").trim()).filter(Boolean))];
          
          if (vals.length === 1) {
            this._handleDetection(vals[0]);
          } else if (vals.length > 1) {
            this._showPickerSimple(vals);
          }
          
        } catch (_) {
          // Ignore frame errors
        }
      };
      
      loop();
    }

    /**
     * ZXing fallback
     */
    async _startZXing(deviceId) {
      if (!window.ZXing || !ZXing.BrowserMultiFormatReader) {
        throw new Error('ZXing not available');
      }
      
      const codeReader = new ZXing.BrowserMultiFormatReader();
      const devices = await codeReader.listVideoInputDevices().catch(() => []);
      let chosenId = deviceId || (devices[devices.length - 1] || devices[0] || {}).deviceId;
      if (!chosenId) throw new Error('No camera for ZXing');
      
      await codeReader.decodeFromVideoDevice(chosenId, this.videoElement, (result, err) => {
        if (result && result.getText) {
          const raw = result.getText();
          
          if (this.config.scanMode === 'imei') {
            const imeis = imeiCandidatesFromString(raw);
            if (imeis.length > 1) {
              this._showPickerSimple(imeis, 'IMEI');
            } else if (imeis.length === 1) {
              this._handleDetection(imeis[0]);
            } else {
              this._handleDetection(raw);
            }
          } else {
            this._handleDetection(raw);
          }
          
          pauseScanline(this.scanLineElement);
          try { navigator.vibrate?.(20); } catch (_) {}
        }
      });
      
      const stream = this.videoElement.srcObject;
      this.mediaStream = stream || null;
      this.videoTrack = stream ? (stream.getVideoTracks()[0] || null) : null;
      
      // Store stop function
      this._startZXing._stop = () => {
        try { codeReader.reset(); } catch (_) {}
      };
    }

    /**
     * Quagga fallback (1D barcodes only, no QR)
     */
    async _startQuagga(deviceId) {
      if (!window.Quagga) {
        if (this.config.showToast) {
          this.config.showToast('Quagga not loaded.', false);
        }
        return;
      }
      
      Quagga.init({
        inputStream: {
          type: 'LiveStream',
          target: this.videoElement,
          constraints: {
            facingMode: deviceId ? undefined : 'environment',
            deviceId: deviceId || undefined,
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
          if (this.config.showToast) {
            this.config.showToast('Camera init failed. Use HTTPS or allow camera.', false);
          }
          return;
        }
        Quagga.start();
      });
      
      Quagga.onDetected((result) => {
        const code = (result && result.codeResult && result.codeResult.code) || '';
        if (!code) return;
        this._handleDetection(code);
      });
    }

    /**
     * Show picker with full choice objects
     */
    _showPicker(choices) {
      const now = Date.now();
      if (now - this.lastPickerAt < 600) return; // Debounce
      this.lastPickerAt = now;
      
      buildPicker(
        choices,
        (picked) => {
          if (this.config.scanMode === 'imei') {
            const imeis = imeiCandidatesFromString(picked);
            this._handleDetection(imeis[0] || picked);
          } else {
            this._handleDetection(picked);
          }
        },
        this.config.scanMode === 'imei' ? 'Multiple QR codes found — pick one' : 'Multiple codes found — pick one'
      );
    }

    /**
     * Show picker with simple value array
     */
    _showPickerSimple(vals, metaLabel = 'Barcode') {
      const now = Date.now();
      if (now - this.lastPickerAt < 600) return;
      this.lastPickerAt = now;
      
      buildPicker(
        vals.map(v => ({
          label: v.length > 120 ? (v.slice(0, 120) + '…') : v,
          value: v,
          meta: metaLabel
        })),
        (picked) => this._handleDetection(picked),
        vals.length > 1 ? `Multiple ${this.config.scanMode}s found — pick one` : 'Pick one'
      );
    }

    /**
     * Handle a detected value
     */
    _handleDetection(rawValue) {
      const normalized = normalizeCandidate(rawValue, this.config.scanMode);
      
      // Fill target input
      if (this.targetInput) {
        this.targetInput.value = normalized;
        
        // Trigger events for existing listeners
        this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
        this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
      
      // Pause scan line for feedback
      pauseScanline(this.scanLineElement);
      
      // Vibrate
      try { navigator.vibrate?.(20); } catch (_) {}
      
      // Custom callback
      if (this.config.onDetect) {
        this.config.onDetect(normalized);
      }
      
      // Auto-submit if configured
      if (this.config.autoSubmit) {
        const form = this.targetInput?.closest('form');
        if (form) {
          setTimeout(() => form.submit(), 150);
        }
      }
    }
  }

  // ====== Public API ======
  
  window.SmartScanner = {
    /**
     * Create and return a new scanner instance
     */
    create: function(config) {
      return new SmartScanner(config);
    },
    
    /**
     * Convenience: init scanner and start immediately
     */
    init: function(config) {
      const scanner = new SmartScanner(config);
      return scanner;
    }
  };

})(window);

