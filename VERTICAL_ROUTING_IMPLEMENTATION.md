# Business-Kind-Aware Dashboard Routing Implementation

## Summary

Successfully implemented business-kind-aware dashboard routing to ensure that users are directed to the correct vertical-specific dashboard based on their business type (Gym, Clothing, Liquor, Pharmacy, or Phones).

## Problem

When a new business signed up as a **Gym**, the main dashboard still looked like the phones vertical:
- Left nav showed: Dashboard, Inventory Dashboard, Stock, Scan IN, Sell, etc.
- Welcome card said "Add your first product / stock in items / invite agents"
- This was acceptable for phones, but NOT for Gym, Clothing, Liquor, or Pharmacy

## Solution

Made the app **strictly business-kind aware** by:
1. Creating a centralized vertical routing utility
2. Updating the main dashboard to redirect based on business kind
3. Making onboarding steps dynamic per business type
4. Fixing URL namespace registration

---

## Files Created

### 1. `inventory/utils_verticals.py`
Central utility module for vertical-specific logic:

**Functions:**
- `get_vertical_kind(business)` - Returns normalized vertical code ("phones", "gym", "clothing", "liquor", "pharmacy", "grocery")
- `get_vertical_dashboard_url(vertical_kind)` - Maps vertical to dashboard URL name
- `get_onboarding_steps(vertical_kind, request)` - Returns tailored onboarding steps for each vertical
- `get_vertical_display_name(vertical_kind)` - Returns human-friendly name

### 2. `tests/test_vertical_routing.py`
Comprehensive test suite (22 tests, all passing):

**Test Coverage:**
- Utility function tests (vertical detection, URL mapping, onboarding steps)
- Dashboard routing tests (redirects for gym/clothing/liquor/pharmacy, default for phones)
- Onboarding step tests (business-kind-aware welcome flows)
- Integration tests (full signup and navigation flows)
- Edge cases (legacy businesses without kind, grocery fallback)

---

## Files Modified

### 1. `dashboard/views.py`
**Changes:**
- Added import: `from inventory.utils_verticals import get_vertical_kind, get_vertical_dashboard_url, get_onboarding_steps`
- Updated `home()` view to:
  - Detect business vertical using `get_vertical_kind(biz)`
  - Redirect to vertical-specific dashboard if available
  - Pass `vertical_kind` and `onboarding_steps` to template context

**Code Added:**
```python
# ==============================================================================
# VERTICAL ROUTING: Redirect to vertical-specific dashboards
# ==============================================================================
vertical_kind = get_vertical_kind(biz)
vertical_dashboard_url = get_vertical_dashboard_url(vertical_kind)

if vertical_dashboard_url:
    # Redirect to vertical-specific dashboard (gym, pharmacy, clothing, liquor)
    try:
        return redirect(vertical_dashboard_url)
    except NoReverseMatch:
        # If the URL doesn't exist, fall through to default dashboard
        pass

# Onboarding steps tailored to business vertical
onboarding_steps = get_onboarding_steps(vertical_kind, request)
```

### 2. `templates/dashboard/home.html`
**Changes:**
- Made the "Welcome to X" card business-kind aware
- Replaced hardcoded onboarding steps with dynamic `onboarding_steps` loop
- Added vertical-specific messaging

**Before:**
```django
<a class="btn btn-primary w-100" href="...">1) Add your first product</a>
<a class="btn btn-outline-primary w-100" href="...">2) Stock in items</a>
<a class="btn btn-outline-primary w-100" href="...">3) Invite/approve agents</a>
```

**After:**
```django
{% for step in onboarding_steps %}
<a class="btn {% if step.number == '1' %}btn-primary{% else %}btn-outline-primary{% endif %} w-100" 
   href="{{ step.url }}">
  <i class="bi {{ step.icon }}"></i> {{ step.number }}) {{ step.label }}
</a>
{% endfor %}
```

### 3. `cc/urls.py`
**Changes:**
- Added direct inclusion of vertical URLs at root level to ensure namespace registration

**Code Added:**
```python
path("inventory/verticals/", include_or_raise("inventory.urls_verticals", "inventory_verticals")),
```

**Why:** Django doesn't automatically nest namespaces when including URLs within other URL files. By including `urls_verticals` directly in the root URL configuration with an explicit namespace, the `inventory_verticals:` namespace is properly registered.

### 4. `inventory/urls.py`
**Changes:**
- Removed nested inclusion of `urls_verticals` (moved to root `cc/urls.py`)
- Added comment explaining the change

**Before:**
```python
urlpatterns += [
    path("verticals/", include("inventory.urls_verticals")),
]
```

**After:**
```python
# Vertical dashboards are now included directly in cc/urls.py at the root level
# to ensure the namespace is properly registered
```

---

## Behavior

### Routing Logic

| Business Kind | Dashboard Behavior |
|--------------|-------------------|
| **Phones** (or none) | Shows default dashboard with stock/scan/sell |
| **Gym** | Redirects to `/inventory/verticals/gym/` |
| **Clothing** | Redirects to `/inventory/verticals/clothing/` |
| **Liquor** | Redirects to `/inventory/verticals/liquor/` |
| **Pharmacy** | Redirects to `/inventory/verticals/pharmacy/` |
| **Grocery** | Shows default dashboard (vertical not yet implemented) |

### Onboarding Steps

#### Phones (Default)
1. Add your first product
2. Stock in items
3. Invite/approve agents

#### Gym
1. Add membership plans
2. Add your first members
3. Track payments & arrears

#### Clothing
1. Add clothing products
2. Set up sizes & colors
3. Start selling

#### Liquor
1. Add liquor products
2. Stock in inventory
3. Record sales

#### Pharmacy
1. Create products & batches
2. Set expiry & reorder levels
3. Track sales & alerts

---

## Navigation

The sidebar (`templates/partials/sidebar.html`) already had vertical-aware logic that checks `BUSINESS_VERTICAL`:

```django
{% if vertical == 'gym' %}
  <!-- Gym-specific menu items -->
{% else %}
  <!-- Phones menu items (Stock, Scan IN, Sell) -->
{% endif %}
```

This existing logic now works correctly with the new routing because:
1. The `BUSINESS_VERTICAL` context variable is set by `inventory/context_processors.py`
2. Vertical users are redirected to their specific dashboards
3. The sidebar shows relevant menu items for each vertical

---

## Testing

### Test Results
```
tests/test_vertical_routing.py ...................... [ 100%]
====================== 22 passed, 21 warnings in 20.16s =======================
```

### Key Test Cases
✅ Phone business shows default dashboard  
✅ Gym business redirects to gym dashboard  
✅ Clothing business redirects to clothing dashboard  
✅ Liquor business redirects to liquor dashboard  
✅ Pharmacy business redirects to pharmacy dashboard  
✅ Onboarding steps are tailored to business kind  
✅ Legacy businesses without kind default to phones  
✅ Grocery business uses default dashboard (not yet implemented)  

---

## Constraints Met

✅ **Did NOT remove any existing vertical functionality**  
✅ **Additive changes only** - no models or views removed  
✅ **Business kind determined from `active_business.kind`** - no hardcoded IDs  
✅ **Signup wizard not broken** - routing happens after business is created  
✅ **Existing phone shops still work** - default dashboard for phones/legacy  
✅ **All vertical tests still pass** - no regressions in vertical-specific logic  

---

## URL Structure

```
/dashboard/                                    → Main dashboard (routes based on business kind)
/inventory/verticals/gym/                      → Gym-specific dashboard
/inventory/verticals/clothing/                 → Clothing-specific dashboard
/inventory/verticals/liquor/                   → Liquor-specific dashboard
/inventory/verticals/pharmacy/                 → Pharmacy-specific dashboard
```

**URL Names:**
- `dashboard:home` - Main dashboard entry point (smart routing)
- `inventory_verticals:gym_dashboard` - Gym dashboard
- `inventory_verticals:clothing_dashboard` - Clothing dashboard
- `inventory_verticals:liquor_dashboard` - Liquor dashboard
- `inventory_verticals:pharmacy_dashboard` - Pharmacy dashboard

---

## How to Test

### 1. Create a Gym Business
```python
from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.create_user(username="gym_manager", email="gym@test.com", password="test123")
gym = Business.objects.create(name="Test Gym", slug="test-gym", business_kind=BusinessKind.GYM, status="ACTIVE")
Membership.objects.create(user=user, business=gym, role="MANAGER", status="ACTIVE")
```

### 2. Log in and navigate to `/dashboard/`
- Should automatically redirect to `/inventory/verticals/gym/`
- Sidebar should show gym-specific menu items (Members, Attendance, Wallet)
- No "Stock", "Scan IN", or "Sell" menu items

### 3. Create a Phones Business
```python
phones = Business.objects.create(name="Phone Shop", slug="phone-shop", business_kind=BusinessKind.PHONES, status="ACTIVE")
Membership.objects.create(user=user, business=phones, role="MANAGER", status="ACTIVE")
```

### 4. Log in and navigate to `/dashboard/`
- Should stay on default dashboard (no redirect)
- Sidebar should show: "Inventory Dashboard", "Stock", "Scan IN", "Sell"
- Welcome card shows: "Add your first product", "Stock in items", "Invite/approve agents"

---

## Future Enhancements

1. **Grocery vertical**: Implement grocery-specific dashboard and routing
2. **Dashboard customization**: Allow businesses to customize their dashboard layout
3. **Multi-vertical support**: Allow a single business to operate multiple verticals
4. **Vertical-specific permissions**: Fine-grained access control per vertical

---

## Summary of Changes

| Component | What Changed | Why |
|-----------|-------------|-----|
| `inventory/utils_verticals.py` | Created | Centralize vertical routing logic |
| `dashboard/views.py` | Modified `home()` | Add vertical routing and dynamic onboarding |
| `templates/dashboard/home.html` | Updated welcome card | Make onboarding steps business-kind aware |
| `cc/urls.py` | Added verticals include | Fix namespace registration |
| `inventory/urls.py` | Removed nested include | Prevent namespace conflict |
| `tests/test_vertical_routing.py` | Created | Ensure routing works correctly |

**Lines of Code:**
- Added: ~550 lines (utils + tests)
- Modified: ~30 lines (views + templates + URLs)
- **Total impact:** Minimal, focused changes

**Test Coverage:** 22 new tests, all passing ✅

