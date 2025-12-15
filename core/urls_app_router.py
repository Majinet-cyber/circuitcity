# core/urls_app_router.py
"""
App router URL configuration for shared application routes.
This module provides routes under the /app/ prefix for cross-vertical features.
"""
from django.urls import path

# Import analytics views
from inventory import views_analytics

app_name = "app_router"

urlpatterns = [
    path("analytics/", views_analytics.analytics_dashboard, name="analytics"),
    # Analytics API endpoints
    path("analytics/api/kpis/", views_analytics.api_kpis, name="analytics_api_kpis"),
    path("analytics/api/sales_trend/", views_analytics.api_sales_trend, name="analytics_api_sales_trend"),
    path("analytics/api/profit_trend/", views_analytics.api_profit_trend, name="analytics_api_profit_trend"),
    path("analytics/api/payment_mix/", views_analytics.api_payment_mix, name="analytics_api_payment_mix"),
    path("analytics/api/top_products/", views_analytics.api_top_products, name="analytics_api_top_products"),
    path("analytics/api/top_agents/", views_analytics.api_top_agents, name="analytics_api_top_agents"),
    path("analytics/api/stock_overview/", views_analytics.api_stock_overview, name="analytics_api_stock_overview"),
    path("analytics/api/cost_breakdown/", views_analytics.api_cost_breakdown, name="analytics_api_cost_breakdown"),
    path("analytics/api/alerts/", views_analytics.api_alerts, name="analytics_api_alerts"),
    path("analytics/api/export_csv/", views_analytics.api_export_csv, name="analytics_api_export_csv"),
]

