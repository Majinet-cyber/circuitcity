# inventory/views_dispatch.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from tenants.decorators import require_business_access as require_business

from .helpers import (
    PHARMACY,
    PHONES,
    CLOTHING,
    GYM,
    LIQUOR,
    business_vertical,
    product_new_url_for_business,
)

_VERTICAL_ROUTES = {
    CLOTHING: "verticals:clothing_dashboard",
    LIQUOR: "verticals:liquor_dashboard",
    PHARMACY: "verticals:pharmacy_dashboard",
    GYM: "verticals:gym_dashboard",
}
_DEFAULT_ROUTE = "verticals:no_business"


def _safe_reverse(name: str, default: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return default


@login_required
@require_business
def vertical_dispatcher(request):
    """
    Route users to the correct dashboard for their business vertical.
    
    PHONES businesses now redirect to Analytics (replaces inventory dashboard).
    Other verticals redirect to their specialized dashboards.
    Falls back to a generic prompt if the vertical is unknown.
    """
    vertical = business_vertical(request)
    
    # PHONES: redirect to analytics (replaces inventory dashboard)
    if vertical == PHONES:
        # Redirect to analytics router endpoint with fallback
        analytics_url = _safe_reverse("app_router:analytics", "/app/analytics/")
        return redirect(analytics_url)
    
    # Other verticals: redirect to their specialized dashboards
    target = _VERTICAL_ROUTES.get(vertical, _DEFAULT_ROUTE)
    return redirect(target)


@login_required
@require_business
def product_new_entry(request):
    """
    Redirect 'Add Product' to the correct, business-specific form.
    Legacy businesses go to PHONE/Electronics by default.
    """
    try:
        sess_vertical = (request.session.get("active_business_vertical") or "").strip().lower()
    except Exception:
        sess_vertical = ""

    if sess_vertical in {"clothing", "liquor", "phones"}:
        if sess_vertical == "clothing":
            url = _safe_reverse("inventory:clothing_product_new_v2", "/inventory/clothing/products/new/v2/")
        elif sess_vertical == "liquor":
            url = _safe_reverse("inventory:liquor_product_new_v2", "/inventory/liquor/products/new/v2/")
        else:
            url = _safe_reverse("inventory:merch_product_new", "/inventory/merch/products/new/v2/")
        return redirect(url)

    url = product_new_url_for_business(getattr(request, "business", None))
    return redirect(url)
