# verticals/urls.py
"""
URL patterns for vertical-specific business types.
All real verticals (gym, clothing, liquor, pharmacy) live under /verticals/<slug>/
Phones are NOT a vertical - they use the core /inventory/ routes.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.urls import path

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.verticals import (
    car_hire,
    cement,
    clothing,
    clothing_v2,
    fallback,
    farm,
    groceries,
    groceries_v2,
    gym,
    liquor,
    pharmacy,
    phones,
    welding,
)

try:
    from inventory.verticals import energy as _energy_module
    _HAS_ENERGY = True
except ImportError:
    _energy_module = None  # type: ignore
    _HAS_ENERGY = False

try:
    from inventory.verticals import car_dealer as _car_dealer_module
    _HAS_CAR_DEALER = True
except ImportError:
    _car_dealer_module = None  # type: ignore
    _HAS_CAR_DEALER = False

# Import data correction views
from inventory import views_data_correction as data_correction

# Import new Farm modules
from inventory.verticals import farm_sales, farm_expenses, farm_assets, farm_locations, farm_reports
from tenants.utils import require_business

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
    path(
        "clothing/api/fast-sell/create-product/",
        clothing.fast_sell_create_product_api,
        name="clothing_fast_sell_create_product_api",
    ),
    path("clothing/api/fast-sell/kpis/", clothing.fast_sell_kpis_api, name="clothing_fast_sell_kpis_api"),
    # NEW: Unified Fast Sell endpoints (supports both tracked units AND common stock)
    path("clothing/api/fast-sell/lookup-unified/", clothing.fast_sell_lookup_unified_api, name="clothing_fast_sell_lookup_unified_api"),
    path("clothing/api/fast-sell/sell-unified/", clothing.fast_sell_sell_unified_api, name="clothing_fast_sell_sell_unified_api"),
    path("clothing/api/fast-sell/resolve-product/", clothing.fast_sell_resolve_product_api, name="clothing_fast_sell_resolve_product_api"),
    # NEW: Tracked units list (clickable from Hub)
    path("clothing/products/<int:product_id>/tracked-units/", clothing.tracked_units_list, name="clothing_tracked_units_list"),
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
    path(
        "liquor/api/barman/reconciliation/toggle/",
        liquor.barman_reconciliation_toggle_api,
        name="liquor_barman_reconciliation_toggle_api",
    ),
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
    # Phase 2: Groceries intelligence views
    path("groceries/intelligence/", groceries.inventory_intelligence, name="groceries_intelligence"),
    path("groceries/sales-analytics/", groceries.sales_analytics, name="groceries_sales_analytics"),
    path("groceries/restocking/", groceries.smart_restocking, name="groceries_restocking"),
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
    path(
        "phones/accessories/sell/", phones.accessories_normal_sell, name="phones_accessories_sell"
    ),  # NEW: Normal sell
    path("phones/accessories/api/lookup/", phones.accessories_lookup_api, name="phones_accessories_lookup_api"),
    path("phones/accessories/api/stock-in/", phones.accessories_stock_in_api, name="phones_accessories_stock_in_api"),
    path("phones/accessories/api/sell/", phones.accessories_sell_api, name="phones_accessories_sell_api"),
    # ==========================================================================
    # PHONES DATA CORRECTION (Manager-only feature)
    # Allows managers to fix wrong sales/stock data safely with full audit trail
    # ==========================================================================
    path("phones/data-correction/", data_correction.data_correction_dashboard, name="phones_data_correction"),
    path(
        "phones/data-correction/phone/<int:item_id>/",
        data_correction.phone_item_detail,
        name="phones_data_correction_phone_detail",
    ),
    path(
        "phones/data-correction/phone/<int:item_id>/edit/",
        data_correction.phone_item_edit,
        name="phones_data_correction_phone_edit",
    ),
    path(
        "phones/data-correction/phone/<int:item_id>/void/",
        data_correction.phone_item_void,
        name="phones_data_correction_phone_void",
    ),
    path(
        "phones/data-correction/accessory/<int:stock_id>/",
        data_correction.accessory_stock_detail,
        name="phones_data_correction_accessory_detail",
    ),
    path(
        "phones/data-correction/accessory/<int:stock_id>/edit/",
        data_correction.accessory_stock_edit,
        name="phones_data_correction_accessory_edit",
    ),
    path(
        "phones/data-correction/audit-trail/",
        data_correction.correction_audit_trail,
        name="phones_data_correction_audit_trail",
    ),
    path(
        "phones/data-correction/export.csv",
        data_correction.export_corrections_csv,
        name="phones_data_correction_export",
    ),
    # Data Correction API endpoints
    path(
        "phones/data-correction/api/search/",
        data_correction.api_search_items,
        name="phones_data_correction_api_search",
    ),
    path(
        "phones/data-correction/api/history/<str:model_name>/<int:object_id>/",
        data_correction.api_item_history,
        name="phones_data_correction_api_history",
    ),
    path(
        "phones/data-correction/api/edit-phone/",
        data_correction.api_edit_phone,
        name="phones_data_correction_api_edit_phone",
    ),
    path(
        "phones/data-correction/api/void-phone/",
        data_correction.api_void_phone,
        name="phones_data_correction_api_void_phone",
    ),
    # Cement vertical (building materials, gamified stock + sell)
    path("cement/dashboard/", cement.dashboard, name="cement_dashboard"),
    path("cement/stock/", cement.stock_list, name="cement_stock_list"),
    path("cement/stock-in/", cement.stock_in, name="cement_stock_in"),
    path("cement/sell/", cement.sell, name="cement_sell"),
    path("cement/costs/", cement.costs, name="cement_costs"),
    path("cement/analytics/", cement.analytics, name="cement_analytics"),
    # ==================== FARM VERTICAL ====================
    path("farm/dashboard/", farm.dashboard, name="farm_dashboard"),
    
    # Sales (new premium gamified flow)
    path("farm/sales/", farm_sales.sales_landing, name="farm_sales"),
    path("farm/sales/crops/", farm_sales.sales_crops, name="farm_sales_crops"),
    path("farm/sales/livestock/", farm_sales.sales_livestock, name="farm_sales_livestock"),
    path("farm/sales/record/", farm_sales.sales_record, name="farm_sales_record"),
    
    # Expenses (new premium gamified flow)
    path("farm/expenses/", farm_expenses.expenses_landing, name="farm_expenses"),
    path("farm/expenses/record/", farm_expenses.expenses_record, name="farm_expenses_record"),
    path("farm/expenses/export/", farm_expenses.expenses_export, name="farm_expenses_export"),
    
    # Assets (new premium section)
    path("farm/assets/", farm_assets.assets_landing, name="farm_assets"),
    
    # Locations (new premium section)
    path("farm/locations/", farm_locations.locations_list, name="farm_locations"),
    path("farm/locations/create/", farm_locations.locations_create, name="farm_locations_create"),
    path("farm/locations/<int:location_id>/edit/", farm_locations.locations_edit, name="farm_locations_edit"),
    
    # Legacy ledger URLs (keep for backward compatibility)
    path("farm/ledger/", farm.ledger_list, name="farm_ledger_list"),
    path("farm/ledger/add-expense/", farm.add_expense, name="farm_add_expense"),
    path("farm/ledger/add-sale/", farm.add_sale, name="farm_add_sale"),
    
    # Livestock
    path("farm/livestock/", farm.livestock_list, name="farm_livestock_list"),
    path(
        "farm/livestock/<int:batch_id>/",
        farm.livestock_batch_detail,
        name="farm_livestock_detail",
    ),
    path("farm/livestock/create/", farm.livestock_batch_create, name="farm_livestock_create"),
    path("farm/livestock/add-batch/", farm.livestock_batch_create, name="farm_livestock_add_batch"),
    path("farm/livestock/add-event/", farm.livestock_add_event, name="farm_livestock_add_event"),
    
    # Crops/Seasons
    path("farm/crops/", farm.crops_list, name="farm_crops_list"),
    path("farm/crops/create/", farm.crop_season_create, name="farm_crop_create"),
    path("farm/crops/add-season/", farm.crop_season_create, name="farm_add_season"),
    path("farm/crops/<int:season_id>/", farm.crop_season_detail, name="farm_crop_detail"),
    
    # Reports
    path("farm/reports/", farm.reports, name="farm_reports"),
    path("farm/reports/profit-loss/", farm_reports.profit_loss_report, name="farm_report_profit_loss"),
    path("farm/reports/livestock/", farm_reports.livestock_report, name="farm_report_livestock"),
    path("farm/reports/crop-season/", farm_reports.crop_season_report, name="farm_report_crop_season"),
    path("farm/reports/ledger-export/", farm_reports.ledger_export, name="farm_report_ledger_export"),
    path("farm/reports/livestock-export/", farm_reports.livestock_export, name="farm_report_livestock_export"),
    path("farm/reports/crops-export/", farm_reports.crops_export, name="farm_report_crops_export"),
    
    # ==================== WELDING VERTICAL ====================
    path("welding/dashboard/", welding.dashboard, name="welding_dashboard"),
    path("welding/sales/", welding.sales, name="welding_sales"),
    path("welding/revenue/", welding.revenue_list, name="welding_revenue"),
    path("welding/revenue/add/", welding.revenue_add, name="welding_revenue_add"),
    path("welding/costs/", welding.costs_list, name="welding_costs"),
    path("welding/costs/add/", welding.costs_add, name="welding_costs_add"),
    path("welding/materials/", welding.materials_list, name="welding_materials_list"),
    path("welding/materials/<int:material_id>/edit/", welding.material_edit, name="welding_material_edit"),
    path("welding/stock-in/", welding.stock_in, name="welding_stock_in"),
    path("welding/quotes/", welding.quotes_list, name="welding_quotes_list"),
    path("welding/quotes/create/", welding.quote_create, name="welding_quote_create"),
    path("welding/quotes/<int:quote_id>/", welding.quote_detail, name="welding_quote_detail"),
    path("welding/quotes/<int:quote_id>/pdf/", welding.quote_pdf, name="welding_quote_pdf"),
    path("welding/quotes/<int:quote_id>/accept/", welding.quote_accept, name="welding_quote_accept"),
    path("welding/quotes/<int:quote_id>/invoice/", welding.invoice_from_quote, name="welding_invoice_from_quote"),
    # New quote builder endpoints (AJAX)
    path("welding/quotes/<int:quote_id>/add-line-item/", welding.quote_add_line_item, name="welding_quote_add_line_item"),
    path("welding/quotes/<int:quote_id>/line-item/<int:item_id>/update/", welding.quote_update_line_item, name="welding_quote_update_line_item"),
    path("welding/quotes/<int:quote_id>/line-item/<int:item_id>/delete/", welding.quote_delete_line_item, name="welding_quote_delete_line_item"),
    path("welding/quotes/<int:quote_id>/add-cost/", welding.quote_add_cost, name="welding_quote_add_cost"),
    path("welding/quotes/<int:quote_id>/cost/<int:cost_id>/update/", welding.quote_update_cost, name="welding_quote_update_cost"),
    path("welding/quotes/<int:quote_id>/cost/<int:cost_id>/delete/", welding.quote_delete_cost, name="welding_quote_delete_cost"),
    path("welding/jobs/", welding.jobs_list, name="welding_jobs_list"),
    path("welding/jobs/<int:job_id>/", welding.job_detail, name="welding_job_detail"),
    path("welding/jobs/<int:job_id>/status/", welding.job_update_status, name="welding_job_update_status"),
    path("welding/invoices/", welding.invoices_list, name="welding_invoices_list"),
    path("welding/invoices/<int:invoice_id>/", welding.invoice_detail, name="welding_invoice_detail"),
    path("welding/reports/", welding.reports, name="welding_reports"),
    path("welding/simulator/", welding.job_simulator, name="welding_job_simulator"),
    path("welding/simulations/", welding.welding_simulations, name="welding_simulations"),
    path("welding/simulator/to-quote/", welding.simulator_to_quote, name="welding_simulator_to_quote"),
    # Phase 2: Welding intelligence
    path("welding/intelligence/", welding.workshop_intelligence, name="welding_intelligence"),
    path("welding/clients/", welding.client_management, name="welding_client_management"),
    
    # ==================== CAR HIRE VERTICAL ====================
    path("car_hire/dashboard/", car_hire.dashboard, name="car_hire_dashboard"),
    
    # Vehicles (Fleet)
    path("car_hire/vehicles/", car_hire.vehicles_list, name="car_hire_vehicles"),
    path("car_hire/vehicles/new/", car_hire.vehicle_add, name="car_hire_vehicle_add"),
    path("car_hire/vehicles/<int:vehicle_id>/", car_hire.vehicle_detail, name="car_hire_vehicle_detail"),
    path("car_hire/vehicles/<int:vehicle_id>/images/<int:image_pk>/delete/", car_hire.delete_hire_vehicle_image, name="car_hire_delete_vehicle_image"),
    path("car_hire/vehicles/<int:vehicle_id>/images/<int:image_pk>/set-cover/", car_hire.set_hire_cover_image, name="car_hire_set_cover_image"),
    
    # Trips / Bookings
    path("car_hire/trips/", car_hire.trips_list, name="car_hire_trips"),
    path("car_hire/trips/new/", car_hire.trip_add, name="car_hire_trip_add"),
    path("car_hire/trips/<int:trip_id>/", car_hire.trip_detail, name="car_hire_trip_detail"),
    path("car_hire/trips/<int:trip_id>/start/", car_hire.trip_start, name="car_hire_trip_start"),
    path("car_hire/trips/<int:trip_id>/complete/", car_hire.trip_complete, name="car_hire_trip_complete"),
    
    # Maintenance
    path("car_hire/maintenance/", car_hire.maintenance_list, name="car_hire_maintenance"),
    path("car_hire/maintenance/add/", car_hire.maintenance_add, name="car_hire_maintenance_add"),
    
    # Revenue
    path("car_hire/revenue/", car_hire.revenue_list, name="car_hire_revenue"),
    path("car_hire/revenue/add/", car_hire.revenue_add, name="car_hire_revenue_add"),
    
    # Costs
    path("car_hire/costs/", car_hire.costs_list, name="car_hire_costs"),
    path("car_hire/costs/add/", car_hire.costs_add, name="car_hire_costs_add"),
    
    # Fallback for businesses without a kind
    path("none/", fallback.no_business, name="no_business"),
]

# Car Dealer vertical — registered under /verticals/ for dashboard routing
if _HAS_CAR_DEALER and _car_dealer_module:
    urlpatterns += [
        path("car_dealer/dashboard/", _car_dealer_module.car_dealer_dashboard, name="car_dealer_dashboard"),
    ]

# Renewable Energy vertical (flagship)
if _HAS_ENERGY and _energy_module:
    urlpatterns += [
        path("energy/dashboard/",       _energy_module.dashboard,          name="energy_dashboard"),
        path("energy/sites/",            _energy_module.sites_list,          name="energy_sites"),
        path("energy/sites/new/",        _energy_module.site_create,         name="energy_site_create"),
        path("energy/sites/<int:site_id>/", _energy_module.site_detail,      name="energy_site_detail"),
        path("energy/sites/<int:site_id>/report/pdf/", _energy_module.site_report_pdf, name="energy_site_report_pdf"),
        path("energy/assets/",           _energy_module.assets_list,         name="energy_assets"),
        path("energy/assets/new/",       _energy_module.asset_create,        name="energy_asset_create"),
        path("energy/monitoring/",       _energy_module.monitoring,          name="energy_monitoring"),
        path("energy/maintenance/",      _energy_module.maintenance_list,    name="energy_maintenance"),
        path("energy/maintenance/log/",  _energy_module.maintenance_create,  name="energy_maintenance_create"),
        path("energy/forecasting/",      _energy_module.forecasting,         name="energy_forecasting"),
        path("energy/load-management/",  _energy_module.load_management,     name="energy_load_management"),
        path("energy/sizing/",           _energy_module.system_sizing_list,  name="energy_sizing_list"),
        path("energy/sizing/new/",       _energy_module.system_sizing_create, name="energy_sizing_create"),
        path("energy/sizing/<int:run_id>/", _energy_module.system_sizing_detail, name="energy_sizing_detail"),
        path("energy/sizing/<int:run_id>/pdf/", _energy_module.system_sizing_pdf, name="energy_sizing_pdf"),
        path("energy/sizing/<int:run_id>/clone/", _energy_module.system_sizing_clone, name="energy_sizing_clone"),
        path("energy/sizing/<int:run_id>/recalculate/", _energy_module.system_sizing_recalculate, name="energy_sizing_recalculate"),
        path("energy/economics/",        _energy_module.economics,           name="energy_economics"),
        path("energy/alerts/",           _energy_module.alerts_list,         name="energy_alerts"),
        path("energy/alerts/<int:alert_id>/resolve/", _energy_module.alert_resolve, name="energy_alert_resolve"),
        path("energy/alerts/scan/",      _energy_module.trigger_alert_scan,  name="energy_trigger_alerts"),
        path("energy/technicians/",      _energy_module.technicians,         name="energy_technicians"),
        path("energy/technicians/new/",  _energy_module.technician_visit_create, name="energy_technician_create"),
        path("energy/reports/",          _energy_module.reports,             name="energy_reports"),
        path("energy/api/reading/",      _energy_module.api_add_reading,     name="energy_api_reading"),
        # Phase 2: Scenario comparison
        path("energy/sizing/<int:run_id>/scenarios/", _energy_module.scenario_compare, name="energy_scenario_compare"),
        path("energy/scenarios/<str:group_id>/", _energy_module.scenario_view, name="energy_scenario_view"),
        # Phase 2: Proposal lifecycle
        path("energy/sizing/<int:run_id>/proposal/", _energy_module.proposal_update_status, name="energy_proposal_update"),
        # Phase 2: Portfolio command center
        path("energy/portfolio/", _energy_module.portfolio, name="energy_portfolio"),
        # Phase 2: Energy copilot
        path("energy/copilot/", _energy_module.copilot, name="energy_copilot"),
        # Phase 2: Data upload / ingestion
        path("energy/data-upload/", _energy_module.data_upload, name="energy_data_upload"),
        # Commerce: product catalog, stock-in, sales
        path("energy/products/",   _energy_module.energy_catalog,      name="energy_catalog"),
        path("energy/stock-in/",   _energy_module.energy_stock_in,     name="energy_stock_in"),
        path("energy/sell/",       _energy_module.energy_sell,         name="energy_sell"),
        path("energy/seed/",       _energy_module.energy_seed_catalog, name="energy_seed_catalog"),
        # Simulations — interactive scenario engine
        path("energy/simulations/", _energy_module.energy_simulations, name="energy_simulations"),
    ]
