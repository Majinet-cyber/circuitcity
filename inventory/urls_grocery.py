# inventory/urls_grocery.py
"""
URL routing for Grocery vertical.
Simple vertical: Costs, Stock In, Sell, Dashboard, Analytics only.
NO agents, wallets, or timelogs.
"""
from django.urls import path
from . import views_grocery

app_name = "grocery"

urlpatterns = [
    # Dashboard (home)
    path("", views_grocery.grocery_dashboard, name="dashboard"),
    path("dashboard/", views_grocery.grocery_dashboard, name="home"),
    
    # Stock operations
    path("stock-in/", views_grocery.grocery_stock_in, name="stock_in"),
    path("products/", views_grocery.grocery_products, name="products"),
    
    # Sales
    path("sell/", views_grocery.grocery_sell, name="sell"),
    path("fast-sell/", views_grocery.grocery_fast_sell, name="fast_sell"),
    path("fast-sell/lookup/", views_grocery.grocery_fast_sell_lookup, name="fast_sell_lookup"),
    
    # Costs
    path("costs/", views_grocery.grocery_costs, name="costs"),
    
    # Analytics
    path("analytics/", views_grocery.grocery_analytics, name="analytics"),
]

