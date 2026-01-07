# LIQUOR STOCK VERTICAL LEAKAGE FIX

**Date**: 2025-12-31  
**Priority**: CRITICAL  
**Status**: ✅ FIXED

## Problem Summary

**CRITICAL BUG**: Liquor "View Stock" buttons in the Liquor Hub were routing to `/inventory/list/` (the phone stock list), which displayed IMEI scanners and phone-specific UI. This is a severe vertical leakage violation.

### Reproduction Steps (BEFORE FIX)
1. Login to a liquor business (BUSINESS_VERTICAL = liquor)
2. Go to Liquor Hub: `/liquor/inventory/`
3. Click "View Stock" on any category card (e.g., Cider)
4. ❌ **BUG**: Redirects to `/inventory/list/?category=cider`
5. ❌ **BUG**: Shows phone stock list UI with "Scan IMEI" button and phone metrics

### Root Cause
- Liquor hub template used `{% url 'inventory:stock_list' %}` (phone-centric route)
- No liquor-specific stock list view existed
- Generic `inventory:stock_list` view had no vertical gating
- Routing helper `_get_vertical_stock_url()` returned wrong URL for liquor

---

## Solution Implemented

### A) New Liquor Stock List View
**File**: `inventory/views_liquor_inventory.py`

Created `liquor_stock_list()` view with:
- ✅ Vertical gating via `@require_business_kind(BusinessKind.LIQUOR)`
- ✅ Category filtering via `?category=` param
- ✅ Search filtering (by name, SKU, barcode)
- ✅ Business + location scoping (no cross-business leakage)
- ✅ Liquor-appropriate metrics (bottles, cost/bottle, profit margin)
- ✅ No IMEI or phone logic

**Key Features**:
```python
@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def liquor_stock_list(request):
    """
    Liquor Stock List - Detailed view of liquor inventory.
    
    CRITICAL: This view is LIQUOR-ONLY. Phone businesses must NEVER access this.
    Supports filtering by category via ?category= param.
    """
    business = get_active_business(request)
    
    # Base queryset: liquor products for this business only
    products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True
    )
    
    # Category filter
    category = request.GET.get('category', '').strip().lower()
    if category:
        products = products.filter(category__iexact=category)
    
    # ... metrics calculation ...
```

---

### B) New Liquor Stock List Template
**File**: `templates/verticals/liquor/stock_list.html`

Created liquor-specific template with:
- ✅ No IMEI scanner UI
- ✅ No phone/warranty references
- ✅ Liquor-appropriate columns:
  - Product Name
  - Category (beer, cider, wine, spirits)
  - SKU
  - Bottles in Stock
  - Cost/Bottle
  - Price/Bottle
  - Total Cost
  - Total Retail
  - Profit Margin
- ✅ Category badges (color-coded)
- ✅ Low stock indicators
- ✅ Search and filter UI

---

### C) URL Route Added
**File**: `inventory/urls_liquor.py`

```python
urlpatterns = [
    # ...
    # Stock List (detailed inventory with category filtering)
    path("stock/list/", views_liquor_inventory.liquor_stock_list, name="stock_list"),
    # ...
]
```

**Route**: `/liquor/stock/list/`  
**Named URL**: `liquor:stock_list`

---

### D) Liquor Hub Template Fixed
**File**: `templates/verticals/liquor/inventory_dashboard.html`

**BEFORE**:
```html
<a href="{% url 'inventory:stock_list' %}?category={{ battery.key }}" class="btn-view">View Stock</a>
```

**AFTER**:
```html
<a href="{% url 'liquor:stock_list' %}?category={{ battery.key }}" class="btn-view">View Stock</a>
```

Also fixed:
- Quick Actions "View All Stock" button now uses `liquor:stock_list`

---

### E) Phone Stock List Vertical Gate
**File**: `inventory/views.py`

Added vertical gate to `stock_list()` view:

```python
@login_required
@never_cache
def stock_list(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """
    Inventory · Stock List
    
    VERTICAL GATE: This view is for phones/pharmacy/clothing/gym.
    Liquor businesses must use liquor:stock_list instead.
    """
    # ... business context ...
    
    # ---------- VERTICAL GATE: Prevent liquor businesses from accessing phone stock list ----------
    from .helpers_core import business_vertical, LIQUOR
    vertical = business_vertical(request)
    
    if vertical == LIQUOR:
        # Liquor businesses MUST use their own stock list
        # Redirect to liquor stock list with same query params
        from django.urls import reverse
        
        try:
            liquor_url = reverse("liquor:stock_list")
            # Preserve query params (category, search, etc.)
            if request.GET:
                liquor_url += f"?{request.GET.urlencode()}"
            return redirect(liquor_url)
        except Exception:
            # Fallback: return 404 to prevent leakage
            from django.http import Http404
            raise Http404("This feature is not available for your business type")
    
    # ... rest of phone stock list logic ...
```

**Behavior**:
- Liquor business accessing `/inventory/list/` → **Redirected** to `/liquor/stock/list/`
- Phone business accessing `/inventory/list/` → **200 OK** (normal behavior)

---

### F) Routing Helper Fixed
**File**: `inventory/views_router.py`

**BEFORE**:
```python
def _get_vertical_stock_url(vertical: str) -> str:
    if vertical == LIQUOR:
        return reverse("liquor:stock_overview")  # ❌ WRONG (battery view)
```

**AFTER**:
```python
def _get_vertical_stock_url(vertical: str) -> str:
    if vertical == LIQUOR:
        # CRITICAL FIX: Liquor must use liquor:stock_list (detailed inventory)
        # NOT liquor:stock_overview (battery view) or inventory:stock_list (phones)
        return reverse("liquor:stock_list")  # ✅ CORRECT
```

---

### G) Base Context Helper Fixed
**File**: `inventory/verticals/base.py`

```python
if vertical == "liquor":
    url_home = reverse("verticals:liquor_dashboard")
    url_stock = reverse("liquor:stock_list")  # FIXED: Use stock_list not stock_overview
    url_sell = reverse("liquor:sell")
    url_scan_in = reverse("liquor:inventory_dashboard")
```

---

## Tests Added

**File**: `tests/test_liquor_stock_vertical_leakage.py`

Created comprehensive test suite with **13 tests** (all passing ✅):

### Test Class 1: `TestLiquorStockListVerticalIsolation`

1. ✅ `test_liquor_stock_list_url_exists` - Route exists
2. ✅ `test_liquor_user_can_access_liquor_stock_list` - Liquor users get 200
3. ✅ `test_liquor_user_accessing_phone_stock_list_gets_redirected` - **CRITICAL**: Liquor users redirected from phone route
4. ✅ `test_phone_user_can_access_phone_stock_list` - Phone users unaffected
5. ✅ `test_liquor_stock_list_shows_liquor_products_only` - Business scoping works
6. ✅ `test_liquor_stock_list_category_filter` - Category filtering works
7. ✅ `test_liquor_stock_list_has_no_imei_ui` - **CRITICAL**: No IMEI/phone UI
8. ✅ `test_liquor_stock_list_shows_liquor_appropriate_ui` - Shows bottles/liquor terms
9. ✅ `test_liquor_stock_list_search_filter` - Search works
10. ✅ `test_liquor_stock_list_displays_correct_metrics` - Metrics accurate
11. ✅ `test_routing_helper_returns_liquor_stock_list_for_liquor_business` - Helper fixed
12. ✅ `test_no_cross_business_data_leakage` - **CRITICAL**: No cross-business leakage

### Test Class 2: `TestLiquorHubLinks`

13. ✅ `test_liquor_hub_uses_liquor_stock_list_url` - Hub links to liquor route

**Run Tests**:
```bash
pytest tests/test_liquor_stock_vertical_leakage.py -v
# Result: 13 passed, 10 warnings in 27.13s
```

---

## Acceptance Criteria (All Met ✅)

### ✅ Liquor "View Stock" Never Lands on Phone Stock List
- Clicking "View Stock" in Liquor Hub → `/liquor/stock/list/` (not `/inventory/list/`)
- Template uses `liquor:stock_list` route
- Tests confirm no phone UI appears

### ✅ Liquor Stock List is Liquor-Appropriate
- Shows bottles, categories (beer/cider/wine/spirits)
- No IMEI scanner
- No phone/warranty references
- Liquor-specific metrics (cost/bottle, profit margin)

### ✅ Liquor Business Cannot Access Phone Stock List
- GET `/inventory/list/` as liquor business → **302 Redirect** to `/liquor/stock/list/`
- Tests confirm liquor businesses never get 200 from phone route

### ✅ Business + Location Scoping Enforced
- All queries filtered by `business=active_business`
- No cross-business data leakage
- Tests confirm Business A cannot see Business B's data

### ✅ Tests Cover Vertical Isolation Rules
- 13 tests added
- All tests passing
- Covers:
  - Vertical gating
  - Cross-business isolation
  - UI leakage prevention
  - Routing correctness

---

## Files Changed

### Created (3 files)
1. `templates/verticals/liquor/stock_list.html` - Liquor stock list template
2. `tests/test_liquor_stock_vertical_leakage.py` - Test suite (13 tests)
3. `LIQUOR_STOCK_VERTICAL_LEAKAGE_FIX.md` - This document

### Modified (5 files)
1. `inventory/views_liquor_inventory.py` - Added `liquor_stock_list()` view
2. `inventory/urls_liquor.py` - Added `liquor:stock_list` route
3. `templates/verticals/liquor/inventory_dashboard.html` - Fixed "View Stock" links
4. `inventory/views.py` - Added vertical gate to `stock_list()`
5. `inventory/views_router.py` - Fixed `_get_vertical_stock_url()`
6. `inventory/verticals/base.py` - Fixed `url_stock` for liquor

---

## Verification Steps

### Manual Testing

1. **Login to Liquor Business**
   ```
   Username: liquor_manager
   Business: Test Liquor Store (vertical=liquor)
   ```

2. **Navigate to Liquor Hub**
   ```
   URL: /liquor/inventory/
   Expected: See category batteries (Beer, Cider, Wine, Spirits)
   ```

3. **Click "View Stock" on Beer Category**
   ```
   Expected URL: /liquor/stock/list/?category=beer
   Expected UI: 
     - Table with liquor products
     - Columns: Name, Category, SKU, Bottles, Cost, Price, Profit
     - NO "Scan IMEI" button
     - NO phone/warranty references
   ```

4. **Try to Access Phone Stock List Directly**
   ```
   URL: /inventory/list/
   Expected: Redirect to /liquor/stock/list/
   Status: 302 → 200 (after redirect)
   ```

5. **Login to Phone Business**
   ```
   Username: phone_manager
   Business: Test Phone Store (vertical=phones)
   ```

6. **Access Phone Stock List**
   ```
   URL: /inventory/list/
   Expected: 200 OK (phone stock list with IMEI UI)
   ```

### Automated Testing
```bash
# Run vertical leakage tests
pytest tests/test_liquor_stock_vertical_leakage.py -v

# Run all liquor tests
pytest tests/test_verticals_liquor.py -v

# Run all vertical isolation tests
pytest tests/test_vertical_routing.py tests/test_vertical_nav.py -v
```

---

## Security Implications

### Before Fix (CRITICAL VULNERABILITIES)
- ❌ Liquor businesses could access phone stock list UI
- ❌ IMEI scanner visible to non-phone businesses
- ❌ Vertical leakage could expose phone-specific data
- ❌ No vertical gating on generic stock list view

### After Fix (SECURE)
- ✅ Liquor businesses hard-gated to liquor routes
- ✅ Phone stock list redirects liquor businesses
- ✅ No IMEI UI visible to liquor businesses
- ✅ Vertical isolation enforced at view + template levels
- ✅ Tests prevent regressions

---

## Related Issues

### Similar Fixes Needed?
Check other verticals for similar leakage:
- [ ] Pharmacy "View Stock" → Should use pharmacy-specific route?
- [ ] Gym "View Stock" → Should use gym-specific route?
- [ ] Clothing "View Stock" → Should use clothing-specific route?

### Audit Recommendations
1. Review all vertical hub templates for cross-vertical URL usage
2. Add vertical gates to all generic inventory views
3. Ensure routing helpers return correct URLs for all verticals
4. Add vertical isolation tests for pharmacy/gym/clothing

---

## Rollback Plan (If Needed)

If this fix causes issues:

1. **Revert Template Changes**
   ```bash
   git checkout HEAD~1 templates/verticals/liquor/inventory_dashboard.html
   ```

2. **Revert View Changes**
   ```bash
   git checkout HEAD~1 inventory/views.py
   git checkout HEAD~1 inventory/views_liquor_inventory.py
   ```

3. **Revert URL Changes**
   ```bash
   git checkout HEAD~1 inventory/urls_liquor.py
   ```

4. **Remove New Files**
   ```bash
   rm templates/verticals/liquor/stock_list.html
   rm tests/test_liquor_stock_vertical_leakage.py
   ```

---

## Deployment Notes

### Pre-Deployment Checklist
- ✅ All tests passing (13/13)
- ✅ No new linter errors
- ✅ Template syntax validated
- ✅ URL routes tested
- ✅ Vertical gating tested
- ✅ Business scoping verified

### Post-Deployment Verification
1. Test liquor hub "View Stock" links
2. Verify liquor stock list loads correctly
3. Confirm phone businesses unaffected
4. Check logs for any 404/500 errors on `/liquor/stock/list/`
5. Monitor for vertical leakage reports

---

## Summary

**Problem**: Liquor "View Stock" routed to phone stock list (IMEI UI visible)  
**Solution**: Created liquor-specific stock list with vertical gating  
**Result**: Liquor businesses now use `/liquor/stock/list/` (no IMEI UI)  
**Tests**: 13/13 passing  
**Status**: ✅ FIXED

**Key Principle Enforced**: **Vertical isolation is non-negotiable. Liquor users must NEVER see phone UI.**

