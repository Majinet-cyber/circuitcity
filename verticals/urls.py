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
from inventory.verticals import clothing, fallback, gym, liquor, pharmacy, phones, clothing_v2, groceries, groceries_v2

app_name = "verticals"

# Canonical vertical dashboard routes
# NOTE: Detailed sub-routes for each vertical (members, payments, etc.)
# are defined in inventory/urls_gym.py, inventory/urls_clothing.py, etc.
# and are included in the main cc/urls.py at paths like /gym/, /clothing/, etc.
# This file only defines the main dashboard entry points under /verticals/
urlpatterns = [
    # Gym vertical (membership-based, no inventory/fast-sell)
    path("gym/dashboard/", gym.dashboard, name="gym_dashboard"),
    # Note: gym fast-sell removed - gym is members + payments, not products
    
    # Clothing vertical (LEGACY - keep for backward compatibility)
    path("clothing/dashboard/", clothing.dashboard, name="clothing_dashboard"),
    path("clothing/hub/", clothing.hub, name="clothing_hub"),
    path("clothing/fast-sell/", clothing.fast_sell, name="clothing_fast_sell"),
    path("clothing/scan-in/", clothing.scan_in, name="clothing_scan_in"),
    path("clothing/sell/", clothing.sell, name="clothing_sell"),
    path("clothing/sales/", clothing.sales_history, name="clothing_sales_history"),
    path("clothing/sales/export.csv", clothing.sales_export_csv, name="clothing_sales_export_csv"),
    path("clothing/sales/<int:sale_id>/rollback/", clothing.rollback_sale, name="clothing_rollback_sale"),
    path("clothing/api/sales-trend/", clothing.sales_trend_json, name="clothing_sales_trend_json"),
    path("clothing/api/fast-sell/lookup/", clothing.fast_sell_lookup_api, name="clothing_fast_sell_lookup_api"),
    path("clothing/api/fast-sell/sell/", clothing.fast_sell_create_api, name="clothing_fast_sell_create_api"),
    path("clothing/api/fast-sell/create/", clothing.fast_sell_create_api, name="clothing_fast_sell_create_alias"),
    path("clothing/api/fast-sell/create-product/", clothing.fast_sell_create_product_api, name="clothing_fast_sell_create_product_api"),
    path("clothing/api/fast-sell/kpis/", clothing.fast_sell_kpis_api, name="clothing_fast_sell_kpis_api"),
    
    # Clothing V2 (PREMIUM - New gamified experience)
    path("clothing/v2/dashboard/", clothing_v2.dashboard_v2, name="clothing_dashboard_v2"),
    path("clothing/add/", clothing_v2.quick_add_step1, name="clothing_quick_add_step1"),
    path("clothing/add/<str:category>/", clothing_v2.quick_add_step2, name="clothing_quick_add_step2"),
    path("clothing/add/success/", clothing_v2.quick_add_success, name="clothing_quick_add_success"),
    path("clothing/stock-in/fast/", clothing_v2.fast_stock_in, name="clothing_fast_stock_in"),
    path("clothing/sell/fast/", clothing_v2.fast_sell, name="clothing_fast_sell_v2"),
    path("clothing/products/", clothing_v2.products_list, name="clothing_products_list"),
    path("clothing/labels/<int:product_id>/", clothing_v2.print_labels, name="clothing_print_labels"),
    path("clothing/scan/<str:token>/", clothing_v2.scan_qr, name="clothing_scan_qr"),
    
    # Liquor vertical
    path("liquor/dashboard/", liquor.dashboard, name="liquor_dashboard"),
    path("liquor/fast-sell/", liquor.fast_sell_page, name="liquor_fast_sell_page"),
    # Note: Fast Sell removed - liquor uses dedicated sell flow with barman attribution
    path("liquor/barman/invite/", liquor.barman_invite, name="liquor_barman_invite"),
    path("liquor/barman/reconciliation/", liquor.barman_reconciliation, name="liquor_barman_reconciliation"),
    path("liquor/sales/", liquor.sales_history, name="liquor_sales_history"),
    path("liquor/sales/export.csv", liquor.sales_export_csv, name="liquor_sales_export_csv"),
    path("liquor/sales/<int:sale_id>/rollback/", liquor.rollback_sale, name="liquor_rollback_sale"),
    path("liquor/api/sales-trend/", liquor.sales_trend_json, name="liquor_sales_trend_json"),
    path("liquor/api/fast-sell/lookup/", liquor.fast_sell_lookup_api, name="liquor_fast_sell_lookup"),
    path("liquor/api/fast-sell/sell/", liquor.fast_sell_create_api, name="liquor_fast_sell_sell"),
    path("liquor/api/barman/agents/", liquor.barman_agents_api, name="liquor_barman_agents_api"),
    path("liquor/api/barman/reconciliation/toggle/", liquor.barman_reconciliation_toggle_api, name="liquor_barman_reconciliation_toggle_api"),
    
    # Pharmacy vertical
    path("pharmacy/dashboard/", pharmacy.dashboard, name="pharmacy_dashboard"),
    path("pharmacy/hub/", pharmacy.hub, name="pharmacy_hub"),
    path("pharmacy/fast-sell/", pharmacy.fast_sell, name="pharmacy_fast_sell"),
    path("pharmacy/sales/", pharmacy.sales_history, name="pharmacy_sales_history"),
    path("pharmacy/sales/export.csv", pharmacy.sales_export_csv, name="pharmacy_sales_export_csv"),
    path("pharmacy/sales/<int:sale_id>/rollback/", pharmacy.rollback_sale, name="pharmacy_rollback_sale"),
    path("pharmacy/api/sales-trend/", pharmacy.sales_trend_json, name="pharmacy_sales_trend_json"),
    path("pharmacy/api/fast-sell/lookup/", pharmacy.fast_sell_lookup_api, name="pharmacy_fast_sell_lookup_api"),
    path("pharmacy/api/fast-sell/sell/", pharmacy.fast_sell_create_api, name="pharmacy_fast_sell_create_api"),
    path("pharmacy/api/fast-sell/kpis/", pharmacy.fast_sell_kpis_api, name="pharmacy_fast_sell_kpis_api"),
    
    # Groceries vertical (LEGACY - keep for backward compatibility)
    path("groceries/dashboard/", groceries.dashboard, name="groceries_dashboard"),
    path("groceries/stock/", groceries.stock_list, name="groceries_stock_list"),
    path("groceries/stock-in/", groceries.stock_in, name="groceries_stock_in"),
    path("groceries/products/add/", groceries.product_add, name="groceries_product_add"),
    path("groceries/sell/", groceries.sell, name="groceries_sell"),
    path("groceries/analytics/", groceries.analytics, name="groceries_analytics"),
    path("groceries/sales/<int:sale_id>/rollback/", groceries.rollback_sale, name="groceries_rollback_sale"),
    
    # Groceries V2 (NEW - Stupid Simple Retail + Wholesale Flow)
    path("groceries/v2/dashboard/", groceries_v2.dashboard_v2, name="groceries_dashboard_v2"),
    path("groceries/v2/products/", groceries_v2.product_list_v2, name="groceries_products_v2"),
    path("groceries/v2/products/add/", groceries_v2.product_add_v2, name="groceries_product_add_v2"),
    path("groceries/v2/stock-in/", groceries_v2.stock_in_v2, name="groceries_stock_in_v2"),
    path("groceries/v2/stock-in/submit/", groceries_v2.stock_in_submit_v2, name="groceries_stock_in_submit_v2"),
    path("groceries/v2/sell/", groceries_v2.sell_v2, name="groceries_sell_v2"),
    path("groceries/v2/sell/submit/", groceries_v2.sell_submit_v2, name="groceries_sell_submit_v2"),
    path("groceries/v2/scan/<str:scan_value>/", groceries_v2.scan_v2, name="groceries_scan_v2"),
    
    # Phones vertical (sales history + reports)
    path("phones/dashboard/", phones.dashboard, name="phones_dashboard"),
    # Note: Fast Sell removed - phones uses dedicated scan/sell flows
    path("phones/sales/", phones.sales_history, name="phones_sales_history"),
    path("phones/sales/export.csv", phones.sales_export_csv, name="phones_sales_export_csv"),
    path("phones/api/sales-trend/", phones.sales_trend_json, name="phones_sales_trend_json"),
    path("phones/reports/", phones.reports, name="phones_reports"),
    
    # Phones Accessories (quantity-based, separate from IMEI phones)
    path("phones/accessories/", phones.accessories_dashboard, name="phones_accessories_dashboard"),
    path("phones/accessories/stock-in/", phones.accessories_stock_in, name="phones_accessories_stock_in"),
    path("phones/accessories/fast-sell/", phones.accessories_fast_sell, name="phones_accessories_fast_sell"),
    path("phones/accessories/sell/", phones.accessories_normal_sell, name="phones_accessories_sell"),  # NEW: Normal sell
    path("phones/accessories/api/lookup/", phones.accessories_lookup_api, name="phones_accessories_lookup_api"),
    path("phones/accessories/api/stock-in/", phones.accessories_stock_in_api, name="phones_accessories_stock_in_api"),
    path("phones/accessories/api/sell/", phones.accessories_sell_api, name="phones_accessories_sell_api"),
    
    # Fallback for businesses without a kind
    path("none/", fallback.no_business, name="no_business"),
]

