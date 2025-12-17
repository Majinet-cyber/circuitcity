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
    path("inventory/", views.inventory_report, name="inventory"),
]

# Debug helper: shows which templates each URL resolves to
if settings.DEBUG:
    urlpatterns += [
        path("which/", views.which_templates, name="which"),
    ]
