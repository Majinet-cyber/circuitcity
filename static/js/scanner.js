// static/js/scanner.js
(() => {
  const hasBarcodeDetector = 'BarcodeDetector' in window;
  let stream, track, detector, zxingReader, stopRequested = false;

  async function getBackCameraStream(videoEl) {
    // Prefer back camera
    const constraints = {
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 }
      }
    };
    const media = await navigator.mediaDevices.getUserMedia(constraints);
    stream = media;
    track = stream.getVideoTracks()[0];
    videoEl.srcObject = stream;
    await videoEl.play();
  }

  async function tryTorch(on) {
    try {
      if (!track) return false;
      const caps = track.getCapabilities?.();
      if (!caps || !caps.torch) return false;
      await track.applyConstraints({ advanced: [{ torch: !!on }] });
      return true;
    } catch { return false; }
  }

  async function startScan({videoEl, onResult, statusEl}) {
    stopRequested = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      statusEl.textContent = "Camera not supported";
      return;
    }

    statusEl.textContent = "Starting camera…";
    await getBackCameraStream(videoEl);

    // Native first
    if (hasBarcodeDetector) {
      const formats = ['qr_code','code_128','ean_13','ean_8','upc_a','upc_e','code_39','code_93','itf'];
      detector = new window.BarcodeDetector({ formats });
      statusEl.textContent = "Point camera at barcode…";

      const loop = async () => {
        if (stopRequested) return;
        try {
          const codes = await detector.detect(videoEl);
          if (codes && codes.length) {
            const val = codes[0].rawValue || codes[0].rawValueText || "";
            if (val) {
              navigator.vibrate?.(40);
              onResult(val);
              return; // stop after first
            }
          }
        } catch {}
        requestAnimationFrame(loop);
      };
      loop();
      return;
    }

    // Fallback: ZXing (CDN)
    statusEl.textContent = "Loading scanner…";
    await new Promise((res, rej) => {
      if (window.ZXingBrowser) return res();
      const s = document.createElement('script');
      s.src = "https://unpkg.com/@zxing/browser@latest";
      s.onload = res; s.onerror = rej; document.head.appendChild(s);
    });

    // Use Continuous decoding from stream
    statusEl.textContent = "Point camera at barcode…";
    const hints = new ZXingBrowser.BarcodeHint();
    // optional: set a subset if you want faster
    zxingReader = await ZXingBrowser.BrowserMultiFormatReader.createInstanceWithDelay(0);
    const controls = await zxingReader.decodeFromVideoDevice(
      undefined, videoEl, (result, err) => {
        if (stopRequested) { controls.stop(); return; }
        if (result) {
          navigator.vibrate?.(40);
          onResult(result.getText());
          controls.stop();
        }
      }
    );
  }

  function stopScan() {
    stopRequested = true;
    try { if (track) track.stop(); } catch {}
    try { if (stream) stream.getTracks().forEach(t => t.stop()); } catch {}
  }

  // Expose minimal API
  window.CCScanner = { startScan, stopScan, tryTorch };
})();
