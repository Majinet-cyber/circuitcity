# Smart Scanner Usage Guide

## Quick Start

The Smart Scanner is a unified, intelligent barcode/IMEI scanner component that works across all CircuitCity verticals.

## Basic Usage

### 1. Include the Partial in Your Template

```django
{% include "partials/smart_scanner.html" with
  scanner_title="Scan IMEI"
  scanner_target_input_id="id_imei"
  scanner_mode="imei"
%}
```

### 2. That's It!

The scanner will automatically:
- Load the required JavaScript (`smart_scanner.js`)
- Render camera controls and video preview
- Detect multiple barcodes and show a numbered selection list
- Fill your target input when a code is selected
- Trigger `input` and `change` events on the target input

## Parameters

### Required
- **`scanner_target_input_id`**: The ID of the input field to fill with scanned value
  - Example: `"id_imei"`, `"barcode-input"`, `"sku_field"`

### Optional
- **`scanner_title`**: Title shown above scanner controls
  - Default: `"Scan Code"`
  - Example: `"📷 Scan IMEI with Camera"`

- **`scanner_mode`**: Type of scanning
  - Options: `"imei"`, `"sku"`, `"barcode"`
  - Default: `"barcode"`
  - IMEI mode: Extracts 15-digit sequences from QR codes
  - SKU/Barcode mode: Uses raw detected value

- **`scanner_container_id`**: Custom container element ID
  - Default: `"smartScannerContainer"`
  - Use unique IDs if you have multiple scanners on one page

- **`scanner_video_id`**: Custom video element ID
  - Default: `"smartScannerVideo"`

- **`scanner_scanline_id`**: Custom scan line element ID
  - Default: `"smartScannerScanline"`

- **`scanner_auto_start`**: Auto-start camera on page load
  - Default: `false`
  - Set to `true` to start immediately (requires HTTPS)

## Examples

### Example 1: IMEI Scanner (Phones)

```django
<!-- In your form -->
<div>
  <label for="id_imei">IMEI (15 digits)</label>
  <input type="text" id="id_imei" name="imei" maxlength="15">
</div>

<!-- Include scanner -->
{% include "partials/smart_scanner.html" with
  scanner_title="📷 Scan IMEI"
  scanner_target_input_id="id_imei"
  scanner_mode="imei"
%}
```

### Example 2: Barcode Scanner (Clothing/Liquor/Pharmacy)

```django
<!-- In your form -->
<div>
  <label for="product_barcode">Product Barcode</label>
  <input type="text" id="product_barcode" name="barcode">
</div>

<!-- Include scanner -->
{% include "partials/smart_scanner.html" with
  scanner_title="📷 Scan Product Barcode"
  scanner_target_input_id="product_barcode"
  scanner_mode="barcode"
%}
```

### Example 3: SKU Scanner

```django
<!-- In your form -->
<div>
  <label for="sku_input">SKU</label>
  <input type="text" id="sku_input" name="sku">
</div>

<!-- Include scanner -->
{% include "partials/smart_scanner.html" with
  scanner_title="Scan SKU"
  scanner_target_input_id="sku_input"
  scanner_mode="sku"
%}
```

### Example 4: Multiple Scanners on One Page

```django
<!-- Scanner 1: IMEI -->
{% include "partials/smart_scanner.html" with
  scanner_title="Scan IMEI"
  scanner_target_input_id="id_imei"
  scanner_mode="imei"
  scanner_container_id="imeiScanner"
  scanner_video_id="imeiVideo"
  scanner_scanline_id="imeiScanline"
%}

<!-- Scanner 2: Serial Number -->
{% include "partials/smart_scanner.html" with
  scanner_title="Scan Serial"
  scanner_target_input_id="id_serial"
  scanner_mode="barcode"
  scanner_container_id="serialScanner"
  scanner_video_id="serialVideo"
  scanner_scanline_id="serialScanline"
%}
```

## Features

### Multi-Barcode Detection
When multiple barcodes are detected in the same frame, the scanner shows a numbered list:

```
Multiple codes found — pick one

1. 1234567890123
2. ABCD-9911-XYZ
3. 9876543210987
```

User clicks/taps their choice, and it fills the target input.

### Visual Feedback
- **Animated scan line**: Sweeps up and down continuously
- **Pause on detection**: Scan line pauses briefly when code detected
- **Status messages**: Shows "Camera active", "Scanned: XXX", etc.
- **Vibration**: Brief vibration on mobile when code detected

### Camera Controls
- **Start Camera**: Opens camera and begins scanning
- **Stop Camera**: Closes camera and releases resources
- **Camera Selection**: Dropdown to switch between cameras (if multiple available)
- **Torch/Flash**: Toggle flashlight (if supported by device)

### Fallback Support
1. **BarcodeDetector API**: Native browser API (fastest, most formats)
2. **ZXing Library**: JavaScript fallback (QR + 1D barcodes)
3. **Quagga Library**: Final fallback (1D barcodes only)
4. **Manual Entry**: Always available if camera fails

## Browser Requirements

### Required
- **HTTPS or localhost**: Camera access requires secure context
- **Camera permission**: User must grant camera access

### Supported Browsers
- ✅ Chrome/Edge 83+ (BarcodeDetector native)
- ✅ Safari 14+ (via ZXing fallback)
- ✅ Firefox 90+ (via ZXing fallback)
- ✅ Mobile browsers (iOS Safari, Chrome Android)

### Unsupported
- ❌ Internet Explorer (no camera API support)
- ❌ Very old browsers (< 2020)

## Advanced Usage

### Listening to Scan Events

The scanner automatically triggers `input` and `change` events on the target input. You can listen to these:

```javascript
const targetInput = document.getElementById('id_imei');

targetInput.addEventListener('input', function(e) {
  console.log('Scanned value:', e.target.value);
  // Your custom logic here
});

targetInput.addEventListener('change', function(e) {
  console.log('Value changed:', e.target.value);
  // Trigger validation, API calls, etc.
});
```

### Programmatic Control

If you need more control, you can access the SmartScanner API directly:

```javascript
// Create scanner instance
const scanner = SmartScanner.create({
  videoElementId: 'myVideo',
  targetInputId: 'myInput',
  scanMode: 'barcode',
  onDetect: function(value) {
    console.log('Detected:', value);
    // Custom handling
  },
  onError: function(error) {
    console.error('Scanner error:', error);
  }
});

// Start scanning
await scanner.start();

// Stop scanning
scanner.stop();

// Enable torch
await scanner.enableTorch(true);
```

## Troubleshooting

### Camera Not Starting
- **Check HTTPS**: Camera requires secure context (HTTPS or localhost)
- **Check permissions**: User must allow camera access
- **Check device**: Ensure device has a camera
- **Check browser**: Update to latest version

### No Barcodes Detected
- **Check lighting**: Ensure good lighting on barcode
- **Check distance**: Hold camera 10-30cm from barcode
- **Check focus**: Ensure camera is focused (may take 1-2 seconds)
- **Check format**: Ensure barcode format is supported

### Multiple Scanners Conflict
- **Use unique IDs**: Provide custom `scanner_container_id`, `scanner_video_id`, etc.
- **Don't start multiple simultaneously**: Only one scanner should be active at a time

### Performance Issues
- **Close other camera apps**: Ensure no other apps using camera
- **Reduce frame rate**: Scanner throttles to 30 FPS by default
- **Use native API**: BarcodeDetector is fastest (Chrome/Edge only)

## Styling

The scanner uses CSS variables for theming. You can override these in your page:

```css
:root {
  --cc-panel: #ffffff;
  --cc-border: #e2e8f0;
  --cc-text: #0f172a;
  --cc-muted: #64748b;
}
```

Or add custom styles:

```css
.smart-scanner-container {
  /* Your custom styles */
}

.smart-scanner-video {
  /* Custom video styles */
}
```

## Migration from Old Scanners

If you're migrating from an old scanner implementation:

### Before (Old Way)
```django
<button id="openScannerBtn">Scan</button>
<script src="{% static 'js/old-scanner.js' %}"></script>
<script>
  // 100+ lines of scanner initialization code
</script>
```

### After (New Way)
```django
{% include "partials/smart_scanner.html" with
  scanner_target_input_id="id_imei"
  scanner_mode="imei"
%}
```

That's it! 100+ lines reduced to 3 lines.

## Support

For issues or questions:
1. Check `SCANNER_UNIFICATION_IMPLEMENTATION.md` for implementation details
2. Check browser console for error messages
3. Verify HTTPS and camera permissions
4. Test with manual entry as fallback

## License

Part of CircuitCity project. Internal use only.

