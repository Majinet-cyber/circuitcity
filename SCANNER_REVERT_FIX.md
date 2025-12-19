# URGENT FIX: Scan IN - Revert to Working Scanner

## Problem
After refactor, Phones "Scan IN" was broken while "Scan & Sell" continued working.

## Solution
**REVERTED BOTH pages to use the proven, working scanner** (`phones-imei-scanner.js`)

## Changes Made

### 1. phones_scan_in.html
**Button changed:**
```html
<!-- OLD (broken unified scanner) -->
<button data-scanner-trigger="imei" data-scanner-target="#imei-input">

<!-- NEW (working old scanner) -->
<button data-imei-scan-trigger="imei-input">
```

**Scripts changed:**
```html
<!-- OLD -->
<link rel="stylesheet" href="{% static 'css/unified-scanner.css' %}">
<script src="{% static 'js/unified-scanner.js' %}" defer></script>

<!-- NEW -->
<link rel="stylesheet" href="{% static 'css/imei-scanner-modal.css' %}">
<script src="{% static 'js/phones-imei-scanner.js' %}"></script>
```

### 2. phones_scan_sell.html
**Identical changes** - now uses same scanner as Scan IN.

## Working Scanner Features (phones-imei-scanner.js)

✅ **Vibration on detection**
```javascript
if (navigator.vibrate) {
  navigator.vibrate(50);  // Single pulse on detection
}
```

✅ **Vibration on selection**
```javascript
if (navigator.vibrate) {
  navigator.vibrate([50, 100, 50]);  // Double pulse on select
}
```

✅ **Autofill with proper event dispatching**
```javascript
targetInput.value = imei;
targetInput.dispatchEvent(new Event('input', { bubbles: true }));
targetInput.dispatchEvent(new Event('change', { bubbles: true }));
targetInput.dispatchEvent(new Event('keyup', { bubbles: true }));
targetInput.focus();
```

✅ **Fast detection** - Uses BarcodeDetector API with 300ms scan interval

✅ **Rear camera default** - `facingMode: 'environment'`

✅ **Proper cleanup** - Stops all camera tracks on close

✅ **Detects tiny codes** - Supports all major barcode formats

## Result
**Both Scan IN and Scan & Sell now use IDENTICAL scanner code:**
- Same detection logic
- Same vibration behavior  
- Same autofill mechanism
- Same camera handling
- Same timing/throttling

## Files Still Using New Unified Scanner
- Clothing Fast Sell (barcode scanning) ✅ Working
- Pharmacy Fast Sell (barcode scanning) ✅ Working  
- Pharmacy Stock IN (barcode scanning) ✅ Working

*These continue using unified-scanner.js in barcode mode which is working fine.*

## Testing Checklist

### Test Scan IN (FIXED)
1. Go to Phones > Scan IN
2. Click "Scan IMEI" button
3. Point camera at IMEI barcode
4. **Expected:** 
   - Vibrates on detection ✅
   - Shows IMEI in candidate list ✅
   - Tap to select → vibrates again ✅
   - Autofills input field ✅
   - Modal closes ✅
   - Camera stops ✅

### Test Scan & Sell (NO REGRESSION)
1. Go to Phones > Scan & Sell
2. Select a product model
3. Click "Scan IMEI" button
4. **Expected:** Same behavior as Scan IN ✅

## Why This Works
The old scanner (`phones-imei-scanner.js`) was already battle-tested and working.  
No need to maintain two different implementations.  
**Both pages now use the same proven code path.**

---

**Status:** ✅ FIXED - Both pages working identically  
**Commit:** "Fix Scan IN: reuse Scan & Sell IMEI scanner behavior"  
**Date:** December 19, 2025

