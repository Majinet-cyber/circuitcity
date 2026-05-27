# Phones Dashboard & CSRF Fix Implementation Summary

## Overview

This document summarizes the implementation of the Phones Dashboard improvements and CSRF security fixes for the Circuit City / Emajinet Django SaaS project.

## Changes Implemented

### A) CSRF Security Fixes (Production-Ready for Render)

#### 1. Settings Configuration (`cc/settings.py`)

**RENDER_EXTERNAL_HOSTNAME Support:**
```python
# Render deployment support: add RENDER_EXTERNAL_HOSTNAME if present
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, RENDER_EXTERNAL_HOSTNAME})

# Add RENDER_EXTERNAL_HOSTNAME to CSRF trusted origins
if RENDER_EXTERNAL_HOSTNAME:
    _default_csrf_fixed.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")
```

**What This Fixes:**
- Automatic detection of Render external hostname from environment
- Adds hostname to both `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Prevents `403 CSRF verification failed` errors on Render deployments

**Existing Security Settings (Already Correct):**
- `CSRF_COOKIE_SECURE = not DEBUG` (secure cookies in production)
- `SESSION_COOKIE_SECURE = not DEBUG` (secure session cookies in production)
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (works with Render)
- Wildcard support: `https://*.onrender.com` already in CSRF_TRUSTED_ORIGINS

#### 2. CSRF Verification Tests (`cc/tests/test_csrf_settings.py`)

**New Test Suite:**
- `CSRFSettingsTestCase`: Verifies RENDER_EXTERNAL_HOSTNAME is added to settings
- `LoginCSRFTestCase`: Verifies login forms handle CSRF tokens correctly
- `InviteAcceptCSRFTestCase`: Verifies invite acceptance has CSRF protection
- `RegistrationLoginTemplateCSRFTestCase`: Verifies all auth templates have CSRF tokens
- `CSRFOriginMatchingTestCase`: Verifies production/staging URLs are trusted

**Coverage:**
- ✅ Login page sets CSRF cookie
- ✅ Login template includes `{% csrf_token %}`
- ✅ POST with valid CSRF token does not return 403
- ✅ POST without CSRF token returns 403
- ✅ Production URLs (emajinet.africa, emajinet-staging.onrender.com) are trusted

#### 3. Template Verification

**All login/auth templates verified to have CSRF tokens:**
- ✅ `templates/registration/login.html` (line 123: `{% csrf_token %}`)
- ✅ `templates/accounts/login.html` (line 209: `{% csrf_token %}`)
- ✅ `templates/tenants/invite_accept.html` (line 109: `{% csrf_token %}`)

All forms use `method="post"` and include hidden CSRF token inputs.

---

### B) Phones Dashboard as Landing Page

#### 1. Post-Login Redirect Logic (`circuitcity/accounts/views.py`)

**Updated `_post_login_url()` function:**
```python
def _post_login_url(request=None) -> str:
    """
    Best-effort landing page after successful login.
    
    For phone businesses: redirect to phones dashboard.
    Otherwise: prefer general dashboard; fall back to inventory dashboard/list.
    """
    # If we have a request with an active business, check if it's phones
    if request:
        business = getattr(request, 'business', None)
        if not business:
            # Try to get from session
            try:
                from tenants.models import Business
                business_id = request.session.get('active_business_id')
                if business_id:
                    business = Business.objects.filter(id=business_id).first()
            except Exception:
                pass
        
        # Redirect phones businesses to their dedicated dashboard
        if business:
            try:
                from inventory.business_kinds import BusinessKind
                business_kind = getattr(business, 'business_kind', None)
                if business_kind == BusinessKind.PHONES or business_kind == 'phones':
                    try:
                        return reverse("inventory_verticals:phones_dashboard")
                    except NoReverseMatch:
                        pass
            except Exception:
                pass
    
    # Default landing pages (general dashboard, inventory, etc.)
    for name in (
        "dashboard:home",
        "dashboard:dashboard_home",
        "inventory:inventory_dashboard",
        "inventory:dashboard",
        "inventory:stock_list",
    ):
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return "/inventory/dashboard/"
```

**Behavior:**
- Phone businesses → redirect to `/inventory/verticals/phones/` (Phones Dashboard)
- Other verticals → redirect to their respective dashboards
- Fallback → general inventory dashboard

#### 2. Sidebar Navigation (`inventory/utils_verticals.py`)

**Updated phones sidebar to prioritize Phone Dashboard:**
```python
else:  # "phones" or default
    return [
        # MAIN section - Phones Dashboard is the primary entry point
        {"section": "MAIN", "url": "inventory_verticals:phones_dashboard", "label": "Phone Dashboard", "icon": "bi-speedometer2", "active_pattern": "/inventory/verticals/phones", "require_manager": False},
        {"section": "MAIN", "url": "inventory:stock_list", "label": "Stock", "icon": "bi-box-seam", "active_pattern": "/inventory/list/", "require_manager": False},
        {"section": "MAIN", "url": "inventory:phone_products", "label": "Products", "icon": "bi-grid-3x3-gap", "active_pattern": "/inventory/phone-products", "require_manager": False},
        {"section": "MAIN", "url": "inventory:scan_in", "label": "Scan IN", "icon": "bi-upc-scan", "active_pattern": "/inventory/scan", "require_manager": False},
        {"section": "MAIN", "url": "inventory:phone_sale_wizard", "label": "Scan & Sell", "icon": "bi-bag-check", "active_pattern": "/inventory/phone-sale-wizard/", "require_manager": False},
        ...
    ]
```

**Sidebar Changes:**
- Added "Phone Dashboard" as first item in MAIN section
- Icon: `bi-speedometer2` (speedometer/dashboard icon)
- URL: `inventory_verticals:phones_dashboard`
- Active pattern: `/inventory/verticals/phones`
- Visible to all users (agents and managers)

---

### C) Phones Dashboard Functionality (Already Implemented)

The phones dashboard at `/inventory/verticals/phones/` already has comprehensive functionality:

#### 1. Metrics Cards

**KPI Metrics:**
- **Revenue (MK)**: Total phone sales value in selected period
- **Costs (MK)**: Total phone acquisition cost + business costs (wallet)
- **Profit (MK)**: Revenue - Costs
- **Profit Margin (%)**: Profit / Revenue × 100 (0% if revenue is zero)
- **Total Stock**: Number of phone units currently in stock (status=IN_STOCK)
- **Sum Sold**: Number of phone units sold in selected period

**Data Sources:**
- Revenue: `InventoryItem.selling_price` aggregated for sold items
- Costs: `InventoryItem.order_price` (COGS) + `WalletTransaction` (admin costs)
- Stock: `InventoryItem.objects.filter(status="IN_STOCK", is_active=True).count()`
- Sales: `InventoryItem.objects.filter(status="SOLD", sold_at__range=...)`

#### 2. Date Range Filtering

**Supported Filters:**
- **Today**: Sales from today only
- **Last 7 Days**: Sales from past 7 days
- **This Month (MTD)**: Sales from start of current month (default)
- **Custom**: User-specified start/end dates

**Implementation:**
- URL params: `?range=today`, `?range=7d`, `?range=mtd`, `?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD`
- All metrics respect the selected date range
- Stock count is NOT date-filtered (always shows current stock)

#### 3. Dashboard Enhancements

**Greeting & Quotes:**
- Personalized greeting using `dashboard.helpers_greetings.get_personalized_greeting()`
- Daily rotating quotes using `dashboard.helpers_quotes.get_todays_quotes()`
- Same pattern as other vertical dashboards (Liquor, Pharmacy, Gym, Clothing)

**Yesterday Summary:**
- Shows once per day when viewing "today" range
- Uses `dashboard.helpers_yesterday` module

#### 4. Real Data Movement

**When a phone is sold:**
- Revenue increases by `selling_price`
- Profit increases by `selling_price - order_price`
- Margin recalculates: `(profit / revenue) * 100`
- Sum sold increases by 1
- Total stock decreases by 1 (status changes from IN_STOCK to SOLD)

**When a cost is recorded (Admin Wallet):**
- Costs increase by the amount
- Profit decreases by the amount
- Margin recalculates

---

### D) Testing

#### 1. CSRF Tests (`cc/tests/test_csrf_settings.py`)

**Test Coverage:**
- ✅ RENDER_EXTERNAL_HOSTNAME added to ALLOWED_HOSTS
- ✅ RENDER_EXTERNAL_HOSTNAME added to CSRF_TRUSTED_ORIGINS with https://
- ✅ Production CSRF/session cookies are secure (not DEBUG)
- ✅ Login page sets CSRF cookie
- ✅ Login POST with valid token does not return 403
- ✅ Login POST without token returns 403
- ✅ Staging/production URLs are trusted

**Run Tests:**
```bash
python manage.py test cc.tests.test_csrf_settings
```

#### 2. Phones Dashboard Tests (`inventory/tests/test_phone_dashboard_metrics.py`)

**Test Coverage:**
- ✅ Phones dashboard is accessible for phone businesses
- ✅ Metrics are zero when no sales exist
- ✅ Metrics update correctly after a sale
- ✅ Stock count decreases after a sale
- ✅ Date filter "today" works correctly
- ✅ Date filter "last 7 days" works correctly
- ✅ Business costs from wallet are included in metrics
- ✅ Profit margin is 0% when revenue is zero
- ✅ Phone businesses redirect to phones dashboard after login

**Run Tests:**
```bash
python manage.py test inventory.tests.test_phone_dashboard_metrics
```

#### 3. Existing Dashboard Tests (`inventory/tests/test_dashboard_metrics.py`)

The existing test suite (698 lines) already covers:
- ✅ Dashboard metrics update after sales
- ✅ Payment mix percentages sum to 100%
- ✅ Revenue vs Costs battery sums to 100%
- ✅ Profit vs Costs battery sums to 100%
- ✅ Low margin warning triggers when margin < 10%
- ✅ Stock alerts update after sales
- ✅ Zero revenue edge cases
- ✅ Single payment method edge cases
- ✅ Admin costs from wallet are included
- ✅ Recurring admin costs are included

---

## Environment Variables

### Required for Render Deployment

**On Render, set the following environment variable:**

```bash
RENDER_EXTERNAL_HOSTNAME=emajinet-staging.onrender.com
```

(Or your actual Render external hostname, without `https://`)

**What It Does:**
- Automatically adds your Render hostname to `ALLOWED_HOSTS`
- Automatically adds `https://<hostname>` to `CSRF_TRUSTED_ORIGINS`
- Prevents 403 CSRF errors on Render deployments

**Alternative (Manual Configuration):**

If you prefer manual configuration, you can also set:

```bash
ALLOWED_HOSTS=emajinet-staging.onrender.com,emajinet.africa,localhost
CSRF_TRUSTED_ORIGINS=https://emajinet-staging.onrender.com,https://emajinet.africa
```

But using `RENDER_EXTERNAL_HOSTNAME` is recommended as it's more maintainable.

### Existing Environment Variables (No Changes)

These variables already work correctly and don't need changes:

- `DEBUG=false` (production)
- `DATABASE_URL` (PostgreSQL connection)
- `SECRET_KEY` (Django secret)
- `RENDER=true` (Render detection)
- `USE_SSL=true` (SSL redirect)
- `FORCE_SSL=true` (enforce HTTPS)

---

## Files Changed

### 1. Settings & Configuration

- `cc/settings.py`
  - Added `RENDER_EXTERNAL_HOSTNAME` support
  - Enhanced CSRF_TRUSTED_ORIGINS with Render hostname

### 2. Authentication & Redirects

- `circuitcity/accounts/views.py`
  - Updated `_post_login_url()` to detect phone businesses
  - Redirect phone businesses to phones dashboard after login

### 3. Navigation

- `inventory/utils_verticals.py`
  - Updated phones sidebar to include "Phone Dashboard" as first item
  - Icon: `bi-speedometer2`
  - URL: `inventory_verticals:phones_dashboard`

### 4. Tests (New Files)

- `cc/tests/test_csrf_settings.py`
  - Comprehensive CSRF configuration tests
  - Login form CSRF token tests
  - Production security settings tests

- `inventory/tests/test_phone_dashboard_metrics.py`
  - Phones dashboard metrics tests
  - Date filtering tests
  - Post-login redirect tests
  - Business costs integration tests

### 5. Documentation (New File)

- `PHONES_DASHBOARD_CSRF_FIX_SUMMARY.md` (this file)

---

## Verification Steps

### 1. Verify CSRF Fix on Render

**Before deploying:**
```bash
# Set environment variable on Render
RENDER_EXTERNAL_HOSTNAME=emajinet-staging.onrender.com
```

**After deploying:**
1. Navigate to `https://emajinet-staging.onrender.com/accounts/login/`
2. Open browser DevTools (F12) → Network tab
3. Attempt to log in
4. Verify:
   - ✅ No 403 CSRF error
   - ✅ Login succeeds or shows credential error (not CSRF error)
   - ✅ CSRF cookie is set (check Application → Cookies)

### 2. Verify Phone Dashboard Landing

**Create a phone business:**
1. Sign up as a manager
2. Create a business with `business_kind = "phones"`
3. Log out and log back in
4. Verify:
   - ✅ You land on `/inventory/verticals/phones/` (Phones Dashboard)
   - ✅ Sidebar shows "Phone Dashboard" as first item
   - ✅ Dashboard displays metrics cards (Revenue, Costs, Profit, etc.)

### 3. Verify Metrics Update

**Test data movement:**
1. Navigate to `/inventory/scan-in/` and add a phone to stock
2. Note the "Total Stock" count on the dashboard
3. Navigate to `/inventory/phone-sale-wizard/` and sell the phone
4. Return to the dashboard
5. Verify:
   - ✅ Revenue increases
   - ✅ Profit increases
   - ✅ Total Stock decreases by 1
   - ✅ Sum Sold increases by 1
   - ✅ Margin % recalculates

### 4. Run Test Suite

```bash
# Run CSRF tests
python manage.py test cc.tests.test_csrf_settings

# Run phones dashboard tests
python manage.py test inventory.tests.test_phone_dashboard_metrics

# Run all dashboard metrics tests
python manage.py test inventory.tests.test_dashboard_metrics
```

**Expected:**
- ✅ All tests pass
- ✅ No CSRF failures
- ✅ All metrics tests pass

---

## Summary of Metrics Calculations

### Revenue (MK)
```python
revenue = InventoryItem.objects.filter(
    business=business,
    status="SOLD",
    sold_at__gte=start_date,
    sold_at__lt=end_date
).aggregate(total=Sum('selling_price'))['total'] or Decimal('0.00')
```

### Costs (MK)
```python
# A) Cost of Goods Sold (COGS)
cogs = sold_items.aggregate(total=Sum('order_price'))['total'] or Decimal('0.00')

# B) Business Costs (Admin Wallet)
business_costs = WalletTransaction.objects.filter(
    business=business,
    ledger=Ledger.COMPANY,
    type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
    effective_date__gte=start_date,
    effective_date__lt=end_date
).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

# Total Costs
total_costs = cogs + abs(business_costs)
```

### Profit (MK)
```python
profit = revenue - total_costs
```

### Profit Margin (%)
```python
profit_margin = (profit / revenue * 100) if revenue > 0 else Decimal('0.00')
```

### Total Stock (Units)
```python
total_stock = InventoryItem.objects.filter(
    business=business,
    status="IN_STOCK",
    is_active=True
).count()
```

### Sum Sold (Units)
```python
sum_sold = InventoryItem.objects.filter(
    business=business,
    status="SOLD",
    sold_at__gte=start_date,
    sold_at__lt=end_date
).count()
```

---

## Deployment Checklist

### Pre-Deployment

- [x] CSRF settings updated with RENDER_EXTERNAL_HOSTNAME support
- [x] Login redirect logic updated for phone businesses
- [x] Sidebar navigation updated with Phone Dashboard link
- [x] Tests written and passing
- [x] Documentation complete

### On Render

1. Set environment variable:
   ```
   RENDER_EXTERNAL_HOSTNAME=emajinet-staging.onrender.com
   ```

2. Deploy to Render

3. Verify login works (no 403 CSRF errors)

4. Verify phone businesses land on phones dashboard

### Post-Deployment

1. Test login flow on staging
2. Test phones dashboard on staging
3. Record a test sale and verify metrics update
4. Check sidebar navigation
5. Test date range filters

---

## Notes for Future Development

### Adding New Verticals

When adding a new vertical dashboard (e.g., "Hardware"), follow this pattern:

1. **Create dashboard view** in `inventory/verticals/<vertical>.py`
2. **Add URL** in `inventory/urls_verticals.py`
3. **Update sidebar** in `inventory/utils_verticals.py` (add to `get_vertical_sidebar_items()`)
4. **Update post-login redirect** in `circuitcity/accounts/views.py` (add to `_post_login_url()`)
5. **Add tests** in `inventory/tests/test_<vertical>_dashboard_metrics.py`

### CSRF Best Practices

- Always include `{% csrf_token %}` in POST forms
- Always use `method="post"` (not GET) for mutations
- Set `CSRF_COOKIE_SECURE = True` in production
- Set `SESSION_COOKIE_SECURE = True` in production
- Use `SECURE_PROXY_SSL_HEADER` for proxies (Render, NGINX, etc.)
- Test with `Client(enforce_csrf_checks=True)` in tests

---

## Support

If you encounter issues:

1. Check that `RENDER_EXTERNAL_HOSTNAME` is set correctly on Render
2. Check that `DEBUG=false` in production
3. Check browser DevTools → Network tab for CSRF errors
4. Run tests: `python manage.py test cc.tests.test_csrf_settings`
5. Check logs on Render for detailed error messages

---

**Implementation Date:** December 10, 2025  
**Branch:** `mobile-layout-v1`  
**Status:** ✅ Complete and tested

