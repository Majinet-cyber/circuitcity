// static/js/scanner.js
// Drop-in advanced scanner with:
// - HTTPS/localhost/Android-flag compatible camera start
// - Native BarcodeDetector (multi-code per frame) with ZXing fallback
// - Auto-pick OR user picker when multiple codes are seen
// - Torch support (when available)
// - Camera switch helper
//
// Usage (example):
// CCScanner.startScan({
//   videoEl: document.querySelector("#scannerVideo"),
//   statusEl: document.querySelector("#scannerStatus"),
//   onResult: (value, ctx) => { /* write value into input, submit, etc. */ },
//   allowMultiple: true,            // show a picker if >1 code detected
//   scanWindowMs: 2000,             // how long to aggregate codes before picking
//   continueAfterResult: false      // keep scanning after a selection/result?
// });
(() => {
  "use strict";

  const hasBarcodeDetector = "BarcodeDetector" in window;

  let stream = null;
  let track = null;
  let detector = null;
  let zxingReader = null;
  let zxingControls = null;
  let stopRequested = false;

  // device management
  let currentDeviceId = null;

  // multi-detection aggregator
  let seenMap = new Map(); // value -> lastSeenTs
  let seenTimeoutMs = 2000;

  // ---------- small helpers ----------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function ensureVideoAttrs(videoEl) {
    // Required for autoplaying inline video on mobile browsers
    videoEl.setAttribute("playsinline", "");
    videoEl.setAttribute("muted", "");
    videoEl.playsInline = true;
    videoEl.autoplay = true;
    videoEl.muted = true;
    // Avoid PiP button overlay on some browsers
    try { videoEl.disablePictureInPicture = true; } catch {}
  }

  function isSecureEnough() {
    // Camera requires a secure context: HTTPS or localhost.
    // Android Chrome dev-flag may also mark it secure.
    if (window.isSecureContext) return true;
    const host = location.hostname || "";
    return host === "localhost" || host === "127.0.0.1";
  }

  async function getDevices(kind = "videoinput") {
    try {
      return (await navigator.mediaDevices.enumerateDevices()).filter(
        (d) => d.kind === kind
      );
    } catch {
      return [];
    }
  }

  async function getBestCameraDeviceId() {
    // After permissions granted, labels include "back"/"rear"
    const cams = await getDevices("videoinput");
    if (!cams.length) return null;
    const back = cams.find((c) => /back|rear|environment/i.test(c.label));
    return (back || cams[0]).deviceId;
  }

  async function openStream(videoEl, deviceId = null) {
    ensureVideoAttrs(videoEl);

    const base = {
      audio: false,
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        // Prefer high frame-rate if available
        frameRate: { ideal: 30 },
      },
    };

    const constraints = deviceId
      ? { ...base, video: { ...base.video, deviceId: { exact: deviceId } } }
      : { ...base, video: { ...base.video, facingMode: { ideal: "environment" } } };

    const media = await navigator.mediaDevices.getUserMedia(constraints);
    stream = media;
    track = stream.getVideoTracks()[0];
    videoEl.srcObject = stream;
    await videoEl.play();
    return stream;
  }

  async function getBackCameraStream(videoEl) {
    // Some browsers only reveal labels *after* a first permission-grant
    try {
      const temp = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      temp.getTracks().forEach((t) => t.stop());
    } catch {}
    try {
      const id = await getBestCameraDeviceId();
      currentDeviceId = id;
      return await openStream(videoEl, id);
    } catch {
      // Fallback to "environment" constraint
      return await openStream(videoEl, null);
    }
  }

  async function tryTorch(on) {
    try {
      if (!track) return false;
      const caps = track.getCapabilities?.();
      if (!caps || !caps.torch) return false;
      await track.applyConstraints({ advanced: [{ torch: !!on }] });
      return true;
    } catch {
      return false;
    }
  }

  function stopTracks() {
    try { zxingControls?.stop?.(); } catch {}
    try { if (track) track.stop(); } catch {}
    try { stream?.getTracks?.().forEach((t) => t.stop()); } catch {}
    stream = track = null;
  }

  function clearSeen() {
    seenMap.clear();
  }

  function addDetections(values) {
    const now = Date.now();
    let changed = false;

    (values || []).forEach((raw) => {
      const val = String(raw || "").trim();
      if (!val) return;
      if (!seenMap.has(val)) changed = true;
      seenMap.set(val, now);
    });

    // purge stale
    for (const [k, t] of [...seenMap.entries()]) {
      if (now - t > seenTimeoutMs) {
        seenMap.delete(k);
        changed = true;
      }
    }

    return changed;
  }

  // ------- minimal built-in picker UI (no external CSS required) -------
  function buildPicker(values, onPick) {
    const id = "ccscan-picker";
    document.getElementById(id)?.remove();

    const wrapper = document.createElement("div");
    wrapper.id = id;
    wrapper.style.cssText =
      "position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);z-index:9999;";

    const card = document.createElement("div");
    card.style.cssText =
      "background:#fff;max-width:90vw;width:520px;padding:16px;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.35);font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;";

    const h = document.createElement("div");
    h.textContent = "Multiple codes found — pick one";
    h.style.cssText = "font-weight:600;margin-bottom:10px";

    const list = document.createElement("div");
    list.style.cssText =
      "max-height:55vh;overflow:auto;display:flex;flex-direction:column;gap:8px;";

    values.forEach((v) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = v;
      btn.style.cssText =
        "text-align:left;padding:10px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#f9fafb;cursor:pointer;word-break:break-all;";
      btn.onclick = () => {
        wrapper.remove();
        onPick?.(v);
      };
      list.appendChild(btn);
    });

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    cancel.style.cssText =
      "margin-top:12px;padding:8px 12px;border-radius:10px;border:1px solid #e5e7eb;background:#fff;cursor:pointer;";
    cancel.onclick = () => wrapper.remove();

    card.append(h, list, cancel);
    wrapper.appendChild(card);
    document.body.appendChild(wrapper);
  }

  function handleFoundFactory({ onResult, allowMultiple, continueAfterResult }) {
    return (values) => {
      if (!values?.length) return;
      navigator.vibrate?.(30);

      addDetections(values);
      const uniq = [...seenMap.keys()];

      if (allowMultiple && uniq.length > 1) {
        // Show a selection overlay
        buildPicker(uniq, (choice) => {
          if (!continueAfterResult) stopScan();
          onResult?.(choice, { multiple: uniq });
        });
        return;
      }

      // Single value path
      const v = uniq[0] ?? values[0];
      if (v) {
        if (!continueAfterResult) stopScan();
        onResult?.(v, { multiple: uniq });
      }
    };
  }

  // ---------- public start/stop ----------
  async function startScan({
    videoEl,
    onResult,
    statusEl,
    allowMultiple = true,
    scanWindowMs = 2000,
    continueAfterResult = false,
  }) {
    stopRequested = false;
    seenTimeoutMs = scanWindowMs || 2000;
    clearSeen();

    if (!navigator.mediaDevices?.getUserMedia) {
      statusEl && (statusEl.textContent = "Camera not supported in this browser.");
      return;
    }

    if (!isSecureEnough()) {
      // Helpful status if camera is blocked by insecure origin
      statusEl &&
        (statusEl.textContent =
          "Camera blocked: use HTTPS/localhost (on Android Chrome you can enable the dev flag).");
      // We still attempt; Android dev-flag may make it work.
    }

    statusEl && (statusEl.textContent = "Starting camera…");
    await getBackCameraStream(videoEl);

    const handleFound = handleFoundFactory({ onResult, allowMultiple, continueAfterResult });

    // ----- Native path -----
    if (hasBarcodeDetector) {
      const formats = [
        "qr_code",
        "aztec",
        "code_128",
        "code_39",
        "code_93",
        "data_matrix",
        "ean_13",
        "ean_8",
        "itf",
        "pdf417",
        "upc_a",
        "upc_e",
      ];

      try {
        detector = new window.BarcodeDetector({ formats });
      } catch {
        detector = null;
      }

      if (detector) {
        statusEl && (statusEl.textContent = "Point camera at code…");
        const loop = async () => {
          if (stopRequested) return;
          try {
            const codes = await detector.detect(videoEl);
            if (codes?.length) {
              const vals = codes
                .map(
                  (c) =>
                    c.rawValue ||
                    c.rawValueText || // older impls
                    ""
                )
                .filter(Boolean);
              if (vals.length) handleFound(vals);
            }
          } catch {}
          requestAnimationFrame(loop);
        };
        loop();
        return;
      }
    }

    // ----- Fallback: ZXing -----
    statusEl && (statusEl.textContent = "Loading scanner…");
    await new Promise((res, rej) => {
      if (window.ZXingBrowser) return res();
      const s = document.createElement("script");
      s.src = "https://unpkg.com/@zxing/browser@latest";
      s.onload = res;
      s.onerror = rej;
      document.head.appendChild(s);
    });

    statusEl && (statusEl.textContent = "Point camera at code…");
    zxingReader = await ZXingBrowser.BrowserMultiFormatReader.createInstanceWithDelay(0);

    zxingControls = await zxingReader.decodeFromVideoDevice(
      currentDeviceId || undefined,
      videoEl,
      (result, err, controls_) => {
        zxingControls = controls_;
        if (stopRequested) {
          try { zxingControls?.stop(); } catch {}
          return;
        }
        if (result) {
          // ZXing returns one at a time; we still aggregate and show picker once we have >1 in the window
          handleFound([result.getText()]);
          if (!continueAfterResult) {
            try { zxingControls?.stop(); } catch {}
          }
        }
      }
    );
  }

  function stopScan() {
    stopRequested = true;
    stopTracks();
    detector = null;
    zxingReader = null;
    zxingControls = null;
  }

  // Optional helper: switch camera (front/back/next)
  async function switchCamera(videoEl) {
    try { stopTracks(); } catch {}
    const cams = await getDevices("videoinput");
    if (!cams.length) return false;

    const idx = Math.max(0, cams.findIndex((c) => c.deviceId === currentDeviceId));
    const next = cams[(idx + 1) % cams.length];
    currentDeviceId = next.deviceId;

    await openStream(videoEl, currentDeviceId);
    return true;
  }

  // ---------- expose minimal API ----------
  window.CCScanner = { startScan, stopScan, tryTorch, switchCamera };
})();
