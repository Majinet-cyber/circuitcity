# reports/urls.py
"""
Reports URLs - delegates to ccreports views.
This module exists for backward compatibility; actual views are in ccreports/.
"""
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings

# Import views from ccreports
try:
    from ccreports import views
except ImportError:
    # Fallback if ccreports not available
    from django.http import HttpResponse
    def _unavailable(request):
        return HttpResponse("Reports module is not available.", status=503)
    
    class views:  # type: ignore
        home = _unavailable
        sales_report = _unavailable
        inventory_report = _unavailable
        which_templates = _unavailable

# Import export views
try:
    from . import views_export
except ImportError:
    views_export = None  # type: ignore

app_name = "reports"

urlpatterns = [
    # Landing page for Reports (must RENDER, not redirect)
    path("", views.home, name="home"),
    
    # Back-compat alias → send /reports/index/ to /reports/
    path(
        "index/",
        RedirectView.as_view(pattern_name="reports:home", permanent=False),
        name="index",
    ),
    
    # Concrete report pages
    path("sales/", views.sales_report, name="sales"),
    path("sales/pdf/", views.sales_report_pdf, name="sales_pdf"),
    path("inventory/", views.inventory_report, name="inventory"),
    path("inventory/pdf/", views.inventory_report_pdf, name="inventory_pdf"),
    # New premium report pages (additive — no existing routes changed)
    path("pl/", views.pl_report, name="pl_report"),
    path("pl/pdf/", views.pl_report_pdf, name="pl_report_pdf"),
    path("executive/", views.executive_summary, name="executive_summary"),
    path("executive/pdf/", views.executive_summary_pdf, name="executive_summary_pdf"),
    path("credit-exposure/", views.credit_exposure_report, name="credit_exposure"),
]

# Monthly export endpoints (canonical patterns)
if views_export:
    urlpatterns += [
        path("export/sales/", views_export.export_monthly_sales, name="export_monthly_sales"),
        path("export/costs/", views_export.export_monthly_costs, name="export_monthly_costs"),
        path("export/summary/", views_export.export_monthly_summary, name="export_monthly_summary"),
    ]

# Debug helper: shows which templates each URL resolves to
if settings.DEBUG:
    urlpatterns += [
        path("which/", views.which_templates, name="which"),
    ]
