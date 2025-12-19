"""
Vertical isolation utilities - Single source of truth for vertical routing & guards.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.http import Http404


# Vertical aliases and normalization
VERTICAL_ALIASES = {
    'groceries': 'grocery',
    'electronics': 'phones',
}

# Map each vertical to its home dashboard URL name
VERTICAL_DASHBOARDS = {
    'phones': 'verticals:phones_dashboard',
    'grocery': 'verticals:grocery_dashboard',
    'hardware': 'verticals:hardware_dashboard',
    'cement': 'verticals:cement_dashboard',
    'liquor': 'verticals:liquor_dashboard',
    'pharmacy': 'verticals:pharmacy_dashboard',
    'clothing': 'verticals:clothing_dashboard',
    'gym': 'verticals:gym_dashboard',
    'cosmetics': 'inventory:dashboard',  # No cosmetics vertical yet, use default
}

# Navigation items per vertical
VERTICAL_NAV_CONFIG = {
    'phones': [
        {'icon': 'fa-tachometer-alt', 'label': 'Dashboard', 'url': 'inventory:dashboard'},
        {'icon': 'fa-barcode', 'label': 'Scan IMEI', 'url': 'inventory:scan_imei'},
        {'icon': 'fa-box-open', 'label': 'Scan IN', 'url': 'inventory:scan_in'},
        {'icon': 'fa-cash-register', 'label': 'Scan & Sell', 'url': 'inventory:scan_sell'},
        {'icon': 'fa-boxes', 'label': 'Inventory', 'url': 'inventory:list'},
        {'icon': 'fa-chart-line', 'label': 'Sales', 'url': 'inventory:sales_list'},
        {'icon': 'fa-shopping-cart', 'label': 'Quick Sell', 'url': 'inventory:quick_sell'},
    ],
    'grocery': [
        {'icon': 'fa-tachometer-alt', 'label': 'Dashboard', 'url': 'inventory:grocery_dashboard'},
        {'icon': 'fa-boxes', 'label': 'Products', 'url': 'inventory:grocery_products'},
        {'icon': 'fa-box-open', 'label': 'Stock In', 'url': 'inventory:grocery_stock_in'},
        {'icon': 'fa-cash-register', 'label': 'Sales', 'url': 'inventory:grocery_sales'},
        {'icon': 'fa-chart-line', 'label': 'Reports', 'url': 'inventory:grocery_reports'},
    ],
    'hardware': [
        {'icon': 'fa-tachometer-alt', 'label': 'Dashboard', 'url': 'inventory:hardware_dashboard'},
        {'icon': 'fa-boxes', 'label': 'Products', 'url': 'inventory:hardware_products'},
        {'icon': 'fa-box-open', 'label': 'Stock In', 'url': 'inventory:hardware_stock_in'},
        {'icon': 'fa-cash-register', 'label': 'Sales', 'url': 'inventory:hardware_sales'},
        {'icon': 'fa-chart-line', 'label': 'Reports', 'url': 'inventory:hardware_reports'},
    ],
    'cement': [
        {'icon': 'fa-tachometer-alt', 'label': 'Dashboard', 'url': 'inventory:cement_dashboard'},
        {'icon': 'fa-boxes', 'label': 'Products', 'url': 'inventory:cement_products'},
        {'icon': 'fa-box-open', 'label': 'Stock In', 'url': 'inventory:cement_stock_in'},
        {'icon': 'fa-cash-register', 'label': 'Sales', 'url': 'inventory:cement_sales'},
        {'icon': 'fa-chart-line', 'label': 'Reports', 'url': 'inventory:cement_reports'},
    ],
}

# Default nav for verticals not yet configured
DEFAULT_VERTICAL_NAV = [
    {'icon': 'fa-tachometer-alt', 'label': 'Dashboard', 'url': 'inventory:dashboard'},
    {'icon': 'fa-boxes', 'label': 'Inventory', 'url': 'inventory:list'},
    {'icon': 'fa-chart-line', 'label': 'Sales', 'url': 'inventory:sales_list'},
]


def normalize_vertical(value):
    """
    Normalize vertical name: lowercase, strip, apply aliases.
    
    Args:
        value: Raw vertical string (e.g., 'GROCERY', 'Groceries', 'grocery')
    
    Returns:
        Normalized vertical string (e.g., 'grocery')
    """
    if not value:
        return None
    
    normalized = str(value).lower().strip()
    return VERTICAL_ALIASES.get(normalized, normalized)


def get_active_vertical(request):
    """
    Get the active business vertical from the request.
    
    Args:
        request: Django request object with active_business set by middleware
    
    Returns:
        Normalized vertical string (e.g., 'grocery', 'phones') or None
    """
    if not hasattr(request, 'active_business') or not request.active_business:
        return None
    
    business_kind = getattr(request.active_business, 'business_kind', None)
    return normalize_vertical(business_kind)


def vertical_home_url(vertical):
    """
    Get the home dashboard URL name for a given vertical.
    
    Args:
        vertical: Normalized vertical string
    
    Returns:
        URL name string (e.g., 'inventory:grocery_dashboard')
    """
    normalized = normalize_vertical(vertical)
    return VERTICAL_DASHBOARDS.get(normalized, 'inventory:dashboard')


def vertical_nav_items(vertical):
    """
    Get navigation menu items for a given vertical.
    
    Args:
        vertical: Normalized vertical string
    
    Returns:
        List of nav item dicts with 'icon', 'label', 'url' keys
    """
    normalized = normalize_vertical(vertical)
    return VERTICAL_NAV_CONFIG.get(normalized, DEFAULT_VERTICAL_NAV)


def require_vertical(*allowed_verticals, redirect_to_home=True, raise_404=False):
    """
    Decorator to restrict view access to specific verticals.
    
    Usage:
        @require_vertical('phones')
        def scan_imei_view(request):
            # Only accessible to phones vertical
            pass
        
        @require_vertical('grocery', 'hardware', 'cement')
        def sku_products_view(request):
            # Accessible to SKU-based verticals
            pass
    
    Args:
        *allowed_verticals: Vertical names that can access this view
        redirect_to_home: If True, redirect to business home; if False, raise 404
        raise_404: If True, raise 404 instead of redirect (overrides redirect_to_home)
    
    Returns:
        Decorator function
    """
    # Normalize allowed verticals
    normalized_allowed = [normalize_vertical(v) for v in allowed_verticals]
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            active_vertical = get_active_vertical(request)
            
            # No active business/vertical
            if not active_vertical:
                if raise_404:
                    raise Http404("No active business selected")
                messages.warning(request, "Please select or activate a business first.")
                # Redirect to tenant chooser (avoid onboarding namespace)
                try:
                    return redirect('tenants:choose_business')
                except:
                    return redirect('/tenants/join/')
            
            # Check if vertical is allowed
            if active_vertical not in normalized_allowed:
                if raise_404:
                    raise Http404("This feature is not available for your business type")
                
                # Just raise 404 to avoid redirect loops
                # (Previously this would redirect to home, causing loops)
                raise Http404("This feature is not available for your business type")
            
            # All good, proceed
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def get_vertical_context(request):
    """
    Get vertical-specific context for templates.
    
    Args:
        request: Django request object
    
    Returns:
        Dict with vertical info for template context
    """
    vertical = get_active_vertical(request)
    
    return {
        'active_vertical': vertical,
        'vertical_nav_items': vertical_nav_items(vertical) if vertical else [],
        'vertical_home_url': vertical_home_url(vertical) if vertical else None,
        'is_phones_vertical': vertical == 'phones',
        'is_sku_vertical': vertical in ('grocery', 'hardware', 'cement'),
    }

