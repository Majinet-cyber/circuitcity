# inventory/urls_hardware.py
"""
URL routing for Hardware Store vertical.
Simple vertical: Costs, Stock In, Sell, Dashboard, Analytics only.
NO agents, wallets, or timelogs.
"""
from django.urls import path
from . import views_hardware

app_name = "hardware"

urlpatterns = [
    # Dashboard (home)
    path("", views_hardware.hardware_dashboard, name="dashboard"),
    path("dashboard/", views_hardware.hardware_dashboard, name="home"),
    
    # Stock operations
    path("stock-in/", views_hardware.hardware_stock_in, name="stock_in"),
    path("products/", views_hardware.hardware_products, name="products"),
    
    # Sales
    path("sell/", views_hardware.hardware_sell, name="sell"),
    path("sales/", views_hardware.hardware_sales, name="sales"),
    
    # Costs
    path("costs/", views_hardware.hardware_costs, name="costs"),
    
    # Analytics
    path("analytics/", views_hardware.hardware_analytics, name="analytics"),
    path("reports/", views_hardware.hardware_reports, name="reports"),
]

