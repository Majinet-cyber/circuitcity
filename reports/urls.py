# reports/urls.py
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings

from . import views, views_export, views_api

app_name = "reports"

urlpatterns = [
    # Main Reports Home (renders template + sets X-Template-Origin header)
    path("", views.reports_home, name="home"),

    # Back-compat alias: /reports/index/ -> /reports/
    path("index/", RedirectView.as_view(pattern_name="reports:home", permanent=False), name="index"),

    # -------------------------------
    # API (charts / tables)
    # -------------------------------
    path("api/sales-summary/",      views_api.sales_summary_api,      name="api_sales_summary"),
    path("api/profit-trend/",       views_api.profit_trend_api,       name="api_profit_trend"),
    path("api/agent-performance/",  views_api.agent_performance_api,  name="api_agent_performance"),
    path("api/inventory-velocity/", views_api.inventory_velocity_api, name="api_inventory_velocity"),
    path("api/ads-roi/",            views_api.ads_roi_api,            name="api_ads_roi"),

    # -------------------------------
    # Exports
    # -------------------------------
    path("export/sales.csv",             views_export.export_sales_csv,             name="export_sales_csv"),
    path("export/expenses.csv",          views_export.export_expenses_csv,          name="export_expenses_csv"),
    path("export/inventory.csv",         views_export.export_inventory_csv,         name="export_inventory_csv"),
    path("export/management-report.csv", views_export.export_management_report_csv, name="export_management_csv"),
]

# ðŸ”Ž DEBUG-only alias to easily see the headers from reports_home
# (Open DevTools â†’ Network â†’ Headers to view X-Template-Origin / X-Template-Name)
if settings.DEBUG:
    urlpatterns += [
        path("which/", views.reports_home, name="which"),
    ]


