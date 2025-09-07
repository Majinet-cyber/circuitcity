# inventory/urls.py
from django.urls import path, re_path
from django.views.generic import RedirectView
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from types import SimpleNamespace

from . import views

# Optional API helper module (inventory/api.py)
try:
    from . import api as _api
except Exception:
    _api = SimpleNamespace()

# Optional audit views module (inventory/views_audit.py)
try:
    from . import views_audit as _views_audit
except Exception:
    _views_audit = SimpleNamespace()

app_name = "inventory"

# ---------- helpers ----------
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

# ---------- resolve views safely ----------
_inventory_dashboard = _get_view("inventory_dashboard", views, msg="inventory_dashboard view missing")
_scan_in            = _get_view("scan_in",   views)
_scan_sold          = _get_view("scan_sold", views)
_scan_web           = _get_view("scan_web",  views)
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

# Orders (pages + APIs)
_place_order_page   = _get_view("place_order_page", views, msg="place order page not implemented")
_orders_list        = _get_view("orders_list", views, msg="orders list page not implemented")
_po_invoice         = _get_view("po_invoice", views, msg="invoice view missing")

# APIs present in views.py
_mark_sold_view     = _get_view("api_mark_sold",      views)
_time_checkin_view  = _get_view("api_time_checkin",   views)
_wallet_summary     = _get_view("api_wallet_summary", views)
_wallet_add_txn     = _get_view("api_wallet_add_txn", views)
_sales_trend_view   = _get_view("api_sales_trend",    views)
_top_models_view    = _get_view("api_top_models",     views)
_profit_bar_view    = _get_view("api_profit_bar",     views)
_value_trend_view   = _get_view("api_value_trend",    views)  # dashboard uses this
_agent_trend_view   = _get_view("api_agent_trend",    views)
_predictions_view   = _get_view("api_predictions",    views)
_cash_overview_view = _get_view("api_cash_overview",  views)
_alerts_view        = _get_view("api_alerts",         views)
_restock_heatmap    = _get_view("restock_heatmap_api", views)
_api_order_price    = _get_view("api_order_price",    views)
_api_stock_models   = _get_view("api_stock_models",   views)
_api_place_order    = _get_view("api_place_order",    views)

# Admin product endpoints (safe even if not implemented)
_api_product_create       = _get_view("api_product_create", views, msg="api_product_create missing")
_api_product_update_price = _get_view("api_product_update_price", views, msg="api_product_update_price missing")

# inventory/api.py modern endpoints (optional)
_api_task_submit  = _get_view("api_task_submit",  _api, msg="api_task_submit missing")
_api_task_status  = _get_view("api_task_status",  _api, msg="api_task_status missing")
_api_audit_verify = _get_view("api_audit_verify", _api, msg="api_audit_verify missing")

# Audit pages (optional views_audit.py)
_audit_verify = _get_view("verify_chain", _views_audit, msg="audit verify view missing")
_audit_list   = _get_view("audit_list",   _views_audit, msg="audit list view missing")
_audit_detail = _get_view("audit_detail", _views_audit, msg="audit detail view missing")
_audit_export = _get_view("audit_export_csv", _views_audit, msg="audit export view missing")

# Predictions proxy — prefer inventory.api if it exists, else views.api_predictions, else stub
def _predictions_proxy(request, *args, **kwargs):
    try:
        func = getattr(_api, "predictions_summary", None)
        if callable(func):
            return func(request, *args, **kwargs)
    except Exception:
        pass
    if callable(_predictions_view):
        return _predictions_view(request, *args, **kwargs)
    return JsonResponse({"ok": False, "error": "predictions endpoint not available"}, status=200)

# Helper redirect: list view with ?view=all
def _list_all_redirect(request):
    base = reverse("inventory:stock_list")
    qs = request.GET.copy()
    qs["view"] = "all"
    return redirect(f"{base}?{qs.urlencode()}")

# ---------- URL patterns ----------
urlpatterns = [
    # Make stock list the module home
    path("",                    _stock_list,            name="home"),
    path("list/",               _stock_list,            name="stock_list"),
    path("stock/",              _stock_list),  # alias
    path("list/all/",           _list_all_redirect,     name="stock_list_all"),
    path("stocks/",             RedirectView.as_view(pattern_name="inventory:stock_list", permanent=False)),

    # Dashboard
    path("dashboard/",          _inventory_dashboard,   name="inventory_dashboard"),
    path("dashboard",           _inventory_dashboard,   name="dashboard"),  # friendly name
    path("dash/",               RedirectView.as_view(pattern_name="inventory:inventory_dashboard", permanent=False)),

    # Scanning
    path("scan-in/",            _scan_in,               name="scan_in"),
    path("scan-sold/",          _scan_sold,             name="scan_sold"),
    path("scan-web/",           _scan_web,              name="scan_web"),
    path("in/",                 RedirectView.as_view(pattern_name="inventory:scan_in",   permanent=False), name="short_in"),
    path("sold/",               RedirectView.as_view(pattern_name="inventory:scan_sold", permanent=False), name="short_sold"),
    path("scan/",               RedirectView.as_view(pattern_name="inventory:scan_web",  permanent=False), name="short_scan"),

    # CSV export
    path("export/",             _export_csv,            name="export_csv"),
    path("dashboard/export-csv/", _dashboard_export,    name="dashboard_export_csv"),

    # Stock ops
    path("update/<int:pk>/",    _update_stock,          name="update_stock"),
    path("delete/<int:pk>/",    _delete_stock,          name="delete_stock"),
    path("restore/<int:pk>/",   _restore_stock,         name="restore_stock"),

    # Time & Wallet
    path("time/checkin/",       _time_checkin_page,     name="time_checkin_page"),
    path("time/logs/",          _time_logs,             name="time_logs"),
    path("wallet/",             _wallet_page,           name="wallet"),
    path("time/",               RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-checkin/",       RedirectView.as_view(pattern_name="inventory:time_checkin_page", permanent=False)),
    path("time-logs/",          RedirectView.as_view(pattern_name="inventory:time_logs",         permanent=False)),
    re_path(r"^timelogs/?$",    RedirectView.as_view(pattern_name="inventory:time_logs",         permanent=False),),

    # Health
    path("healthz/",            _healthz,               name="healthz"),
]

# Orders — pages + APIs that exist
urlpatterns += [
    path("place-order/",                 _place_order_page,   name="place_order_page"),
    path("orders/",                      _orders_list,        name="orders_list"),
    path("orders/<int:po_id>/invoice/",  _po_invoice,         name="po_invoice"),
    path("orders/<int:po_id>/download/", _po_invoice,         name="po_invoice_download"),

    # JSON APIs for ordering flow
    path("api/place-order/",             _api_place_order,    name="api_place_order"),
    path("api/order-price/<int:product_id>/", _api_order_price, name="api_order_price"),
    path("api/stock-models/",           _api_stock_models,   name="api_stock_models"),

    # Admin product management
    path("api/product/create/",         _api_product_create,       name="api_product_create"),
    path("api/product/update-price/",   _api_product_update_price, name="api_product_update_price"),
]

# Dashboard/API routes (modern)
urlpatterns += [
    path("api/predictions/",       _predictions_proxy,   name="predictions_summary"),
    path("api/alerts/",            _alerts_view,         name="api_alerts"),
    path("api/cash/",              _cash_overview_view,  name="api_cash_overview"),
    path("api/sales-trend/",       _sales_trend_view,    name="api_sales_trend"),
    path("api/top-models/",        _top_models_view,     name="api_top_models"),
    path("api/value-trend/",       _value_trend_view,    name="api_value_trend"),
    path("api/profit-bar/",        _profit_bar_view,     name="api_profit_bar"),
    path("api/agent-trend/",       _agent_trend_view,    name="api_agent_trend"),
    path("api/restock-heatmap/",   _restock_heatmap,     name="restock_heatmap_api"),
    path("api/wallet-summary/",    _wallet_summary,      name="api_wallet_summary"),
    path("api/wallet-txn/",        _wallet_add_txn,      name="api_wallet_add_txn"),
    path("api/mark-sold/",         _mark_sold_view,      name="api_mark_sold"),
    path("api/time-checkin/",      _time_checkin_view,   name="api_time_checkin"),

    # NEW: async tasks + audit quick-verify
    path("api/task-submit/",       _api_task_submit,     name="api_task_submit"),
    path("api/task-status/",       _api_task_status,     name="api_task_status"),
    path("api/audit-verify/",      _api_audit_verify,    name="api_audit_verify"),
]

# Audit pages (if views_audit.py is present)
urlpatterns += [
    path("audit/verify/",          _audit_verify,        name="audit_verify"),
    path("audit/verify",           _audit_verify),  # no-slash fallback
    path("audit/",                 _audit_list,          name="audit_list"),
    path("audit/<int:pk>/",        _audit_detail,        name="audit_detail"),
    path("audit/<int:pk>",         _audit_detail),       # no-slash fallback
    path("audit/export.csv",       _audit_export,        name="audit_export_csv"),
]

# Legacy/compat aliases used by existing JS or older templates
urlpatterns += [
    # Underscore endpoints referenced in templates/JS
    path("api_sales_trend/",      _sales_trend_view),
    path("api_top_models/",       _top_models_view),
    path("api_value_trend/",      _value_trend_view),  # legacy alias
    path("api_profit_bar/",       _profit_bar_view),

    # Extra legacy regex aliases
    re_path(r"^api[-_]?predictions/?$",        _predictions_proxy),
    re_path(r"^api_predictions/?$",            _predictions_proxy),
    re_path(r"^api/ai[-_]?insights/?$",        _alerts_view),
    re_path(r"^api[_-]?sales[_-]?trend/?$",    _sales_trend_view),
    re_path(r"^api[_-]?top[_-]?models/?$",     _top_models_view),
    re_path(r"^api[_-]?value[_-]?trend/?$",    _value_trend_view),
    re_path(r"^api[_-]?profit[_-]?bar/?$",     _profit_bar_view),
    re_path(r"^api[_-]?agent[_-]?trend/?$",    _agent_trend_view),
    re_path(r"^api/mark[-_]?sold/?$",          _mark_sold_view),
    re_path(r"^api/time[-_]?checkin/?$",       _time_checkin_view),
]
