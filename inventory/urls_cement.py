# inventory/urls_cement.py
"""
URL routing for Cement vertical.
Simple vertical: Costs, Stock In, Sell, Dashboard, Analytics only.
NO agents, wallets, or timelogs.
"""
from django.urls import path
from . import views_cement

app_name = "cement"

urlpatterns = [
    # Dashboard (home)
    path("", views_cement.cement_dashboard, name="dashboard"),
    path("dashboard/", views_cement.cement_dashboard, name="home"),
    
    # Stock operations
    path("stock-in/", views_cement.cement_stock_in, name="stock_in"),
    path("products/", views_cement.cement_products, name="products"),
    
    # Sales
    path("sell/", views_cement.cement_sell, name="sell"),
    path("sales/", views_cement.cement_sales, name="sales"),
    
    # Costs
    path("costs/", views_cement.cement_costs, name="costs"),
    
    # Analytics
    path("analytics/", views_cement.cement_analytics, name="analytics"),
    path("reports/", views_cement.cement_reports, name="reports"),
]

