# cc/urls.py
from __future__ import annotations

import importlib
import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path, reverse, NoReverseMatch
from django.views.generic import RedirectView

from cc import views as core_views  # healthz, logout, etc.

log = logging.getLogger(__name__)

# ---------------- Helpers ----------------
def robots_txt(_request):
    return HttpResponse("User-agent: *\nDisallow: /", content_type="text/plain")


def root_redirect(request):
    """
    Try candidates in order; first that reverses wins.
    LOGIN_URL will handle auth bounce if needed.
    """
    candidates = (
        "inventory:inventory_dashboard",
        "dashboard:agent_dashboard",
        "inventory:stock_list",
        "admin:index",
        "login",  # alias -> accounts:login
    )
    for name in candidates:
        try:
            reverse(name)
            return redirect(name)
        except NoReverseMatch:
            continue
    return HttpResponse("No landing route configured.", status=501)


def safe_include(urlconf_dotted: str, *, label: str):
    """
    Try to include an app's urlconf. If it's missing, expose a tiny stub view so
    the project still boots (you'll see a 501 if you hit that root).
    """
    try:
        importlib.import_module(urlconf_dotted)
        return include(urlconf_dotted)
    except Exception:
        msg = f"{label} real urlconf unavailable -> using stub"
        try:
            print(f"[cc.urls] {msg}")
        except Exception:
            log.warning(msg)

        def _stub(_req, *_a, **_kw):
            return HttpResponse(f"{label} module not installed.", status=501)

        return _stub


def _try_import(path_fq: str, path_short: str | None = None):
    try:
        return importlib.import_module(path_fq)
    except Exception:
        if path_short:
            try:
                return importlib.import_module(path_short)
            except Exception:
                return None
        return None


# ---------- Exports & import (hard/required) ----------
try:
    from circuitcity.inventory.views_export import export_inventory_csv, export_audits_csv
    from circuitcity.inventory.views_import import import_opening_stock
except Exception as e:
    def _missing(_req, *_a, **_kw):
        return HttpResponse(f"Export/Import endpoint not available: {e}", status=503)
    export_inventory_csv = _missing
    export_audits_csv = _missing
    import_opening_stock = _missing

# Optional sales export
try:
    from circuitcity.sales.views_export import export_sales_csv  # optional
except Exception:
    export_sales_csv = None

# ---------- URL patterns ----------
urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    path("__admin__/", RedirectView.as_view(url="/admin/", permanent=True)),

    # Health / robots / favicon
    path("healthz/", core_views.healthz, name="healthz"),
    path("healthz", core_views.healthz),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.ico", permanent=False)),

    # Landing
    path("", root_redirect, name="root"),
]

# ---------------- Accounts (robust, always namespaced) ----------------
# Prefer fully-qualified circuitcity.accounts.urls to avoid PYTHONPATH shadowing.
_accounts_mod = _try_import("circuitcity.accounts.urls") or _try_import("accounts.urls")

if _accounts_mod and hasattr(_accounts_mod, "urlpatterns"):
    urlpatterns += [
        path("accounts/", include((_accounts_mod.urlpatterns, "accounts"), namespace="accounts")),
    ]
else:
    # Minimal fallback so {% url 'accounts:*' %} never crashes
    fallback_patterns = [
        path(
            "login/",
            auth_views.LoginView.as_view(template_name="accounts/login.html", redirect_authenticated_user=True),
            name="login",
        ),
        path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
        # what the sidebar expects
        path(
            "settings/",
            RedirectView.as_view(pattern_name="inventory:settings", permanent=False),
            name="settings_unified",
        ),
        # handy aliases used by some templates
        path(
            "profile/",
            RedirectView.as_view(pattern_name="accounts:settings_unified", permanent=False),
            name="profile",
        ),
        path(
            "signup/",
            RedirectView.as_view(url="/onboarding/", permanent=False),
            name="signup",
        ),
        # forgot/reset placeholders (alias typical names)
        path(
            "password/forgot/",
            RedirectView.as_view(pattern_name="accounts:login", permanent=False),
            name="forgot_password_request",
        ),
        path(
            "password/reset/",
            RedirectView.as_view(pattern_name="accounts:login", permanent=False),
            name="forgot_password_reset",
        ),
    ]
    urlpatterns += [path("accounts/", include((fallback_patterns, "accounts"), namespace="accounts"))]

# Project-level convenience aliases
urlpatterns += [
    path("login/",  RedirectView.as_view(pattern_name="accounts:login",  permanent=False), name="login"),
    path("logout/", core_views.logout_view, name="logout"),
    path("accounts/logout/", core_views.logout_view, name="accounts_logout"),

    # Legacy/common names used by some templates
    path("password/forgot/", RedirectView.as_view(pattern_name="accounts:forgot_password_request", permanent=False),
         name="password_forgot"),
    path("password/reset/",  RedirectView.as_view(pattern_name="accounts:forgot_password_reset",  permanent=False),
         name="password_reset_flow"),
    path("password_reset/",   RedirectView.as_view(pattern_name="accounts:forgot_password_reset",  permanent=False),
         name="password_reset"),
]

# CSV exports & import helpers
urlpatterns += [
    path("exports/inventory.csv",  export_inventory_csv,  name="export_inventory_csv"),
    path("exports/audits.csv",     export_audits_csv,     name="export_audits_csv"),
    path("imports/opening-stock/", import_opening_stock,  name="import_opening_stock"),
]

# ---------- Singular “/account/…” convenience redirects ----------
urlpatterns += [
    path("account/",                RedirectView.as_view(url="/accounts/", permanent=False)),
    path("account/login/",          RedirectView.as_view(pattern_name="accounts:login",  permanent=False)),
    path("account/logout/",         RedirectView.as_view(pattern_name="accounts:logout", permanent=False)),
    path("account/password/forgot/",RedirectView.as_view(pattern_name="accounts:forgot_password_request", permanent=False)),
    path("account/password/reset/", RedirectView.as_view(pattern_name="accounts:forgot_password_reset",  permanent=False)),
]

# ---------- Required app URLConfs ----------
urlpatterns += [
    path("dashboard/", include(("circuitcity.dashboard.urls", "dashboard"), namespace="dashboard")),
    path("inventory/", include(("circuitcity.inventory.urls", "inventory"),   namespace="inventory")),
    path("tenants/",   include(("circuitcity.tenants.urls",   "tenants"),     namespace="tenants")),
]

# ---------- Optional apps (safe includes) ----------
urlpatterns += [
    path("sales/",    safe_include("circuitcity.sales.urls",    label="sales")),
    path("wallet/",   safe_include("circuitcity.wallet.urls",   label="wallet")),
    path("billing/",  safe_include("circuitcity.billing.urls",  label="billing")),
    path("reports/",  safe_include("circuitcity.reports.urls",  label="reports")),
    path("layby/",    safe_include("circuitcity.layby.urls",    label="layby")),
    path("hq/",       safe_include("circuitcity.hq.urls",       label="hq")),
    path("insights/", safe_include("circuitcity.insights.urls", label="insights")),
]

# ---------- Optional sales CSV export top-level (if you want it exposed here)
if export_sales_csv:
    urlpatterns.append(path("exports/sales.csv", export_sales_csv, name="export_sales_csv"))

# ---------- Static & media in DEBUG ----------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
