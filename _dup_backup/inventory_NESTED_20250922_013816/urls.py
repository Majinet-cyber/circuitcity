# inventory/urls.py
from django.urls import path, re_path
from django.views.generic import RedirectView
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from types import SimpleNamespace

from . import views

# Try to import API module; if missing or broken, use empty namespace
try:
    from . import api as _api
except Exception:
    _api = SimpleNamespace()

app_name = "inventory"

# ---- helpers ---------------------------------------------------------------
def _stub(msg):
    def _fn(request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def _get_view(name, *sources, msg=None):
    for src in sources:
        fn = getattr(src, name, None)
        if callable(fn):
            return fn
    return _stub(msg or f"{name} endpoint not implemented")

# ---- page views (safe resolution, no AttributeError at import) -------------
_inventory_dashboard = _get_view("inventory_dashboard", views, msg="inventory_dashboard view missing")
_scan_in            = _get_view("scan_in",   views)
_scan_sold          = _get_view("scan_sold", views)
_scan_web           = _get_view("scan_web",  views)
_scan_unified       = getattr(views, "scan_unified", None) or _scan_web
_stock_list         = _get_view("stock_list", views)
_export_csv         = _get_view("export_csv", views)
_dashboard_export   = _get_view("dashboard_export_csv", views)
_update_stock       = _get_view("update_stock", views)
_delete_stock       = _get_view("delete_stock", views)
_restore_stock      = _get_view("restore_stock", views)
_time_checkin_page  = _get_view("time_checkin_page", views)
_time_logs          = _get_view("time_logs", views)
_wallet_page        = _get_view("wallet_page", views)
_healthz            = _get_view("healthz", views, msg="OK")

# ---- API views (prefer api.py, then views.py, else stub) -------------------
_alerts_view        = _get_view("alerts_feed",       _api, views)
_sales_trend_view   = _get_view("api_sales_trend",   _api, views)
_top_models_view    = _get_view("api_top_models",    _api, views)
_mark_sold_view     = _get_view("api_mark_sold",     _api, views)
_time_checkin_view  = _get_view("api_time_checkin",  _api, views)
_profit_bar_view    = _get_view("api_profit_bar",    views)
_wallet_summary     = _get_view("api_wallet_summary", views)
_wallet_add_txn     = _get_view("api_wallet_add_txn", views)
_restock_heatmap    = _get_view("restock_heatmap_api", views)

# Predictions proxy (never fail at import)
def _predictions_proxy(request, *args, **kwargs):
    try:
        fn = getattr(_api, "predictions_summary", None)
        if callable(fn):
            return fn(request, *args, **kwargs)
    except Exception:
        pass
    fn2 = getattr(views, "api_predictions", None)
    if callable(fn2):
        return fn2(request, *args, **kwargs)
    return JsonResponse({"ok": False, "error": "predictions endpoint not available"}, status=200)

# Helper redirect: list view with ?view=all
def _list_all_redirect(request):
    base = reverse("inventory:stock_list")
    qs = request.GET.copy()
    qs["view"] = "all"
    return redirect(f"{base}?{qs.urlencode()}")

# ---- URL patterns ----------------------------------------------------------
urlpatterns = [
    # Dashboard
    path("dashboard/", _inventory_dashboard, name="inventory_dashboard"),
    path("",   RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False), name="home"),
    path("dash/", RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),

    # Scanning
    path("scan-in/",   _scan_in,   name="scan_in"),
    path("scan-sold/", _scan_sold, name="scan_sold"),
    path("scan-web/",  _scan_web,  name="scan_web"),
    path("scanner/",   _scan_unified, name="scan_unified"),
    path("scan-unified/", RedirectView.as_view(pattern_name="inventory:scan_unified", permanent=False)),
    path("in/",   RedirectView.as_view(pattern_name="inventory:scan_in",   permanent=False), name="short_in"),
    path("sold/", RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="short_sold"),
    path("scan/", RedirectView.as_view(pattern_name="inventory:scan_unified", permanent=False), name="short_scan"),

    # Stock viewing
    path("list/",        _stock_list, name="stock_list"),
    path("list/all/",    _list_all_redirect, name="stock_list_all"),
    path("stocks/",      RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False)),

    # CSV export
    path("export/", _export_csv, name="export_csv"),
    path("dashboard/export-csv/", _dashboard_export, name="dashboard_export_csv"),

    # Stock ops
    path("update/<int:pk>/",  _update_stock,  name="update_stock"),
    path("delete/<int:pk>/",  _delete_stock,  name="delete_stock"),
    path("restore/<int:pk>/", _restore_stock, name="restore_stock"),

    # Time & Wallet
    path("time/checkin/", _time_checkin_page, name="time_checkin_page"),
    path("time/logs/",    _time_logs,         name="time_logs"),
    path("wallet/",       _wallet_page,       name="wallet"),
    path("time/",         RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-checkin/", RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-logs/",    RedirectView.as_view(pattern_name="inventory:time_logs",         permanent=False)),

    # Health
    path("healthz/", _healthz, name="healthz"),
]

# API & legacy aliases
urlpatterns += [
    path("api/predictions/", _predictions_proxy, name="predictions_summary"),
    path("api/alerts/",      _alerts_view,       name="alerts_feed"),
    path("api/sales-trend/", _sales_trend_view,  name="api_sales_trend"),
    path("api/top-models/",  _top_models_view,   name="api_top_models"),
    path("api/wallet-summary/", _wallet_summary, name="api_wallet_summary"),
    path("api/wallet-txn/",     _wallet_add_txn, name="api_wallet_add_txn"),
    path("api/restock-heatmap/", _restock_heatmap, name="restock_heatmap_api"),
    path("api/mark-sold/",    _mark_sold_view,    name="api_mark_sold"),
    path("api/time-checkin/", _time_checkin_view, name="api_time_checkin"),

    # Legacy fallbacks
    re_path(r"^api[-_]?predictions/?$", _predictions_proxy),
    re_path(r"^api_predictions/?$",      _predictions_proxy),
    re_path(r"^api/predictions/v2/?$",   _predictions_proxy, name="api_predictions_v2"),
    re_path(r"^api[_-]?sales[_-]?trend/?$",  _sales_trend_view),
    re_path(r"^api[_-]?profit[_-]?bar/?$",   _profit_bar_view),
    re_path(r"^api[_-]?top[_-]?models/?$",   _top_models_view),
    re_path(r"^api/mark[-_]?sold/?$",        _mark_sold_view),
    re_path(r"^api/time[-_]?checkin/?$",     _time_checkin_view),
]
