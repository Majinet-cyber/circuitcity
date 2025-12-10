# Phones Dashboard & CSRF Fix - Quick Reference

## What Was Done

### ✅ A) Fixed CSRF for Render (403 Error Fix)

**Problem:** Getting `403 CSRF verification failed` on `https://emajinet-staging.onrender.com/accounts/login/`

**Solution:** Added automatic Render hostname detection to settings

**File:** `cc/settings.py`
```python
# Added RENDER_EXTERNAL_HOSTNAME support
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME:
    # Add to ALLOWED_HOSTS
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, RENDER_EXTERNAL_HOSTNAME})
    # Add to CSRF_TRUSTED_ORIGINS with https://
    _default_csrf_fixed.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")
```

### ✅ B) Phones Dashboard as Landing Page

**Goal:** Phone businesses land on `/inventory/verticals/phones/` after login

**Implementation:**
1. Updated `_post_login_url()` in `circuitcity/accounts/views.py` to detect phone businesses
2. Updated sidebar in `inventory/utils_verticals.py` to show "Phone Dashboard" as first item

**Behavior:**
- Phone businesses → `/inventory/verticals/phones/` (Phones Dashboard)
- Other verticals → their respective dashboards
- Default → general inventory dashboard

### ✅ C) Sidebar Navigation

**Added "Phone Dashboard" to phones sidebar:**
- Position: First item in MAIN section
- Icon: `bi-speedometer2` (speedometer)
- Label: "Phone Dashboard"
- URL: `inventory_verticals:phones_dashboard`
- Visible to: All users (agents and managers)

### ✅ D) CSRF Verification Tests

**New test file:** `cc/tests/test_csrf_settings.py`

**Coverage:**
- RENDER_EXTERNAL_HOSTNAME added to settings
- Login forms have CSRF tokens
- POST with valid token succeeds
- POST without token fails with 403
- Production/staging URLs are trusted

### ✅ E) Phones Dashboard Tests

**New test file:** `inventory/tests/test_phone_dashboard_metrics.py`

**Coverage:**
- Metrics update after sales
- Stock decreases after sales
- Date filtering works (today, 7d, mtd, custom)
- Business costs from wallet included
- Post-login redirect for phone businesses

---

## Environment Variable (REQUIRED on Render)

**On Render Dashboard, add this environment variable:**

```
RENDER_EXTERNAL_HOSTNAME=emajinet-staging.onrender.com
```

(Replace with your actual Render external hostname)

**What it does:**
- Fixes 403 CSRF errors
- Automatically adds hostname to ALLOWED_HOSTS
- Automatically adds https://hostname to CSRF_TRUSTED_ORIGINS

---

## Files Changed

### Settings & Auth
- `cc/settings.py` - CSRF config with RENDER_EXTERNAL_HOSTNAME
- `circuitcity/accounts/views.py` - Post-login redirect for phone businesses

### Navigation
- `inventory/utils_verticals.py` - Added "Phone Dashboard" to sidebar

### Tests (New)
- `cc/tests/test_csrf_settings.py` - CSRF configuration tests
- `inventory/tests/test_phone_dashboard_metrics.py` - Phones dashboard tests

### Documentation (New)
- `PHONES_DASHBOARD_CSRF_FIX_SUMMARY.md` - Comprehensive documentation
- `PHONES_DASHBOARD_QUICK_REFERENCE.md` - This file

---

## Phones Dashboard Metrics (How They Work)

### Revenue (MK)
- Sum of `selling_price` for all phones sold in selected date range
- Updates when a phone is sold

### Costs (MK)
- **COGS**: Sum of `order_price` for phones sold
- **Business Costs**: Admin wallet costs (rent, salaries, etc.) from `WalletTransaction`
- **Total**: COGS + Business Costs

### Profit (MK)
- Revenue - Total Costs
- Updates when sales or costs are recorded

### Margin (%)
- `(Profit / Revenue) × 100`
- Shows 0% when revenue is zero

### Total Stock
- Count of `InventoryItem` with `status="IN_STOCK"` and `is_active=True`
- **Not** date-filtered (always shows current stock)

### Sum Sold
- Count of phones sold in selected date range
- Updates when a phone is sold

---

## Verification Steps

### 1. Fix CSRF on Render

1. On Render Dashboard → Environment → Add:
   ```
   RENDER_EXTERNAL_HOSTNAME=emajinet-staging.onrender.com
   ```

2. Deploy

3. Test login at `https://emajinet-staging.onrender.com/accounts/login/`

4. Should NOT see 403 CSRF error ✅

### 2. Test Phones Dashboard Landing

1. Sign up as manager
2. Create phone business
3. Log out and log back in
4. Should land on `/inventory/verticals/phones/` ✅
5. Sidebar should show "Phone Dashboard" as first item ✅

### 3. Test Metrics Update

1. Scan in a phone
2. Note "Total Stock" count
3. Sell the phone
4. Return to dashboard
5. Verify:
   - Revenue increased ✅
   - Total Stock decreased ✅
   - Sum Sold increased ✅
   - Profit & Margin updated ✅

### 4. Run Tests

```bash
# CSRF tests
python manage.py test cc.tests.test_csrf_settings

# Phones dashboard tests
python manage.py test inventory.tests.test_phone_dashboard_metrics
```

All tests should pass ✅

---

## Troubleshooting

### Still getting 403 CSRF error?

**Check:**
1. `RENDER_EXTERNAL_HOSTNAME` is set on Render
2. Value matches your actual hostname (no `https://`)
3. `DEBUG=false` in production
4. Restart Render service after adding env var

**Verify in Django shell:**
```python
from django.conf import settings
print(settings.CSRF_TRUSTED_ORIGINS)
# Should include 'https://emajinet-staging.onrender.com'
```

### Phone businesses not landing on phones dashboard?

**Check:**
1. Business has `business_kind = "phones"` or `BusinessKind.PHONES`
2. User is logged in
3. Active business is set in session

**Verify:**
```python
# In view or shell
print(request.business.business_kind)  # Should be 'phones'
```

### Metrics not updating?

**Check:**
1. Item status changed to `SOLD`
2. Sale has `sold_at` timestamp
3. Date range filter includes the sale date
4. Business is scoped correctly

---

## Next Steps (Optional Enhancements)

These are NOT required now but could be added later:

1. **Chart/Graph:** Add sales trend chart to phones dashboard
2. **Top Agents:** Add leaderboard of top-selling agents
3. **Fast-Moving Models:** Show which phone models sell fastest
4. **Low Stock Alerts:** Alert when specific models are low/out of stock
5. **Profit by Model:** Break down profit by phone brand/model

All data infrastructure is already in place for these enhancements.

---

**Branch:** `mobile-layout-v1`  
**Date:** December 10, 2025  
**Status:** ✅ Complete

**Remember to set `RENDER_EXTERNAL_HOSTNAME` on Render before deploying!**

