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


def get_vertical_sidebar_items(business_kind: str) -> list[dict]:
    """
    Returns a list of sidebar navigation items for the given business kind.
    
    Each item is a dict with keys:
        - section: str (e.g., "MAIN", "TIME", "MONEY", "BUSINESS", "LAYBY")
        - url: str (URL or named route)
        - label: str (display label)
        - icon: str (Bootstrap icon class, e.g., "bi-speedometer2")
        - active_pattern: str (optional, for path matching)
    
    Args:
        business_kind: Vertical code (e.g., "phones", "gym", "clothing", "liquor", "pharmacy")
    
    Returns:
        List of nav items organized by section
    """
    if business_kind == "gym":
        return [
            # MAIN section
            {"section": "MAIN", "url": "dashboard:home", "label": "Dashboard", "icon": "bi-speedometer2", "active_pattern": "/dashboard/"},
            {"section": "MAIN", "url": "inventory_verticals:gym_dashboard", "label": "Gym Hub", "icon": "bi-activity", "active_pattern": "/verticals/gym/"},
            {"section": "MAIN", "url": "tenants:manager_review_agents", "label": "Members", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/"},
            {"section": "MAIN", "url": "inventory:time_logs", "label": "Check-ins", "icon": "bi-clipboard-check", "active_pattern": "/inventory/time"},
            {"section": "MAIN", "url": "wallet:agent_wallet", "label": "Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            
            # TIME section
            {"section": "TIME", "url": "inventory:time_logs", "label": "Time Logs", "icon": "bi-journal-text", "active_pattern": "/inventory/time/logs"},
            
            # MONEY section (for managers)
            {"section": "MONEY", "url": "wallet:agent_wallet", "label": "My Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            {"section": "MONEY", "url": "wallet:admin_home", "label": "Admin Wallet", "icon": "bi-briefcase", "active_pattern": "/wallet/admin/", "require_manager": True},
            
            # BUSINESS section (for managers)
            {"section": "BUSINESS", "url": "tenants:manager_review_agents", "label": "Trainers", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_locations", "label": "Locations", "icon": "bi-geo", "active_pattern": "/tenants/manager/locations/", "require_manager": True},
            {"section": "BUSINESS", "url": "billing:plans", "label": "Choose Plan", "icon": "bi-credit-card-2-front", "active_pattern": "/billing/plans", "require_manager": True},
        ]
    
    elif business_kind == "clothing":
        return [
            # MAIN section
            {"section": "MAIN", "url": "dashboard:home", "label": "Dashboard", "icon": "bi-speedometer2", "active_pattern": "/dashboard/"},
            {"section": "MAIN", "url": "inventory_verticals:clothing_dashboard", "label": "Clothing Hub", "icon": "bi-person-bounding-box", "active_pattern": "/verticals/clothing/"},
            {"section": "MAIN", "url": "inventory:clothing_product_new_v2", "label": "Add Product", "icon": "bi-plus-square", "active_pattern": "/clothing/products/new"},
            {"section": "MAIN", "url": "inventory:scan_in", "label": "Stock In", "icon": "bi-upc-scan", "active_pattern": "/inventory/scan"},
            {"section": "MAIN", "url": "inventory:scan_sold", "label": "Sell", "icon": "bi-bag-check", "active_pattern": "/sell/"},
            
            # TIME section
            {"section": "TIME", "url": "inventory:time_logs", "label": "Time Logs", "icon": "bi-journal-text", "active_pattern": "/inventory/time/logs"},
            
            # MONEY section
            {"section": "MONEY", "url": "wallet:agent_wallet", "label": "My Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            {"section": "MONEY", "url": "wallet:admin_home", "label": "Admin Wallet", "icon": "bi-briefcase", "active_pattern": "/wallet/admin/", "require_manager": True},
            
            # BUSINESS section (for managers)
            {"section": "BUSINESS", "url": "tenants:manager_review_agents", "label": "Agents", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_locations", "label": "Locations", "icon": "bi-geo", "active_pattern": "/tenants/manager/locations/", "require_manager": True},
            {"section": "BUSINESS", "url": "billing:plans", "label": "Choose Plan", "icon": "bi-credit-card-2-front", "active_pattern": "/billing/plans", "require_manager": True},
            {"section": "BUSINESS", "url": "inventory:orders_list", "label": "Orders", "icon": "bi-clipboard-data", "active_pattern": "/inventory/orders/", "require_manager": True},
        ]
    
    elif business_kind == "liquor":
        return [
            # MAIN section
            {"section": "MAIN", "url": "dashboard:home", "label": "Dashboard", "icon": "bi-speedometer2", "active_pattern": "/dashboard/"},
            {"section": "MAIN", "url": "inventory_verticals:liquor_dashboard", "label": "Liquor Hub", "icon": "bi-cup-straw", "active_pattern": "/verticals/liquor/"},
            {"section": "MAIN", "url": "inventory:liquor_product_new_v2", "label": "Add Product", "icon": "bi-droplet-half", "active_pattern": "/liquor/products/new"},
            {"section": "MAIN", "url": "inventory:scan_in", "label": "Stock In", "icon": "bi-upc-scan", "active_pattern": "/inventory/scan"},
            {"section": "MAIN", "url": "inventory:scan_sold", "label": "Sell", "icon": "bi-lightning-charge", "active_pattern": "/sell/"},
            
            # TIME section
            {"section": "TIME", "url": "inventory:time_logs", "label": "Time Logs", "icon": "bi-journal-text", "active_pattern": "/inventory/time/logs"},
            
            # MONEY section
            {"section": "MONEY", "url": "wallet:agent_wallet", "label": "My Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            {"section": "MONEY", "url": "wallet:admin_home", "label": "Admin Wallet", "icon": "bi-briefcase", "active_pattern": "/wallet/admin/", "require_manager": True},
            
            # BUSINESS section (for managers)
            {"section": "BUSINESS", "url": "tenants:manager_review_agents", "label": "Agents", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_locations", "label": "Locations", "icon": "bi-geo", "active_pattern": "/tenants/manager/locations/", "require_manager": True},
            {"section": "BUSINESS", "url": "billing:plans", "label": "Choose Plan", "icon": "bi-credit-card-2-front", "active_pattern": "/billing/plans", "require_manager": True},
        ]
    
    elif business_kind == "pharmacy":
        return [
            # MAIN section
            {"section": "MAIN", "url": "dashboard:home", "label": "Dashboard", "icon": "bi-speedometer2", "active_pattern": "/dashboard/"},
            {"section": "MAIN", "url": "inventory_verticals:pharmacy_dashboard", "label": "Pharmacy Hub", "icon": "bi-prescription2", "active_pattern": "/verticals/pharmacy/"},
            {"section": "MAIN", "url": "inventory:pharmacy_product_new", "label": "Add Medicine", "icon": "bi-capsule", "active_pattern": "/pharmacy/products/new"},
            {"section": "MAIN", "url": "inventory:pharmacy_batches", "label": "Batches", "icon": "bi-boxes", "active_pattern": "/pharmacy/batches"},
            {"section": "MAIN", "url": "inventory:scan_in", "label": "Stock In", "icon": "bi-upc-scan", "active_pattern": "/inventory/scan"},
            {"section": "MAIN", "url": "inventory:scan_sold", "label": "Sell", "icon": "bi-bag-check", "active_pattern": "/sell/"},
            
            # TIME section
            {"section": "TIME", "url": "inventory:time_logs", "label": "Time Logs", "icon": "bi-journal-text", "active_pattern": "/inventory/time/logs"},
            
            # MONEY section
            {"section": "MONEY", "url": "wallet:agent_wallet", "label": "My Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            {"section": "MONEY", "url": "wallet:admin_home", "label": "Admin Wallet", "icon": "bi-briefcase", "active_pattern": "/wallet/admin/", "require_manager": True},
            
            # BUSINESS section (for managers)
            {"section": "BUSINESS", "url": "tenants:manager_review_agents", "label": "Agents", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_locations", "label": "Locations", "icon": "bi-geo", "active_pattern": "/tenants/manager/locations/", "require_manager": True},
            {"section": "BUSINESS", "url": "billing:plans", "label": "Choose Plan", "icon": "bi-credit-card-2-front", "active_pattern": "/billing/plans", "require_manager": True},
        ]
    
    else:  # "phones" or default
        return [
            # MAIN section
            {"section": "MAIN", "url": "dashboard:home", "label": "Dashboard", "icon": "bi-speedometer2", "active_pattern": "/dashboard/"},
            {"section": "MAIN", "url": "inventory:inventory_dashboard", "label": "Inventory Dashboard", "icon": "bi-columns-gap", "active_pattern": "/inventory/dashboard"},
            {"section": "MAIN", "url": "inventory:stock_list", "label": "Stock", "icon": "bi-box-seam", "active_pattern": "/inventory/list/"},
            {"section": "MAIN", "url": "inventory:scan_in", "label": "Scan IN", "icon": "bi-upc-scan", "active_pattern": "/inventory/scan"},
            {"section": "MAIN", "url": "sell:sell_index", "label": "Sell", "icon": "bi-bag-check", "active_pattern": "/sell/"},
            
            # TIME section
            {"section": "TIME", "url": "inventory:time_logs", "label": "Time Logs", "icon": "bi-journal-text", "active_pattern": "/inventory/time/logs"},
            
            # MONEY section
            {"section": "MONEY", "url": "wallet:agent_wallet", "label": "My Wallet", "icon": "bi-wallet2", "active_pattern": "/wallet/"},
            {"section": "MONEY", "url": "wallet:admin_home", "label": "Admin Wallet", "icon": "bi-briefcase", "active_pattern": "/wallet/admin/", "require_manager": True},
            
            # BUSINESS section (for managers)
            {"section": "BUSINESS", "url": "reports:home", "label": "Reports", "icon": "bi-graph-up", "active_pattern": "/reports/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_review_agents", "label": "Agents", "icon": "bi-people", "active_pattern": "/tenants/manager/agents/", "require_manager": True},
            {"section": "BUSINESS", "url": "tenants:manager_locations", "label": "Locations", "icon": "bi-geo", "active_pattern": "/tenants/manager/locations/", "require_manager": True},
            {"section": "BUSINESS", "url": "billing:plans", "label": "Choose Plan", "icon": "bi-credit-card-2-front", "active_pattern": "/billing/plans", "require_manager": True},
            {"section": "BUSINESS", "url": "inventory:orders_list", "label": "Orders", "icon": "bi-clipboard-data", "active_pattern": "/inventory/orders/", "require_manager": True},
            
            # LAYBY section (phones specific)
            {"section": "LAYBY", "url": "layby:dashboard", "label": "Layby", "icon": "bi-journal-check", "active_pattern": "/layby/"},
        ]


__all__ = [
    "get_vertical_kind",
    "get_vertical_dashboard_url",
    "get_onboarding_steps",
    "get_vertical_display_name",
    "get_vertical_sidebar_items",
]

