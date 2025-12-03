# Inventory Dashboard Redirect Loop Fix

## Problem Summary

The URL `/inventory/dashboard/` was stuck in an infinite redirect loop, causing browser error `ERR_TOO_MANY_REDIRECTS`. Django runserver logs showed hundreds of `GET /inventory/dashboard/ HTTP/1.1" 302 0` entries.

## Root Cause

The redirect loop was caused by **self-referencing redirect logic** in the vertical dispatcher:

1. **Entry Point**: `/inventory/dashboard/` maps to `vertical_dispatcher` (in `inventory/views_dispatch.py`)

2. **The Problem**: For PHONES businesses, the `_VERTICAL_ROUTES` dictionary mapped:
   ```python
   PHONES: "inventory:inventory_dashboard"
   ```
   And then line 44 did:
   ```python
   return redirect(target)  # Redirects back to itself!
   ```

3. **The Loop**: This created a 302 redirect from `/inventory/dashboard/` → `inventory:inventory_dashboard` → `/inventory/dashboard/` → (infinite loop)

## Solution

### 1. Fixed `inventory/views_dispatch.py` (Primary Fix)

**Changed**: Instead of redirecting PHONES businesses, the dispatcher now **renders the dashboard directly**:

```python
@login_required
@require_business
def vertical_dispatcher(request):
    """
    Route users to the correct dashboard for their business vertical.
    
    PHONES businesses render the inventory dashboard directly (no redirect to avoid loops).
    Other verticals redirect to their specialized dashboards.
    """
    vertical = business_vertical(request)
    
    # PHONES: render the inventory dashboard directly to prevent self-redirect loop
    if vertical == PHONES:
        from inventory.views_dashboard import inventory_dashboard
        return inventory_dashboard(request)
    
    # Other verticals: redirect to their specialized dashboards
    target = _VERTICAL_ROUTES.get(vertical, _DEFAULT_ROUTE)
    return redirect(target)
```

**Key Changes**:
- Removed `PHONES: "inventory:inventory_dashboard"` from `_VERTICAL_ROUTES`
- Added conditional logic to call `inventory_dashboard(request)` directly for PHONES
- Other verticals (liquor, pharmacy, gym, clothing) still redirect correctly

### 2. Fixed `tenants/utils.py` (Guard in `require_business` Decorator)

**Added**: Safety check to prevent redirecting back to `/inventory/dashboard/` when no business is set:

```python
# GUARD: Never redirect back to inventory:dashboard to avoid loops
current_path = getattr(request, "path", "")
if current_path and current_path.rstrip("/") == "/inventory/dashboard":
    # Instead of redirecting to activate_mine and back, go straight to choose business
    target = _safe_reverse("tenants:choose_business", "/tenants/choose/")
else:
    target = _safe_reverse("tenants:activate_mine", "/tenants/activate/")
```

### 3. Fixed `inventory/views.py` (`_require_active_business`)

**Changed**: Redirect to choose-business page instead of `dashboard:home` to avoid circular dependencies:

```python
def _require_active_business(request):
    """
    Attach/choose a business for this request, or show error + redirect.
    
    GUARD: To avoid redirect loops, redirect to choose-business page instead of dashboard:home
    when no active business is found.
    """
    biz = _get_active_business(request)
    if not biz:
        messages.error(request, "No active business selected. Switch business and try again.")
        # Redirect to choose-business to avoid loops (dashboard:home also needs a business)
        try:
            from django.urls import reverse, NoReverseMatch
            try:
                return redirect(reverse("tenants:choose_business"))
            except NoReverseMatch:
                return redirect("/tenants/choose/")
        except Exception:
            return redirect("/tenants/choose/")
    return None  # OK
```

### 4. Added `@require_business` Decorator to `dashboard/views.py`

**Changed**: Added decorator to ensure `request.business` is always set:

```python
@login_required
@require_business
def home(request):
    """
    Default dashboard for managers/agents within an active business.
    ...
    NOTE: @require_business ensures request.business is set; if no active business,
    user is redirected to choose-business page, preventing redirect loops.
    """
```

## Regression Tests

Created comprehensive test suite in `tests/test_inventory_dashboard_redirects.py`:

### Test Coverage

✅ **Test 1**: Anonymous user redirected to login (not looped)
- Anonymous GET `/inventory/dashboard/` → 302 to `/accounts/login/?next=...`
- Redirect target is NOT `/inventory/dashboard/` itself

✅ **Test 2**: Authenticated user with NO active business redirected to choose-business (not looped)
- Logged-in user without business → 302 to `/tenants/choose/` or `/tenants/activate/`
- Redirect target is NOT `/inventory/dashboard/`

✅ **Test 3**: Authenticated user WITH PHONES business gets 200 OK dashboard
- User with PHONES business + active business in session → 200 OK
- NO redirect occurs (dashboard renders directly)

✅ **Test 4**: Hard guard against self-redirect
- Any redirect from `/inventory/dashboard/` MUST NOT target itself
- Catches self-redirect loops regardless of scenario

✅ **Test 5 & 6**: Following redirects terminates cleanly
- Anonymous user chain terminates at login (200)
- User without business chain terminates at choose-business (200)
- No infinite loops in the redirect chain

✅ **Test 7**: Vertical dispatcher does NOT redirect PHONES to itself (CRITICAL)
- PHONES business → 200 OK (renders directly)
- Absolutely NO 302 redirect occurs

✅ **Test 8**: Other verticals (liquor) redirect properly
- Liquor business → 302 to `/verticals/liquor/dashboard/`
- Does NOT redirect to `/inventory/dashboard/`

### Test Results

```bash
$ python -m pytest tests/test_inventory_dashboard_redirects.py -v
============================= test session starts =============================
collected 8 items

tests\test_inventory_dashboard_redirects.py ........                     [100%]

======================= 8 passed, 20 warnings in 8.38s ========================
```

**All tests pass! ✅**

## Files Changed

### Modified Files

1. **`inventory/views_dispatch.py`**
   - Fixed vertical_dispatcher to render PHONES dashboard directly instead of redirecting
   - Removed PHONES from `_VERTICAL_ROUTES` dictionary

2. **`tenants/utils.py`**
   - Added guard in `require_business` decorator to prevent redirecting to `/inventory/dashboard/` when no business

3. **`inventory/views.py`**
   - Changed `_require_active_business` to redirect to choose-business instead of dashboard:home

4. **`dashboard/views.py`**
   - Added `@require_business` decorator to `home` view for safety

### New Files

5. **`tests/test_inventory_dashboard_redirects.py`** (NEW)
   - Comprehensive test suite with 8 tests
   - Guards against future regressions

## Verification

The fix has been verified through:

1. **Unit Tests**: All 8 regression tests pass
2. **Redirect Chain Mapping**: Explicitly documented the redirect chain that produced the loop
3. **Code Comments**: Added explanatory comments at key decision points

## Impact Assessment

### What Changed

- PHONES businesses now get their dashboard rendered directly (200 OK) instead of being redirected
- Other verticals (gym, liquor, pharmacy, clothing) still redirect to their specialized dashboards
- Redirect chains now terminate cleanly at appropriate pages (login, choose-business)

### What Did NOT Change

- Tenant/business/location logic remains intact
- HQ vs client UI separation unchanged
- Middleware behavior for other URLs unchanged
- No breaking changes to existing views or templates

### Behavior Changes

| Scenario | Before | After |
|----------|--------|-------|
| Anonymous user on `/inventory/dashboard/` | Infinite 302 loop | 302 → login (clean) |
| User without business on `/inventory/dashboard/` | Infinite 302 loop | 302 → choose-business (clean) |
| User with PHONES business on `/inventory/dashboard/` | Infinite 302 loop | 200 OK (renders dashboard) |
| User with Liquor business on `/inventory/dashboard/` | 302 → liquor dashboard | 302 → liquor dashboard (unchanged) |

## Recommendations

1. **Monitor**: Watch for any issues with PHONES businesses accessing their dashboard
2. **Test in Production**: Verify the fix works with real user accounts and businesses
3. **Document**: Update any internal docs that mention the vertical routing behavior

## Conclusion

The infinite redirect loop has been fixed with a **minimal, targeted change** that:
- ✅ Prevents self-referencing redirects for PHONES businesses
- ✅ Maintains all existing tenant/business/location logic
- ✅ Includes comprehensive regression tests
- ✅ Has no breaking changes to other features

The redirect chain now terminates cleanly in all scenarios.

