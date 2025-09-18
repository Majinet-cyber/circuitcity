# circuitcity/inventory/urls.py
from __future__ import annotations

from types import SimpleNamespace

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import path, re_path, reverse, NoReverseMatch

# ---- Import app views (and optional modules) safely ----
try:
    from . import views
except Exception:
    views = SimpleNamespace()

try:
    from . import api as _api
except Exception:
    _api = SimpleNamespace()

try:
    from . import views_audit as _views_audit
except Exception:
    _views_audit = SimpleNamespace()

# ---- Role guards ----
try:
    from core.decorators import manager_required  # admin/manager lock
except Exception:
    def manager_required(view_func):
        return view_func

# ✅ Require a tenant for inventory pages (no-op if tenants app missing)
try:
    from tenants.utils import require_business
except Exception:
    def require_business(view_func):
        return view_func

app_name = "inventory"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _stub(msg: str):
    def _fn(_request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def _get_view(name: str, *sources, msg: str | None = None):
    for src in sources:
        fn = getattr(src, name, None)
        if callable(fn):
            return fn
    return _stub(msg or f"{name} endpoint not implemented")

def _get_any(names: tuple[str, ...], src, msg: str | None = None):
    for name in names:
        fn = getattr(src, name, None)
        if callable(fn):
            return fn
    return _stub(msg or f"{'/'.join(names)} endpoint not implemented")

# Best-effort reverse that tolerates missing namespaces
def _safe_reverse(view_name: str, *args, **kwargs) -> str | None:
    try:
        return reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        if ":" in view_name:
            # Try without namespace
            _, bare = view_name.split(":", 1)
            try:
                return reverse(bare, args=args, kwargs=kwargs)
            except NoReverseMatch:
                pass
    return None

# Fallback hardcoded paths (only used if reversing fails)
_FALLBACKS = {
    "inventory:stock_list": "/inventory/list/",
    "inventory:inventory_dashboard": "/inventory/dashboard/",
    "inventory:scan_in": "/inventory/scan-in/",
    "inventory:scan_sold": "/inventory/scan-sold/",
    "inventory:scan_web": "/inventory/scan-web/",
    # helpful fallbacks for orders
    "inventory:place_order_page": "/inventory/place-order/",
    "inventory:place_order": "/inventory/orders/new/",
}

def _redirect_to(view_name: str):
    def _v(request, *args, **kwargs):
        url = _safe_reverse(view_name, *args, **kwargs) or _FALLBACKS.get(view_name) or "/"
        return redirect(url)
    return _v

# ---------------------------------------------------------------------
# Resolve views safely
# ---------------------------------------------------------------------
_inventory_dashboard = _get_view("inventory_dashboard", views, msg="inventory_dashboard view missing")
_stock_list         = _get_view("stock_list", views)
_stock_detail       = _get_view("stock_detail", views)
_scan_in            = _get_view("scan_in", views)
_scan_sold          = _get_view("scan_sold", views)
_scan_web           = _get_view("scan_web", views)

_export_csv         = _get_view("export_csv", views)
_dashboard_export   = _get_view("dashboard_export_csv", views)

_update_stock       = _get_view("update_stock", views)
_delete_stock       = _get_view("delete_stock", views)
_restore_stock      = _get_view("restore_stock", views)

_time_checkin_page  = _get_view("time_checkin_page", views)
_time_logs          = _get_view("time_logs", views)
_wallet_page        = _get_view("wallet_page", views)

_healthz            = _get_view("healthz", views, msg="OK")

_settings_view      = _get_any(("settings_home", "settings"), views, msg="settings view missing")

_place_order_page   = _get_view("place_order_page", views, msg="place order page not implemented")
_orders_list        = _get_view("orders_list", views, msg="orders list page not implemented")
_po_invoice         = _get_view("po_invoice", views, msg="invoice view missing")

_mark_sold_view     = _get_view("api_mark_sold",      views)
_time_checkin_view  = _get_view("api_time_checkin",   views)
_wallet_summary     = _get_view("api_wallet_summary", views)
_wallet_add_txn     = _get_view("api_wallet_add_txn", views)
_sales_trend_view   = _get_view("api_sales_trend",    views)
_top_models_view    = _get_view("api_top_models",     views)
_profit_bar_view    = _get_view("api_profit_bar",     views)
_value_trend_view   = _get_view("api_value_trend",    views)
_agent_trend_view   = _get_view("api_agent_trend",    views)
_predictions_view   = _get_view("api_predictions",    views)
_cash_overview_view = _get_view("api_cash_overview",  views)
_alerts_view        = _get_view("api_alerts",         views)
_restock_heatmap    = _get_view("restock_heatmap_api", views)
_api_order_price    = _get_view("api_order_price",    views)
_api_stock_models   = _get_view("api_stock_models",   views)
_api_place_order    = _get_view("api_place_order",    views)

_api_product_create       = _get_view("api_product_create", views, msg="api_product_create missing")
_api_product_update_price = _get_view("api_product_update_price", views, msg="api_product_update_price missing")

_api_task_submit   = _get_view("api_task_submit",   _api, msg="api_task_submit missing")
_api_task_status   = _get_view("api_task_status",   _api, msg="api_task_status missing")
_api_audit_verify  = _get_view("api_audit_verify",  _api, msg="api_audit_verify missing")

_audit_home    = _get_view("audit_home",    _views_audit, _api, views)
_audit_verify  = _get_view("audit_verify",  _views_audit, _api, views)
_audit_list    = _get_view("audit_list",    _views_audit, _api, views)
_audit_detail  = _get_view("audit_detail",  _views_audit, _api, views)
_audit_export  = _get_view("audit_export",  _views_audit, _api, views)

# ---------------------------------------------------------------------
# Local redirect helpers
# ---------------------------------------------------------------------
def _list_all_redirect(request):
    base = _safe_reverse("inventory:stock_list") or _safe_reverse("stock_list") or "/inventory/list/"
    qs = request.GET.copy()
    qs["view"] = "all"
    join = "&" if "?" in base else "?"
    return redirect(f"{base}{join}{qs.urlencode()}")

def _home_redirect(_request):
    url = _safe_reverse("inventory:inventory_dashboard") or _safe_reverse("inventory_dashboard") or "/inventory/dashboard/"
    return redirect(url)

_need_biz = require_business

# ---------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------
urlpatterns = [
    path("", _home_redirect, name="home"),

    # Stock + dashboard (tenant required)
    path("list/",               _need_biz(_stock_list),          name="stock_list"),
    path("stock/",              _need_biz(_stock_list)),
    path("list/all/",           _need_biz(_list_all_redirect),   name="stock_list_all"),
    path("stocks/",             _redirect_to("inventory:stock_list")),

    path("dashboard/",          _need_biz(_inventory_dashboard), name="inventory_dashboard"),
    path("dashboard",           _need_biz(_inventory_dashboard), name="dashboard"),
    path("dash/",               _redirect_to("inventory:inventory_dashboard")),

    # Scanning
    path("scan-in/",            _need_biz(_scan_in),             name="scan_in"),
    path("scan-sold/",          _need_biz(_scan_sold),           name="scan_sold"),
    path("scan-web/",           _need_biz(_scan_web),            name="scan_web"),
    path("in/",                 _redirect_to("inventory:scan_in"),   name="short_in"),
    path("sold/",               _redirect_to("inventory:scan_sold"), name="short_sold"),
    path("scan/",               _redirect_to("inventory:scan_web"),  name="short_scan"),

    # CSV export
    path("export/",               _need_biz(_export_csv),        name="export_csv"),
    path("dashboard/export-csv/", _need_biz(_dashboard_export),  name="dashboard_export_csv"),

    # Stock ops
    path("update/<int:pk>/",    _need_biz(_update_stock),        name="update_stock"),
    path("delete/<int:pk>/",    _need_biz(_delete_stock),        name="delete_stock"),
    path("restore/<int:pk>/",   _need_biz(_restore_stock),       name="restore_stock"),

    # Time & Wallet (page links in inventory UI)
    path("time/checkin/",       _need_biz(_time_checkin_page),   name="time_checkin_page"),
    path("time/logs/",          _need_biz(_time_logs),           name="time_logs"),
    path("wallet/",             _need_biz(_wallet_page),         name="wallet"),

    # Settings (legacy redirect kept)
    path("settings/",           _redirect_to("accounts:settings_unified"), name="settings"),

    # Health
    path("healthz/",            _healthz,                        name="healthz"),
]

# Orders — pages + APIs (ADMIN/MANAGER ONLY)
urlpatterns += [
    # Current canonical route
    path("place-order/",                 manager_required(_need_biz(_place_order_page)),   name="place_order_page"),
    # 🔙 Back-compat alias for older templates/links
    path("orders/new/",                  manager_required(_need_biz(_place_order_page)),   name="place_order"),

    path("orders/",                      manager_required(_need_biz(_orders_list)),        name="orders_list"),
    path("orders/<int:po_id>/invoice/",  manager_required(_need_biz(_po_invoice)),         name="po_invoice"),
    path("orders/<int:po_id>/download/", manager_required(_need_biz(_po_invoice)),         name="po_invoice_download"),

    path("api/place-order/",                  manager_required(_need_biz(_api_place_order)),  name="api_place_order"),
    path("api/order-price/<int:product_id>/", manager_required(_need_biz(_api_order_price)),  name="api_order_price"),
    path("api/stock-models/",                 manager_required(_need_biz(_api_stock_models)), name="api_stock_models"),

    path("api/product/create/",         manager_required(_need_biz(_api_product_create)),       name="api_product_create"),
    path("api/product/update-price/",   manager_required(_need_biz(_api_product_update_price)), name="api_product_update_price"),
]

# Dashboard/API routes (modern)
urlpatterns += [
    path("api/predictions/",       _need_biz(_predictions_view),   name="predictions_summary"),
    path("api/alerts/",            _need_biz(_alerts_view),        name="api_alerts"),
    path("api/cash/",              _need_biz(_cash_overview_view), name="api_cash_overview"),
    path("api/sales-trend/",       _need_biz(_sales_trend_view),   name="api_sales_trend"),
    path("api/top-models/",        _need_biz(_top_models_view),    name="api_top_models"),
    path("api/value-trend/",       _need_biz(_value_trend_view),   name="api_value_trend"),
    path("api/profit-bar/",        _need_biz(_profit_bar_view),    name="api_profit_bar"),
    path("api/agent-trend/",       _need_biz(_agent_trend_view),   name="api_agent_trend"),
    path("api/restock-heatmap/",   _need_biz(_restock_heatmap),    name="restock_heatmap_api"),
    path("api/wallet-summary/",    _need_biz(_wallet_summary),     name="api_wallet_summary"),
    path("api/wallet-txn/",        _need_biz(_wallet_add_txn),     name="api_wallet_add_txn"),
    path("api/mark-sold/",         _need_biz(_mark_sold_view),     name="api_mark_sold"),
    path("api/time-checkin/",      _need_biz(_time_checkin_view),  name="api_time_checkin"),

    path("api/task-submit/",       _need_biz(_api_task_submit),    name="api_task_submit"),
    path("api/task-status/",       _need_biz(_api_task_status),    name="api_task_status"),
    path("api/audit-verify/",      _need_biz(_api_audit_verify),   name="api_audit_verify"),
]

# Audit pages
urlpatterns += [
    path("audit/verify/",          _need_biz(_audit_verify),        name="audit_verify"),
    path("audit/verify",           _need_biz(_audit_verify)),
    path("audit/",                 _need_biz(_audit_list),          name="audit_list"),
    path("audit/<int:pk>/",        _need_biz(_audit_detail),        name="audit_detail"),
    path("audit/<int:pk>",         _need_biz(_audit_detail)),
    path("audit/export.csv",       _need_biz(_audit_export),        name="audit_export_csv"),
]

# Legacy/compat aliases
urlpatterns += [
    path("api_sales_trend/",      _need_biz(_sales_trend_view)),
    path("api_top_models/",       _need_biz(_top_models_view)),
    path("api_value_trend/",      _need_biz(_value_trend_view)),
    path("api_profit_bar/",       _need_biz(_profit_bar_view)),

    re_path(r"^api[-_]?predictions/?$",        _need_biz(_predictions_view)),
    re_path(r"^api_predictions/?$",            _need_biz(_predictions_view)),
    re_path(r"^api/ai[-_]?insights/?$",        _need_biz(_alerts_view)),
    re_path(r"^api[_-]?sales[_-]?trend/?$",    _need_biz(_sales_trend_view)),
    re_path(r"^api[_-]?top[_-]?models/?$",     _need_biz(_top_models_view)),
    re_path(r"^api[_-]?value[_-]?trend/?$",    _need_biz(_value_trend_view)),
    re_path(r"^api[_-]?profit[_-]?bar/?$",     _need_biz(_profit_bar_view)),
    re_path(r"^api[_-]?agent[_-]?trend/?$",    _need_biz(_agent_trend_view)),
    re_path(r"^api/mark[-_]?sold/?$",          _need_biz(_mark_sold_view)),
    re_path(r"^api/time[-_]?checkin/?$",       _need_biz(_time_checkin_view)),
]
