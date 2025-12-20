# inventory/urls_pharmacy.py
"""
URL patterns for pharmacy operations.
"""
from django.urls import path
from . import views_pharmacy

app_name = "pharmacy"

urlpatterns = [
    # Dashboard
    path("", views_pharmacy.pharmacy_dashboard, name="dashboard"),
    
    # Gamified vertical-aware flows
    path("stock-in/", views_pharmacy.pharmacy_stock_in_wizard, name="stock_in"),  # NEW: Wizard-based flow
    path("stock-in/wizard/", views_pharmacy.pharmacy_stock_in_wizard, name="stock_in_wizard"),  # Explicit wizard route
    path("stock-in/legacy/", views_pharmacy.pharmacy_stock_in, name="stock_in_legacy"),  # Fallback form
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
    
    # API endpoints
    path("api/batch/<int:batch_id>/", views_pharmacy.api_batch_info, name="api_batch_info"),
]

