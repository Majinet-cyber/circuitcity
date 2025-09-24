# circuitcity/inventory/urls.py
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Iterable

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, path, reverse
from django.views.generic import TemplateView

# ---------------------------------------------------------------------
# Import page views (your real templates live here)
# ---------------------------------------------------------------------
try:
    from . import views
except Exception:
    views = SimpleNamespace()

# Optional dashboard-specific views
try:
    from . import views_dashboard
except Exception:
    views_dashboard = SimpleNamespace()

# ---------------------------------------------------------------------
# Import API modules (v2 preferred; then singular fallback; then legacy)
# ---------------------------------------------------------------------
def _import_optional(modname: str):
    try:
        return importlib.import_module(f".{modname}", package=__package__)
    except Exception:
        return SimpleNamespace()

_api_v2_primary = _import_optional("api_views")
_api_v2_alt = _import_optional("api_view")
_api_v2 = SimpleNamespace()
for _src in (_api_v2_primary, _api_v2_alt):
    for _k in dir(_src):
        if not _k.startswith("_"):
            setattr(_api_v2, _k, getattr(_src, _k))

try:
    from . import api as _api_legacy
except Exception:
    _api_legacy = SimpleNamespace()

# Optional audit views
try:
    from . import views_audit as _views_audit
except Exception:
    _views_audit = SimpleNamespace()

# ---------------------------------------------------------------------
# Guards (role / tenant)
# ---------------------------------------------------------------------
try:
    from core.decorators import manager_required  # manager/admin lock
except Exception:
    def manager_required(view_func):
        return view_func

try:
    from tenants.utils import require_business
except Exception:
    def require_business(view_func):
        return view_func

# Use this guard only for endpoints that truly require a selected business
_need_biz = require_business

app_name = "inventory"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _stub(msg: str):
    def _fn(_request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def _safe_reverse(view_name: str, *args, **kwargs) -> str | None:
    try:
        return reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        if ":" in view_name:
            _, bare = view_name.split(":", 1)
            try:
                return reverse(bare, args=args, kwargs=kwargs)
            except NoReverseMatch:
                pass
    return None

_FALLBACKS = {
    "inventory:stock_list": "/inventory/list/",
    "inventory:inventory_dashboard": "/inventory/dashboard/",
    "inventory:scan_in": "/inventory/scan-in/",
    "inventory:scan_sold": "/inventory/scan-sold/",
    "inventory:scan_web": "/inventory/scan-web/",
    "inventory:place_order_page": "/inventory/place-order/",
    "inventory:place_order": "/inventory/orders/new/",
}

def _redirect_to(view_name: str):
    def _v(request, *args, **kwargs):
        url = _safe_reverse(view_name, *args, **kwargs) or _FALLBACKS.get(view_name) or "/"
        return redirect(url)
    return _v

def _resolve_page(
    candidate_names: Iterable[str],
    template_name: str,
    missing_msg: str,
):
    """
    Prefer your objects in `views` (function or class with .as_view()).
    If none exist, fall back to a template so the page always renders.
    """
    for nm in candidate_names:
        obj = getattr(views, nm, None)
        if callable(obj):
            return obj
        if obj is not None and hasattr(obj, "as_view"):
            try:
                return obj.as_view()
            except Exception:
                pass
    return TemplateView.as_view(template_name=template_name) if template_name else _stub(missing_msg)

def _get_any(names: tuple[str, ...], *sources, msg: str | None = None):
    for src in sources:
        for name in names:
            fn = getattr(src, name, None)
            if callable(fn):
                return fn
            if fn is not None and hasattr(fn, "as_view"):
                try:
                    return fn.as_view()
                except Exception:
                    continue
    return _stub(msg or f"{'/'.join(names)} endpoint not implemented")

# ---------------------------------------------------------------------
# Single-source-of-truth glue for Stock List
# ---------------------------------------------------------------------
# All aliases we’ve seen in older codebases
_BIZ_KEYS = ("biz", "business", "business_id", "tenant", "tenant_id")
_LOC_KEYS = ("loc", "location", "location_id", "store", "store_id", "warehouse_id")

# Legacy session mirrors (set by middleware elsewhere)
_SESS_BIZ = ("active_business_id", "business_id", "tenant_id", "current_business_id")
_SESS_LOC = ("active_location_id", "location_id", "store_id", "current_location_id")

_VALID_STATUS = {"all", "available", "in_stock", "selling", "sold", "archived"}

def _derive_active_ids(request):
    """
    Pull active biz/location id from request attributes first (set by your ActiveContext middleware),
    then fall back to session, then to any GET alias already present.
    """
    # 1) Attributes (preferred)
    bid = getattr(request, "business_id", None)
    lid = getattr(request, "active_location_id", None)

    # 2) Session
    if bid is None:
        sess = getattr(request, "session", {}) or {}
        bid = next((sess.get(k) for k in _SESS_BIZ if sess.get(k) is not None), None)
    if lid is None:
        sess = getattr(request, "session", {}) or {}
        lid = next((sess.get(k) for k in _SESS_LOC if sess.get(k) is not None), None)

    # 3) Existing GET
    if bid is None:
        for k in _BIZ_KEYS:
            v = request.GET.get(k)
            if v:
                bid = v
                break
    if lid is None:
        for k in _LOC_KEYS:
            v = request.GET.get(k)
            if v:
                lid = v
                break
    return bid, lid

def _coerce_int(v):
    try:
        return int(v)
    except Exception:
        return v

def _stock_list_wrapper(view_func):
    """
    Wrap the stock list page so it always sees consistent business/location + sane filters.
    We don’t change the view’s code; we only normalize GET and mirror typical aliases.
    """
    def _wrapped(request, *args, **kwargs):
        # Only for GET page renders
        if request.method == "GET":
            bid, lid = _derive_active_ids(request)
            # Mutate a copy of the QueryDict
            qs = request.GET.copy()
            if bid is not None:
                bid = _coerce_int(bid)
                for key in _BIZ_KEYS:
                    qs[key] = bid
            if lid is not None:
                lid = _coerce_int(lid)
                for key in _LOC_KEYS:
                    qs[key] = lid

            # Normalize status (some templates show "AI" instead of "All")
            raw_status = (qs.get("status") or "").strip().lower()
            if raw_status in ("", "ai") or raw_status not in _VALID_STATUS:
                qs["status"] = "all"

            # Ensure view=all so nothing is hidden by a default
            if qs.get("view") not in ("all", "mine", "store"):
                qs["view"] = "all"

            # If something changed, redirect once with enriched QS
            if qs.urlencode() != request.GET.urlencode():
                return redirect(f"{request.path}?{qs.urlencode()}")

            try:
                print(
                    "INFO inventory.urls: stock_list context -> "
                    f"biz={bid} loc={lid} status={qs.get('status')} view={qs.get('view')}"
                )
            except Exception:
                pass

        return view_func(request, *args, **kwargs)
    return _wrapped

# ---------------------------------------------------------------------
# Resolve views safely
# ---------------------------------------------------------------------
_inventory_dashboard = _get_any(
    ("inventory_dashboard",), views_dashboard, views, msg="inventory_dashboard view missing"
)

# Prefer the **page view** first so /inventory/list/ renders HTML.
_stock_list = _get_any(
    ("stock_list", "inventory_list"),
    views, _api_v2, _api_legacy,
    msg="stock_list endpoint not implemented",
)

# Page views for Scan IN / Scan SOLD (HTML by default)
_scan_in_page_view = _get_any(("scan_in",), views,
                              msg="scan_in page view missing")
_scan_sold_page_view = _get_any(("scan_sold",), views,
                                msg="scan_sold page view missing")

# Tiny tester pages (fallback templates if page views are missing)
_scan_in_tester = _resolve_page(
    ("scan_in_page", "scan_in_view", "scan_in_form"),
    template_name="inventory/scan_in.html",
    missing_msg="scan_in page view missing",
)
_scan_sold_tester = _resolve_page(
    ("scan_sold_page", "scan_sold_view", "scan_sold_form"),
    template_name="inventory/scan_sold.html",
    missing_msg="scan_sold page view missing",
)
_place_order_page = _resolve_page(
    ("place_order_page", "place_order_view"),
    template_name="inventory/place_order.html",
    missing_msg="place order page not implemented",
)
_scan_web = _resolve_page(
    ("scan_web",),
    template_name="inventory/scan_web.html",
    missing_msg="scan_web page view missing",
)

_stock_detail = _get_any(("stock_detail",), views, msg="stock_detail page view missing")
_export_csv = _get_any(("export_csv",), views, msg="export_csv view missing")
_dashboard_export = _get_any(("dashboard_export_csv",), views, msg="dashboard_export view missing")

_update_stock = _get_any(("update_stock",), views, msg="update_stock view missing")
_delete_stock = _get_any(("delete_stock",), views, msg="delete_stock view missing")
_restore_stock = _get_any(("restore_stock",), views, msg="restore_stock view missing")

_time_checkin_page = _get_any(("time_checkin_page",), views, msg="time_checkin page view missing")
_time_logs = _resolve_page(
    ("time_logs",),
    template_name="inventory/time_logs.html",
    missing_msg="time_logs page view missing",
)
_wallet_page = _get_any(("wallet_page",), views, msg="wallet page view missing")

_healthz = _get_any(("healthz",), views, msg="OK")
_settings_view = _get_any(("settings_home", "settings"), views, msg="settings view missing")

_orders_list = _get_any(("orders_list",), views, msg="orders list page not implemented")
_po_invoice = _get_any(("po_invoice",), views, msg="invoice view missing")

# ---- API resolvers (require business) ----
_scan_in_api = _get_any(("scan_in", "api_scan_in"), _api_v2, _api_legacy, msg="scan_in API not implemented")
_scan_sold_api = _get_any(("scan_sold", "api_scan_sold"), _api_v2, _api_legacy, msg="scan_sold API not implemented")

_mark_sold_view = _get_any(("api_mark_sold",), _api_v2, _api_legacy, msg="api_mark_sold not implemented")
_time_checkin_view = _get_any(("api_time_checkin",), _api_v2, _api_legacy, msg="api_time_checkin not implemented")
_wallet_summary = _get_any(("api_wallet_summary",), _api_v2, _api_legacy, msg="api_wallet_summary not implemented")
_wallet_add_txn = _get_any(("api_wallet_add_txn",), _api_v2, _api_legacy, msg="api_wallet_add_txn not implemented")
_sales_trend_view = _get_any(("api_sales_trend", "sales_trend"), _api_v2, _api_legacy, msg="api_sales_trend not implemented")
_top_models_view = _get_any(("api_top_models",), _api_v2, _api_legacy, msg="api_top_models not implemented")
_profit_bar_view = _get_any(("api_profit_bar",), _api_v2, _api_legacy, msg="api_profit_bar not implemented")
_value_trend_view = _get_any(("value_trend", "api_value_trend", "api_sales_trend", "sales_trend"), _api_v2, _api_legacy, msg="api_value_trend not implemented")
_agent_trend_view = _get_any(("api_agent_trend",), _api_v2, _api_legacy, msg="api_agent_trend not implemented")
_predictions_view = _get_any(("api_predictions",), _api_v2, _api_legacy, msg="api_predictions not implemented")
_cash_overview_view = _get_any(("api_cash_overview",), _api_v2, _api_legacy, msg="api_cash_overview not implemented")
_alerts_view = _get_any(("api_alerts",), _api_v2, _api_legacy, msg="api_alerts not implemented")

# Heatmap: use the gateway that ALWAYS returns 200
_restock_heatmap = _get_any(("restock_heatmap", "restock_heatmap_api"), _api_v2, _api_legacy, msg="restock_heatmap not implemented")

_api_order_price = _get_any(("api_order_price",), _api_v2, _api_legacy, msg="api_order_price not implemented")
_api_stock_models = _get_any(("api_stock_models",), _api_v2, _api_legacy, msg="api_stock_models not implemented")
_api_place_order = _get_any(("api_place_order",), _api_v2, _api_legacy, msg="api_place_order not implemented")

# NEW: unify product ops (avoid NameError)
_api_product_create = _get_any(
    ("api_product_create", "product_create"),
    _api_v2, _api_legacy,
    msg="product_create not implemented"
)
_api_product_update_price = _get_any(
    ("api_product_update_price", "product_update_price", "update_price"),
    _api_v2, _api_legacy,
    msg="product_update_price not implemented"
)

# Optional audit endpoints/pages
_api_task_submit = _get_any(("api_task_submit",), _api_v2, _api_legacy, msg="api_task_submit missing")
_api_task_status = _get_any(("api_task_status",), _api_v2, _api_legacy, msg="api_task_status missing")
_api_audit_verify = _get_any(("api_audit_verify",), _api_v2, _api_legacy, msg="api_audit_verify missing")

_audit_verify = _get_any(("audit_verify",), _views_audit, views, msg="audit_verify page view missing")
_audit_list = _get_any(("audit_list",), _views_audit, views, msg="audit_list page view missing")
_audit_detail = _get_any(("audit_detail",), _views_audit, views, msg="audit_detail page view missing")
_audit_export = _get_any(("audit_export",), _views_audit, views, msg="audit_export page view missing")

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

# ---------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------
urlpatterns = [
    path("", _home_redirect, name="home"),

    # Stock + dashboard (require business)
    path("list/", _need_biz(_stock_list_wrapper(_stock_list)), name="stock_list"),
    path("stock/", _need_biz(_stock_list_wrapper(_stock_list))),
    path("list/all/", _need_biz(_stock_list_wrapper(_list_all_redirect)), name="stock_list_all"),
    path("stocks/", _redirect_to("inventory:stock_list")),

    path("dashboard/", _need_biz(_inventory_dashboard), name="inventory_dashboard"),
    path("dashboard", _need_biz(_inventory_dashboard), name="dashboard"),
    path("dash/", _redirect_to("inventory:inventory_dashboard")),

    # ---------------- Scanning ----------------
    # PAGE endpoints (require business) — HTML by default:
    path("scan-in/", _need_biz(_scan_in_page_view), name="scan_in"),
    path("scan-sold/", _need_biz(_scan_sold_page_view), name="scan_sold"),

    # API endpoints (JSON) stay under /api/:
    path("api/scan-in/", _need_biz(_scan_in_api), name="api_scan_in"),
    path("api/scan-sold/", _need_biz(_scan_sold_api), name="api_scan_sold"),

    # Tiny tester pages (fallback templates if page views missing):
    path("scan-in/page/", _scan_in_tester, name="scan_in_page"),
    path("scan-sold/page/", _scan_sold_tester, name="scan_sold_page"),
    path("scan-web/", _scan_web, name="scan_web"),

    # Short links
    path("in/", _redirect_to("inventory:scan_in"), name="short_in"),
    path("sold/", _redirect_to("inventory:scan_sold"), name="short_sold"),
    path("scan/", _redirect_to("inventory:scan_web"), name="short_scan"),

    # CSV export
    path("export/", _need_biz(_export_csv), name="export_csv"),
    path("dashboard/export-csv/", _need_biz(_dashboard_export), name="dashboard_export_csv"),

    # Stock ops
    path("update/<int:pk>/", _need_biz(_update_stock), name="update_stock"),
    path("delete/<int:pk>/", _need_biz(_delete_stock), name="delete_stock"),
    path("restore/<int:pk>/", _need_biz(_restore_stock), name="restore_stock"),

    # Time & Wallet
    path("time/checkin/", _need_biz(_time_checkin_page), name="time_checkin_page"),
    path("time/logs/", _need_biz(_time_logs), name="time_logs"),
    path("wallet/", _need_biz(_wallet_page), name="wallet"),

    # Settings
    path("settings/", _redirect_to("accounts:settings_unified"), name="settings"),

    # Health
    path("healthz/", _get_any(("healthz",), views, msg="OK"), name="healthz"),
]

# Orders — pages + APIs (ADMIN/MANAGER ONLY, require business)
urlpatterns += [
    path("place-order/", manager_required(_need_biz(_place_order_page)), name="place_order_page"),
    path("orders/new/", manager_required(_need_biz(_place_order_page)), name="place_order"),
    path("orders/",
         manager_required(_need_biz(_get_any(('orders_list',), views, msg='orders list page not implemented'))),
         name="orders_list"),
    path("orders/<int:po_id>/invoice/", manager_required(_need_biz(_po_invoice)), name="po_invoice"),
    path("orders/<int:po_id>/download/", manager_required(_need_biz(_po_invoice)), name="po_invoice_download"),

    path("api/place-order/", manager_required(_need_biz(_api_place_order)), name="api_place_order"),
    path("api/order-price/<int:product_id>/", manager_required(_need_biz(_api_order_price)), name="api_order_price"),
    path("api/stock-models/", manager_required(_need_biz(_api_stock_models)), name="api_stock_models"),

    # unified names to avoid NameError at import time
    path("api/product/create/", manager_required(_need_biz(_api_product_create)), name="api_product_create"),
    path("api/product/update-price/", manager_required(_need_biz(_api_product_update_price)),
         name="api_product_update_price"),
]

# Dashboard/API routes (modern) — all require business
urlpatterns += [
    path("api/predictions/", _need_biz(_predictions_view), name="predictions_summary"),
    path("api/alerts/", _need_biz(_alerts_view), name="api_alerts"),
    path("api/cash/", _need_biz(_cash_overview_view), name="api_cash_overview"),
    path("api/sales-trend/", _need_biz(_sales_trend_view), name="api_sales_trend"),
    path("api/top-models/", _need_biz(_top_models_view), name="api_top_models"),
    path("api/value-trend/", _need_biz(_value_trend_view), name="api_value_trend"),
    path("api/profit-bar/", _need_biz(_profit_bar_view), name="api_profit_bar"),
    path("api/agent-trend/", _need_biz(_agent_trend_view), name="api_agent_trend"),
    path("api/restock-heatmap/", _need_biz(_restock_heatmap), name="restock_heatmap_api"),
    path("api/wallet-summary/", _need_biz(_wallet_summary), name="api_wallet_summary"),
    path("api/wallet-txn/", _need_biz(_wallet_add_txn), name="api_wallet_add_txn"),
    path("api/mark-sold/", _need_biz(_mark_sold_view), name="api_mark_sold"),
    path("api/time-checkin/", _need_biz(_time_checkin_view), name="api_time_checkin"),

    path("api/task-submit/", _need_biz(_api_task_submit), name="api_task_submit"),
    path("api/task-status/", _need_biz(_api_task_status), name="api_task_status"),
    path("api/audit-verify/", _need_biz(_api_audit_verify), name="api_audit_verify"),
]
