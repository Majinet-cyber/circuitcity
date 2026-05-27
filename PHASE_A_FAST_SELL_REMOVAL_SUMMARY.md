# Phase A: Fast Sell Removal from Phones + Liquor - COMPLETE

## Summary

Successfully removed Fast Sell feature from phones and liquor verticals. Fast Sell is now **ONLY** available for pharmacy and clothing verticals.

## Changes Made

### 1. Capability Flags (✅ Complete)
**File**: `inventory/utils_vertical_capabilities.py`

- Updated `vertical_supports_fast_sell()` function
- Now returns `True` ONLY for "pharmacy" and "clothing"
- Returns `False` for "phones", "liquor", and "gym"
- Updated docstrings with correct examples

### 2. Sidebar Navigation (✅ Complete)
**File**: `inventory/utils_verticals.py`

- **Phones sidebar**: Removed Fast Sell menu item (line 353)
- **Liquor sidebar**: Removed Fast Sell menu item (line 299)
- Pharmacy and clothing sidebars: Fast Sell menu items retained
- Added explanatory comments for why Fast Sell was removed

### 3. URL Routes (✅ Complete)
**File**: `verticals/urls.py`

- **Phones**: Removed `path("phones/fast-sell/", ...)` route
- **Liquor**: Removed `path("liquor/fast-sell/", ...)` route
- **Liquor**: Removed 3 Fast Sell API routes:
  - `liquor/api/fast-sell/lookup/`
  - `liquor/api/fast-sell/sell/`
  - `liquor/api/fast-sell/kpis/`
- Pharmacy and clothing routes: Fast Sell routes retained
- Added explanatory comments

### 4. Service Layer Capability Checks (✅ Complete)
**File**: `inventory/services/fast_sell.py`

- Added capability checks to all 3 main functions:
  - `lookup_product_by_barcode()`: Returns error if vertical doesn't support Fast Sell
  - `create_fast_sell()`: Returns error if vertical doesn't support Fast Sell
  - `get_fast_sell_kpis()`: Returns error if vertical doesn't support Fast Sell

- **Removed liquor-specific code**:
  - Removed liquor lookup logic from `lookup_product_by_barcode()`
  - Removed liquor sale creation logic from `create_fast_sell()`
  - Removed liquor KPI aggregation from `get_fast_sell_kpis()`
  - Removed `attributed_to_agent_id` parameter (was liquor-specific)

- Updated docstrings to clarify pharmacy + clothing only support

### 5. Tests Updated (✅ Complete)
**File**: `inventory/tests/test_fast_sell_integration.py`

- Updated file docstring: Fast Sell ONLY for pharmacy + clothing
- **Phones tests**: Converted to negative tests (should NOT have Fast Sell)
  - `TestPhonesDoesNotSupportFastSell` class
  - Tests verify route doesn't exist, sidebar doesn't have it, capability check returns False
- **Liquor tests**: Converted to negative tests (should NOT have Fast Sell)
  - `TestLiquorDoesNotSupportFastSell` class
  - Tests verify route doesn't exist, sidebar doesn't have it, capability check returns False
- **Gym tests**: Already had negative tests (unchanged)
- **Pharmacy tests**: Retained (still supports Fast Sell)
- **Clothing tests**: Retained (still supports Fast Sell)
- **Sidebar tests**: Removed phones and liquor positive assertions

## Verification Checklist

✅ Capability function returns False for phones/liquor/gym
✅ Capability function returns True for pharmacy/clothing
✅ Phones sidebar does NOT show Fast Sell
✅ Liquor sidebar does NOT show Fast Sell
✅ Pharmacy sidebar DOES show Fast Sell
✅ Clothing sidebar DOES show Fast Sell
✅ Phones fast-sell route removed from URLs
✅ Liquor fast-sell route removed from URLs
✅ Liquor fast-sell API routes removed from URLs
✅ Service layer rejects phones/liquor with clear error messages
✅ Tests updated to reflect new scope
✅ No regressions to existing scan/sell flows

## Backward Compatibility

- **Phones**: Original scan-in and phone sale wizard flows remain unchanged
- **Liquor**: Original sell flow with barman attribution remains unchanged
- **Pharmacy**: Fast Sell remains fully functional
- **Clothing**: Fast Sell remains fully functional
- **Gym**: Never had Fast Sell (membership-based)

## Error Handling

If a client attempts to use Fast Sell API for unsupported verticals:

```json
{
  "ok": false,
  "error": "Fast Sell is not enabled for phones. Use the dedicated scan/sell flow instead."
}
```

This prevents 500 errors and provides clear guidance to users.

## Next Steps

Phase A is complete. Ready to proceed with:
- **Phase B - Task 2**: Implement "Has Barcode?" workflow for scan-in pages
- **Phase B - Task 3**: Implement Liquor roles + assignment + reconciliation
- **Phase B - Task 4**: Implement Salary wallet for liquor staff
- **Phase B - Task 5**: Comprehensive tests + hardening

