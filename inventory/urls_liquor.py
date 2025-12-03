# inventory/urls_liquor.py
"""
URL patterns for liquor store operations.
"""
from django.urls import path
from . import views_liquor
from . import views_liquor_inventory

app_name = "liquor"

urlpatterns = [
    # Inventory Dashboard
    path("inventory/", views_liquor_inventory.liquor_inventory_dashboard, name="inventory_dashboard"),
    
    # Stock Overview
    path("stock/", views_liquor.stock_overview, name="stock_overview"),
    path("stock/settings/", views_liquor.stock_settings, name="stock_settings"),
    path("stock/category/<str:category>/update-target/", views_liquor.update_category_target, name="update_category_target"),
    
    # Shifts
    path("shifts/start/", views_liquor.start_shift, name="start_shift"),
    path("shifts/<int:shift_id>/close/", views_liquor.close_shift, name="close_shift"),
    path("shifts/<int:shift_id>/report/", views_liquor.shift_report, name="shift_report"),
    path("api/shifts/active/", views_liquor.active_shift_status, name="active_shift_status"),
    
    # Sales
    path("sell/", views_liquor.sell_liquor, name="sell"),
    path("sales/", views_liquor.sales_list, name="sales_list"),
    path("api/product/<int:product_id>/pricing/", views_liquor.get_product_pricing, name="product_pricing"),
    
    # Credits
    path("credits/", views_liquor.credits_list, name="credits_list"),
    path("credit/<int:credit_id>/", views_liquor.credit_detail, name="credit_detail"),
    path("sale/<int:sale_id>/convert-to-credit/", views_liquor.convert_sale_to_credit, name="convert_to_credit"),
    path("credit/<int:credit_id>/submit-payment/", views_liquor.submit_credit_payment, name="submit_payment"),
    
    # Payments (Manager approval)
    path("payments/pending/", views_liquor.pending_payments, name="pending_payments"),
    path("payment/<int:payment_id>/approve/", views_liquor.approve_payment, name="approve_payment"),
    path("payment/<int:payment_id>/reject/", views_liquor.reject_payment, name="reject_payment"),
    
    # Stock edit requests
    path("product/<int:product_id>/request-edit/", views_liquor.request_stock_edit, name="request_stock_edit"),
    path("stock-requests/", views_liquor.stock_edit_requests, name="stock_edit_requests"),
]

