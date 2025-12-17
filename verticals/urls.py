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
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy, phones

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
    path("clothing/hub/", clothing.hub, name="clothing_hub"),
    path("clothing/scan-in/", clothing.scan_in, name="clothing_scan_in"),
    path("clothing/sell/", clothing.sell, name="clothing_sell"),
    path("clothing/sales/", clothing.sales_history, name="clothing_sales_history"),
    path("clothing/sales/export.csv", clothing.sales_export_csv, name="clothing_sales_export_csv"),
    path("clothing/api/sales-trend/", clothing.sales_trend_json, name="clothing_sales_trend_json"),
    
    # Liquor vertical
    path("liquor/dashboard/", liquor.dashboard, name="liquor_dashboard"),
    path("liquor/sales/", liquor.sales_history, name="liquor_sales_history"),
    path("liquor/sales/export.csv", liquor.sales_export_csv, name="liquor_sales_export_csv"),
    path("liquor/api/sales-trend/", liquor.sales_trend_json, name="liquor_sales_trend_json"),
    
    # Pharmacy vertical
    path("pharmacy/dashboard/", pharmacy.dashboard, name="pharmacy_dashboard"),
    path("pharmacy/hub/", pharmacy.hub, name="pharmacy_hub"),
    path("pharmacy/sales/", pharmacy.sales_history, name="pharmacy_sales_history"),
    path("pharmacy/sales/export.csv", pharmacy.sales_export_csv, name="pharmacy_sales_export_csv"),
    path("pharmacy/api/sales-trend/", pharmacy.sales_trend_json, name="pharmacy_sales_trend_json"),
    
    # Phones vertical (sales history + reports)
    path("phones/dashboard/", phones.dashboard, name="phones_dashboard"),
    path("phones/sales/", phones.sales_history, name="phones_sales_history"),
    path("phones/sales/export.csv", phones.sales_export_csv, name="phones_sales_export_csv"),
    path("phones/api/sales-trend/", phones.sales_trend_json, name="phones_sales_trend_json"),
    path("phones/reports/", phones.reports, name="phones_reports"),
    
    # Fallback for businesses without a kind
    path("none/", fallback.no_business, name="no_business"),
]

