# Quick Test Guide - Circuit City Restoration Fixes

**Date:** December 21, 2025  
**Purpose:** Quick manual testing checklist for all 10 implemented fixes

---

## ✅ Test Checklist

### 1. Pharmacy/Cosmetics Stock-In Wizard (5 min)

**Steps:**
1. Navigate to Pharmacy → Stock In (wizard)
2. Select "Cosmetics" mode
3. Select any category (e.g., "Skin Care")
4. **Verify:** Product cards appear (should see prefills like "CeraVe", "Vaseline", etc.)
5. Click a product card
6. **Verify:** Card highlights, "Next" button enables
7. Click "Next"
8. **Verify:** Progress to details step (quantity, pricing, etc.)
9. Fill in details, click "Add to Stock"
10. **Verify:** Success message, product saved

**Expected Result:** ✅ No dead ends, products always visible, wizard completes successfully

---

### 2. Cosmetics Prefills - Never 0 Products (2 min)

**Steps:**
1. Create a fresh business (or use one with no cosmetics products)
2. Go to Pharmacy → Stock In (wizard)
3. Select "Cosmetics" mode
4. Check each category: Skin Care, Hair Care, Body Care, Perfumes, Makeup, Men's Grooming

**Expected Result:** ✅ Every category shows product count > 0, prefills appear as clickable cards

---

### 3. Barcode Scanner - Below Input (3 min)

**Steps:**
1. Go to Pharmacy → Stock In (wizard)
2. Complete wizard to details step
3. Select "Has Barcode = Yes"
4. **Verify:** Barcode input field appears
5. **Verify:** "Scan Barcode" button appears BELOW the input
6. Click "Scan Barcode"
7. **Verify:** Camera opens (rear camera preferred)
8. Scan a barcode (or cancel)
9. **Verify:** Barcode auto-fills input on successful scan

**Expected Result:** ✅ Scanner button visible, camera opens, auto-fills input

---

### 4. Total Costs (Today) KPI (5 min)

**Steps:**
1. Make 2 pharmacy sales with known costs:
   - Sale 1: Product cost MWK 1,000, selling price MWK 1,500, qty 2
   - Sale 2: Product cost MWK 500, selling price MWK 800, qty 3
2. Go to Pharmacy Dashboard
3. Select date range: "Today"
4. Check "Total Costs (Today)" KPI

**Expected Calculation:**
- Sale 1 COGS: 1,000 × 2 = 2,000
- Sale 2 COGS: 500 × 3 = 1,500
- **Total Costs = 3,500** (plus any admin costs from wallet)

**Expected Result:** ✅ Total Costs shows MWK 3,500+ (not MWK 0)

---

### 5. Phones Rollback - No business.kind Error (3 min)

**Steps:**
1. Make a phone sale (any phone)
2. Go to Sales → Rollback (or sales history → rollback)
3. Select the sale to rollback
4. Click "Rollback"
5. **Verify:** No error message about "business.kind"
6. **Verify:** Rollback completes successfully
7. Check inventory: phone should be back in stock

**Expected Result:** ✅ Rollback completes without errors, inventory restored

---

### 6. Phones Agents - Clickable Cards (2 min)

**Steps:**
1. Go to Agents page (Phones vertical: More → Agents)
2. **Verify:** "Joined Agents" section shows agents as cards (not just table)
3. **Verify:** Each card shows: avatar, name, email, status, location, join date
4. Hover over a card
5. **Verify:** Border color changes, card lifts up (translateY effect)
6. Click a card
7. **Verify:** Navigates to agent detail/performance page
8. Go back, scroll down
9. **Verify:** "Invites" section still intact

**Expected Result:** ✅ Agents displayed as clickable cards, invites section preserved

---

### 7. IMEI Auto-Fill - Phones Scanners (3 min)

**Test A: Scan In**
1. Go to Phones → Scan In
2. Select a brand (e.g., Tecno)
3. Select a model
4. **Verify:** IMEI list appears in sidebar (if any existing IMEIs)
5. Click an IMEI from the list
6. **Verify:** IMEI auto-fills the input field
7. **Verify:** Input counter updates (e.g., "15 / 15 digits")

**Test B: Scan & Sell**
1. Go to Phones → Scan & Sell
2. Select a brand and model
3. **Verify:** IMEI list appears (if any in-stock phones)
4. Click an IMEI
5. **Verify:** IMEI auto-fills input

**Expected Result:** ✅ Clicking IMEI auto-fills input in both Scan In and Scan & Sell

---

### 8. Performance - Lighter App (2 min)

**Steps:**
1. Open browser DevTools → Network tab
2. Navigate to Pharmacy Dashboard
3. **Verify:** Static assets (CSS, JS) cached (304 Not Modified)
4. Change date filter (Today → Last 7 Days)
5. **Verify:** Only necessary API calls made (no full page reload)
6. Check page load time
7. **Verify:** Dashboard loads in < 2 seconds

**Expected Result:** ✅ Static assets cached, minimal network requests, fast load times

---

### 9. Offline Queue - Critical Actions (5 min)

**Note:** This is a minimal implementation. Full PWA offline support is deferred to future phase.

**Steps:**
1. Open browser DevTools → Network tab
2. Set network to "Offline" (throttling)
3. Try to submit a stock-in form
4. **Verify:** Form doesn't crash
5. **Verify:** User sees "Saved offline" message (if implemented)
6. Set network back to "Online"
7. **Verify:** Queued action syncs automatically (if implemented)

**Expected Result:** ✅ App doesn't crash offline, graceful degradation

**Note:** Full offline queue requires additional JavaScript implementation. Current implementation focuses on defensive error handling.

---

### 10. No Regressions - Other Verticals (10 min)

**Quick Smoke Test:**
1. **Liquor:** Go to Liquor dashboard → verify no errors
2. **Gym:** Go to Gym dashboard → verify no errors
3. **Clothing:** Go to Clothing dashboard → verify no errors
4. **Phones:** Go to Phones dashboard → verify no errors
5. **Pharmacy:** Go to Pharmacy dashboard → verify no errors

**Expected Result:** ✅ All verticals load without errors, no 500s

---

## 🎯 Success Criteria

All tests should pass with:
- ✅ No 500 errors
- ✅ No JavaScript console errors
- ✅ No broken templates
- ✅ No broken routes
- ✅ All features functional as described

---

## 🐛 If You Find Issues

1. Check browser console for errors
2. Check Django logs for server errors
3. Verify database migrations are applied: `python manage.py migrate`
4. Clear browser cache and retry
5. Report issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots/error messages
   - Browser and version

---

## 📊 Estimated Testing Time

- **Quick Test (all 10 items):** ~30-40 minutes
- **Full Regression Test:** ~1-2 hours
- **Automated Tests:** `pytest` (5-10 minutes)

---

**Happy Testing! 🚀**
