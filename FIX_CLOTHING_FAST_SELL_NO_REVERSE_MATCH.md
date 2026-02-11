# Fix: NoReverseMatch Error for clothing_fast_sell_resolve_product_api

**Date**: 2026-02-08  
**Issue**: 500 Internal Server Error on `GET /verticals/clothing/fast-sell/`  
**Error**: `django.urls.exceptions.NoReverseMatch: Reverse for 'clothing_fast_sell_resolve_product_api' not found`

## Root Cause

The `verticals.urls` module was included **twice** in the URL configuration with the same namespace name `"verticals"`:

1. **`cc/urls.py` line 687**: 
   ```python
   path("verticals/", include_or_raise("verticals.urls", "verticals"))
   ```
   → Makes URLs accessible at `/verticals/...` with namespace `verticals:`

2. **`inventory/urls.py` line 1820**: 
   ```python
   path("verticals/", include(("verticals.urls", "verticals"), namespace="verticals"))
   ```
   → Makes URLs accessible at `/inventory/verticals/...` but **also using namespace** `verticals:`

This created a **namespace collision**. Django's URL resolver became confused when template code tried to reverse `verticals:clothing_fast_sell_resolve_product_api`, leading to unpredictable behavior and NoReverseMatch errors during template rendering.

## Solution

**Removed the duplicate registration** from `inventory/urls.py` lines 1816-1821.

### Before (inventory/urls.py):
```python
# ---------------------------------------------------------------------
# Nested verticals namespace (for inventory:verticals:* URLs)
# ---------------------------------------------------------------------
urlpatterns += [
    path("verticals/", include(("verticals.urls", "verticals"), namespace="verticals")),
]
```

### After (inventory/urls.py):
```python
# ---------------------------------------------------------------------
# REMOVED: Duplicate verticals namespace registration (2026-02-08)
# The verticals namespace is already registered in cc/urls.py at /verticals/
# Having it here at /inventory/verticals/ with the same namespace name "verticals"
# caused Django's URL resolver to behave unpredictably during template rendering.
# Legacy path /inventory/verticals/ is handled by inventory.urls_verticals namespace.
# ---------------------------------------------------------------------
```

The URL pattern is now registered **only once** in `cc/urls.py`, making all verticals URLs accessible at `/verticals/*` with the `verticals:` namespace.

## Verification

### 1. URL Reversal Works
```python
from django.urls import reverse
url = reverse('verticals:clothing_fast_sell_resolve_product_api')
# Returns: '/verticals/clothing/api/fast-sell/resolve-product/'
```

### 2. Template Rendering Works
```python
from django.template import Template, Context
template = Template("{% url 'verticals:clothing_fast_sell_resolve_product_api' %}")
rendered = template.render(Context({}))
# Returns: '/verticals/clothing/api/fast-sell/resolve-product/'
```

### 3. All Tests Pass
- ✅ `inventory/tests/test_clothing_unified_fast_sell.py` - 20 tests passed
- ✅ `inventory/tests/test_clothing_fast_sell_scanner.py` - 11 passed, 2 skipped
- ✅ `inventory/tests/test_fast_sell_integration.py` - 13 tests passed
- ✅ `inventory/tests/test_clothing_scanner_fixes_regression.py` - 7 passed, 3 skipped
- ✅ **Total: 125 clothing-related tests passed, 9 skipped, 0 failures**

### 4. Page Loads Successfully
- ✅ `GET /verticals/clothing/fast-sell/` returns HTTP 200 (not 500)
- ✅ Template renders without NoReverseMatch errors
- ✅ JavaScript can fetch from the resolved API endpoint

## Impact

- **No regressions**: All existing tests continue to pass
- **No breaking changes**: URLs remain at the same paths
- **Namespace cleanup**: Single source of truth for `verticals:` namespace
- **Improved reliability**: URL resolution is now deterministic

## Related Files

- `inventory/urls.py` - Removed duplicate namespace registration
- `verticals/urls.py` - Contains the actual URL patterns (unchanged)
- `cc/urls.py` - Primary registration point for verticals namespace (unchanged)
- `templates/verticals/clothing/fast_sell.html` - Template using the URL tag (unchanged)
- `inventory/verticals/clothing.py` - View function `fast_sell_resolve_product_api` (unchanged)

## Notes

The legacy path `/inventory/verticals/*` is still supported via the `inventory_verticals` namespace registered separately in `cc/urls.py` line 689. This fix only removes the conflicting duplicate registration of the `verticals` namespace itself.









