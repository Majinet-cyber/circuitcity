# ccreports/urls.py
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings
from . import views

app_name = "reports"

urlpatterns = [
    # Landing page for Reports (must RENDER, not redirect)
    path("", views.home, name="home"),
    # Back-compat alias
    path(
        "index/",
        RedirectView.as_view(pattern_name="reports:home", permanent=False),
        name="index",
    ),
    # Existing report pages
    path("sales/", views.sales_report, name="sales"),
    path("inventory/", views.inventory_report, name="inventory"),
    # New premium report pages (additive — no existing routes changed)
    path("pl/", views.pl_report, name="pl_report"),
    path("pl/pdf/", views.pl_report_pdf, name="pl_report_pdf"),
    path("executive/", views.executive_summary, name="executive_summary"),
    path("executive/pdf/", views.executive_summary_pdf, name="executive_summary_pdf"),
    path("credit-exposure/", views.credit_exposure_report, name="credit_exposure"),
]

# Debug helper: shows which templates each URL resolves to
if settings.DEBUG:
    urlpatterns += [
        path("which/", views.which_templates, name="which"),
    ]
