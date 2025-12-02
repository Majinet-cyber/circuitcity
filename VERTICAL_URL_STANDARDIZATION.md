# Vertical URL Standardization - Implementation Summary

## Overview

This document describes the standardization of URLs for vertical business types (gym, clothing, liquor, pharmacy) in the Circuit City/Emajinet Django SaaS project.

## Key Concept

**Phones are the original/core inventory module** - they are NOT a vertical. Their URLs remain under `/inventory/...`

**Real verticals** (gym, clothing, liquor, pharmacy) are now standardized under `/verticals/<slug>/...`

---

## Changes Made

### 1. New Canonical Vertical URLs

Created a new `verticals/` package with standardized URLs:

**File: `verticals/urls.py`**
- Namespace: `verticals`
- Routes:
  - `/verticals/gym/dashboard/` → `verticals:gym_dashboard`
  - `/verticals/clothing/dashboard/` → `verticals:clothing_dashboard`
  - `/verticals/liquor/dashboard/` → `verticals:liquor_dashboard`
  - `/verticals/pharmacy/dashboard/` → `verticals:pharmacy_dashboard`

### 2. Backward Compatibility

**File: `inventory/urls_verticals.py`**
- Kept legacy namespace: `inventory_verticals`
- Legacy URLs now redirect to new canonical locations:
  - `/inventory/verticals/gym/` → 302 redirect to `/verticals/gym/dashboard/`
  - `/inventory/verticals/clothing/` → 302 redirect to `/verticals/clothing/dashboard/`
  - `/inventory/verticals/liquor/` → 302 redirect to `/verticals/liquor/dashboard/`
  - `/inventory/verticals/pharmacy/` → 302 redirect to `/verticals/pharmacy/dashboard/`

### 3. Updated Main URL Configuration

**File: `cc/urls.py`**
```python
# New canonical verticals at root level
path("verticals/", include_or_raise("verticals.urls", "verticals")),

# Legacy URLs kept for backward compatibility
path("inventory/verticals/", include_or_raise("inventory.urls_verticals", "inventory_verticals")),
```

### 4. Updated Utilities

**File: `inventory/utils_verticals.py`**

Updated `get_vertical_dashboard_url()`:
```python
vertical_dashboard_map = {
    "gym": "verticals:gym_dashboard",           # NEW namespace
    "pharmacy": "verticals:pharmacy_dashboard",  # NEW namespace
    "clothing": "verticals:clothing_dashboard",  # NEW namespace
    "liquor": "verticals:liquor_dashboard",      # NEW namespace
    # "phones" uses the default dashboard at /inventory/dashboard/
}
```

Updated `get_vertical_sidebar_items()`:
- All vertical sidebar items now reference `verticals:*_dashboard` instead of `inventory_verticals:*_dashboard`
- Phones sidebar items remain unchanged (still use `inventory:*` routes)

### 5. Updated Dispatcher

**File: `inventory/views_dispatch.py`**

Updated route mapping:
```python
_VERTICAL_ROUTES = {
    PHONES: "inventory:inventory_dashboard",  # Phones use core inventory dashboard
    CLOTHING: "verticals:clothing_dashboard",  # NEW namespace
    LIQUOR: "verticals:liquor_dashboard",      # NEW namespace
    PHARMACY: "verticals:pharmacy_dashboard",  # NEW namespace
    GYM: "verticals:gym_dashboard",            # NEW namespace
}
_DEFAULT_ROUTE = "verticals:no_business"
```

### 6. Comprehensive Tests

**File: `tests/test_vertical_url_routing.py`**

Created 6 test classes with 25+ individual tests:

1. **TestPhonesInventoryRouting** - Ensures phones use `/inventory/` routes and inventory-style sidebar
2. **TestGymVerticalRouting** - Verifies gym uses `/verticals/gym/` with gym-specific sidebar
3. **TestClothingVerticalRouting** - Verifies clothing routing
4. **TestLiquorVerticalRouting** - Verifies liquor routing
5. **TestPharmacyVerticalRouting** - Verifies pharmacy routing
6. **TestVerticalUtilsFunctions** - Tests utility functions

---

## URL Structure

### Phones (Core Inventory)

| Route | URL | Named Route |
|-------|-----|-------------|
| Dashboard | `/inventory/dashboard/` | `inventory:inventory_dashboard` |
| Stock List | `/inventory/list/` | `inventory:stock_list` |
| Scan IN | `/inventory/scan-in/` | `inventory:scan_in` |
| Scan Sold | `/inventory/scan-sold/` | `inventory:scan_sold` |
| Time Logs | `/inventory/time/logs/` | `inventory:time_logs` |

### Gym Vertical

| Route | URL | Named Route |
|-------|-----|-------------|
| Dashboard | `/verticals/gym/dashboard/` | `verticals:gym_dashboard` |
| Legacy (redirects) | `/inventory/verticals/gym/` | `inventory_verticals:gym_dashboard` → redirects |

### Clothing Vertical

| Route | URL | Named Route |
|-------|-----|-------------|
| Dashboard | `/verticals/clothing/dashboard/` | `verticals:clothing_dashboard` |
| Legacy (redirects) | `/inventory/verticals/clothing/` | `inventory_verticals:clothing_dashboard` → redirects |

### Liquor Vertical

| Route | URL | Named Route |
|-------|-----|-------------|
| Dashboard | `/verticals/liquor/dashboard/` | `verticals:liquor_dashboard` |
| Legacy (redirects) | `/inventory/verticals/liquor/` | `inventory_verticals:liquor_dashboard` → redirects |

### Pharmacy Vertical

| Route | URL | Named Route |
|-------|-----|-------------|
| Dashboard | `/verticals/pharmacy/dashboard/` | `verticals:pharmacy_dashboard` |
| Legacy (redirects) | `/inventory/verticals/pharmacy/` | `inventory_verticals:pharmacy_dashboard` → redirects |

---

## Sidebar Behavior

### Phones Sidebar (business_kind = "phones")

**MAIN Section:**
- Dashboard
- Inventory Dashboard
- Stock
- Scan IN
- Sell

**TIME Section:**
- Time Logs

**MONEY Section:**
- My Wallet
- Admin Wallet (managers only)

**BUSINESS Section (managers only):**
- Reports
- Agents
- Locations
- Choose Plan
- Orders

**LAYBY Section:**
- Layby

### Gym Sidebar (business_kind = "gym")

**MAIN Section:**
- Dashboard
- Gym Hub
- Members
- Check-ins
- Wallet

**TIME Section:**
- Time Logs

**MONEY Section:**
- My Wallet
- Admin Wallet (managers only)

**BUSINESS Section (managers only):**
- **Trainers** (agents labeled as "Trainers" for gym)
- Locations
- Choose Plan

**Key Difference:** "Agents" is labeled as "Trainers" in the gym vertical.

### Clothing Sidebar (business_kind = "clothing")

**MAIN Section:**
- Dashboard
- Clothing Hub
- Add Product
- Stock In
- Sell

**TIME Section:**
- Time Logs

**MONEY Section:**
- My Wallet
- Admin Wallet (managers only)

**BUSINESS Section (managers only):**
- Agents
- Locations
- Choose Plan
- Orders

### Liquor Sidebar (business_kind = "liquor")

**MAIN Section:**
- Dashboard
- Liquor Hub
- Add Product
- Stock In
- Sell

**TIME Section:**
- Time Logs

**MONEY Section:**
- My Wallet
- Admin Wallet (managers only)

**BUSINESS Section (managers only):**
- Agents
- Locations
- Choose Plan

### Pharmacy Sidebar (business_kind = "pharmacy")

**MAIN Section:**
- Dashboard
- Pharmacy Hub
- Add Medicine
- Batches
- Stock In
- Sell

**TIME Section:**
- Time Logs

**MONEY Section:**
- My Wallet
- Admin Wallet (managers only)

**BUSINESS Section (managers only):**
- Agents
- Locations
- Choose Plan

---

## How the Sidebar Works

The sidebar is built dynamically based on the business kind:

1. **Context Processor** (`tenants/context_processors.py`):
   - Determines the business kind from `request.business.business_kind`
   - Calls `get_vertical_sidebar_items(business_kind)` from `inventory/utils_verticals.py`
   - Adds `sidebar_items` to template context

2. **Sidebar Template** (`templates/partials/sidebar.html`):
   - Receives `sidebar_items` from context
   - Groups items by section (MAIN, TIME, MONEY, BUSINESS, LAYBY)
   - Renders each section with appropriate items
   - Handles manager-only items with `require_manager` flag
   - Special handling: For gym, "Agents" label becomes "Trainers"

3. **URL Resolution**:
   - Django's `{% url %}` tag resolves the named routes
   - Falls back to raw URLs if named route doesn't exist

---

## Testing Results

All tests passed successfully:

✓ **URL Resolution** - All new vertical URLs resolve correctly  
✓ **Phones Sidebar** - Contains inventory items, excludes vertical items  
✓ **Gym Sidebar** - Contains gym items, excludes phones items  
✓ **Clothing Sidebar** - Contains clothing items, excludes phones items  
✓ **Liquor Sidebar** - Contains liquor items, excludes phones items  
✓ **Pharmacy Sidebar** - Contains pharmacy items, excludes phones items  
✓ **Legacy Redirects** - Old URLs redirect to new canonical URLs  
✓ **Utility Functions** - All helper functions return correct values  

---

## Migration Guide

### For Template Authors

**Old:**
```django
{% url 'inventory_verticals:gym_dashboard' %}
```

**New:**
```django
{% url 'verticals:gym_dashboard' %}
```

**Both work** - the old URL redirects to the new one.

### For View Authors

**Old:**
```python
return redirect('inventory_verticals:gym_dashboard')
```

**New:**
```python
return redirect('verticals:gym_dashboard')
```

### For Test Authors

When testing vertical dashboards:
- Phones: Test `/inventory/dashboard/`
- Verticals: Test `/verticals/<slug>/dashboard/`

---

## Key Files Modified

1. `verticals/urls.py` - NEW canonical vertical URLs
2. `verticals/__init__.py` - NEW package initialization
3. `cc/urls.py` - Include new verticals URLs at root level
4. `inventory/urls_verticals.py` - Updated to redirect legacy URLs
5. `inventory/utils_verticals.py` - Updated namespace references
6. `inventory/views_dispatch.py` - Updated dispatcher routes
7. `tests/test_vertical_url_routing.py` - NEW comprehensive tests

---

## Summary

✅ **Phones remain at `/inventory/...`** - They are not a vertical  
✅ **Verticals now at `/verticals/<slug>/...`** - Clean, standardized structure  
✅ **Legacy URLs still work** - Backward compatibility via 302 redirects  
✅ **Sidebar is vertical-aware** - Shows correct items per business type  
✅ **Fully tested** - 25+ tests ensure nothing breaks  

The implementation maintains full backward compatibility while providing a cleaner, more maintainable URL structure for the future.

