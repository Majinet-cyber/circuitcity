# Phone UX - Quick Test Guide

## 🚀 Quick Start Testing

### Prerequisites
1. Have a PHONES business set up
2. Be logged in as a manager (for Add Products) or agent (for Scan In/Sell)
3. Have at least one location configured

---

## 📱 Test Flow 1: Add a Phone Model

**URL:** `/inventory/phones/products/new/`

### Steps:
1. **Click a brand panel** (e.g., Tecno - blue panel)
   - Panel expands to show inline form
   
2. **Fill out form:**
   - Model Name: `Spark 40`
   - Model Number: `KJ7` (optional)
   - Specs: `4+128` (must be format: digits+digits)
   - Order Price: `150000` (optional)

3. **Click "✅ Add Model"**
   - Success message appears: "✅ Added TECNO Spark 40 (4+128)"
   - Model appears in "Recent models" list below panel

### Mobile Test (iPhone SE / 375px):
- Open on mobile browser (or Chrome DevTools mobile view)
- All 5 panels stack vertically ✓
- Form fields fit without horizontal scroll ✓
- Tapping input doesn't zoom (16px font) ✓

### Expected Results:
✅ Model saved to PhoneProductCatalog
✅ Shows in Recent models (max 10)
✅ No duplicate if same brand+model+specs submitted again (updates instead)

---

## 📦 Test Flow 2: Scan In a Phone

**URL:** `/inventory/phones/scan-in/` or `/inventory/scan-in/`

### Steps:
1. **Select brand** (e.g., tap Samsung - orange panel)
   - Panel highlights
   - Model dropdown loads

2. **Choose model** from dropdown (e.g., "Galaxy A15 (4+128)")
   - IMEI picker sidebar shows existing IMEIs (if any)

3. **Enter IMEI:**
   - Type: `123456789012345` (exactly 15 digits)
   - Counter updates: "0 / 15" → "15 / 15 digits"
   - Green checkmark appears: "✅ 15 / 15 digits"
   - "✅ Scan In Phone" button enables

4. **Click "✅ Scan In Phone"**
   - Success: "✅ Samsung Galaxy A15 (4+128) (IMEI: 123456789012345) added to stock! Scanned 1 today. Keep going!"
   - Daily target progress bar updates

### Test Invalid IMEI:
- Type 14 digits → Button stays disabled ✓
- Type 16 digits → Input blocks at 15 ✓
- Try same IMEI twice → Error: "IMEI ... already exists" ✓

### Mobile Test:
- Numeric keyboard appears (inputmode="numeric") ✓
- Counter is visible and updates in real-time ✓
- No zoom on input focus ✓

### Expected Results:
✅ InventoryItem created with status IN_STOCK
✅ IMEI is stored as exactly 15 digits
✅ Duplicate IMEI prevented
✅ Gamification bar shows updated count

---

## 💰 Test Flow 3: Sell a Phone (3-Step Wizard)

**URL:** `/inventory/sell-phone/`

### Step 1: IMEI Lookup
1. **Enter IMEI:** `123456789012345` (the one you just scanned in)
   - Counter: "15 / 15 digits" with green checkmark
   - "Search" button enabled

2. **Click "Search"**
   - Success: Shows phone summary card with:
     - Brand, Model, Specs
     - IMEI
     - Location
   - Button: "Next: Set Price →"

### Test Not Found:
- Enter a random 15-digit IMEI (e.g., `999999999999999`)
- Error: "This phone (IMEI ...) is not in stock."
- Options: "Try another IMEI" ✓

### Step 2: Price Entry
1. **Price auto-fills** (if default_selling_price set)
2. **Change price:** `200000`
3. **Click "Next: Payment Method →"**

### Step 3: Payment Method
1. **Review sale summary:**
   - Phone: Samsung Galaxy A15 (4+128)
   - IMEI: 123456789012345
   - Selling Price: MWK 200,000

2. **Select payment:**
   - Tap "💵 Cash" (or Bank/Mobile Money)
   - Radio card highlights with blue border

3. **Click "✅ Complete Sale"**
   - Success: Sale recorded
   - Inventory status updated to SOLD
   - Redirect to dashboard or "New sale" option

### Test Already Sold:
- Try to sell same IMEI again (Step 1)
- Error: "This phone is already sold or inactive." ✓

### Mobile Test:
- All 3 wizard steps fit in viewport ✓
- Radio cards are big tap targets (full-width) ✓
- Progress bar shows current step clearly ✓

### Expected Results:
✅ Sale record created
✅ InventoryItem.status = "SOLD"
✅ Commission recorded (if configured)
✅ Dashboards/wallets updated

---

## 🌐 Test Flow 4: Landing Page Mobile Menu

**URL:** `/` (root)

### Desktop Test (>768px):
1. **See horizontal nav** at top
   - How It Works, About, Login, Get Started buttons visible
   - No hamburger icon

### Mobile Test (≤768px):
1. **Hamburger icon visible** (☰ three bars)
2. **Desktop nav hidden**
3. **Tap hamburger:**
   - Menu slides down
   - Shows vertical list: Home, How It Works, About, Login, Get Started
   - Hamburger animates to X

4. **Tap "How It Works":**
   - Menu closes
   - Scrolls to section

5. **Tap hamburger again:**
   - Menu closes (X animates back to ☰)

6. **Test click outside:**
   - Open menu
   - Tap anywhere outside menu
   - Menu closes ✓

### Mobile Hero Test:
- Text "Doing business shouldn't be a headache" wraps cleanly ✓
- Two buttons stack vertically (Get Started + See How It Works) ✓
- No horizontal scroll at 375px width ✓

### Expected Results:
✅ Hamburger menu appears only on mobile
✅ Menu items are vertical with big tap targets
✅ Menu auto-closes on link click or outside click
✅ No text overflow or horizontal scroll

---

## 🎯 Quick Regression Tests

### 1. Existing Inventory Still Works
- Navigate to `/inventory/list/`
- Stock list loads ✓
- Existing phones show correct data ✓

### 2. Dashboard Loads
- Navigate to `/inventory/dashboard/`
- Dashboard loads without errors ✓
- Counters show correct numbers ✓

### 3. No 500 Errors
- Check Django logs for any exceptions
- All pages load successfully ✓

---

## 🐛 Common Issues & Fixes

### Issue: IMEI button stays disabled
**Fix:** Ensure exactly 15 digits typed. Check browser console for JS errors.

### Issue: Brand models don't load
**Fix:** Ensure PhoneProductCatalog has entries for that brand. Run `seed_phone_catalog(business)`.

### Issue: Duplicate IMEI error on first scan
**Fix:** Check if IMEI already exists in database. Use different IMEI or delete existing.

### Issue: Mobile menu doesn't open
**Fix:** Check browser console. Ensure JavaScript is enabled. Try hard refresh (Ctrl+Shift+R).

### Issue: Wizard loses data between steps
**Fix:** Check Django sessions are configured. Session middleware must be active.

---

## 📊 Success Metrics

After testing, confirm:
- [ ] All 5 brands work in Add Products
- [ ] IMEI validation blocks <15 and >15 digits
- [ ] Scan In creates InventoryItem correctly
- [ ] Wizard completes sale and updates inventory
- [ ] Mobile menu works on small screens
- [ ] No horizontal scroll on any page at 375px
- [ ] No console errors in browser DevTools

---

## 🔍 Debug Tips

### View Django Logs
```bash
# Check for errors
tail -f logs/django.log
```

### Browser DevTools (F12)
- **Console:** Check for JS errors
- **Network:** Check API calls (e.g., `/api/phone-models/`)
- **Mobile View:** Toggle device toolbar (Ctrl+Shift+M in Chrome)
  - Test at: 375px (iPhone SE), 390px (iPhone 12), 430px (iPhone 14 Pro Max)

### Database Queries
```python
# Django shell
python manage.py shell

from inventory.models_phone_products import PhoneProductCatalog
from inventory.models import InventoryItem

# Check catalog
PhoneProductCatalog.objects.filter(brand="TECNO").count()

# Check inventory
InventoryItem.objects.filter(imei="123456789012345").first()
```

---

## ✅ Final Checklist

Before marking as complete:
- [ ] Add at least 1 model per brand (5 total)
- [ ] Scan in at least 3 phones (different IMEIs)
- [ ] Complete at least 1 sale via wizard
- [ ] Test mobile menu on real phone or emulator
- [ ] Verify no linter errors (`python manage.py check`)
- [ ] Verify no migrations pending (`python manage.py showmigrations`)

---

**Happy Testing! 🎉**

*For detailed implementation notes, see PHONE_UX_IMPLEMENTATION_SUMMARY.md*

