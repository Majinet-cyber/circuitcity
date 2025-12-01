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

    ctx: Dict[str, Any] = {
        "business": business,
        "location": location,
        "location_label": location_label,
        "vertical": vertical,
        "scan_in_url": reverse("inventory:scan_in"),
        "scan_sold_url": reverse("inventory:scan_sold"),
        "stock_url": reverse("inventory:stock_list"),
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

