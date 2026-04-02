# inventory/urls_groceries.py
"""URL routing for Groceries vertical"""
from django.urls import path
from inventory.verticals import groceries

app_name = "groceries"

urlpatterns = [
    path("dashboard/", groceries.dashboard, name="dashboard"),
    path("stock/", groceries.stock_list, name="stock_list"),
    path("stock-in/", groceries.stock_in, name="stock_in"),
    path("products/add/", groceries.product_add, name="product_add"),
    path("sell/", groceries.sell, name="sell"),
    path("analytics/", groceries.analytics, name="analytics"),
    path("sales/<int:sale_id>/rollback/", groceries.rollback_sale, name="rollback_sale"),
    # Phase 2: Intelligence views
    path("intelligence/", groceries.inventory_intelligence, name="inventory_intelligence"),
    path("sales-analytics/", groceries.sales_analytics, name="sales_analytics"),
    path("restocking/", groceries.smart_restocking, name="smart_restocking"),
]
