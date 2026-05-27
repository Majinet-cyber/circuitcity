# inventory/urls_mixed_retail.py
"""URL routing for Mixed Retail vertical."""
from django.urls import path

from inventory.verticals import mixed_retail

app_name = "mixed_retail"

urlpatterns = [
    path("dashboard/", mixed_retail.dashboard, name="dashboard"),
    path("products/", mixed_retail.products_list, name="products"),
    path("products/add/", mixed_retail.product_add, name="product_add"),
    path("products/<int:product_id>/edit/", mixed_retail.product_edit, name="product_edit"),
    path("stock-in/", mixed_retail.stock_in, name="stock_in"),
    path("sell/", mixed_retail.sell, name="sell"),
    path("sales/", mixed_retail.sales_history, name="sales"),
    path("expenses/", mixed_retail.expenses, name="expenses"),
    path("departments/", mixed_retail.departments, name="departments"),
    path("reports/", mixed_retail.reports, name="reports"),
    path("api/products/", mixed_retail.api_product_lookup, name="api_products"),
    path("api/categories/", mixed_retail.api_categories, name="api_categories"),
]
