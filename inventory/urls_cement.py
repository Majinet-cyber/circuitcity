# inventory/urls_cement.py
"""URL routing for Cement / Hardware & General Dealers vertical"""
from django.urls import path

from inventory.verticals import cement

app_name = "cement"

urlpatterns = [
    path("dashboard/", cement.dashboard, name="dashboard"),
    path("products/", cement.products_catalog, name="products_catalog"),
    path("products/<slug:slug>/", cement.product_detail, name="product_detail"),
    path("stock/", cement.stock_list, name="stock_list"),
    path("stock-in/", cement.stock_in, name="stock_in"),
    path("sell/", cement.sell, name="sell"),
    path("costs/", cement.costs, name="costs"),
    path("analytics/", cement.analytics, name="analytics"),
    path("sales/<int:sale_id>/undo/", cement.undo_sale, name="undo_sale"),
    path("sales/<int:sale_id>/edit/", cement.edit_sale, name="edit_sale"),
]
