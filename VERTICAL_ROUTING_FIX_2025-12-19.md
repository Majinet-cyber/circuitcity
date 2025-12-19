# Vertical Routing Fix - December 19, 2025

## Problem Statement

The new "groceries" vertical was incorrectly landing on `/verticals/none/` and showing phones-only pages with phones KPIs (e.g., stock list showing "Scan IMEI", phones filters, and "This page is only available for phones businesses"). This was a critical issue that could affect any new vertical added to the system.

## Root Causes

1. **Missing vertical constants**: GROCERY, CEMENT, and HARDWARE were not properly defined in all helper modules
2. **Incomplete dispatcher mapping**: The vertical dispatcher didn't include routes for grocery, cement, and hardware
3. **Missing vertical modules**: No view modules or templates existed for grocery, cement, and hardware verticals
4. **Incomplete sidebar navigation**: Sidebar nav didn't include menu items for new verticals
5. **Missing URL registration**: Hardware URLs weren't registered in cc/urls.py

## Solution Overview

Created a comprehensive vertical routing system that ensures:
- Every business with a vertical ALWAYS lands on a valid dashboard page
- No `/verticals/none/` for businesses that have a vertical set
- Vertical-aware navigation (groceries see groceries menu, hardware sees hardware menu, etc.)
- Complete data isolation (groceries never served phone templates, phone KPIs, or phone endpoints)
- Minimal but real dashboards for all verticals
- Guard rails to prevent phones-only views from being accessed by other verticals

## Files Changed/Created

### A. Core Constants and Helpers

**Modified: `inventory/helpers_core.py`**
- Added `CEMENT` and `HARDWARE` constants
- Updated `_ALIASES` dict to include cement/hardware synonyms
- Ensures single source of truth for vertical keys

**Modified: `inventory/helpers/__init__.py`**
- Re-exported CEMENT and HARDWARE constants
- Updated __all__ list

**Modified: `inventory/business_kinds.py`**
- Added `CEMENT = "cement", "Cement & Hardware"`
- Added `HARDWARE = "hardware", "Hardware Store"`

### B. Vertical Dispatcher and Routing

**Modified: `inventory/views_dispatch.py`**
- Added GROCERY, CEMENT, HARDWARE imports
- Updated `_VERTICAL_ROUTES` dict:
  ```python
  _VERTICAL_ROUTES = {
      CLOTHING: "verticals:clothing_dashboard",
      LIQUOR: "verticals:liquor_dashboard",
      PHARMACY: "verticals:pharmacy_dashboard",
      GYM: "verticals:gym_dashboard",
      GROCERY: "verticals:grocery_dashboard",
      CEMENT: "verticals:cement_dashboard",
      HARDWARE: "verticals:hardware_dashboard",
  }
  ```

**Modified: `inventory/utils_verticals.py`**
- Updated `valid_kinds` list to include "grocery", "cement", "hardware"
- Updated `vertical_dashboard_map` with new vertical URLs
- Updated `get_vertical_display_name()` with friendly names
- Added sidebar navigation configurations for:
  - Grocery: Dashboard, Analytics, Fast Sell, Inventory, Stock In, Sell, Costs
  - Cement/Hardware: Dashboard, Analytics, Inventory, Stock In, Sell, Costs

### C. Vertical View Modules

**Created: `inventory/verticals/grocery.py`**
- `dashboard(request)` - Main grocery dashboard (redirects to full view)
- `hub(request)` - Grocery hub page
- Protected with `@require_business_kind(BusinessKind.GROCERY)`

**Created: `inventory/verticals/cement.py`**
- `dashboard(request)` - Cement & Hardware dashboard
- `hub(request)` - Cement & Hardware hub page
- Protected with `@require_business_kind(BusinessKind.CEMENT)`

**Created: `inventory/verticals/hardware.py`**
- `dashboard(request)` - Hardware Store dashboard
- `hub(request)` - Hardware Store hub page
- Protected with `@require_business_kind(BusinessKind.HARDWARE)`

### D. URL Configuration

**Modified: `verticals/urls.py`**
- Added imports for grocery, cement, hardware modules
- Added URL patterns:
  ```python
  # Grocery vertical
  path("grocery/dashboard/", grocery.dashboard, name="grocery_dashboard"),
  path("grocery/hub/", grocery.hub, name="grocery_hub"),
  
  # Cement & Hardware vertical
  path("cement/dashboard/", cement.dashboard, name="cement_dashboard"),
  path("cement/hub/", cement.hub, name="cement_hub"),
  
  # Hardware Store vertical
  path("hardware/dashboard/", hardware.dashboard, name="hardware_dashboard"),
  path("hardware/hub/", hardware.hub, name="hardware_hub"),
  ```

**Created: `inventory/urls_hardware.py`**
- Complete URL routing for hardware vertical
- Includes: dashboard, stock_in, sell, costs, analytics, products

**Modified: `cc/urls.py`**
- Added hardware URL registration:
  ```python
  path("hardware/", include_or_raise("inventory.urls_hardware", "hardware")),
  ```

### E. Dashboard Templates

**Created: `templates/verticals/grocery/dashboard.html`**
- Mobile-first, premium UI
- KPI cards: Products, Low Stock, Today Sales, Month Sales
- Quick actions: Fast Sell, Stock In, Record Sale, View Inventory
- Recent activity section
- Motivational quote display

**Created: `templates/verticals/cement/dashboard.html`**
- Mobile-first, premium UI
- KPI cards: Products, Low Stock, Today Sales, Month Sales
- Quick actions: Stock In, Record Sale, View Inventory, Record Costs
- Welcome message section

**Created: `templates/verticals/hardware/dashboard.html`**
- Mobile-first, premium UI
- KPI cards: Products, Low Stock, Today Sales, Month Sales
- Quick actions: Stock In, Record Sale, View Inventory, Record Costs
- Welcome message section

### F. Comprehensive Tests

**Created: `tests/test_vertical_routing_comprehensive.py`**

Test classes:
1. **TestGroceryVerticalRouting**
   - `test_grocery_routes_to_grocery_dashboard()` - Ensures correct routing
   - `test_grocery_never_sees_verticals_none()` - Prevents /verticals/none/
   - `test_grocery_cannot_access_phone_scan_imei()` - Guards phones-only views
   - `test_grocery_sidebar_has_correct_items()` - Validates navigation

2. **TestCementVerticalRouting**
   - `test_cement_routes_to_cement_dashboard()` - Ensures correct routing
   - `test_cement_never_sees_verticals_none()` - Prevents /verticals/none/
   - `test_cement_cannot_access_phone_wizard()` - Guards phones-only views

3. **TestHardwareVerticalRouting**
   - `test_hardware_routes_to_hardware_dashboard()` - Ensures correct routing
   - `test_hardware_never_sees_verticals_none()` - Prevents /verticals/none/

4. **TestPhonesVerticalProtection**
   - `test_phones_business_can_access_imei_scan()` - Phones can access IMEI
   - `test_grocery_redirected_from_phone_pages()` - Non-phones blocked

5. **TestVerticalUtilities**
   - `test_get_vertical_kind_returns_correct_vertical()` - Utility validation
   - `test_get_vertical_dashboard_url_maps_correctly()` - URL mapping
   - `test_business_vertical_helper_returns_correct_value()` - Helper validation

6. **TestNoBusinessFallback**
   - `test_no_vertical_shows_selection_page()` - Fallback behavior

## Key Features Implemented

### 1. Single Source of Truth for Vertical Resolution
- `inventory/helpers_core.py` defines all vertical constants
- `inventory/utils_verticals.py` provides vertical-aware utilities
- All vertical checks use these helpers (no scattered hardcoded checks)

### 2. Fixed Landing/Redirect Logic
- If `business.vertical` is set → redirect to correct vertical dashboard
- If not set → show "Select your business type" page
- **Never** default to phones

### 3. Vertical-Aware URL Routing
- Each vertical has its own URL module and view module
- Grocery: `inventory/urls_grocery.py`, `inventory/views_grocery.py`
- Cement: `inventory/urls_cement.py`, `inventory/verticals/cement.py`
- Hardware: `inventory/urls_hardware.py`, `inventory/verticals/hardware.py`

### 4. Vertical-Aware Sidebar/Navigation
- Sidebar renders menu items based on `get_vertical_sidebar_items(vertical)`
- Phones menu: Stock, Scan IN, Scan & Sell, Layby
- Groceries menu: Dashboard, Analytics, Fast Sell, Inventory, Stock In, Sell
- Hardware/Cement menu: Dashboard, Analytics, Inventory, Stock In, Sell, Costs
- Mobile-optimized (no overflow)

### 5. Data Scoping
- All inventory/sales queries scoped by business + location
- Never assume phones fields (IMEI) for other verticals
- Templates conditionally show fields based on vertical

### 6. Guard Rails
- Phones-only views protected with `@require_business_kind(BusinessKind.PHONES)`
- Non-phone verticals accessing phones pages get 403/404 or redirect
- "This page is only available for phones businesses" message unreachable for other verticals

## Vertical Navigation Structure

### Phones (Original)
- Dashboard → Analytics
- Stock (IMEI-based)
- Scan IN (IMEI)
- Scan & Sell (IMEI)
- Layby
- Products, Wallet, Time Logs, Reports, etc.

### Grocery
- Dashboard → Grocery Dashboard
- Analytics
- Fast Sell (Barcode/SKU)
- Inventory (SKU-based)
- Stock In
- Sell
- Costs, Reports, Locations, etc.

### Cement & Hardware
- Dashboard → Cement/Hardware Dashboard
- Analytics
- Inventory (SKU-based)
- Stock In
- Sell
- Costs, Reports, Locations, etc.

### Gym (Existing)
- Dashboard → Gym Dashboard
- Analytics
- Members
- Member Check-ins
- Wallet, Time Logs, Reports, etc.

### Clothing (Existing)
- Dashboard → Clothing Dashboard
- Analytics
- Fast Sell
- Clothing Hub
- Add Product, Scan IN, Sell
- Wallet, Time Logs, Reports, etc.

### Liquor (Existing)
- Dashboard → Liquor Dashboard
- Analytics
- Liquor Hub
- Stock, Add Product, Stock In, Sell
- Credits
- Wallet, Time Logs, Reports, etc.

### Pharmacy (Existing)
- Dashboard → Pharmacy Dashboard
- Analytics
- Fast Sell
- Pharmacy Hub
- Stock In, Sell, Batches
- Wallet, Time Logs, Reports, etc.

## Testing Strategy

### Unit Tests
- Vertical utility functions return correct values
- URL mapping is correct for all verticals
- Business vertical detection works correctly

### Integration Tests
- Each vertical routes to its dashboard
- Navigation items match vertical
- Phones-only pages blocked for non-phone verticals
- /verticals/none/ never appears once vertical is set

### Manual Testing Checklist
1. ✅ Create grocery business → lands on grocery dashboard
2. ✅ Create cement business → lands on cement dashboard
3. ✅ Create hardware business → lands on hardware dashboard
4. ✅ Grocery business cannot access /inventory/phone-scan-in/
5. ✅ Grocery business cannot access /inventory/phone-sale-wizard/
6. ✅ Grocery sidebar shows grocery menu items only
7. ✅ Cement sidebar shows cement menu items only
8. ✅ Hardware sidebar shows hardware menu items only
9. ✅ Business without vertical shows "Select your business type"
10. ✅ No vertical ever lands on /verticals/none/ once vertical is set

## Migration Notes

### Database Changes
No database migrations required. The `business_kind` field already exists in the Business model. We added two new choices:
- `CEMENT = "cement", "Cement & Hardware"`
- `HARDWARE = "hardware", "Hardware Store"`

### Backward Compatibility
- All existing verticals (phones, clothing, liquor, pharmacy, gym) continue to work
- Legacy businesses without `business_kind` set will see "Select your business type"
- No breaking changes to existing URLs or views

## Performance Considerations

- Minimal overhead: vertical resolution happens once per request
- Sidebar navigation cached in session
- No additional database queries for vertical detection
- Templates are lightweight and mobile-optimized

## Security Considerations

- All vertical views protected with `@login_required` and `@require_business`
- Phones-only views protected with `@require_business_kind(BusinessKind.PHONES)`
- Business scoping enforced at query level (no cross-tenant data leaks)
- Authorization checks happen before rendering templates

## Future Enhancements

1. **Enhanced Dashboards**: Add real-time KPIs and charts for grocery/cement/hardware
2. **Barcode Scanning**: Implement barcode scanning for grocery fast sell
3. **Batch Operations**: Add bulk stock-in for cement/hardware
4. **Reports**: Create vertical-specific reports (e.g., cement sales by product category)
5. **Mobile Apps**: Develop native mobile apps for each vertical
6. **AI Insights**: Add AI-powered insights for inventory optimization

## Conclusion

This implementation ensures that:
- ✅ Every business with a vertical ALWAYS lands on a valid dashboard
- ✅ No `/verticals/none/` for businesses with a vertical set
- ✅ Navigation is vertical-aware (groceries see groceries menu, etc.)
- ✅ Complete data isolation (no vertical data leaks)
- ✅ Minimal but real dashboards for all verticals
- ✅ Comprehensive tests guarantee correct routing
- ✅ Guard rails prevent phones-only views from being accessed by other verticals

The system is now robust, scalable, and ready for any new verticals to be added in the future.

