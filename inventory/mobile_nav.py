# inventory/mobile_nav.py
"""
Vertical-aware mobile bottom navigation configuration.
Provides a single source of truth for mobile nav items per business vertical.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

from .helpers_core import CEMENT, CLOTHING, GYM, LIQUOR, PHARMACY, PHONES, business_vertical


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
        return [
            {
                "key": "home",
                "label": "Home",
                "icon_class": "bi-speedometer2",
                "url": _safe_reverse_any(["verticals:cement_dashboard"], "/verticals/cement/dashboard/"),
                "active_prefix": "/verticals/cement/dashboard",
                "is_menu": False,
            },
            {
                "key": "stock_in",
                "label": "Stock In",
                "icon_class": "bi-box-arrow-in-down",
                "url": _safe_reverse_any(["cement:stock_in"], "/cement/stock-in/"),
                "active_prefix": "/cement/stock-in",
                "is_menu": False,
            },
            {
                "key": "sell",
                "label": "Sell",
                "icon_class": "bi-bag-check",
                "url": _safe_reverse_any(["cement:sell"], "/cement/sell/"),
                "active_prefix": "/cement/sell",
                "is_menu": False,
            },
            {
                "key": "products",
                "label": "Products",
                "icon_class": "bi-box-seam",
                "url": _safe_reverse_any(["cement:stock_list"], "/cement/stock/"),
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
