# cc/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.http import HttpResponse

from cc import views as core_views  # home + healthz (+ optional legacy)

# ---- Exports & import (Phase 6/7) ----
from inventory.views_export import export_inventory_csv, export_audits_csv
from inventory.views_import import import_opening_stock

# Sales export may not exist yet — import defensively
try:
    from sales.views_export import export_sales_csv  # optional
except Exception:
    export_sales_csv = None  # route added only if available


def robots_txt(_request):
    """
    Disallow indexing during beta. If you later want indexing, swap this to allow.
    """
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


urlpatterns = [
    # ---- Django admin ----
    path("admin/", admin.site.urls),

    # ---- Auth ----
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    # you use a custom logout view in cc.views
    path("logout/", core_views.logout_view, name="logout"),
    path("accounts/logout/", core_views.logout_view, name="accounts_logout"),

    # ---- Health / Ops ----
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots_txt"),

    # ---- Landing → dashboard (requires auth; will bounce to LOGIN_URL) ----
    path("", RedirectView.as_view(pattern_name="dashboard:agent_dashboard", permanent=False), name="root"),

    # ---- Optional convenience routes if you keep them in cc.views ----
    # path("home/", core_views.home, name="home"),
    # path("legacy/", core_views.legacy, name="legacy"),

    # ---- Feature: CSV exports & import helpers ----
    path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"),
    path("exports/audits.csv", export_audits_csv, name="export_audits_csv"),
    path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"),
]

# Add sales export only if the view exists
if export_sales_csv:
    urlpatterns.append(path("exports/sales.csv", export_sales_csv, name="export_sales_csv"))

# ---- App URLConfs (namespaced) ----
# Include only if the apps have urls.py; wrap in try/except so missing modules don't break prod.
try:
    urlpatterns.append(path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")))
except Exception:
    pass

try:
    urlpatterns.append(path("inventory/", include(("inventory.urls", "inventory"), namespace="inventory")))
except Exception:
    pass

try:
    urlpatterns.append(path("sales/", include(("sales.urls", "sales"), namespace="sales")))
except Exception:
    pass

# ---- Static & media in DEBUG (prod handled by Nginx/Whitenoise) ----
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Serving STATIC_URL via Django in DEBUG is fine; Whitenoise handles it too.
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
