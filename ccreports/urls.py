# ccreports/urls.py
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings
from . import views

app_name = "reports"

urlpatterns = [
    # Landing page for Reports (must RENDER, not redirect)
    path("", views.home, name="home"),

    # Back-compat alias â†’ send /reports/index/ to /reports/
    path(
        "index/",
        RedirectView.as_view(pattern_name="reports:home", permanent=False),
        name="index",
    ),

    # Concrete report pages (these should render a template directly)
    path("sales/",     views.sales_report,     name="sales"),
    path("inventory/", views.inventory_report, name="inventory"),
]

# Debug helper: shows which templates each URL resolves to
if settings.DEBUG:
    urlpatterns += [
        path("which/", views.which_templates, name="which"),
    ]


