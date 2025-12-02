# verticals/urls.py
"""
URL patterns for vertical-specific business types.
All real verticals (gym, clothing, liquor, pharmacy) live under /verticals/<slug>/
Phones are NOT a vertical - they use the core /inventory/ routes.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.urls import path

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy

app_name = "verticals"

# Canonical vertical dashboard routes
# NOTE: Detailed sub-routes for each vertical (members, payments, etc.)
# are defined in inventory/urls_gym.py, inventory/urls_clothing.py, etc.
# and are included in the main cc/urls.py at paths like /gym/, /clothing/, etc.
# This file only defines the main dashboard entry points under /verticals/
urlpatterns = [
    # Gym vertical
    path("gym/dashboard/", gym.dashboard, name="gym_dashboard"),
    
    # Clothing vertical
    path("clothing/dashboard/", clothing.dashboard, name="clothing_dashboard"),
    
    # Liquor vertical
    path("liquor/dashboard/", liquor.dashboard, name="liquor_dashboard"),
    
    # Pharmacy vertical
    path("pharmacy/dashboard/", pharmacy.dashboard, name="pharmacy_dashboard"),
    
    # Fallback for businesses without a kind
    path("none/", fallback.no_business, name="no_business"),
]

