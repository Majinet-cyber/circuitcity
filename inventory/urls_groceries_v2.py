# inventory/urls_groceries_v2.py
"""
URL routing for Groceries V2 vertical (new stupid-simple flow)
Old routes in urls_groceries.py remain intact for zero regressions.
"""
from django.urls import path
from inventory.verticals import groceries_v2

app_name = 'groceries_v2'

urlpatterns = [
    # Dashboard
    path('dashboard/', groceries_v2.dashboard_v2, name='dashboard'),
    
    # Products
    path('products/', groceries_v2.product_list_v2, name='product_list'),
    path('products/add/', groceries_v2.product_add_v2, name='product_add'),
    
    # Stock In
    path('stock-in/', groceries_v2.stock_in_v2, name='stock_in'),
    path('stock-in/submit/', groceries_v2.stock_in_submit_v2, name='stock_in_submit'),
    
    # Sell
    path('sell/', groceries_v2.sell_v2, name='sell'),
    path('sell/submit/', groceries_v2.sell_submit_v2, name='sell_submit'),
    
    # Barcode scan (optional)
    path('scan/<str:scan_value>/', groceries_v2.scan_v2, name='scan'),
]

