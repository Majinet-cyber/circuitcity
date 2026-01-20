# inventory/mobile_nav.py
"""
Vertical-aware mobile bottom navigation configuration.
Provides a single source of truth for mobile nav items per business vertical.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

from .helpers_core import CAR_HIRE, CEMENT, CLOTHING, FARM, GYM, LIQUOR, PHARMACY, PHONES, WELDING, business_vertical


def _safe_reverse(url_name: str, fallback: str = "#") -> str:
    """Safely reverse a URL name, returning fallback on NoReverseMatch."""
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return fallback


def _safe_reverse_any(url_names: List[str], fallback: str = "#") -> str:
    """
    Try multiple URL names in order, returning the first successful reverse.
    Falls back to the provided fallback if all fail.

    Args:
        url_names: List of URL names to try in order
        fallback: Fallback URL if all reverse attempts fail

    Returns:
        Resolved URL string
    """
    for url_name in url_names:
        try:
            return reverse(url_name)
        except NoReverseMatch:
            continue
    return fallback


def get_mobile_nav_items(request: HttpRequest) -> List[Dict[str, Any]]:
    """
    Get mobile navigation items for the current business vertical.

    Each item is a dict with:
        - key: str - Unique identifier for the tab (e.g., 'home', 'scan')
        - label: str - Display label (e.g., 'Home', 'Scan')
        - icon_class: str - Bootstrap icon class (e.g., 'bi-speedometer2')
        - url: str - Resolved URL or href
        - active_prefix: Optional[str] - URL prefix to match for active state
        - is_menu: bool - If True, opens drawer instead of navigating

    Args:
        request: HttpRequest with BUSINESS_VERTICAL in context

    Returns:
        List of nav item dicts, empty list if vertical unknown
    """
    vertical = business_vertical(request)

    # CRITICAL: Handle None/unknown/generic business_kind FIRST
    if vertical in (None, "", "generic", "none"):
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-house",
                "url": _safe_reverse_any(["verticals:no_business"], "/verticals/none/"),
                "active_prefix": "/verticals/none",
                "is_menu": False,
            },
            {
                "key": "settings",
                "label": "Settings",
                "icon_class": "bi-gear",
                "url": _safe_reverse_any(["settings_root"], "/settings/"),
                "active_prefix": "/settings",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    if vertical == PHONES:
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("inventory_verticals:phones_dashboard", "/inventory/verticals/phones/"),
                "active_prefix": "/inventory/verticals/phones",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "scan",
                "label": "Scan",
                "icon_class": "bi-upc-scan",
                "url": _safe_reverse("app_router:scan", "/inventory/scan-in/"),
                "active_prefix": "/inventory/scan",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-cart-check",
                "url": _safe_reverse("app_router:sell", "/inventory/phone-sale-wizard/"),
                "active_prefix": "/inventory/phone-sale-wizard",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == CLOTHING:
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("app_router:home", "/verticals/clothing/dashboard/"),
                "active_prefix": "/verticals/clothing",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "add_product",
                "label": "Add Product",
                "icon_class": "bi-plus-square",
                "url": _safe_reverse("inventory:clothing_product_new_v2", "/inventory/clothing/products/new/v2/"),
                "active_prefix": "/inventory/clothing/products/new",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-cart-check",
                "url": _safe_reverse_any(["verticals:clothing_sell"], "/verticals/clothing/sell/"),
                "active_prefix": "/verticals/clothing/sell",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == PHARMACY:
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("app_router:home", "/verticals/pharmacy/dashboard/"),
                "active_prefix": "/verticals/pharmacy",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "stock_in",
                "label": "Stock In",
                "icon_class": "bi-box-arrow-in-down",
                "url": _safe_reverse("pharmacy:stock_in", "/pharmacy/stock-in/"),
                "active_prefix": "/pharmacy/stock-in",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-cart-check",
                "url": _safe_reverse_any(["pharmacy:sell"], "/pharmacy/sell/"),
                "active_prefix": "/pharmacy/sell",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == LIQUOR:
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("app_router:home", "/verticals/liquor/dashboard/"),
                "active_prefix": "/verticals/liquor",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "stock_in",
                "label": "Stock In",
                "icon_class": "bi-box-arrow-in-down",
                "url": _safe_reverse("liquor:inventory_dashboard", "/liquor/inventory/"),
                "active_prefix": "/liquor/inventory",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-cart-check",
                "url": _safe_reverse_any(["liquor:sell"], "/liquor/sell/"),
                "active_prefix": "/liquor/sell",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == GYM:
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("app_router:home", "/verticals/gym/dashboard/"),
                "active_prefix": "/verticals/gym",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "members",
                "label": "Members",
                "icon_class": "bi-people",
                "url": _safe_reverse("gym:members_list", "/gym/members/"),
                "active_prefix": "/gym/members",
                "is_menu": False,
            },
            {
                "key": "payments",
                "label": "Payments",
                "icon_class": "bi-wallet2",
                "url": _safe_reverse("gym:add_payment", "/gym/payment/add/"),
                "active_prefix": "/gym/payment",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == CEMENT:
        # Cement uses both /verticals/cement/ and /cement/ routes
        # Prefer the cement: namespace (urls_cement.py) for consistency
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse_any(["cement:dashboard", "verticals:cement_dashboard"], "/cement/dashboard/"),
                "active_prefix": "/cement/",
                "is_menu": False,
            },
            {
                "key": "stock_in",
                "label": "Stock In",
                "icon_class": "bi-box-arrow-in-down",
                "url": _safe_reverse_any(["cement:stock_in", "verticals:cement_stock_in"], "/cement/stock-in/"),
                "active_prefix": "/cement/stock-in",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-bag-check",
                "url": _safe_reverse_any(["cement:sell", "verticals:cement_sell"], "/cement/sell/"),
                "active_prefix": "/cement/sell",
                "is_menu": False,
            },
            {
                "key": "products",
                "label": "Products",
                "icon_class": "bi-box-seam",
                "url": _safe_reverse_any(["cement:stock_list", "verticals:cement_stock_list"], "/cement/stock/"),
                "active_prefix": "/cement/stock",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "More",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == FARM:
        # Farm Manager vertical - profitability tracking
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse_any(["verticals:farm_dashboard"], "/verticals/farm/dashboard/"),
                "active_prefix": "/verticals/farm/dashboard",
                "is_menu": False,
            },
            {
                "key": "ledger",
                "label": "Ledger",
                "icon_class": "bi-journal-text",
                "url": _safe_reverse_any(["verticals:farm_ledger_list"], "/verticals/farm/ledger/"),
                "active_prefix": "/verticals/farm/ledger",
                "is_menu": False,
            },
            {
                "key": "add_expense",
                "label": "Expense",
                "icon_class": "bi-dash-circle",
                "url": _safe_reverse_any(["verticals:farm_add_expense"], "/verticals/farm/ledger/add-expense/"),
                "active_prefix": "/verticals/farm/ledger/add-expense",
                "is_menu": False,
            },
            {
                "key": "add_sale",
                "label": "Sale",
                "icon_class": "bi-plus-circle",
                "url": _safe_reverse_any(["verticals:farm_add_sale"], "/verticals/farm/ledger/add-sale/"),
                "active_prefix": "/verticals/farm/ledger/add-sale",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "More",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == WELDING:
        # Welding Workshop vertical - job estimation & invoicing
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse_any(["verticals:welding_dashboard"], "/verticals/welding/dashboard/"),
                "active_prefix": "/verticals/welding/dashboard",
                "is_menu": False,
            },
            {
                "key": "quotes",
                "label": "Quotes",
                "icon_class": "bi-file-text",
                "url": _safe_reverse_any(["verticals:welding_quotes_list"], "/verticals/welding/quotes/"),
                "active_prefix": "/verticals/welding/quotes",
                "is_menu": False,
            },
            {
                "key": "jobs",
                "label": "Jobs",
                "icon_class": "bi-kanban",
                "url": _safe_reverse_any(["verticals:welding_jobs_list"], "/verticals/welding/jobs/"),
                "active_prefix": "/verticals/welding/jobs",
                "is_menu": False,
            },
            {
                "key": "revenue",
                "label": "Revenue",
                "icon_class": "bi-cash-coin",
                "url": _safe_reverse_any(["verticals:welding_revenue"], "/verticals/welding/revenue/"),
                "active_prefix": "/verticals/welding/revenue",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "More",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    elif vertical == CAR_HIRE:
        # Car Hire Service vertical - fleet management & bookings
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse_any(["verticals:car_hire_dashboard"], "/verticals/car_hire/dashboard/"),
                "active_prefix": "/verticals/car_hire/dashboard",
                "is_menu": False,
            },
            {
                "key": "vehicles",
                "label": "Vehicles",
                "icon_class": "bi-truck",
                "url": _safe_reverse_any(["verticals:car_hire_vehicles"], "/verticals/car_hire/vehicles/"),
                "active_prefix": "/verticals/car_hire/vehicles",
                "is_menu": False,
            },
            {
                "key": "trips",
                "label": "Trips",
                "icon_class": "bi-calendar-check",
                "url": _safe_reverse_any(["verticals:car_hire_trips"], "/verticals/car_hire/trips/"),
                "active_prefix": "/verticals/car_hire/trips",
                "is_menu": False,
            },
            {
                "key": "add_trip",
                "label": "Book",
                "icon_class": "bi-plus-circle",
                "url": _safe_reverse_any(["verticals:car_hire_trip_add"], "/verticals/car_hire/trips/new/"),
                "active_prefix": "/verticals/car_hire/trips/new",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "More",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]

    else:
        # Generic/unknown vertical - default to phones nav
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse("app_router:home", "/inventory/dashboard/"),
                "active_prefix": "/inventory/dashboard",
                "is_menu": False,
            },
            {
                "key": "analytics",
                "label": "Analytics",
                "icon_class": "bi-graph-up",
                "url": _safe_reverse("app_router:analytics", "/app/analytics/"),
                "active_prefix": "/app/analytics",
                "is_menu": False,
            },
            {
                "key": "scan",
                "label": "Scan",
                "icon_class": "bi-upc-scan",
                "url": _safe_reverse("app_router:scan", "/inventory/scan-in/"),
                "active_prefix": "/inventory/scan",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-cart-check",
                "url": _safe_reverse("app_router:sell", "/inventory/phone-sale-wizard/"),
                "active_prefix": "/inventory/phone-sale-wizard",
                "is_menu": False,
            },
            {
                "key": "menu",
                "label": "Menu",
                "icon_class": "bi-list",
                "url": "#",
                "active_prefix": None,
                "is_menu": True,
            },
        ]


__all__ = ["get_mobile_nav_items"]
