# Phone Scanner Unification Guide

## Overview
Unify phone scanner across Scan In and Scan & Sell pages to use identical detection logic.

---

## Current State

### Existing Scanner Files
- `static/js/phone_scanner.js` - Shared scanner (partially used)
- `static/js/unified-scanner.js` - Unified scanner module
- `static/js/smart_scanner.js` - Smart detection
- `static/js/imei_scanner.js` - IMEI-specific
- `static/js/phones-imei-scanner.js` - Phones IMEI scanner

### Problem
Multiple scanner implementations exist with inconsistent behavior between:
- **Phones Scan In** (`templates/inventory/phones_scan_in.html`)
- **Phones Scan & Sell / Fast Sell** (`templates/inventory/scan_sold.html`)

---

## Target Behavior

### Unified Scanner Features

1. **Multi-format detection**:
   - Barcodes (EAN, UPC, Code128, etc.)
   - QR codes
   - IMEI (15 digits)

2. **Smart prompts**:
   - 15 digits detected → "Use as IMEI?" or "Use as Barcode?"
   - QR/EAN detected → "Use as Barcode?" or "Product lookup?"
   - Multiple IMEIs in QR → Picker modal with clickable list

3. **Not found flow**:
   - Product not found → Show: "Product not found. ➕ Add Product"
   - Clicking Add Product → Opens `{% url 'inventory:phones_wizard' %}`

4. **Camera features**:
   - Rear camera default (environment-facing)
   - Front/rear camera toggle
   - Torch/flashlight toggle (if supported)
   - Multiple fallback libraries:
     1. BarcodeDetector API (Chrome/Edge native)
     2. ZXing (cross-platform)
     3. Quagga (fallback for legacy)

---

## Recommended Approach

### Option 1: Use `static/js/unified-scanner.js` (Preferred)

Extract the scanner from `scan_sold.html` and make it reusable.

**Implementation:**

1. **Extract scanner logic to `static/js/unified-scanner.js`**:

```javascript
/**
 * Unified Phone Scanner
 * Supports IMEI, Barcode, QR detection
 * Usage: UnifiedScanner.init(inputId, options)
 */

class UnifiedScanner {
  constructor(inputId, options = {}) {
    this.input = document.getElementById(inputId);
    this.options = {
      onIMEI: options.onIMEI || ((imei) => { console.log('IMEI:', imei); }),
      onBarcode: options.onBarcode || ((code) => { console.log('Barcode:', code); }),
      onNotFound: options.onNotFound || (() => { alert('Product not found'); }),
      onError: options.onError || ((err) => { console.error(err); }),
      wizardUrl: options.wizardUrl || '/inventory/wizard/phones/',
      mode: options.mode || 'auto' // 'imei', 'barcode', 'auto'
    };
    
    this.scanning = false;
    this.stream = null;
    this.video = null;
  }
  
  async init() {
    // Create scanner UI
    this.createUI();
    
    // Try detection methods in order
    try {
      if ('BarcodeDetector' in window) {
        await this.startBarcodeDetector();
      } else if (window.ZXing) {
        await this.startZXing();
      } else if (window.Quagga) {
        await this.startQuagga();
      } else {
        throw new Error('No scanner library available');
      }
    } catch (err) {
      this.options.onError(err);
    }
  }
  
  createUI() {
    // Create video element and controls
    const container = document.createElement('div');
    container.id = 'scanner-container';
    container.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.95); z-index: 9999;
      display: none; flex-direction: column;
    `;
    
    const video = document.createElement('video');
    video.id = 'scanner-video';
    video.autoplay = true;
    video.playsinline = true;
    video.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
    
    const controls = document.createElement('div');
    controls.style.cssText = 'position: absolute; bottom: 20px; left: 0; right: 0; text-align: center; z-index: 10000;';
    controls.innerHTML = `
      <button id="scanner-close" style="padding:12px 24px;background:white;border:none;border-radius:8px;font-weight:600;margin:0 8px">Close</button>
      <button id="scanner-torch" style="padding:12px 24px;background:#6366f1;color:white;border:none;border-radius:8px;font-weight:600;margin:0 8px">💡 Torch</button>
    `;
    
    container.appendChild(video);
    container.appendChild(controls);
    document.body.appendChild(container);
    
    this.container = container;
    this.video = video;
    
    // Event listeners
    document.getElementById('scanner-close').onclick = () => this.stop();
    document.getElementById('scanner-torch').onclick = () => this.toggleTorch();
  }
  
  async startBarcodeDetector() {
    const detector = new BarcodeDetector({ formats: ['qr_code', 'ean_13', 'code_128'] });
    
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: 1280, height: 720 }
    });
    
    this.video.srcObject = this.stream;
    this.container.style.display = 'flex';
    this.scanning = true;
    
    const detect = async () => {
      if (!this.scanning) return;
      
      try {
        const barcodes = await detector.detect(this.video);
        if (barcodes.length > 0) {
          const code = barcodes[0].rawValue;
          this.handleDetection(code);
        }
      } catch (err) {
        console.error('Detection error:', err);
      }
      
      requestAnimationFrame(detect);
    };
    
    detect();
  }
  
  async startZXing() {
    const reader = new ZXing.BrowserMultiFormatReader();
    
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment' }
    });
    
    this.video.srcObject = this.stream;
    this.container.style.display = 'flex';
    this.scanning = true;
    
    reader.decodeFromVideoDevice(null, this.video, (result) => {
      if (result) {
        this.handleDetection(result.getText());
      }
    });
  }
  
  handleDetection(code) {
    const imeiMatch = code.match(/(\d{15})/g);
    
    if (this.options.mode === 'auto') {
      // Smart detection
      if (imeiMatch && imeiMatch.length === 1) {
        this.promptUse('IMEI', imeiMatch[0]);
      } else if (imeiMatch && imeiMatch.length > 1) {
        this.showPicker(imeiMatch);
      } else {
        this.promptUse('Barcode', code);
      }
    } else if (this.options.mode === 'imei') {
      if (imeiMatch) {
        this.options.onIMEI(imeiMatch[0]);
      }
    } else {
      this.options.onBarcode(code);
    }
    
    this.stop();
  }
  
  promptUse(type, value) {
    const use = confirm(`Use this ${type}?\n\n${value}`);
    if (use) {
      if (type === 'IMEI') {
        this.options.onIMEI(value);
      } else {
        this.options.onBarcode(value);
      }
    }
  }
  
  showPicker(options) {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
      background: white; padding: 24px; border-radius: 16px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3); z-index: 10001;
      max-width: 400px; width: 90%;
    `;
    
    modal.innerHTML = `
      <h3 style="margin:0 0 16px">Select IMEI</h3>
      ${options.map((imei, i) => `
        <button onclick="picker_select_${i}()" style="
          width: 100%; padding: 12px; margin: 8px 0;
          background: #f1f5f9; border: 2px solid #e2e8f0;
          border-radius: 8px; font-size: 16px; cursor: pointer;
        ">${imei}</button>
      `).join('')}
      <button onclick="picker_close()" style="
        width: 100%; padding: 12px; margin: 16px 0 0;
        background: #ef4444; color: white; border: none;
        border-radius: 8px; font-weight: 600; cursor: pointer;
      ">Cancel</button>
    `;
    
    document.body.appendChild(modal);
    
    options.forEach((imei, i) => {
      window[`picker_select_${i}`] = () => {
        this.options.onIMEI(imei);
        document.body.removeChild(modal);
      };
    });
    
    window.picker_close = () => document.body.removeChild(modal);
  }
  
  stop() {
    this.scanning = false;
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    if (this.container) {
      this.container.style.display = 'none';
    }
  }
  
  async toggleTorch() {
    const track = this.stream?.getVideoTracks()[0];
    if (!track) return;
    
    const capabilities = track.getCapabilities();
    if (capabilities.torch) {
      const current = track.getSettings().torch;
      await track.applyConstraints({ advanced: [{ torch: !current }] });
    }
  }
  
  static init(inputId, options) {
    return new UnifiedScanner(inputId, options).init();
  }
}

window.UnifiedScanner = UnifiedScanner;
```

2. **Use in Phones Scan In**:

```html
<script src="{% static 'js/unified-scanner.js' %}"></script>
<script>
UnifiedScanner.init('imei-input', {
  onIMEI: (imei) => {
    document.getElementById('imei-input').value = imei;
    // Lookup product
    lookupByIMEI(imei);
  },
  onNotFound: () => {
    showAddProductPrompt();
  },
  wizardUrl: '{% url "inventory:phones_wizard" %}'
});

function showAddProductPrompt() {
  const add = confirm('Product not found. Add new product?');
  if (add) {
    window.location.href = '{% url "inventory:phones_wizard" %}';
  }
}
</script>
```

3. **Use in Phones Scan & Sell (identical)**:

```html
<script src="{% static 'js/unified-scanner.js' %}"></script>
<script>
UnifiedScanner.init('imei-input', {
  onIMEI: (imei) => {
    document.getElementById('imei-input').value = imei;
    // Lookup for sale
    lookupForSale(imei);
  },
  onNotFound: () => {
    showAddProductPrompt();
  },
  wizardUrl: '{% url "inventory:phones_wizard" %}'
});
</script>
```

---

## Files to Update

1. **`static/js/unified-scanner.js`** - Create unified scanner class
2. **`templates/inventory/phones_scan_in.html`** - Replace scanner with unified version
3. **`templates/inventory/scan_sold.html`** - Replace scanner with unified version
4. **`templates/verticals/phones/sale_wizard.html`** - Use unified scanner

---

## Testing Checklist

- [ ] Scan In: IMEI detection works
- [ ] Scan In: Barcode detection works
- [ ] Scan In: QR with multiple IMEIs shows picker
- [ ] Scan In: Not found shows "Add Product" prompt
- [ ] Scan & Sell: IMEI detection works
- [ ] Scan & Sell: Same behavior as Scan In
- [ ] Torch toggle works (if supported)
- [ ] Camera switch works (front/rear)
- [ ] Mobile: Scanner uses rear camera by default
- [ ] Desktop: Scanner works with webcam

---

**Implementation Time**: 2-3 hours  
**Impact**: Consistent scanner experience across all phone pages, no code duplication

