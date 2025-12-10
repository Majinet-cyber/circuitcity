from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import path, reverse

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy, phones

app_name = "inventory_verticals"

# LEGACY URLs - kept for backward compatibility
# All vertical URLs now live under /verticals/ (new canonical location)
# These redirect to the new locations

def _redirect_to_new_vertical(vertical_slug: str):
    """Redirect legacy /inventory/verticals/<slug>/ to /verticals/<slug>/dashboard/"""
    def _view(request, *args, **kwargs):
        return redirect(f"/verticals/{vertical_slug}/dashboard/")
    return _view

urlpatterns = [
    # Phones dashboard at /inventory/verticals/phones/
    path(
        "phones/",
        require_business_kind(BusinessKind.PHONES)(
            require_business(login_required(phones.dashboard))
        ),
        name="phones_dashboard",
    ),
    
    # LEGACY: Redirect old vertical URLs to new canonical locations
    path("gym/", _redirect_to_new_vertical("gym"), name="gym_dashboard"),
    path("clothing/", _redirect_to_new_vertical("clothing"), name="clothing_dashboard"),
    path("liquor/", _redirect_to_new_vertical("liquor"), name="liquor_dashboard"),
    path("pharmacy/", _redirect_to_new_vertical("pharmacy"), name="pharmacy_dashboard"),
    
    path("none/", fallback.no_business, name="no_business"),
]

