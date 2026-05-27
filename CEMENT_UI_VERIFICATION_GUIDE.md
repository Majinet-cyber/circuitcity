# Cement Premium UI — Forensic Verification & Fix Guide

## ✅ PHASE A COMPLETED — PROOF MARKERS ADDED

### What Was Done

1. **Added Visible Proof Marker** to Cement Dashboard Template
   - File: `templates/verticals/cement/dashboard.html`
   - When `DEBUG=True`, shows green alert box at top with:
     - "✅ CEMENT PREMIUM v1 — TEMPLATE OK"
     - Business Kind value
     - Sidebar Items count
     - Business name and ID

2. **Added Response Headers** for DevTools Verification
   - File: `inventory/verticals/cement.py` (dashboard view)
   - Headers added:
     - `X-Template: verticals/cement/dashboard.html`
     - `X-Cement-Premium: v1`
     - `X-Business-Kind: <actual_business_kind>`

3. **Added Locations Button** to Cement Sidebar
   - File: `inventory/utils_verticals.py` (line ~1420)
   - Locations now appears in MAIN section (manager-only)

4. **Verified Mobile Nav** Already Configured
   - File: `inventory/mobile_nav.py` (lines 312-354)
   - Cement mobile nav includes: Home, Stock In, Sell, Products, More

5. **Created UI Presence Tests**
   - File: `tests/test_cement_ui_presence.py`
   - 10 tests covering sidebar, mobile nav, dashboard sections, response headers

---

## 🔍 VERIFICATION STEPS (USER ACTION REQUIRED)

### Step 1: Start Local Server
```bash
python manage.py runserver
```

### Step 2: Navigate to Cement Dashboard
1. Log in as a user with a cement business
2. Go to: `http://localhost:8000/verticals/cement/dashboard/`

### Step 3: Check for Proof Marker (Visible)
**Expected:** Green alert box at top of page showing:
```
✅ CEMENT PREMIUM v1 — TEMPLATE OK
Business Kind: cement
Sidebar Items: 13 (or similar number)
Business: <Your Business Name> (ID: X)
```

**If you DON'T see this:**
- The template is not being rendered (wrong URL or business_kind mismatch)
- DEBUG is False (set `DEBUG=True` in `.env` or settings)

### Step 4: Check Response Headers (DevTools)
1. Open DevTools (F12)
2. Go to **Network** tab
3. Refresh the page
4. Click on the dashboard request
5. Go to **Headers** section

**Expected Headers:**
```
X-Template: verticals/cement/dashboard.html
X-Cement-Premium: v1
X-Business-Kind: cement
```

**If headers are missing:**
- The view is not being called (URL routing issue)
- Middleware is stripping headers (unlikely)

### Step 5: Check Sidebar (Visual)
**Expected sidebar items (MAIN section):**
- ✅ Dashboard
- ✅ Stock In
- ✅ Sell
- ✅ Costs
- ✅ Admin Wallet
- ✅ Analytics
- ✅ Locations (manager-only)

**If sidebar only shows "Home" and "Business Settings":**
- Business `business_kind` field in DB is NOT "cement"
- Sidebar is falling back to generic/none mode

### Step 6: Check Mobile Nav (Bottom Bar on Mobile)
On mobile or narrow browser window:
**Expected bottom nav:**
- Home
- Stock In
- Sell
- Products
- More

---

## 🐛 TROUBLESHOOTING

### Issue: Proof Marker Not Showing

**Cause 1: Wrong Business Kind in Database**
```sql
-- Check your business record:
SELECT id, name, business_kind FROM tenants_business WHERE id = <your_business_id>;
```

**Expected:** `business_kind = 'cement'`

**If it's NULL or something else:**
```sql
-- Fix it:
UPDATE tenants_business SET business_kind = 'cement' WHERE id = <your_business_id>;
```

**Cause 2: Wrong URL**
Cement dashboard is at: `/verticals/cement/dashboard/`
NOT: `/inventory/dashboard/` (that's phones)

**Cause 3: DEBUG=False**
Set `DEBUG=True` in your `.env` file or `cc/settings.py`

---

### Issue: Sidebar Still Shows Only "Home" and "Business Settings"

**Root Cause:** Business `business_kind` field is NULL, empty, or not exactly "cement"

**Fix:**
1. Check DB value (see SQL above)
2. Update to `'cement'` (exact lowercase, no spaces)
3. Restart server
4. Hard refresh browser (Ctrl+Shift+R)

**Verification:**
- Look at the proof marker's "Business Kind" line
- It should say `cement`, not `NONE` or `generic`

---

### Issue: Template Caching (Changes Not Appearing)

**Symptoms:**
- You edit template files but changes don't appear
- Even after server restart

**Fix:**
1. Ensure `DEBUG=True` in settings
2. Check `cc/settings.py` line 331: `"debug": DEBUG`
3. Clear browser cache (Ctrl+Shift+Delete)
4. Hard refresh (Ctrl+Shift+R)

**Nuclear Option:**
```bash
# Delete all .pyc files and restart
find . -name "*.pyc" -delete
python manage.py runserver
```

---

## 📋 CHECKLIST FOR USER

- [ ] Server started successfully
- [ ] Navigated to `/verticals/cement/dashboard/`
- [ ] Green proof marker visible at top
- [ ] Response headers present in DevTools
- [ ] Sidebar shows Stock In, Sell, Costs, Admin Wallet, Analytics, Locations
- [ ] Mobile nav shows Home, Stock In, Sell, Products, More
- [ ] Premium header shows business name + greeting
- [ ] Date filter bar present (Today, Last 7 Days, MTD, Custom)
- [ ] KPI cards visible (Revenue, Profit, Stock Value, Costs)
- [ ] Payment Mix section present
- [ ] Top Products section present
- [ ] Low Stock Alert section present

---

## 🎯 NEXT STEPS IF EVERYTHING WORKS

Once you confirm the UI is visible:

1. **Remove Debug Markers** (optional, for production)
   - Remove the green alert box from `templates/verticals/cement/dashboard.html`
   - Remove response headers from `inventory/verticals/cement.py`

2. **Add Cement Brand Constraints** (Phase D)
   - Ensure only 50KG bags allowed
   - Restrict to approved brands: Dangote, Aksher, Duracrete, Njati, Njati Extra, Khoma, Nkope, Lime, Nthanthwe

3. **Run Tests** (once migration conflict is fixed)
   ```bash
   python manage.py test tests.test_cement_ui_presence
   ```

---

## 📝 FILES CHANGED

1. `inventory/verticals/cement.py` — Added response headers
2. `templates/verticals/cement/dashboard.html` — Added proof marker
3. `inventory/utils_verticals.py` — Added Locations button to sidebar
4. `tests/test_cement_ui_presence.py` — Created UI presence tests

---

## 🔧 KNOWN ISSUES

### Migration Conflict (Pre-existing)
```
django.db.utils.OperationalError: duplicate column name: location_id
```

**Impact:** Tests cannot run until migrations are fixed
**Workaround:** Manual browser testing (this guide)
**Fix Required:** Resolve migration `inventory.1014_add_cementcost_location`

---

## ✨ WHAT WAS VERIFIED

✅ Cement nav config exists in `inventory/utils_verticals.py` (lines 1345-1445)
✅ Cement URLs registered in `cc/urls.py` (line 641)
✅ Cement mobile nav configured in `inventory/mobile_nav.py` (lines 312-354)
✅ Sidebar template included in `base.html` (line 419)
✅ Template extends `base.html` correctly
✅ Context processor provides `sidebar_items` and `MOBILE_NAV_ITEMS`

---

## 🚨 CRITICAL ASSUMPTION TO VERIFY

**The business record in your database MUST have:**
```python
business_kind = "cement"  # Exact lowercase, no typos
```

**Check this FIRST if sidebar doesn't show.**

---

## 📞 IF STILL NOT WORKING

1. Take a screenshot of:
   - The cement dashboard page
   - DevTools Network tab (showing response headers)
   - The proof marker area (or where it should be)

2. Run this in Django shell:
   ```python
   from inventory.models import Business
   from inventory.utils_verticals import get_vertical_sidebar_items
   
   # Replace with your business ID
   biz = Business.objects.get(id=YOUR_BUSINESS_ID)
   print(f"Business Kind: {biz.business_kind}")
   
   items = get_vertical_sidebar_items(biz.business_kind)
   print(f"Sidebar Items Count: {len(items)}")
   for item in items:
       print(f"  - {item['label']} ({item['key']})")
   ```

3. Share the output with the developer.

---

**END OF VERIFICATION GUIDE**

