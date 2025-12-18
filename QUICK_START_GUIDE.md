# Quick Start Guide: New Features

## 🎯 For Users

### "More Features" Sidebar Menu

**What is it?**  
A collapsible menu in the sidebar that groups less-frequently used features to reduce clutter.

**Where to find it:**  
Look for "More Features" near the bottom of the sidebar (below Dashboard, Stock, Sell, etc.)

**What's inside:**
- 💰 My Wallet
- 👔 Admin Wallet (managers only)
- 💾 Data Backup (managers only)
- 📊 Simulator (if enabled)

**How to use:**
1. Click "More Features" to expand
2. Click again to collapse
3. Your preference is saved automatically

---

### Barcode Scanner (Pharmacy & Clothing)

**What is it?**  
A camera-based barcode scanner for quickly adding products with barcodes.

**Where to find it:**
- **Pharmacy:** Stock In page → Toggle "Has Barcode? Yes" → Click scanner icon
- **Clothing:** Scan In page → Toggle "Has Barcode? Yes" → Click scanner icon

**How to use:**
1. Click the scanner icon (📷) next to the barcode field
2. Allow camera access when prompted
3. Hold the barcode in front of your camera
4. The barcode will auto-fill when detected
5. Complete the form and submit

**No camera?**  
No problem! Use the manual input field in the scanner modal to type or paste the barcode.

---

### Fast Sell (Pharmacy & Clothing)

**What is it?**  
Quick barcode-based selling for fast checkout.

**Where to find it:**
- **Pharmacy:** `/verticals/pharmacy/fast-sell/`
- **Clothing:** `/verticals/clothing/fast-sell/`

**How to use:**
1. Click "Start Camera" or use manual input
2. Scan product barcode
3. Product info and price load automatically
4. Adjust quantity if needed
5. Select payment method (Cash/Bank/Mobile)
6. Click "Sell Now"
7. Done! KPIs update automatically

**Missing price?**  
If a product has no selling price, you'll be prompted to enter it. The price will be saved for next time.

---

## 🔧 For Developers

### Testing the Sidebar

```bash
# Run sidebar tests
python manage.py test tests.test_sidebar_more_features

# Manual test
1. Login as manager
2. Navigate to dashboard
3. Click "More Features"
4. Verify submenu expands
5. Refresh page
6. Verify state persists
```

### Testing the Barcode Scanner

```bash
# Run scanner tests
python manage.py test tests.test_barcode_scanner_integration

# Manual test
1. Login as pharmacy/clothing user
2. Navigate to scan-in page
3. Toggle "Has Barcode? Yes"
4. Click scanner icon
5. Grant camera permission
6. Scan a barcode
7. Verify auto-fill works
```

### Debugging

**Sidebar not expanding?**
- Check browser console for JS errors
- Verify `sidebar-more-features.js` is loaded
- Check localStorage: `cc.sidebar.moreFeatures.open`

**Scanner not working?**
- Check camera permissions
- Verify `barcode-scanner-modal.js` is loaded
- Check browser supports BarcodeDetector API (or use manual input)
- Check console for errors

**Fast sell not working?**
- Verify business kind is pharmacy or clothing
- Check barcode exists in database
- Verify product has stock
- Check API endpoints return 200

---

## 📊 Quick Reference

### File Locations

**Sidebar:**
- Template: `templates/partials/sidebar_more_features.html`
- JS: `static/js/sidebar-more-features.js`
- CSS: `static/css/sidebar-more-features.css`

**Barcode Scanner:**
- JS: `static/js/barcode-scanner-modal.js`
- CSS: `static/css/barcode-scanner-modal.css`
- Pharmacy template: `templates/verticals/pharmacy/stock_in.html`
- Clothing template: `templates/verticals/clothing/scan_in.html`

**Fast Sell:**
- Service: `inventory/services/fast_sell.py`
- Pharmacy views: `inventory/verticals/pharmacy.py` (lines 269-374)
- Clothing views: `inventory/verticals/clothing.py` (lines 840-944)
- Templates: `templates/verticals/{vertical}/fast_sell.html`

### API Endpoints

**Fast Sell (Pharmacy):**
```
GET  /verticals/pharmacy/api/fast-sell/lookup/?barcode=<code>
POST /verticals/pharmacy/api/fast-sell/sell/
GET  /verticals/pharmacy/api/fast-sell/kpis/?range=today
```

**Fast Sell (Clothing):**
```
GET  /verticals/clothing/api/fast-sell/lookup/?barcode=<code>
POST /verticals/clothing/api/fast-sell/sell/
GET  /verticals/clothing/api/fast-sell/kpis/?range=today
```

### localStorage Keys

```javascript
// Sidebar state
'cc.sidebar.moreFeatures.open' // "1" = open, "0" = closed
```

---

## 🎨 Customization

### Changing Sidebar Items

Edit `templates/partials/sidebar_more_features.html`:
```django
<ul class="navlist more-features-submenu" id="moreFeaturesSubmenu">
  <!-- Add your custom items here -->
  <li>
    <a class="navlink submenu-item" href="/your-url/">
      <i class="bi bi-your-icon"></i> Your Feature
    </a>
  </li>
</ul>
```

### Changing Scanner Behavior

Edit `static/js/barcode-scanner-modal.js`:
```javascript
const scanner = new BarcodeScanner({
  onScan: (barcode) => { /* your logic */ },
  debounceMs: 1500,  // Change debounce time
  formats: ['ean_13', 'qr_code']  // Change supported formats
});
```

### Styling

**Sidebar:**
- Edit `static/css/sidebar-more-features.css`
- Follows existing glassmorphic theme
- Mobile-first responsive

**Scanner:**
- Edit `static/css/barcode-scanner-modal.css`
- Premium full-screen modal design
- Touch-friendly buttons

---

## 🐛 Troubleshooting

### "More Features" not appearing
1. Clear browser cache (Ctrl+Shift+R)
2. Check if `sidebar_more_features.html` is included
3. Verify static files are collected

### Scanner modal not opening
1. Check console for JS errors
2. Verify `barcode-scanner-modal.js` is loaded
3. Check button ID matches: `openScannerBtn`

### Camera not starting
1. Grant camera permission in browser
2. Use HTTPS (camera requires secure context)
3. Check browser supports getUserMedia API
4. Use manual input fallback

### Barcode not detected
1. Ensure good lighting
2. Hold barcode steady
3. Try different distance from camera
4. Use manual input if needed

### Fast sell not finding product
1. Verify barcode exists in database
2. Check product has stock
3. Verify business kind matches (pharmacy/clothing)
4. Check API response in Network tab

---

## 📞 Support

**For users:**
- Contact your manager or system administrator
- Check the manual test checklist in `IMPLEMENTATION_SUMMARY.md`

**For developers:**
- Review test files: `tests/test_sidebar_more_features.py`, `tests/test_barcode_scanner_integration.py`
- Check implementation summary: `IMPLEMENTATION_SUMMARY.md`
- Review code comments in source files

---

**Last Updated:** December 18, 2025  
**Version:** 1.0.0
