# inventory/urls_pharmacy.py
"""
URL patterns for pharmacy operations.
"""
from django.urls import path
from django.shortcuts import redirect
from . import views_pharmacy

app_name = "pharmacy"

def _redirect_to_pharmacy_dashboard(request):
    """Redirect /pharmacy/ to the canonical pharmacy dashboard at /verticals/pharmacy/dashboard/"""
    return redirect("/verticals/pharmacy/dashboard/")

urlpatterns = [
    # Dashboard - redirect to canonical location
    path("", _redirect_to_pharmacy_dashboard, name="dashboard"),
    # Gamified vertical-aware flows
    path("stock-in/", views_pharmacy.pharmacy_stock_in_choice, name="stock_in_choice"),  # NEW: Landing page with Pharmacy/Cosmetics choice
    path("stock-in/catalog/save/", views_pharmacy.pharmacy_stock_in_catalog_save, name="stock_in_catalog_save"),  # API endpoint - MUST BE BEFORE generic catalog pattern
    path("stock-in/pharmacy/", views_pharmacy.pharmacy_stock_in_catalog, {"category": "pharmacy"}, name="stock_in_catalog_pharmacy"),  # Pharmacy catalog
    path("stock-in/cosmetics/", views_pharmacy.pharmacy_stock_in_catalog, {"category": "cosmetics"}, name="stock_in_catalog_cosmetics"),  # Cosmetics catalog
    path("stock-in/catalog/<str:category>/", views_pharmacy.pharmacy_stock_in_catalog, name="stock_in_catalog"),  # Generic catalog
    path("stock-in/custom/", views_pharmacy.pharmacy_stock_in, name="stock_in"),  # Custom/form-based flow
    path("stock-in/wizard/", views_pharmacy.pharmacy_stock_in_wizard, name="stock_in_wizard"),  # Wizard-based flow
    path("stock-in/legacy/", views_pharmacy.pharmacy_stock_in, name="stock_in_legacy"),  # Alias for compatibility
    path("sell/", views_pharmacy.pharmacy_sell, name="sell"),
    # Batch management (legacy/admin)
    path("batches/", views_pharmacy.batch_list, name="batch_list"),
    path("batches/create/", views_pharmacy.batch_create, name="batch_create"),
    path("batches/<int:batch_id>/edit/", views_pharmacy.batch_edit, name="batch_edit"),
    # Sales (legacy)
    path("sales/", views_pharmacy.sale_list, name="sale_list"),
    path("sales/create/", views_pharmacy.sale_create, name="sale_create"),
    # Manager tools: edit, delete, undo
    path("sales/<int:sale_id>/edit/", views_pharmacy.sale_edit, name="sale_edit"),
    path("sales/<int:sale_id>/delete/", views_pharmacy.sale_delete, name="sale_delete"),
    path("sales/<int:sale_id>/undo/", views_pharmacy.sale_undo, name="sale_undo"),
    # Alerts & Reports
    path("near-expiry/", views_pharmacy.near_expiry_list, name="near_expiry"),
    path("expired/", views_pharmacy.expired_list, name="expired"),
    path("low-stock/", views_pharmacy.low_stock_list, name="low_stock"),
    # Simple UI (NEW)
    path("stock-in/simple/", views_pharmacy.pharmacy_stock_in_simple, name="stock_in_simple"),
    path("sell/simple/", views_pharmacy.pharmacy_sell_simple, name="sell_simple"),
    path("fast-sell/", views_pharmacy.pharmacy_sell_simple, name="fast_sell"),  # Alias
    # API endpoints
    path("api/batch/<int:batch_id>/", views_pharmacy.api_batch_info, name="api_batch_info"),
    path("api/products/search/", views_pharmacy.api_product_search, name="api_product_search"),
    path("api/products-by-category/", views_pharmacy.api_products_by_category, name="api_products_by_category"),  # NEW: Get products filtered by category
    path("api/stock-in/", views_pharmacy.api_stock_in, name="api_stock_in"),
    path("api/sell/", views_pharmacy.api_sell, name="api_sell"),
    path("api/product-suggestions/add/", views_pharmacy.api_add_product_suggestion, name="api_add_product_suggestion"),  # NEW: Add suggested product to catalog
]
