# inventory/urls_butchery.py
"""URL routing for Butchery vertical."""
from django.urls import path

from inventory.verticals import butchery

app_name = "butchery"

urlpatterns = [
    path("dashboard/", butchery.dashboard, name="dashboard"),
    path("products/", butchery.products, name="products"),
    path("products/add/", butchery.product_add, name="product_add"),
    path("products/<int:product_id>/edit/", butchery.product_edit, name="product_edit"),
    path("intake/", butchery.intake, name="intake"),
    path("sell/", butchery.sell, name="sell"),
    path("sales/", butchery.sales, name="sales"),
    path("expenses/", butchery.expenses, name="expenses"),
    path("reports/", butchery.reports, name="reports"),
]
