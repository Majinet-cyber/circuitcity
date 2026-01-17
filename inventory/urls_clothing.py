# inventory/urls_clothing.py
"""
URL patterns for clothing store operations.
"""
from django.urls import path

from . import api_clothing_barcode, views_clothing, views_clothing_wizard

app_name = "clothing"

urlpatterns = [
    # Dashboard
    path("", views_clothing.clothing_dashboard, name="dashboard"),
    # Stock management
    path("stock/", views_clothing.stock_list, name="stock_list"),
    path("stock/archived/", views_clothing.archived_products, name="archived_products"),
    path("product/<int:product_id>/archive/", views_clothing.archive_product, name="archive_product"),
    path("product/<int:product_id>/restore/", views_clothing.restore_product, name="restore_product"),
    path("product/<int:product_id>/logs/", views_clothing.product_logs, name="product_logs"),
    # Sales
    path("sell/", views_clothing.sell_clothing, name="sell"),
    path("sales/", views_clothing.sales_list, name="sales_list"),
    
    # =========================================================================
    # NEW: Redesigned 2-Step Stock-In Wizard (replaces fragile 8-step wizard)
    # =========================================================================
    # Step A: Product Setup (name, category, stock mode, qty, price, size, brand)
    path("stockin/", views_clothing_wizard.step_a_product_setup, name="stockin_step_a"),
    path("stockin/step-a/", views_clothing_wizard.step_a_product_setup, name="stockin_step_a_alt"),
    # Step B: Barcodes (only for unique stock mode)
    path("stockin/barcodes/<str:draft_id>/", views_clothing_wizard.step_b_barcodes, name="stockin_step_b"),
    # AJAX APIs for barcode operations
    path("api/stockin/<str:draft_id>/add-barcode/", views_clothing_wizard.api_add_barcode, name="stockin_api_add_barcode"),
    path("api/stockin/<str:draft_id>/remove-barcode/", views_clothing_wizard.api_remove_barcode, name="stockin_api_remove_barcode"),
    path("api/stockin/<str:draft_id>/finalize/", views_clothing_wizard.api_finalize, name="stockin_api_finalize"),
    
    # =========================================================================
    # Legacy Barcode APIs (kept for backward compatibility with old wizard)
    # =========================================================================
    path(
        "api/check-barcode-duplicate/", api_clothing_barcode.check_barcode_duplicate_api, name="check_barcode_duplicate"
    ),
    path("api/barcode-batch/step1/", api_clothing_barcode.barcode_batch_step1_api, name="barcode_batch_step1"),
    path("api/barcode-batch/scan/", api_clothing_barcode.barcode_batch_scan_api, name="barcode_batch_scan"),
    path("api/fast-sell/lookup/", api_clothing_barcode.fast_sell_lookup_api, name="fast_sell_lookup"),
    path("api/fast-sell/create/", api_clothing_barcode.fast_sell_create_api, name="fast_sell_create"),
]
