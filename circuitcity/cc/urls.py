# cc/urls.py
from django.contrib import admin
from django.urls import path, include, reverse, NoReverseMatch
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.http import HttpResponse
from django.shortcuts import redirect

from cc import views as core_views  # healthz, logout, etc.

# ---- Exports & import ----
# Use the *project* dotted paths that match INSTALLED_APPS
# Inventory exports/imports are REQUIRED in your app, so import hard
try:
    from circuitcity.inventory.views_export import export_inventory_csv, export_audits_csv
    from circuitcity.inventory.views_import import import_opening_stock
except Exception as e:
    # If something is temporarily missing, degrade gracefully so urls.py still loads.
    def _missing(_req, *_a, **_kw):
        return HttpResponse(f"Export/Import endpoint not available: {e}", status=503)

    export_inventory_csv = _missing
    export_audits_csv = _missing
    import_opening_stock = _missing

# Sales export may not exist yet — import defensively
try:
    from circuitcity.sales.views_export import export_sales_csv  # optional
except Exception:
    export_sales_csv = None


def robots_txt(_request):
    """Disallow indexing during beta."""
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


def root_redirect(_request):
    """
    Try these in order; redirect to the first route that exists.
    LOGIN_URL will handle auth bounce if needed.
    """
    candidates = (
        "inventory:inventory_dashboard",
        "dashboard:agent_dashboard",
        "inventory:stock_list",
        "admin:index",
        "login",  # alias to accounts:login below
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

    # ---- Auth (project-level aliases that delegate to accounts app) ----
    path(
        "accounts/",
        include(("circuitcity.accounts.urls", "accounts"), namespace="accounts"),
    ),
    path(
        "login/",
        RedirectView.as_view(pattern_name="accounts:login", permanent=False),
        name="login",
    ),
    path("logout/", core_views.logout_view, name="logout"),
    path("accounts/logout/", core_views.logout_view, name="accounts_logout"),
    path(
        "password/forgot/",
        RedirectView.as_view(
            pattern_name="accounts:forgot_password_request", permanent=False
        ),
    ),
    path(
        "password/reset/",
        RedirectView.as_view(
            pattern_name="accounts:forgot_password_reset", permanent=False
        ),
    ),

    # ---- Health / robots / favicon ----
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False),
    ),

    # ---- Landing → robust redirect ----
    path("", root_redirect, name="root"),

    # ---- CSV exports & import helpers ----
    path("exports/inventory.csv", export_inventory_csv, name="export_inventory_csv"),
    path("exports/audits.csv", export_audits_csv, name="export_audits_csv"),
    path("imports/opening-stock/", import_opening_stock, name="import_opening_stock"),
]

# Optional sales export
if export_sales_csv:
    urlpatterns.append(
        path("exports/sales.csv", export_sales_csv, name="export_sales_csv")
    )

# ---- App URLConfs (namespaced) ----
urlpatterns += [
    path(
        "dashboard/",
        include(("circuitcity.dashboard.urls", "dashboard"), namespace="dashboard"),
    ),
    path(
        "inventory/",
        include(("circuitcity.inventory.urls", "inventory"), namespace="inventory"),
    ),
    path(
        "tenants/",
        include(("circuitcity.tenants.urls", "tenants"), namespace="tenants"),
    ),
]

# Keep sales optional if that app isn’t present yet
try:
    urlpatterns.append(
        path(
            "sales/",
            include(("circuitcity.sales.urls", "sales"), namespace="sales"),
        )
    )
except Exception:
    pass

# ---- Static & media in DEBUG (prod served by WhiteNoise) ----
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
