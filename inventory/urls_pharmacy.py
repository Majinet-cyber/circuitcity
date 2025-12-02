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
    
    # Batch management
    path("batches/", views_pharmacy.batch_list, name="batch_list"),
    path("batches/create/", views_pharmacy.batch_create, name="batch_create"),
    path("batches/<int:batch_id>/edit/", views_pharmacy.batch_edit, name="batch_edit"),
    
    # Sales
    path("sales/", views_pharmacy.sale_list, name="sale_list"),
    path("sales/create/", views_pharmacy.sale_create, name="sale_create"),
    
    # Alerts & Reports
    path("near-expiry/", views_pharmacy.near_expiry_list, name="near_expiry"),
    path("expired/", views_pharmacy.expired_list, name="expired"),
    path("low-stock/", views_pharmacy.low_stock_list, name="low_stock"),
    
    # API endpoints
    path("api/batch/<int:batch_id>/", views_pharmacy.api_batch_info, name="api_batch_info"),
]

