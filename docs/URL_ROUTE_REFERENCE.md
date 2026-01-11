# Quick Reference: URL Route Names

## Global Aliases (Work Without Namespace)

These routes can be used with just `reverse('name')` without namespace prefixes:

| Alias Name | Resolves To | Example |
|------------|-------------|---------|
| `home` | `/home/` (canonical) | `reverse('home')` or `{% url 'home' %}` |
| `stock` | Redirects to `inventory:stock_list` | `reverse('stock')` or `{% url 'stock' %}` |
| `wallet` | Redirects to `wallet:agent_wallet` | `reverse('wallet')` or `{% url 'wallet' %}` |
| `sim` | Redirects to `simulator:home` | `reverse('sim')` or `{% url 'sim' %}` |
| `businesses` | Redirects to `hq:business_directory` | `reverse('businesses')` or `{% url 'businesses' %}` |

## Canonical Namespaced Routes (Recommended)

For better clarity and to avoid naming conflicts, prefer using namespaced routes:

### Dashboard
- `dashboard:home` → `/dashboard/`
- `dashboard:dashboard_home` → `/dashboard/home/` (alias)

### Inventory
- `inventory:stock_list` → `/inventory/list/`
- `inventory:scan_in` → `/inventory/scan-in/`
- `inventory:scan_sold` → `/inventory/scan-sold/`

### Wallet
- `wallet:agent_wallet` → `/wallet/`
- `wallet:admin_home` → `/wallet/admin/`

### Simulator
- `simulator:home` → `/simulator/`
- `simulator:business_home` → `/simulator/business/`

### HQ (Staff/Platform Admin)
- `hq:dashboard` → `/hq/dashboard/`
- `hq:home` → `/hq/home/` (alias to dashboard)
- `hq:business_directory` → `/hq/businesses/`
- `hq:subscriptions` → `/hq/subscriptions/`
- `hq:invoices` → `/hq/invoices/`
- `hq:agents` → `/hq/agents/`

## Vertical Business Types

### inventory_verticals Namespace

All vertical dashboards are accessible via the `inventory_verticals:` namespace:

- `inventory_verticals:phones_dashboard` → `/inventory/verticals/phones/`
- `inventory_verticals:gym_dashboard` → `/inventory/verticals/gym/` (redirects to new location)
- `inventory_verticals:clothing_dashboard` → `/inventory/verticals/clothing/` (redirects)
- `inventory_verticals:liquor_dashboard` → `/inventory/verticals/liquor/` (redirects)
- `inventory_verticals:pharmacy_dashboard` → `/inventory/verticals/pharmacy/` (redirects)

### verticals Namespace (New Canonical)

New canonical location for vertical dashboards:

- `verticals:gym_dashboard` → `/verticals/gym/dashboard/`
- `verticals:clothing_dashboard` → `/verticals/clothing/dashboard/`
- `verticals:liquor_dashboard` → `/verticals/liquor/dashboard/`
- `verticals:pharmacy_dashboard` → `/verticals/pharmacy/dashboard/`

## Usage Guidelines

### In Templates

```django
{# Preferred: Use namespaced routes for clarity #}
{% url 'dashboard:home' %}
{% url 'inventory:stock_list' %}
{% url 'wallet:agent_wallet' %}

{# Acceptable: Use global aliases for common routes #}
{% url 'home' %}
{% url 'stock' %}
{% url 'wallet' %}

{# Vertical dashboards #}
{% url 'inventory_verticals:phones_dashboard' %}
{% url 'verticals:gym_dashboard' %}  {# New canonical #}
```

### In Python Views/Code

```python
from django.urls import reverse
from django.shortcuts import redirect

# Preferred: Namespaced routes
def my_view(request):
    return redirect(reverse('dashboard:home'))
    
def stock_view(request):
    url = reverse('inventory:stock_list')
    return redirect(url)

# Acceptable: Global aliases
def quick_redirect(request):
    return redirect(reverse('home'))
```

## Migration Guide

If you have code using the following patterns, no changes are needed:

✅ **Already Working:**
- `reverse('home')` ← was always working, still works
- `reverse('dashboard:home')` ← canonical, preferred
- `reverse('inventory_verticals:phones_dashboard')` ← now works correctly

✅ **Now Fixed (Previously Broken):**
- `reverse('stock')` ← now works (was NoReverseMatch before)
- `reverse('wallet')` ← now works
- `reverse('sim')` ← now works
- `reverse('businesses')` ← now works
- `reverse('inventory_verticals:gym_dashboard')` ← namespace now properly registered

## Troubleshooting

### NoReverseMatch Error?

1. Check if you're using the correct namespace:
   - ✅ `reverse('inventory:stock_list')` 
   - ❌ `reverse('stock_list')` (unless it's a global alias)

2. For vertical dashboards, use the proper namespace:
   - ✅ `reverse('inventory_verticals:phones_dashboard')`
   - ❌ `reverse('phones_dashboard')`

3. For HQ routes, always use the `hq:` namespace:
   - ✅ `reverse('hq:business_directory')` or `reverse('businesses')`
   - ❌ `reverse('business_directory')` (unless using global alias)

### Redirect vs Direct Route?

Global aliases use `/__alias__/` paths that redirect to canonical routes:
- `reverse('stock')` → `/__alias__/stock/` → redirects to `/inventory/list/`
- `reverse('wallet')` → `/__alias__/wallet/` → redirects to `/wallet/`

If you want to avoid the redirect, use the canonical namespaced route directly:
- `reverse('inventory:stock_list')` → `/inventory/list/` (direct)
- `reverse('wallet:agent_wallet')` → `/wallet/` (direct)

## Testing URL Resolution

Quick test in Django shell:

```python
python manage.py shell

from django.urls import reverse

# Test global aliases
print(reverse('home'))          # /home/
print(reverse('stock'))         # /__alias__/stock/
print(reverse('wallet'))        # /__alias__/wallet/

# Test canonical routes
print(reverse('dashboard:home'))           # /dashboard/
print(reverse('inventory:stock_list'))     # /inventory/list/
print(reverse('hq:business_directory'))    # /hq/businesses/

# Test vertical namespaces
print(reverse('inventory_verticals:phones_dashboard'))  # /inventory/verticals/phones/
print(reverse('verticals:gym_dashboard'))               # /verticals/gym/dashboard/
```

