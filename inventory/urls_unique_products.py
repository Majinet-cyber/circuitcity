# inventory/urls_unique_products.py
"""
URL patterns for Unique Products (Barcode/SKU-based inventory).
"""
from django.urls import path
from . import views_unique_products

app_name = "unique_products"

urlpatterns = [
    # List & Browse
    path("", views_unique_products.unique_products_list, name="list"),
    
    # Create
    path("create/", views_unique_products.unique_product_create, name="create"),
    
    # Stock In
    path("stock-in/", views_unique_products.unique_product_stock_in, name="stock_in"),
    
    # Sales History
    path("sales-history/", views_unique_products.unique_sales_history, name="sales_history"),
    
    # API
    path("api/lookup/", views_unique_products.api_lookup_unique_product, name="api_lookup"),
]

