# inventory/utils_verticals.py
"""
Vertical-specific routing and configuration utilities.
Ensures business-kind-aware dashboards, navigation, and onboarding flows.
"""
from __future__ import annotations
from typing import Optional, Dict, List, Tuple

try:
    from inventory.business_kinds import BusinessKind
except ImportError:
    # Fallback if business_kinds isn't available
    class BusinessKind:
        PHONES = "phones"
        LIQUOR = "liquor"
        GROCERY = "grocery"
        PHARMACY = "pharmacy"
        CLOTHING = "clothing"
        GYM = "gym"


def get_vertical_kind(business) -> str:
    """
    Returns a normalized vertical code for the given business.
    
    Args:
        business: Business model instance (or None)
    
    Returns:
        str: One of "phones", "gym", "clothing", "liquor", "pharmacy", "grocery", or "generic"
    """
    if business is None:
        return "generic"
    
    kind = getattr(business, "business_kind", None)
    if not kind:
        return "phones"  # Default to phones for legacy businesses
    
    # Normalize to lowercase string
    if hasattr(kind, "value"):
        kind = kind.value
    kind = str(kind).strip().lower()
    
    # Map to known verticals
    valid_kinds = ["phones", "gym", "clothing", "liquor", "pharmacy", "grocery"]
    if kind in valid_kinds:
        return kind
    
    return "phones"  # Fallback


def get_vertical_dashboard_url(vertical_kind: str) -> Optional[str]:
    """
    Returns the named URL for a vertical-specific dashboard.
    
    Args:
        vertical_kind: Vertical code (e.g., "gym", "pharmacy")
    
    Returns:
        str: URL name to redirect to, or None if default dashboard should be used
    """
    vertical_dashboard_map = {
        "gym": "inventory_verticals:gym_dashboard",
        "pharmacy": "inventory_verticals:pharmacy_dashboard",
        "clothing": "inventory_verticals:clothing_dashboard",
        "liquor": "inventory_verticals:liquor_dashboard",
        # "phones" uses the default dashboard
        # "grocery" uses default dashboard (for now)
    }
    return vertical_dashboard_map.get(vertical_kind)


def get_onboarding_steps(vertical_kind: str, request=None) -> List[Dict[str, str]]:
    """
    Returns onboarding steps tailored to the business vertical.
    
    Args:
        vertical_kind: Vertical code (e.g., "gym", "pharmacy")
        request: Optional HttpRequest for URL resolution
    
    Returns:
        List of dicts with keys: 'number', 'label', 'url', 'icon'
    """
    # Helper to safely resolve URLs
    def safe_url(name: str, fallback: str = "#") -> str:
        if request is None:
            return fallback
        try:
            from django.urls import reverse
            return reverse(name)
        except Exception:
            return fallback
    
    if vertical_kind == "gym":
        return [
            {
                "number": "1",
                "label": "Add membership plans",
                "url": safe_url("inventory:gym_plans", "/inventory/gym/plans/"),
                "icon": "bi-calendar-check"
            },
            {
                "number": "2",
                "label": "Add your first members",
                "url": safe_url("inventory:gym_members", "/inventory/gym/members/"),
                "icon": "bi-people"
            },
            {
                "number": "3",
                "label": "Track payments & arrears",
                "url": safe_url("inventory:gym_dashboard", "/inventory/gym/dashboard/"),
                "icon": "bi-wallet2"
            },
        ]
    
    elif vertical_kind == "clothing":
        return [
            {
                "number": "1",
                "label": "Add clothing products",
                "url": safe_url("inventory:clothing_product_new", "/inventory/clothing/products/new/"),
                "icon": "bi-bag"
            },
            {
                "number": "2",
                "label": "Set up sizes & colors",
                "url": safe_url("inventory:clothing_stock_list", "/inventory/clothing/stock/"),
                "icon": "bi-palette"
            },
            {
                "number": "3",
                "label": "Start selling",
                "url": safe_url("inventory:clothing_sell", "/inventory/clothing/sell/"),
                "icon": "bi-cart-check"
            },
        ]
    
    elif vertical_kind == "liquor":
        return [
            {
                "number": "1",
                "label": "Add liquor products",
                "url": safe_url("inventory:liquor_product_new", "/inventory/liquor/products/new/"),
                "icon": "bi-cup-straw"
            },
            {
                "number": "2",
                "label": "Stock in inventory",
                "url": safe_url("inventory:liquor_stock_list", "/inventory/liquor/stock/"),
                "icon": "bi-boxes"
            },
            {
                "number": "3",
                "label": "Record sales",
                "url": safe_url("inventory:liquor_sell", "/inventory/liquor/sell/"),
                "icon": "bi-receipt"
            },
        ]
    
    elif vertical_kind == "pharmacy":
        return [
            {
                "number": "1",
                "label": "Create products & batches",
                "url": safe_url("inventory:pharmacy_product_new", "/inventory/pharmacy/products/new/"),
                "icon": "bi-capsule"
            },
            {
                "number": "2",
                "label": "Set expiry & reorder levels",
                "url": safe_url("inventory:pharmacy_batches", "/inventory/pharmacy/batches/"),
                "icon": "bi-calendar-event"
            },
            {
                "number": "3",
                "label": "Track sales & alerts",
                "url": safe_url("inventory:pharmacy_dashboard", "/inventory/pharmacy/dashboard/"),
                "icon": "bi-graph-up"
            },
        ]
    
    else:  # "phones" or default
        return [
            {
                "number": "1",
                "label": "Add your first product",
                "url": safe_url("inventory:product_new", "/inventory/products/new/"),
                "icon": "bi-phone"
            },
            {
                "number": "2",
                "label": "Stock in items",
                "url": safe_url("inventory:scan_in", "/inventory/scan-in/"),
                "icon": "bi-upc-scan"
            },
            {
                "number": "3",
                "label": "Invite/approve agents",
                "url": safe_url("tenants:manager_review_agents", "/tenants/manager/agents/"),
                "icon": "bi-people"
            },
        ]


def get_vertical_display_name(vertical_kind: str) -> str:
    """Returns human-friendly display name for a vertical."""
    display_names = {
        "phones": "Phones & Electronics",
        "gym": "Gym & Fitness",
        "clothing": "Clothing Store",
        "liquor": "Liquor Store",
        "pharmacy": "Pharmacy",
        "grocery": "Grocery Store",
        "generic": "Business",
    }
    return display_names.get(vertical_kind, vertical_kind.title())


__all__ = [
    "get_vertical_kind",
    "get_vertical_dashboard_url",
    "get_onboarding_steps",
    "get_vertical_display_name",
]

