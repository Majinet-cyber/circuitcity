# verticals/urls.py
"""
URL patterns for vertical-specific business types.
All real verticals (gym, clothing, liquor, pharmacy) live under /verticals/<slug>/
Phones are NOT a vertical - they use the core /inventory/ routes.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.urls import path, include

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy

app_name = "verticals"

# Canonical vertical dashboard routes
urlpatterns = [
    # Gym vertical
    path("gym/dashboard/", gym.dashboard, name="gym_dashboard"),
    path("gym/", include("inventory.urls_gym")),  # Already has app_name="gym"
    
    # Clothing vertical
    path("clothing/dashboard/", clothing.dashboard, name="clothing_dashboard"),
    path("clothing/", include("inventory.urls_clothing")),  # Already has app_name="clothing"
    
    # Liquor vertical
    path("liquor/dashboard/", liquor.dashboard, name="liquor_dashboard"),
    path("liquor/", include("inventory.urls_liquor")),  # Already has app_name="liquor"
    
    # Pharmacy vertical
    path("pharmacy/dashboard/", pharmacy.dashboard, name="pharmacy_dashboard"),
    path("pharmacy/", include("inventory.urls_pharmacy")),  # Already has app_name="pharmacy"
    
    # Fallback for businesses without a kind
    path("none/", fallback.no_business, name="no_business"),
]

