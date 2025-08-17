# cc/urls.py
from django.contrib import admin
from django.urls import path, include, reverse, NoReverseMatch
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.http import HttpResponse
from django.shortcuts import redirect

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


def root_redirect(_request):
    """
    Be robust: try inventory dashboard first (primary app), then dashboard app,
    then inventory stock list, then admin, then login.
    """
    candidates = (
        "inventory:inventory_dashboard",
        "dashboard:agent_dashboard",
        "inventory:stock_list",
        "admin:index",
        "login",
    )
    for name in candidates:
        try:
            reverse(name)
            return redirect(name)
        except NoReverseMatch:
            continue
    return HttpResponse("No landing route configured.", status=501)


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

    # Serve favicon from STATIC (nice for browsers and uptime tools)
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),

    # ---- Landing → robust redirect (requires auth; LOGIN_URL will handle bounce) ----
    path("", root_redirect, name="root"),
]

# ---- Feature: CSV exports & import helpers ----
urlpatterns += [
    path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"),
    path("exports/audits.csv", export_audits_csv, name="export_audits_csv"),
    path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"),
]
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
