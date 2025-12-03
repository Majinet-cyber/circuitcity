from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.db.models import QuerySet
from django.urls import reverse

from inventory.helpers import add_product_url_for_request, business_vertical, get_active_business
from inventory.models import MerchProduct
from tenants.scope import resolve_location_for_user, set_scope_in_session


def _get_location(location_id: Optional[int]):
    if not location_id:
        return None
    try:
        Location = apps.get_model("inventory", "Location")
    except Exception:
        return None
    return Location.objects.filter(pk=location_id).first()


def base_context(request) -> Dict[str, Any]:
    """
    Shared context for all vertical dashboards.
    Ensures we keep the tenant scope (business / location) in sync with session defaults.
    
    Provides vertical-aware URLs so liquor/gym/clothing contexts route correctly.
    """
    business = get_active_business(request)
    vertical = business_vertical(request)

    try:
        request.session["active_business_vertical"] = vertical
    except Exception:
        pass

    location_id = resolve_location_for_user(request)
    if business:
        set_scope_in_session(request, business_id=business.id, location_id=location_id)

    location = _get_location(location_id)
    location_label = getattr(location, "name", None) or ("All locations" if business else "No active location")

    # Vertical-aware URL overrides (Task 1A: Fix liquor stock/sell/hub URLs)
    if vertical == "liquor":
        url_home = reverse("verticals:liquor_dashboard")
        url_stock = reverse("liquor:stock_overview")
        url_sell = reverse("liquor:sell")
        url_scan_in = reverse("liquor:inventory_dashboard")  # Liquor Hub
    elif vertical == "gym":
        url_home = reverse("verticals:gym_dashboard")
        url_stock = reverse("inventory:stock_list")  # gym uses default for now
        url_sell = reverse("inventory:scan_sold")  # gym uses default for now
        url_scan_in = reverse("inventory:scan_in")
    elif vertical == "clothing":
        url_home = reverse("verticals:clothing_dashboard")
        url_stock = reverse("inventory:stock_list")  # clothing uses default for now
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")
    else:  # phones or default
        url_home = reverse("inventory:inventory_dashboard")
        url_stock = reverse("inventory:stock_list")
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")

    ctx: Dict[str, Any] = {
        "business": business,
        "location": location,
        "location_label": location_label,
        "vertical": vertical,
        # Vertical-aware URLs (for sidebar & templates)
        "url_home": url_home,
        "url_stock": url_stock,
        "url_sell": url_sell,
        "url_scan_in": url_scan_in,
        # Legacy names (backward compatibility)
        "scan_in_url": url_scan_in,
        "scan_sold_url": url_sell,
        "stock_url": url_stock,
        "add_product_url": add_product_url_for_request(request),
    }
    return ctx


def merch_queryset(business, kind: str) -> QuerySet[MerchProduct]:
    if not business:
        return MerchProduct.objects.none()
    return MerchProduct.objects.filter(business=business, kind=kind)


def merch_metrics(business, kind: str, *, recent_limit: int = 6) -> Dict[str, Any]:
    qs = merch_queryset(business, kind)
    recent = list(qs.order_by("-id")[:recent_limit])
    return {
        "total": qs.count(),
        "active": qs.filter(is_active=True).count(),
        "scan_required": qs.filter(scan_required=True).count(),
        "inventory_tracked": qs.filter(track_inventory=True).count(),
        "recent": recent,
    }

