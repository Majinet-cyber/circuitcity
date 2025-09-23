# circuitcity/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from importlib import import_module
from django.http import JsonResponse
from django.views.generic.base import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage

# Import inventory views for fallbacks
from inventory import views as inv_views

# =========================
# Inventory API fallbacks
# =========================
try:
    api_mod = import_module("inventory.api")

    prediction_view    = getattr(api_mod, "predictions_summary",
                          getattr(inv_views, "api_predictions"))

    value_trend_view   = getattr(api_mod, "api_value_trend",
                          getattr(inv_views, "api_value_trend", prediction_view))

    sales_trend_view   = getattr(api_mod, "api_sales_trend",
                          getattr(inv_views, "api_sales_trend", prediction_view))

    top_models_view    = getattr(api_mod, "api_top_models",
                          getattr(inv_views, "api_top_models", prediction_view))

    alerts_feed_view   = getattr(api_mod, "alerts_feed",
                          getattr(inv_views, "alerts_feed", prediction_view))

    stock_health_view  = getattr(api_mod, "api_stock_health",
                          getattr(inv_views, "api_stock_health", alerts_feed_view))

    # Newly surfaced APIs used by the scanner & time check-in pages
    mark_sold_view     = getattr(api_mod, "api_mark_sold",
                          getattr(inv_views, "api_mark_sold"))

    time_checkin_view  = getattr(api_mod, "api_time_checkin",
                          getattr(inv_views, "api_time_checkin"))

    # Wallet chip on dashboard (optional in some repos)
    wallet_summary_view = (
        getattr(api_mod, "wallet_summary", None)
        or getattr(api_mod, "api_wallet_summary", None)
        or getattr(inv_views, "wallet_summary", None)
        or getattr(inv_views, "api_wallet_summary", None)
    )
except Exception:
    # Extremely defensive fallbacks (no api module or import error)
    prediction_view    = getattr(inv_views, "api_predictions")
    value_trend_view   = getattr(inv_views, "api_value_trend", prediction_view)
    sales_trend_view   = getattr(inv_views, "api_sales_trend", prediction_view)
    top_models_view    = getattr(inv_views, "api_top_models", prediction_view)
    alerts_feed_view   = getattr(inv_views, "alerts_feed", prediction_view)
    stock_health_view  = getattr(inv_views, "api_stock_health", alerts_feed_view)

    # Scanner & time check-in fallbacks
    mark_sold_view     = getattr(inv_views, "api_mark_sold")
    time_checkin_view  = getattr(inv_views, "api_time_checkin")

    # Wallet summary optional fallback
    wallet_summary_view = (
        getattr(inv_views, "wallet_summary", None)
        or getattr(inv_views, "api_wallet_summary", None)
    )

# If wallet endpoint truly doesn't exist, provide a tiny safe stub so the UI doesn't 404
if wallet_summary_view is None:
    def wallet_summary_view(_request):
        return JsonResponse({"balance": 0})


# =========================
# Accounts (auth) hard aliases
# =========================
try:
    acc_views = import_module("accounts.views")
    # Prefer new names; fall back to legacy if present
    login_view_alias        = getattr(acc_views, "login_view", None)

    forgot_request_view     = (
        getattr(acc_views, "forgot_password_request_view", None)
        or getattr(acc_views, "forgot_password_request", None)
    )

    forgot_verify_view      = (
        getattr(acc_views, "forgot_password_verify_view", None)
        or getattr(acc_views, "forgot_password_reset", None)
    )
except Exception:
    acc_views = None
    login_view_alias = None
    forgot_request_view = None
    forgot_verify_view = None

# Define safe stubs if accounts views are missing so routes never 404
if login_view_alias is None:
    def login_view_alias(_request):
        return JsonResponse({"ok": False, "error": "login view unavailable"}, status=501)

if forgot_request_view is None:
    def forgot_request_view(_request):
        return JsonResponse({"ok": False, "error": "forgot-password view unavailable"}, status=501)

if forgot_verify_view is None:
    def forgot_verify_view(_request):
        return JsonResponse({"ok": False, "error": "password reset verify view unavailable"}, status=501)


urlpatterns = [
    path("admin/", admin.site.urls),

    # Public root assets (stop auth redirects & noisy logs)
    path(
        "favicon.ico",
        RedirectView.as_view(url=staticfiles_storage.url("favicon.ico"), permanent=True),
        name="favicon",
    ),
    path(
        "robots.txt",
        RedirectView.as_view(url=staticfiles_storage.url("robots.txt"), permanent=True),
        name="robots",
    ),

    # App (namespaced include so {% url 'inventory:...' %} works)
    path("inventory/", include(("inventory.urls", "inventory"), namespace="inventory")),

    # Accounts app (login, password reset, avatars, etc.)
    path("accounts/", include("accounts.urls")),

    # Global hard aliases so these NEVER 404 even if the app's urls module differs
    re_path(r"^login/?$",                    login_view_alias),
    path(   "password/forgot/",              forgot_request_view),
    path(   "password/reset/",               forgot_verify_view),

    # Insights app
    path("", include("insights.urls")),

    # ---- Hard aliases so these NEVER 404 even if the app's urls module differs ----
    re_path(r"^inventory/api/predictions/?$",        prediction_view),
    re_path(r"^inventory/api/predictions/v2/?$",     inv_views.api_predictions),
    re_path(r"^inventory/api/cash[-_]overview/?$",   inv_views.api_cash_overview),

    # New: Value/Profit/Cost/Revenue trend series (support several spellings)
    path(   "inventory/api/value_trend/",            value_trend_view),
    re_path(r"^inventory/api/value[_-]trend/?$",     value_trend_view),

    # Sales trend – support both legacy underscore and REST-y path with optional hyphen
    re_path(r"^inventory/api_sales_trend/?$",        sales_trend_view),
    path(   "inventory/api/sales_trend/",            sales_trend_view),
    re_path(r"^inventory/api/sales[-_]trend/?$",     sales_trend_view),

    # Top models – support both variants
    re_path(r"^inventory/api_top_models/?$",         top_models_view),
    path(   "inventory/api/top_models/",             top_models_view),
    re_path(r"^inventory/api/top[-_]models/?$",      top_models_view),

    # Alerts
    re_path(r"^inventory/api/alerts/?$",             alerts_feed_view),

    # Stock Health battery
    path(   "inventory/api/stock_health/",           stock_health_view),
    re_path(r"^inventory/api/stock[-_]health/?$",    stock_health_view),

    # Wallet summary
    path(   "inventory/api/wallet-summary/",         wallet_summary_view),
    re_path(r"^inventory/api/wallet[-_]summary/?$",  wallet_summary_view),

    # Scanner + time check-in
    re_path(r"^inventory/api/mark[-_]sold/?$",       mark_sold_view),
    re_path(r"^inventory/api/time[-_]checkin/?$",    time_checkin_view),
]
