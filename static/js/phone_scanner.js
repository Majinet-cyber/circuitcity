/**
 * ==============================================================================
 * SHARED PHONE SCANNER JAVASCRIPT
 * ==============================================================================
 * Reusable scanner logic for IMEI/barcode scanning with camera overlay + moving line.
 * Used by: Scan In, Scan & Sell (sale wizard), and other phone inventory flows.
 *
 * DEPENDENCIES:
 *   - Quagga.js (barcode scanner library)
 *   - ZXing (alternative barcode scanner)
 *   - Modern browser with MediaDevices API
 *
 * USAGE:
 *   PhoneScanner.init('imei'); // Pass the input ID (without '#')
 * ==============================================================================
 */

const PhoneScanner = (function() {
  'use strict';

  // Scanner state
  let mediaStream = null;
  let videoTrack = null;
  let config = {};

  /**
   * Initialize the scanner for a given input field
   * @param {string} inputId - ID of the IMEI input field (without '#')
   * @param {object} options - Optional configuration
   */
  function init(inputId, options = {}) {
    config = {
      inputId: inputId,
      onSuccess: options.onSuccess || null,
      onError: options.onError || null,
      ...options
    };

    const imeiInput = document.getElementById(inputId);
    if (!imeiInput) {
      console.warn(`PhoneScanner: Input field #${inputId} not found`);
      return;
    }

    // Get all scanner elements
    const elements = {
      imeiInput: imeiInput,
      imeiField: document.getElementById(`${inputId}Field`),
      imeiLen: document.getElementById(`${inputId}Len`),
      imeiHelp: document.getElementById(`${inputId}Help`),
      pasteBtn: document.getElementById(`${inputId}PasteBtn`),
      camToggle: document.getElementById(`${inputId}CamToggle`),
      camStop: document.getElementById(`${inputId}CamStop`),
      camBox: document.getElementById(`${inputId}CameraBox`),
      camNode: document.getElementById(`${inputId}Camera`),
      camSelect: document.getElementById(`${inputId}CameraSelect`),
      torchBtn: document.getElementById(`${inputId}TorchBtn`),
      toast: document.getElementById(`${inputId}Toast`),
      scanLine: document.getElementById(`${inputId}Scanline`)
    };

    // Store elements in config
    config.elements = elements;

    // Setup event listeners
    setupEventListeners();

    // Initialize counter
    updateImeiCounter();
  }

  /**
   * Setup all event listeners
   */
  function setupEventListeners() {
    const { imeiInput, pasteBtn, camToggle, camStop, camSelect, torchBtn } = config.elements;

    // Input validation
    imeiInput.addEventListener('input', () => {
      const before = imeiInput.value;
      const onlyDigits = digitsOnly(before);
      imeiInput.value = onlyDigits.length > 15 ? onlyDigits.slice(-15) : onlyDigits;
      updateImeiCounter();
    });

    imeiInput.addEventListener('paste', () => {
      setTimeout(() => {
        const d = digitsOnly(imeiInput.value);
        if (d.length > 15) imeiInput.value = d.slice(-15);
        updateImeiCounter();
      }, 0);
    });

    // Paste button
    if (pasteBtn) {
      pasteBtn.addEventListener('click', async () => {
        try {
          const txt = await navigator.clipboard.readText();
          if (!txt) {
            showToast('Clipboard is empty.', false);
            return;
          }
          const d = digitsOnly(txt);
          imeiInput.value = d.length > 15 ? d.slice(-15) : d;
          updateImeiCounter();
          if (lenDigits(imeiInput.value) === 15) {
            showToast('Pasted 15-digit IMEI!', true);
          } else {
            showToast('Pasted. Need 15 digits.', false);
          }
        } catch {
          showToast('Clipboard blocked. Paste manually (Ctrl+V).', false);
          imeiInput.focus();
        }
      });
    }

    // Camera toggle
    if (camToggle) {
      camToggle.addEventListener('click', async () => {
        if (config.elements.camBox) config.elements.camBox.style.display = 'block';
        const cams = await listCameras();
        const firstId = (cams[0] && cams[0].deviceId) || undefined;

        try {
          if ('BarcodeDetector' in window) {
            await startNativeDetector(firstId);
          } else if (window.ZXing && window.ZXing.BrowserMultiFormatReader) {
            await startZXing(firstId);
          } else {
            await startQuagga(firstId);
          }
          camToggle.innerHTML = '<i class="bi bi-camera"></i> Restart Camera';
        } catch (err) {
          showToast('Could not start camera. Check permission / origin.', false);
        }
      });
    }

    // Camera select
    if (camSelect) {
      camSelect.addEventListener('change', async () => {
        stopAll();
        try {
          if ('BarcodeDetector' in window) {
            await startNativeDetector(camSelect.value);
          } else if (window.ZXing && window.ZXing.BrowserMultiFormatReader) {
            await startZXing(camSelect.value);
          } else {
            await startQuagga(camSelect.value);
          }
        } catch {
          showToast('Could not switch camera.', false);
        }
      });
    }

    // Camera stop
    if (camStop) {
      camStop.addEventListener('click', () => {
        stopAll();
        if (config.elements.camBox) config.elements.camBox.style.display = 'none';
        if (camToggle) camToggle.innerHTML = '<i class="bi bi-camera"></i> Start Camera';
      });
    }

    // Torch toggle
    if (torchBtn) {
      torchBtn.addEventListener('click', () => enableTorch(true));
    }

    // Auto-stop on page hide
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        stopAll();
      }
    });
  }

  /**
   * Helper: Extract digits only from string
   */
  function digitsOnly(s) {
    return (s || '').replace(/\D/g, '');
  }

  /**
   * Helper: Count digits in string
   */
  function lenDigits(s) {
    return digitsOnly(s).length;
  }

  /**
   * Update IMEI counter badge and validation state
   */
  function updateImeiCounter() {
    const { imeiInput, imeiLen, imeiField, imeiHelp } = config.elements;
    const n = lenDigits(imeiInput.value);
    
    if (imeiLen) imeiLen.textContent = `${n}/15`;

    if (n === 0) {
      setBadgeNeutral();
      imeiInput.setAttribute('aria-invalid', 'false');
      if (imeiHelp) imeiHelp.hidden = true;
    } else if (n < 15) {
      setBadgeBad();
      imeiInput.setAttribute('aria-invalid', 'true');
      if (imeiHelp) imeiHelp.hidden = false;
    } else {
      setBadgeOk();
      imeiInput.setAttribute('aria-invalid', 'false');
      if (imeiHelp) imeiHelp.hidden = true;
    }
  }

  /**
   * Set badge to neutral state
   */
  function setBadgeNeutral() {
    const { imeiLen, imeiField } = config.elements;
    if (!imeiLen || !imeiField) return;
    imeiLen.style.background = '#e2e8f0';
    imeiLen.style.color = '#0f172a';
    imeiField.classList.remove('state-ok', 'state-bad');
  }

  /**
   * Set badge to bad state
   */
  function setBadgeBad() {
    const { imeiLen, imeiField } = config.elements;
    if (!imeiLen || !imeiField) return;
    imeiLen.style.background = '#fee2e2';
    imeiLen.style.color = '#991b1b';
    imeiField.classList.add('state-bad');
    imeiField.classList.remove('state-ok');
  }

  /**
   * Set badge to ok state
   */
  function setBadgeOk() {
    const { imeiLen, imeiField } = config.elements;
    if (!imeiLen || !imeiField) return;
    imeiLen.style.background = '#dcfce7';
    imeiLen.style.color = '#065f46';
    imeiField.classList.add('state-ok');
    imeiField.classList.remove('state-bad');
  }

  /**
   * Show toast notification
   */
  function showToast(msg, ok = true) {
    const { toast } = config.elements;
    if (!toast) return;
    toast.textContent = msg;
    toast.className = 'toast ' + (ok ? 'ok' : 'err');
    toast.style.display = 'block';
    setTimeout(() => toast.style.display = 'none', 2600);
  }

  /**
   * Pause scanline animation
   */
  function pauseScanline(ms = 900) {
    const { scanLine } = config.elements;
    if (scanLine) {
      scanLine.classList.add('paused');
      setTimeout(() => scanLine.classList.remove('paused'), ms);
    }
  }

  /**
   * Handle detected IMEI/barcode
   */
  function handleIMEI(value) {
    const { imeiInput } = config.elements;
    const codeRaw = digitsOnly(value);
    if (!codeRaw) return;
    
    const code = (codeRaw.length >= 15) ? codeRaw.slice(-15) : codeRaw;
    imeiInput.value = code;
    updateImeiCounter();
    
    try {
      navigator.vibrate && navigator.vibrate(20);
    } catch (_) {}

    if (code.length === 15) {
      showToast('Scanned IMEI: ' + code, true);
      pauseScanline();
      if (config.onSuccess) config.onSuccess(code);
    } else {
      showToast('Scanned, but not a 15-digit IMEI.', false);
      if (config.onError) config.onError('Invalid IMEI length');
    }
  }

  /**
   * Extract IMEI candidates from string
   */
  function imeiCandidatesFromString(s) {
    const d = digitsOnly(s || '');
    const cands = new Set();
    for (let i = 0; i + 15 <= d.length; i++) {
      const chunk = d.slice(i, i + 15);
      if (chunk.length === 15) cands.add(chunk);
    }
    return Array.from(cands);
  }

  /**
   * Build picker UI for multiple codes
   */
  function buildPicker(values, onPick, title = 'Multiple codes found — pick one') {
    document.getElementById('ccscan-picker')?.remove();
    const wrap = document.createElement('div');
    wrap.id = 'ccscan-picker';
    wrap.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
    
    const card = document.createElement('div');
    card.style.cssText = 'background:#fff;border-radius:16px;padding:24px;max-width:500px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,0.3)';
    
    const h = document.createElement('div');
    h.style.cssText = 'font-weight:700;margin-bottom:16px;font-size:1.1rem;color:#0f172a';
    h.textContent = title;
    
    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:8px;margin-bottom:16px';
    
    values.forEach(v => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = 'background:#f8fafc;border:2px solid #e2e8f0;border-radius:12px;padding:12px;text-align:left;cursor:pointer;transition:all 0.2s;font-weight:600;color:#0f172a';
      const main = (v.label ?? v.value ?? '').toString();
      btn.innerHTML = `${main.replace(/</g, '&lt;').replace(/>/g, '&gt;')}${v.meta ? `<div style="font-size:0.85rem;color:#64748b;margin-top:4px">${v.meta}</div>` : ''}`;
      btn.onmouseover = () => btn.style.borderColor = '#1f6feb';
      btn.onmouseout = () => btn.style.borderColor = '#e2e8f0';
      btn.onclick = () => {
        wrap.remove();
        onPick(v.value ?? main);
      };
      list.appendChild(btn);
    });
    
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;justify-content:flex-end';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.style.cssText = 'background:#ef4444;color:#fff;border:none;border-radius:12px;padding:10px 20px;cursor:pointer;font-weight:600';
    cancel.textContent = 'Cancel';
    cancel.onclick = () => wrap.remove();
    actions.appendChild(cancel);
    
    card.append(h, list, actions);
    wrap.appendChild(card);
    document.body.appendChild(wrap);
  }

  /**
   * List available cameras
   */
  async function listCameras() {
    const { camSelect } = config.elements;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter(d => d.kind === 'videoinput');
      if (camSelect) {
        camSelect.innerHTML = '';
        cams.forEach((c, i) => {
          const opt = document.createElement('option');
          opt.value = c.deviceId;
          opt.textContent = c.label || `Camera ${i + 1}`;
          camSelect.appendChild(opt);
        });
      }
      return cams;
    } catch {
      return [];
    }
  }

  /**
   * Start media stream
   */
  async function startMedia(deviceId) {
    const { camNode } = config.elements;
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
    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
    camNode.srcObject = mediaStream;
    await camNode.play();
    videoTrack = mediaStream.getVideoTracks()[0];
  }

  /**
   * Enable torch/flashlight
   */
  async function enableTorch(desired) {
    if (!videoTrack) return;
    const caps = videoTrack.getCapabilities?.() || {};
    if (!('torch' in caps)) {
      showToast('Torch not supported on this camera.', false);
      return;
    }
    try {
      await videoTrack.applyConstraints({ advanced: [{ torch: desired }] });
    } catch (_) {}
  }

  /**
   * Stop all scanner activities
   */
  function stopAll() {
    if (startZXing._stop) {
      try {
        startZXing._stop();
      } catch (_) {}
    }
    if (window.Quagga) {
      try {
        window.Quagga.stop();
      } catch (_) {}
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(t => t.stop());
    }
    mediaStream = null;
    videoTrack = null;
  }

  /**
   * Start native BarcodeDetector
   */
  async function startNativeDetector(deviceId) {
    const { camNode } = config.elements;
    await startMedia(deviceId);
    
    if (!('BarcodeDetector' in window)) {
      return startZXing(deviceId).catch(() => startQuagga(deviceId));
    }

    const detector = new window.BarcodeDetector({
      formats: ["qr_code", "aztec", "code_128", "code_39", "code_93", "data_matrix", "ean_13", "ean_8", "itf", "pdf417", "upc_a", "upc_e"]
    });

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    let lastPickerAt = 0;

    const loop = async () => {
      if (!mediaStream) return;
      requestAnimationFrame(loop);
      if (camNode.readyState < 2) return;

      canvas.width = camNode.videoWidth;
      canvas.height = camNode.videoHeight;
      ctx.drawImage(camNode, 0, 0, canvas.width, canvas.height);

      try {
        const detections = await detector.detect(canvas);
        if (!detections || !detections.length) return;

        const qrs = detections.filter(c => (c.format || c.type) === 'qr_code');
        if (qrs.length > 0) {
          const choices = [];
          qrs.forEach((c, idx) => {
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
            handleIMEI(imeis[0] || raw);
          } else if (choices.length > 1) {
            const now = Date.now();
            if (now - lastPickerAt > 600) {
              lastPickerAt = now;
              buildPicker(choices, (picked) => {
                const imeis = imeiCandidatesFromString(picked);
                handleIMEI(imeis[0] || picked);
              }, 'Multiple QR codes found — pick one');
            }
          }
          return;
        }

        const vals = [...new Set(detections.map(c => (c.rawValue || c.rawValueText || "").trim()).filter(Boolean))];
        if (vals.length === 1) {
          handleIMEI(vals[0]);
        } else if (vals.length > 1) {
          const now = Date.now();
          if (now - lastPickerAt > 600) {
            lastPickerAt = now;
            buildPicker(
              vals.map(v => ({
                label: v.length > 120 ? (v.slice(0, 120) + '…') : v,
                value: v,
                meta: 'Barcode'
              })),
              (picked) => handleIMEI(picked),
              'Multiple barcodes found — pick one'
            );
          }
        }
      } catch (_) {}
    };
    loop();
  }

  /**
   * Start ZXing scanner
   */
  async function startZXing(deviceId) {
    const { camNode } = config.elements;
    
    if (!window.ZXing || !window.ZXing.BrowserMultiFormatReader) {
      throw new Error('ZXing not available');
    }

    const codeReader = new window.ZXing.BrowserMultiFormatReader();
    const devices = await codeReader.listVideoInputDevices().catch(() => []);
    let chosenId = deviceId || (devices[devices.length - 1] || devices[0] || {}).deviceId;
    if (!chosenId) throw new Error('No camera for ZXing');

    await codeReader.decodeFromVideoDevice(chosenId, camNode, (result, err) => {
      if (result && result.getText) {
        const raw = result.getText();
        const imeis = imeiCandidatesFromString(raw);
        if (imeis.length > 1) {
          buildPicker(
            imeis.map(v => ({ label: v, value: v, meta: 'IMEI' })),
            (picked) => handleIMEI(picked),
            'Multiple IMEIs found — pick one'
          );
        } else if (imeis.length === 1) {
          handleIMEI(imeis[0]);
        } else {
          handleIMEI(raw);
        }
        pauseScanline();
        try {
          navigator.vibrate?.(20);
        } catch (_) {}
      }
    });

    const stream = camNode.srcObject;
    mediaStream = stream || null;
    videoTrack = stream ? (stream.getVideoTracks()[0] || null) : null;
    startZXing._stop = () => {
      try {
        codeReader.reset();
      } catch (_) {}
    };
  }

  /**
   * Start Quagga scanner
   */
  async function startQuagga(deviceId) {
    const { camNode } = config.elements;
    
    if (!window.Quagga) {
      showToast('Quagga not loaded.', false);
      return;
    }
    
    window.Quagga.init({
      inputStream: {
        type: 'LiveStream',
        target: camNode,
        constraints: {
          facingMode: deviceId ? undefined : 'environment',
          deviceId: deviceId || undefined,
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      },
      decoder: {
        readers: [
          'code_128_reader',
          'ean_reader',
          'ean_8_reader',
          'code_39_reader',
          'upc_reader',
          'upc_e_reader',
          'itf_reader',
          'codabar_reader'
        ]
      },
      locate: true,
      numOfWorkers: navigator.hardwareConcurrency ? Math.min(4, navigator.hardwareConcurrency) : 2
    }, (err) => {
      if (err) {
        showToast('Camera init failed. Use HTTPS or allow camera.', false);
        return;
      }
      window.Quagga.start();
    });
    
    window.Quagga.onDetected((result) => {
      const code = (result && result.codeResult && result.codeResult.code) || '';
      if (!code) return;
      handleIMEI(code);
    });
  }

  // Public API
  return {
    init: init,
    stop: stopAll
  };
})();

