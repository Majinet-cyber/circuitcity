# Clothing Vertical Barcode QA Checklist

## Overview
This checklist covers testing for the finalized clothing vertical barcode system including:
- Barcode wizard (add barcoded items)
- Fast sell barcode scanner
- Size validation (shoes = numeric only)
- Manager overrides
- Inline error handling (NO popups)

---

## Phase 1: Barcode Wizard - Step 1 (Pricing Form)

### Basic Flow
- [ ] Navigate to Dashboard → "Add Barcoded" button
- [ ] Step 1 form renders without errors
- [ ] Form shows all fields: Category, Size, Quantity, Cost, Selling, Brand, Color

### Category Selection
- [ ] Select "Shoes" (or sneaker/boot) category
- [ ] Verify size hint appears: "⚠️ Shoes must use NUMERIC sizes only"
- [ ] Size input placeholder changes to "40"

### Size Validation - Shoes (CRITICAL)
- [ ] **Shoes + Size "42"** → Should accept (valid)
- [ ] **Shoes + Size "XL"** → Should reject with inline error "numeric only"
- [ ] **Shoes + Size "XXL"** → Should reject with inline error
- [ ] **Shoes + Size "M"** → Should reject with inline error
- [ ] **Shoes + Size "29"** → Should reject (below range 30-50)
- [ ] **Shoes + Size "51"** → Should reject (above range 30-50)
- [ ] **Shoes + Size "45"** → Should accept (valid)

### Size Validation - Other Categories
- [ ] **Shirt + Size "M"** → Should accept (valid)
- [ ] **Shirt + Size "42"** → Should accept (valid)
- [ ] **Jeans + Size "32"** → Should accept (valid)
- [ ] **Jeans + Size "32x30"** → Should accept (valid waist×inseam)

### Price Validation
- [ ] Enter Cost=10000, Selling=blank → Should auto-suggest ~13500 (cost × 1.35)
- [ ] Enter Cost=10000, Selling=15000 → Should accept (selling > cost)
- [ ] Enter Cost=15000, Selling=10000 → Should show manager override box
- [ ] Manager override checkbox NOT checked → Should show inline error "below cost"
- [ ] Non-manager user checks override → Should show inline error "Only managers"

### Manager Override (Selling Below Cost)
- [ ] Login as Manager
- [ ] Enter Cost=15000, Selling=10000
- [ ] Check "Allow selling below cost" → Should accept and proceed
- [ ] Session should store prices correctly

### Back Button
- [ ] Click "Back to Dashboard" → Should return to dashboard (no data loss warning needed yet)

### Inline Errors (NO POPUPS)
- [ ] Submit empty form → Errors show inline under fields
- [ ] NO alert() popups appear
- [ ] NO intrusive modals appear
- [ ] Errors are red with clear messaging

---

## Phase 2: Barcode Wizard - Step 2 (Scanning Loop)

### Initial State
- [ ] After Step 1 submission → Redirects to Step 2
- [ ] Progress shows "Scanned 0 / QTY"
- [ ] Progress bar at 0%
- [ ] "Open Camera Scanner" button visible
- [ ] Manual input field visible with "Submit" button

### Scanning Flow
- [ ] Enter barcode "TEST001" manually → Click Submit
- [ ] Success message appears (inline, green): "✅ Barcode TEST001 scanned successfully!"
- [ ] Progress updates to "Scanned 1 / QTY"
- [ ] Progress bar advances
- [ ] Remaining count decrements
- [ ] Input field clears and re-focuses
- [ ] Scanned item appears in "Recently Scanned" list

### Duplicate Detection
- [ ] Scan same barcode again → Error message (inline, red): "❌ Barcode already scanned"
- [ ] Scan continues (non-blocking error)
- [ ] Input clears and re-focuses

### Quantity Completion
- [ ] Scan all required units (e.g., 3 scans for qty=3)
- [ ] Last scan shows: "🎉 All items scanned! Redirecting..."
- [ ] After 2 seconds → Redirects to dashboard
- [ ] Success message on dashboard

### Back Button (Session Preservation)
- [ ] During scanning, click "← Back to Step 1"
- [ ] Returns to Step 1 form
- [ ] All form fields still populated (prices, quantity, size, etc.)
- [ ] Can edit and resubmit
- [ ] Returns to Step 2 with updated session

### Database Verification
- [ ] After completion, check admin/database
- [ ] Verify ClothingBarcodeUnit records created
- [ ] Verify barcode, size, cost_price, selling_price correct
- [ ] Verify status = "IN_STOCK"
- [ ] Verify business and location scoped correctly

---

## Phase 3: Fast Sell - Barcode Scanner

### Page Rendering
- [ ] Navigate to Dashboard → "Fast Sell (Barcode)" button
- [ ] Scanner page renders without errors
- [ ] Shows KPIs: "Today's Sales" and "Today's Revenue"
- [ ] Shows "Scan to Sell" button
- [ ] Shows manual barcode input field

### Fast Sell Flow
- [ ] Enter barcode of IN_STOCK unit (from Phase 2)
- [ ] Click "Sell" or press Enter
- [ ] Success message: "✅ Sale completed! Amount: K 15000"
- [ ] KPIs update immediately (Today's Sales +1, Revenue +15000)
- [ ] Unit appears in "Recent Sales" list
- [ ] Input clears and re-focuses

### Error Handling (Inline, Non-Blocking)
- [ ] Scan unknown barcode → Error: "❌ Barcode XXX not found in stock"
- [ ] Scan continues (no blocking modal)
- [ ] Scan same barcode again → Error: "❌ Barcode already sold on YYYY-MM-DD"
- [ ] Error messages disappear after 4 seconds (auto-hide)

### Sale Verification
- [ ] Check database: ClothingBarcodeUnit status changed to "SOLD"
- [ ] Check database: ClothingSale record created with qty=1
- [ ] Check dashboard: Today's revenue updated

### Barcode Enforcement (CRITICAL)
- [ ] Fast sell should ONLY work with ClothingBarcodeUnit records
- [ ] Should NOT fall back to non-barcoded products
- [ ] Scanning non-existent barcode should fail with "not found" error

---

## Phase 4: Non-Barcoded Items (Manual Sell)

### Manual Sell Page
- [ ] Navigate to Dashboard → "Sell (Manual)" button
- [ ] Shows product grid (non-barcoded items)
- [ ] Shows search box
- [ ] Shows cart functionality

### Manual Sell Flow
- [ ] Click product → Adds to cart
- [ ] Select quantity
- [ ] Click "Checkout"
- [ ] Completes sale with quantity decrement (bulk stock)

### Separation Verification
- [ ] Barcoded items should NOT appear in manual sell product grid
- [ ] Non-barcoded items should NOT appear in fast sell scanner
- [ ] Two workflows are completely separate

---

## Phase 5: Manager Permissions

### Non-Manager Users
- [ ] Login as regular user (not in "Manager" group)
- [ ] Try to sell below cost → Should be blocked
- [ ] "Allow selling below cost" checkbox should show error

### Manager Users
- [ ] Login as Manager (or is_staff)
- [ ] Can check "Allow selling below cost" checkbox
- [ ] Can successfully submit Step 1 with selling < cost
- [ ] Units are created with correct prices

---

## Phase 6: Error Handling & UX

### NO Popup Alerts
- [ ] Throughout all flows, verify NO alert() popups appear
- [ ] All errors render inline (red text under fields)
- [ ] All success messages render inline (green banners)
- [ ] Messages are non-blocking (user can continue)

### Back Button Functionality
- [ ] All pages have visible "← Back" links
- [ ] Back buttons preserve user input (session-based)
- [ ] Navigation is intuitive

### Mobile Responsiveness
- [ ] Test on mobile device (or browser devtools mobile view)
- [ ] Forms are readable and usable
- [ ] Scanner button is large and accessible
- [ ] Inputs have good touch targets

---

## Phase 7: Integration Tests

### Multi-Vertical Isolation
- [ ] Create barcoded unit in Clothing vertical
- [ ] Switch to another vertical (e.g., Pharmacy)
- [ ] Verify clothing units are NOT accessible
- [ ] Verify business scoping is correct

### Multi-Location Scoping
- [ ] Create barcoded unit at Location A
- [ ] Switch active location to Location B
- [ ] Verify Location A units are still accessible (business-wide scope)
- [ ] OR verify location-specific scoping if implemented

### Concurrent Users
- [ ] User A starts barcode wizard (Step 1)
- [ ] User B starts barcode wizard (Step 1)
- [ ] Both can scan independently without session conflicts

---

## Phase 8: Data Integrity

### Unique Barcode Constraint
- [ ] Try to create duplicate barcode manually in Django admin
- [ ] Should be blocked by DB unique constraint
- [ ] Verify constraint: (business, barcode) UNIQUE

### Status Transitions
- [ ] Create unit: status = "IN_STOCK"
- [ ] Sell unit: status = "SOLD", sold_at populated
- [ ] Cannot sell SOLD unit again (blocked by fast sell lookup)

### Audit Trail
- [ ] Verify created_at, updated_at timestamps
- [ ] Verify created_by user is recorded
- [ ] Verify sold_at date matches sale date

---

## Phase 9: Performance

### Large Batch Scanning
- [ ] Create batch with qty=50
- [ ] Scan all 50 units
- [ ] Verify no timeouts or performance issues
- [ ] Verify session doesn't overflow

### Fast Sell Speed
- [ ] Scan barcode → Measure time to completion
- [ ] Should complete in < 1 second
- [ ] Verify no network delays or blocking operations

---

## Phase 10: Automated Tests

### Run Django Tests
```bash
python manage.py test inventory.tests.test_clothing_size_validation
python manage.py test inventory.tests.test_clothing_barcode_service
python manage.py test inventory.tests.test_clothing_barcode_wizard_flow
```

Expected Results:
- [ ] All size validation tests pass
- [ ] All barcode service tests pass
- [ ] All wizard flow tests pass
- [ ] NO failures or errors

### Run Cypress E2E (if available)
```bash
npx cypress run --spec "cypress/e2e/verticals/clothing_journey.cy.js"
```

Expected Results:
- [ ] Barcode wizard E2E passes
- [ ] Fast sell E2E passes

---

## Critical Bugs to Watch For

### 🚨 Shoes Size Validation
- [ ] Shoes NEVER accept alpha sizes (XL, M, L, etc.)
- [ ] Validation enforced in BOTH UI and server
- [ ] Error messages are clear and actionable

### 🚨 Fast Sell Barcode-Only
- [ ] Fast sell ONLY works with barcoded units
- [ ] NO fallback to non-barcode products
- [ ] Clear error when barcode not found

### 🚨 Duplicate Barcode Detection
- [ ] Cannot scan same barcode twice in same batch
- [ ] Cannot create duplicate barcode across sessions
- [ ] DB constraint enforced

### 🚨 NO Popup Errors
- [ ] All error handling is inline
- [ ] NO alert(), confirm(), or prompt() calls
- [ ] NO intrusive modal popups

### 🚨 Session Preservation
- [ ] Back button preserves user input
- [ ] Session data doesn't leak between users
- [ ] Session cleared after completion

---

## Sign-Off

### Developer Testing
- [ ] All manual tests completed
- [ ] All automated tests pass
- [ ] No critical bugs found
- [ ] Code reviewed for security (IDOR, XSS, CSRF)

**Developer Signature:** _______________
**Date:** _______________

### QA Testing
- [ ] All checklist items verified
- [ ] Edge cases tested
- [ ] Mobile responsive verified
- [ ] Performance acceptable

**QA Signature:** _______________
**Date:** _______________

### Product Owner Approval
- [ ] Feature meets requirements
- [ ] UX is intuitive and polished
- [ ] Ready for production deployment

**PO Signature:** _______________
**Date:** _______________

---

## Deployment Notes

### Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Static Files
```bash
python manage.py collectstatic --noinput
```

### Cache Clear (if using Redis/Memcached)
```bash
python manage.py clear_cache
```

### Deployment Checklist
- [ ] Migrations applied to production DB
- [ ] Static files collected
- [ ] Django settings DEBUG=False
- [ ] ALLOWED_HOSTS configured
- [ ] CSRF_TRUSTED_ORIGINS configured
- [ ] Backup database before deployment

---

**END OF CHECKLIST**
