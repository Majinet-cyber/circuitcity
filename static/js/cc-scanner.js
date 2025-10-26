// cc-scanner.js
(() => {
  const video  = document.getElementById('ccScannerVideo');
  const canvas = document.getElementById('ccScannerCanvas');
  const startBtn = document.getElementById('ccStartBtn');
  const stopBtn  = document.getElementById('ccStopBtn');
  const torchBtn = document.getElementById('ccTorchBtn');

  let stream = null;
  let track = null;
  let scanning = false;
  let rafId = null;
  let barcodeDetector = null;
  let activeConstraints = null;

  // ——— IMEI helpers ———
  function normalizeCandidate(value) {
    // strip spaces/slashes like "IMEI: 356789012345678/01"
    return (value || '').replace(/[^\d]/g, '').slice(0, 17); // keep extra 2 for IMEI SV
  }
  function looksLikeIMEI(value) {
    const v = normalizeCandidate(value);
    // IMEI is 15 digits; sometimes 16-17 when SV appended. Accept 15–17 then trim.
    return /^\d{15,17}$/.test(v);
  }
  function toIMEI15(value) {
    const v = normalizeCandidate(value);
    return v.length >= 15 ? v.slice(0, 15) : v;
  }

  async function start() {
    if (scanning) return;
    try {
      // Primary constraints: back camera, 60 FPS if possible
      const constraints = {
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 60, max: 60 },
          focusMode: "continuous",
          advanced: [{ focusMode: "continuous" }]
        }
      };
      stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (e1) {
      // Fallback to whatever camera available
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio:false });
    }

    video.srcObject = stream;
    track = stream.getVideoTracks()[0];
    activeConstraints = track.getConstraints?.() || {};
    await video.play().catch(() => { /* will start after tap */ });

    // Prepare canvas
    canvas.width  = video.videoWidth  || 1280;
    canvas.height = video.videoHeight || 720;

    // Try BarcodeDetector first
    if ('BarcodeDetector' in window) {
      try {
        // Code types commonly used for phone boxes/IMEI: code_128, ean_13, upc_e, qr
        barcodeDetector = new window.BarcodeDetector({
          formats: ['code_128','ean_13','upc_e','qr_code']
        });
      } catch { barcodeDetector = null; }
    }

    scanning = true;
    loop();
    enableTorch(true);
  }

  function stop() {
    scanning = false;
    if (rafId) cancelAnimationFrame(rafId);
    if (track) track.stop();
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null; track = null;
    enableTorch(false);
  }

  async function loop() {
    if (!scanning) return;
    rafId = requestAnimationFrame(loop);

    if (video.readyState < 2) return; // not ready
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // 1) Try native BarcodeDetector (super fast)
    if (barcodeDetector) {
      try {
        const barcodes = await barcodeDetector.detect(canvas);
        if (barcodes && barcodes.length) {
          for (const b of barcodes) {
            const raw = (b.rawValue || '').trim();
            const candidate = normalizeCandidate(raw);
            if (looksLikeIMEI(candidate) || candidate.length >= 8) {
              onDetect(raw);
              return;
            }
          }
        }
      } catch (_) { /* ignore */ }
    } else {
      // 2) Lightweight ZXing fallback (no build tools, via dynamic import)
      if (!window._ZXingLoaded) {
        window._ZXingLoaded = import('https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/esm/index.min.js')
          .then(mod => (window._ZXing = mod));
      }
      const ZX = await window._ZXingLoaded.then(() => window._ZXing);
      if (ZX) {
        const luminanceSource = new ZX.HTMLCanvasElementLuminanceSource(canvas);
        const binarizer = new ZX.GlobalHistogramBinarizer(luminanceSource);
        const bitmap = new ZX.BinaryBitmap(binarizer);
        try {
          const result = ZX.MultiFormatReader.decode(bitmap);
          const raw = result?.getText?.() || '';
          if (raw) onDetect(raw);
        } catch { /* no code in this frame */ }
      }
    }
  }

  function onDetect(rawValue) {
    // Debounce by stopping immediately
    stop();

    const value = toIMEI15(rawValue);
    // Fill the active input on page if present:
    const input = document.querySelector('input[name="imei"], input[data-role="imei"]');
    if (input) {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Auto-submit if your page wants that:
    const form = input ? input.closest('form') : document.querySelector('form[data-autosubmit="imei"]');
    if (form) form.requestSubmit();

    // Optional UX: brief vibration
    if (navigator.vibrate) navigator.vibrate(80);
  }

  // Torch (flash) control
  let torchOn = false;
  async function enableTorch(desired) {
    if (!track) return;
    const capabilities = track.getCapabilities?.() || {};
    if (!('torch' in capabilities)) return; // device doesn’t support torch
    try {
      await track.applyConstraints({ advanced: [{ torch: desired }] });
      torchOn = desired;
    } catch {}
  }

  // Buttons
  startBtn?.addEventListener('click', start);
  stopBtn?.addEventListener('click', stop);
  torchBtn?.addEventListener('click', () => enableTorch(!torchOn));

  // Handle page visibility (saves battery and avoids black after resume)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop(); else start();
  });

  // Start automatically if allowed
  window.addEventListener('load', () => {
    // On many mobiles you still need a tap; we try silently.
    start().catch(() => {/* user gesture required */});
  });

  // Prevent iOS auto-fullscreen
  video.setAttribute('playsinline', '');
  video.setAttribute('muted', '');
})();
