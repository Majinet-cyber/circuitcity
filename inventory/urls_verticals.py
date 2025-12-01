from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.urls import path

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy
from inventory.views_dashboard import inventory_dashboard as phones_dashboard

app_name = "inventory_verticals"

urlpatterns = [
    path(
        "phones/",
        require_business_kind(BusinessKind.PHONES)(
            require_business(login_required(phones_dashboard))
        ),
        name="phones_dashboard",
    ),
    path("clothing/", clothing.dashboard, name="clothing_dashboard"),
    path("liquor/", liquor.dashboard, name="liquor_dashboard"),
    path("pharmacy/", pharmacy.dashboard, name="pharmacy_dashboard"),
    path("gym/", gym.dashboard, name="gym_dashboard"),
    path("none/", fallback.no_business, name="no_business"),
]

