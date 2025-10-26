# inventory/urls.py
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Iterable, Optional

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, path, re_path, reverse
from django.views.generic import TemplateView, RedirectView
from django.contrib.auth.decorators import login_required

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

# NEW: optional quick-sell page view
try:
    from .views_sell import sell_quick_page as _sell_quick_page
except Exception:
    _sell_quick_page = TemplateView.as_view(template_name="inventory/sell_quick.html")

# ---------------------------------------------------------------------
# Import API modules (prefer api_views)
# ---------------------------------------------------------------------
def _import_optional(modname: str):
    try:
        return importlib.import_module(f".{modname}", package=__package__)
    except Exception:
        return SimpleNamespace()

# Primary (v2) sources
_api_v2_primary = _import_optional("api_views")
_api_v2_alt = _import_optional("api_view")

# Merge v2 sources into one namespace
_api_v2 = SimpleNamespace()
for _src in (_api_v2_primary, _api_v2_alt):
    for _k in dir(_src):
        if not _k.startswith("_"):
            setattr(_api_v2, _k, getattr(_src, _k))

# Legacy API fallback
try:
    from . import api as _api_legacy
except Exception:
    _api_legacy = SimpleNamespace()

# Optional audit views
try:
    from . import views_audit as _views_audit
except Exception:
    _views_audit = SimpleNamespace()

# Optional Docs (Invoices/Quotations) module
try:
    from . import views_docs as _docs
except Exception:
    _docs = SimpleNamespace()

# ---------------------------------------------------------------------
# Guards (role / tenant)
# ---------------------------------------------------------------------
try:
    from core.decorators import manager_required
except Exception:
    def manager_required(view_func):
        return view_func

try:
    from tenants.utils import require_business
except Exception:
    def require_business(view_func):
        return view_func

_need_biz = require_business
app_name = "inventory"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _stub(msg: str):
    def _fn(_request, *args, **kwargs):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _fn

def _safe_reverse(view_name: str, *args, **kwargs) -> Optional[str]:
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
    "product_list": "/inventory/list/",
    "inventory:inventory_dashboard": "/inventory/dashboard/",
    "inventory:scan_in": "/inventory/scan-in/",
    "inventory:scan_sold": "/inventory/scan-sold/",
    "inventory:scan_web": "/inventory/scan-web/",
    "inventory:place_order_page": "/inventory/place-order/",
    "inventory:place_order": "/inventory/orders/new/",
    "inventory:product_create": "/inventory/products/new/",
}

def _redirect_to(view_name: str):
    def _v(request, *args, **kwargs):
        url = _safe_reverse(view_name, args, kwargs) or _FALLBACKS.get(view_name) or "/"
        return redirect(url)
    return _v

def _forward_to_root_login(request, *args, **kwargs):
    qs = request.META.get("QUERY_STRING", "")
    url = "/login/"
    if qs:
        url = f"{url}?{qs}"
    return redirect(url)

def _resolve_page(candidate_names: Iterable[str], template_name: str, missing_msg: str):
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
# Stock-list glue (+ keys used by product routing)
# ---------------------------------------------------------------------
_BIZ_KEYS = ("biz", "business", "business_id", "tenant", "tenant_id")
_LOC_KEYS = ("loc", "location", "location_id", "store", "store_id", "warehouse_id")

_SESS_BIZ = ("active_business_id", "business_id", "tenant_id", "current_business_id")
_SESS_LOC = ("active_location_id", "location_id", "store_id", "current_location_id")

_VALID_STATUS = {"all", "available", "in_stock", "selling", "sold", "archived"}

def _derive_active_ids(request):
    bid = getattr(request, "business_id", None)
    lid = getattr(request, "active_location_id", None)

    if bid is None:
        sess = getattr(request, "session", {}) or {}
        bid = next((sess.get(k) for k in _SESS_BIZ if sess.get(k) is not None), None)
    if lid is None:
        sess = getattr(request, "session", {}) or {}
        lid = next((sess.get(k) for k in _SESS_LOC if sess.get(k) is not None), None)

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
    def _wrapped(request, *args, **kwargs):
        if request.method == "GET":
            bid, lid = _derive_active_ids(request)
            qs = request.GET.copy()
            if bid is not None:
                bid = _coerce_int(bid)
                for key in _BIZ_KEYS:
                    qs[key] = bid
            if lid is not None:
                lid = _coerce_int(lid)
                for key in _LOC_KEYS:
                    qs[key] = lid

            raw_status = (qs.get("status") or "").strip().lower()
            if raw_status in ("", "ai") or raw_status not in _VALID_STATUS:
                qs["status"] = "all"

            if qs.get("view") not in ("all", "mine", "store"):
                qs["view"] = "all"

            if qs.urlencode() != request.GET.urlencode():
                return redirect(f"{request.path}?{qs.urlencode()}")

        return view_func(request, *args, **kwargs)
    return _wrapped

# ---------------------------------------------------------------------
# Resolve views safely
# ---------------------------------------------------------------------
_inventory_dashboard = _get_any(("inventory_dashboard",), views_dashboard, views, msg="inventory_dashboard view missing")
_stock_list = _get_any(("stock_list", "inventory_list"), views, _api_v2, _api_legacy, msg="stock_list endpoint not implemented")

_scan_in_page_view = _resolve_page(
    ("scan_in", "scan_in_page", "scan_in_view", "scan_in_form"),
    template_name="inventory/scan_in.html",
    missing_msg="scan_in page view missing",
)
_scan_sold_page_view = _resolve_page(
    ("scan_sold", "scan_sold_page", "scan_sold_view", "scan_sold_form"),
    template_name="inventory/scan_sold.html",
    missing_msg="scan_sold page view missing",
)

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
_place_order_page = _resolve_page(("place_order_page", "place_order_view"),
                                  template_name="inventory/place_order.html",
                                  missing_msg="place order page not implemented")
_scan_web = _resolve_page(("scan_web",), template_name="inventory/scan_web.html", missing_msg="scan_web page view missing")

_stock_detail = _get_any(("stock_detail",), views, msg="stock_detail page view missing")
_export_csv = _get_any(("export_csv",), views, msg="export_csv view missing")
_dashboard_export = _get_any(("dashboard_export_csv",), views, msg="dashboard_export view missing")

_update_stock = _get_any(("update_stock",), views, msg="update_stock view missing")
_delete_stock = _get_any(("delete_stock",), views, msg="delete_stock view missing")
_restore_stock = _get_any(("restore_stock",), views, msg="restore_stock view missing")

# ---- Time pages wired to api_views (single source of truth) ----
try:
    from .api_views import time_checkin_page as _time_checkin_page, time_logs_page as _time_logs_page
except Exception:
    _time_checkin_page = _resolve_page(
        ("time_checkin_page", "time_checkin", "time_checkin_view"),
        template_name="inventory/time_checkin.html",
        missing_msg="time_checkin page view missing",
    )
    _time_logs_page = _resolve_page(
        ("time_logs",),
        template_name="inventory/time_logs.html",
        missing_msg="time_logs page view missing",
    )

_wallet_page = _get_any(("wallet_page",), views, msg="wallet page view missing")

_healthz = _get_any(("healthz",), views, msg="OK")
_settings_view = _get_any(("settings_home", "settings"), views, msg="settings view missing")

# ---------- ORDERS: resolve directly, no stub shadowing ----------
def _resolve_orders_list_view():
    fn = getattr(views, "orders_list", None)
    if callable(fn):
        return fn
    # Friendly fallback page (never 501)
    def _fallback(request, *args, **kwargs):
        return render(
            request,
            "inventory/orders_list.html",
            {"page_obj": None, "orders": [], "message": "Orders model not available yet."},
        )
    return _fallback

_orders_list_view = _resolve_orders_list_view()

# Also provide a JSON API that never 501s by default
def _resolve_orders_list_api():
    api_fn = getattr(_api_v2_primary, "orders_list_api", None)
    if callable(api_fn):
        return api_fn

    def _api_ok(_request, *args, **kwargs):
        return JsonResponse({"ok": True, "count": 0, "orders": []}, status=200)
    return _api_ok

_orders_list_api = _resolve_orders_list_api()

_po_invoice = _get_any(("po_invoice",), views, msg="invoice view missing")

# -------- APIs (prefer direct -> v2 -> legacy) ----------
_scan_in_api = _get_any(("scan_in", "api_scan_in"), _api_v2, _api_legacy, msg="scan_in API not implemented")
_scan_sold_api = _get_any(("scan_sold", "api_scan_sold"), _api_v2, _api_legacy, msg="scan_sold API not implemented")

# Prefer NEW api_views for these critical endpoints
_api_stock_status_direct = getattr(views, "api_stock_status", None)
_api_stock_status_view = (
    getattr(_api_v2_primary, "api_stock_status", None)
    or _api_stock_status_direct
    or _get_any(("api_stock_status", "stock_status", "stock_status_api"), _api_v2, _api_legacy, msg="api_stock_status not implemented")
)
_mark_sold_view = (
    getattr(_api_v2_primary, "api_mark_sold", None)
    or _get_any(("api_mark_sold",), _api_v2, _api_legacy, msg="api_mark_sold not implemented")
)

# NEW: JSON stock list API resolver (explicit)
_api_stock_list_view = (
    getattr(_api_v2_primary, "stock_list", None)
    or _get_any(("stock_list",), _api_v2, _api_legacy, msg="stock_list API not implemented")
)

# If you added scan_sold_submit in views, expose it directly (with safe stub).
_scan_sold_submit_view = getattr(views, "scan_sold_submit", None) or _stub("scan_sold_submit view not implemented")

_time_checkin_view = _get_any(("api_time_checkin",), _api_v2, _api_legacy, msg="api_timecheckin not implemented")
_geo_ping_view = _get_any(("api_geo_ping", "geo_ping"), _api_v2, _api_legacy, msg="api_geo_ping not implemented")

_timeclock_event_view = _get_any(
    ("api_timeclock_event", "api_clock_event"),
    views, _api_v2, _api_legacy,
    msg="api_timeclock_event not implemented",
)
_timeclock_bootstrap_view = _get_any(
    ("api_timeclock_bootstrap", "api_clock_bootstrap"),
    views, _api_v2, _api_legacy,
    msg="api_timeclock_bootstrap not implemented",
)

_wallet_summary = _get_any(("api_wallet_summary",), _api_v2, _api_legacy, msg="api_wallet_summary not implemented")
_wallet_add_txn = _get_any(("api_wallet_add_txn",), _api_v2, _api_legacy, msg="api_wallet_add_txn not implemented")
_sales_trend_view = _get_any(("api_sales_trend", "sales_trend"), _api_v2, _api_legacy, msg="api_sales_trend not implemented")
_top_models_view = _get_any(("api_top_models",), _api_v2, _api_legacy, msg="api_top_models not implemented")
_profit_bar_view = _get_any(("api_profit_bar",), _api_v2, _api_legacy, msg="api_profit_bar not implemented")
_value_trend_view = _get_any(("value_trend", "api_value_trend", "api_sales_trend", "sales_trend"), _api_v2, _api_legacy, msg="api_value_trend not implemented")
_agent_trend_view = _get_any(("api_agent_trend",), _api_v2, _api_legacy, msg="api_agent_trend not implemented")

_restock_heatmap = (
    getattr(_api_v2_primary, "restock_heatmap_api", None)
    or _get_any(("restock_heatmap", "restock_heatmap_api"), _api_v2, _api_legacy, msg="restock_heatmap not implemented")
)

_api_order_price = _get_any(("api_order_price",), _api_v2, _api_legacy, msg="api_order_price not implemented")
_api_stock_models = _get_any(("api_stock_models",), _api_v2, _api_legacy, msg="api_stock_models not implemented")
_api_place_order = _get_any(("api_place_order",), _api_v2, _api_legacy, msg="api_place_order not implemented")

# ---- robust predictions resolver ----
_predictions_view = _get_any(
    ("predictions_summary", "predictions_view", "predictions_api"),
    views_dashboard, _api_v2, _api_legacy,
    msg="predictions endpoint not implemented",
)

# ---- ensure cash overview resolver exists BEFORE URL patterns ----
_cash_overview_view = _get_any(("api_cash_overview",), _api_v2, _api_legacy, msg="api_cash_overview not implemented")

# ---- Alerts API resolver (THIS WAS MISSING) ----
_alerts_view = _get_any(("api_alerts",), _api_v2, _api_legacy, msg="api_alerts not implemented")

# ---- NEW: Inventory Summary API resolver (single-source numbers) ----
_inventory_summary_view = (
    getattr(_api_v2_primary, "api_inventory_summary", None)
    or _get_any(("api_inventory_summary",), _api_v2, _api_legacy, msg="api_inventory_summary not implemented")
)

# ---- Product APIs (create / update price) ----
_api_product_create = _get_any(
    ("api_product_create", "product_create_api", "api_create_product"),
    _api_v2, _api_legacy,
    msg="api_product_create not implemented",
)
_api_product_update_price = _get_any(
    ("api_product_update_price",),
    _api_v2, _api_legacy,
    msg="api_product_update_price not implemented",
)

# ---- Tasks & audit (REST resolvers) ----
def _json_501(msg: str):
    def _v(_request, *a, **k):
        return JsonResponse({"ok": False, "error": msg}, status=501)
    return _v

_api_task_submit = (
    getattr(_api_v2_primary, "api_task_submit", None)
    or getattr(_api_v2, "api_task_submit", None)
    or getattr(_api_legacy, "api_task_submit", None)
    or _json_501("api_task_submit missing")
)

_api_task_status = (
    getattr(_api_v2_primary, "api_task_status", None)
    or getattr(_api_v2, "api_task_status", None)
    or getattr(_api_legacy, "api_task_status", None)
    or _json_501("api_task_status missing")
)

_api_audit_verify = (
    getattr(_api_v2_primary, "api_audit_verify", None)
    or getattr(_api_v2, "api_audit_verify", None)
    or getattr(_api_legacy, "api_audit_verify", None)
    or _json_501("api_audit_verify missing")
)

# ---- NEW: Backfill Sale API resolver (added) ----
_backfill_sale_view = (
    getattr(_api_v2_primary, "api_backfill_sale", None)
    or _get_any(("api_backfill_sale",), _api_v2, _api_legacy, msg="api_backfill_sale not implemented")
)

# ---------------------------------------------------------------------
# Product-create page (BUSINESS-SPECIFIC UI; model-agnostic)
# ---------------------------------------------------------------------
def _normalize_label(val: str) -> str:
    v = (val or "").strip().lower()
    if v in {"phones & electronics", "electronics", "phone", "phones", "mobile", "mobiles"}:
        return "phones"
    if v in {"pharmacy", "chemist", "medicine", "drugstore"}:
        return "pharmacy"
    if v in {"liquor", "bar", "alcohol", "pub", "bottle-store", "bottle store"}:
        return "liquor"
    if v in {"grocery", "groceries", "supermarket", "retail", "supermarket & groceries"}:
        return "grocery"
    if v in {"clothing", "clothes", "apparel"}:
        return "clothing"
    return "generic"

def _coerce_str(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    for attr in ("value", "label", "name"):
        try:
            s = getattr(v, attr)
            if isinstance(s, str) and s.strip():
                return s
        except Exception:
            pass
    return None

def _mode_from_session(session) -> Optional[str]:
    if not session:
        return None
    for key in (
        "business_type", "business_kind", "business_vertical", "vertical",
        "category", "industry", "tenant_vertical", "active_business_vertical"
    ):
        val = _coerce_str(session.get(key))
        if val:
            return _normalize_label(val)
    return None

def _current_business_from_request(request):
    biz = (
        getattr(request, "business", None)
        or getattr(request, "active_business", None)
        or getattr(getattr(request, "user", None), "business", None)
        or getattr(getattr(request, "tenant", None), "business", None)
    )
    if biz:
        return biz

    sess = getattr(request, "session", {}) or {}
    bid = next((sess.get(k) for k in _SESS_BIZ if sess.get(k) is not None), None)
    if bid:
        try:
            from tenants.models import Business
            return Business.objects.filter(id=bid).first()
        except Exception:
            return None
    return None

def _infer_product_mode(request) -> str:
    q_mode = _normalize_label(request.GET.get("mode", ""))
    if q_mode in {"phones", "pharmacy", "liquor", "grocery", "clothing"}:
        return q_mode

    biz = _current_business_from_request(request)
    if biz:
        for attr in ("vertical", "category", "industry", "type", "kind", "sector", "business_type"):
            val = _coerce_str(getattr(biz, attr, None))
            if val:
                return _normalize_label(val)
            disp_fn = getattr(biz, f"get_{attr}_display", None)
            if callable(disp_fn):
                try:
                    v = disp_fn()
                    v = _coerce_str(v)
                    if v:
                        return _normalize_label(v)
                except Exception:
                    pass

    from_sess = _mode_from_session(getattr(request, "session", {}) or {})
    if from_sess:
        return from_sess

    return "generic"

def product_create_page(request):
    from django import forms

    mode = _infer_product_mode(request)

    if mode == "phones":
        class DynamicProductForm(forms.Form):
            brand = forms.CharField(label="Brand name", max_length=80, required=True)
            model = forms.CharField(label="Model number (optional)", max_length=80, required=False)
            specs = forms.CharField(label="Specs", widget=forms.Textarea(attrs={"rows": 4}), required=True)
            price = forms.DecimalField(label="Price", max_digits=12, decimal_places=2, required=True)
            phone_name = forms.CharField(label="Phone name", max_length=120, required=True)
        page_title = "Add Phone"
        page_hint = "Phones: IMEI captured on Scan IN (15 digits)."

    elif mode == "liquor":
        class DynamicProductForm(forms.Form):
            liquor_name = forms.CharField(label="Liquor name", max_length=120, required=True)
            price_bottle = forms.DecimalField(label="Price per bottle", max_digits=12, decimal_places=2, required=True)
            price_shot = forms.DecimalField(label="Price per shot (optional)", max_digits=12, decimal_places=2, required=False)
            shots_per_bottle = forms.IntegerField(label="Number of shots in bottle (optional)", min_value=1, required=False)
            qty_bottles = forms.IntegerField(label="Quantity of bottles received (optional)", min_value=0, required=False)
        page_title = "Add Liquor"
        page_hint = "Liquor: sell by bottle or shots; no Scan IN/Sold pages needed."

    elif mode == "pharmacy":
        class DynamicProductForm(forms.Form):
            barcode = forms.CharField(label="Barcode (12–13 digits, optional)", max_length=13, required=False)
            medicine_name = forms.CharField(label="Medicine name", max_length=120, required=True)
            quantity = forms.IntegerField(label="Quantity", min_value=0, required=True)
            price_per_unit = forms.DecimalField(label="Price per unit", max_digits=12, decimal_places=2, required=True)
        page_title = "Add Medicine"
        page_hint = "Pharmacy: medicine name, quantity and unit price."

    elif mode == "grocery":
        class DynamicProductForm(forms.Form):
            product_name = forms.CharField(label="Product name", max_length=120, required=True)
            quantity = forms.IntegerField(label="Quantity", min_value=0, required=True)
            price_per_unit = forms.DecimalField(label="Price per unit", max_digits=12, decimal_places=2, required=True)
            barcode = forms.CharField(label="Barcode (optional)", max_length=32, required=False)
        page_title = "Add Grocery Item"
        page_hint = "Groceries: simple product with quantity and unit price."

    elif mode == "clothing":
        class DynamicProductForm(forms.Form):
            product_name = forms.CharField(label="Clothing item", max_length=120, required=True)
            size = forms.CharField(label="Size (e.g., M, 42)", max_length=32, required=False)
            price = forms.DecimalField(label="Price", max_digits=12, decimal_places=2, required=True)
        page_title = "Add Clothing Item"
        page_hint = "Clothing: simple item with optional size."

    else:
        class DynamicProductForm(forms.Form):
            brand = forms.CharField(label="Brand", max_length=80, required=True)
            product_name = forms.CharField(label="Product name", max_length=120, required=True)
            price = forms.DecimalField(label="Price", max_digits=12, decimal_places=2, required=True)
        page_title = "Add Product"
        page_hint = "Generic products: simple details."

    if request.method == "POST":
        form = DynamicProductForm(request.POST)
        if form.is_valid():
            dest = _safe_reverse("inventory:stock_list") or "/inventory/list/"
            return redirect(dest)
    else:
        form = DynamicProductForm()

    ctx = {
        "PRODUCT_MODE": mode,
        "PAGE_TITLE": page_title,
        "PAGE_HINT": page_hint,
        "business": _current_business_from_request(request),
        "form": form,
    }
    return render(request, "inventory/product_create.html", ctx)

# Router (legacy support)
def product_create_router(request):
    mapping = {
        "phones":   "inventory:product_create_phones",
        "pharmacy": "inventory:product_create_pharmacy",
        "liquor":   "inventory:product_create_liquor",
        "grocery":  "inventory:product_create_grocery",
        "clothing": "inventory:product_create_clothing",
    }
    mode = _infer_product_mode(request)
    if mode in mapping:
        url = _safe_reverse(mapping[mode]) or f"/inventory/{mode}/products/new/"
        return redirect(url)
    return product_create_page(request)

def _product_create_for_mode_factory(force_mode: str):
    def _view(request, *args, **kwargs):
        q = request.GET.copy()
        q["mode"] = force_mode
        request.GET = q
        return product_create_page(request)
    return _view

# ---------------------------------------------------------------------
# Import v2 polished create/edit/delete views — HARD require v2
# ---------------------------------------------------------------------
try:
    from . import views_products_v2 as prodv2
    if not getattr(prodv2, "V2_LOADED", False):
        raise ImportError("views_products_v2 did not set V2_LOADED")
except Exception:
    raise

# ---------------------------------------------------------------------
# Best “Add Product” entry: chooses the correct v2 page
# ---------------------------------------------------------------------
try:
    from .helpers import product_new_url_for_business
except Exception:
    def product_new_url_for_business(biz):  # type: ignore
        def _norm(val: Optional[str]) -> str:
            return (val or "").strip().lower()
        v = None
        if biz:
            for attr in ("template_key", "vertical", "category", "industry", "type", "kind", "sector"):
                val = getattr(biz, attr, None)
                if isinstance(val, str) and val.strip():
                    v = _norm(val)
                    break
        v = v or "phones"
        if v in {"clothing", "fashion", "apparel"}:
            return _safe_reverse("inventory:clothing_product_new_v2") or "/inventory/clothing/products/new/v2/"
        if v in {"liquor", "bar", "pub"}:
            return _safe_reverse("inventory:liquor_product_new_v2") or "/inventory/liquor/products/new/v2/"
        return _safe_reverse("inventory:merch_product_new") or "/inventory/merch/products/new/v2/"

@login_required
@_need_biz
def product_new_entry(request):
    try:
        sess_v = (request.session.get("active_business_vertical") or "").strip().lower()
    except Exception:
        sess_v = ""

    if sess_v in {"clothing", "liquor", "phones"}:
        if sess_v == "clothing":
            url = _safe_reverse("inventory:clothing_product_new_v2") or "/inventory/clothing/products/new/v2/"
        elif sess_v == "liquor":
            url = _safe_reverse("inventory:liquor_product_new_v2") or "/inventory/liquor/products/new/v2/"
        else:
            url = _safe_reverse("inventory:merch_product_new") or "/inventory/merch/products/new/v2/"
        return redirect(url)

    url = product_new_url_for_business(getattr(request, "business", None))
    return redirect(url)

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
# NEW: Locations + Alerts page resolvers (safe fallbacks)
# ---------------------------------------------------------------------
_locations_view = _get_any(("locations",), views, msg="locations view missing")
_alerts_page = _resolve_page(("alerts_feed", "alerts"), template_name="inventory/alerts_feed.html", missing_msg="alerts page view missing")
_capture_gps = _get_any(("capture_gps",), views, msg="capture_gps not implemented")

# ---------------------------------------------------------------------
# Docs (Invoices / Quotations) resolvers — SAFE fallbacks
# ---------------------------------------------------------------------
def _html_fallback(title: str, tip: str):
    def _view(_request, *a, **k):
        return HttpResponse(
            f"""<!doctype html><meta charset='utf-8'>
            <body style="font-family:system-ui;background:#0b1020;color:#eef2ff;margin:0">
            <div style="max-width:900px;margin:24px auto;padding:0 16px">
              <h2>{title}</h2>
              <div style="background:#0e152b;border:1px solid #1c2541;border-radius:14px;padding:16px">
                <p>{tip}</p>
              </div>
            </div></body>""",
            content_type="text/html",
        )
    return _view

_docs_home_view = getattr(_docs, "docs_home", None) or _html_fallback("Business Docs", "Docs module not loaded yet.")
_doc_new_invoice = getattr(_docs, "doc_new_invoice", None) or _html_fallback(
    "New Invoice", "Template missing. Create templates/inventory/doc_edit.html"
)
_doc_new_quote = getattr(_docs, "doc_new_quote", None) or _html_fallback(
    "New Quotation", "Coming soon — wire views_docs.doc_new_quote to enable."
)
_doc_detail = getattr(_docs, "doc_detail", None) or _html_fallback("Document", "Detail page not implemented yet.")
_doc_download_pdf = getattr(_docs, "doc_download_pdf", None) or _stub("doc_download_pdf not implemented")
_doc_download_excel = getattr(_docs, "doc_download_excel", None) or _stub("doc_download_excel not implemented")
_doc_send_email = getattr(_docs, "doc_send_email", None) or _stub("doc_send_email not implemented")
_doc_send_whatsapp = getattr(_docs, "doc_send_whatsapp", None) or _stub("doc_send_whatsapp not implemented")

# ---------------------------------------------------------------------
# Scan-IN: direct to page
# ---------------------------------------------------------------------
def _scan_in_guarded(request, *args, **kwargs):
    return _scan_in_page_view(request, *args, **kwargs)

# ---------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------
urlpatterns = [
    # Login catch-alls
    re_path(r"^(?:.*/)?login/?$", _forward_to_root_login, name="inventory_login_catchall"),
    re_path(r"^(?:.*/)?accounts/login/?$", _forward_to_root_login, name="inventory_accounts_login_catchall"),

    path("", _home_redirect, name="home"),

    # Stock + dashboard (pages)
    path("list/", _need_biz(_stock_list_wrapper(_stock_list)), name="stock_list"),
    path("products/", _need_biz(_stock_list_wrapper(_stock_list)), name="product_list"),
    path("stock/", _need_biz(_stock_list_wrapper(_stock_list))),
    path("list/all/", _need_biz(_stock_list_wrapper(_list_all_redirect)), name="stock_list_all"),
    path("stocks/", _redirect_to("inventory:stock_list")),

    path("dashboard/", _need_biz(_inventory_dashboard), name="inventory_dashboard"),
    path("dashboard", _need_biz(_inventory_dashboard), name="dashboard"),
    path("dash/", _redirect_to("inventory:inventory_dashboard")),

    # Scanning — pages
    path("scan-in/", _need_biz(_scan_in_page_view), name="scan_in"),
    path("scan-sold/", _need_biz(_scan_sold_page_view), name="scan_sold"),

    # NEW — Quick Sell page (no post-sale probe)
    path("sell/quick/", _need_biz(_sell_quick_page), name="sell_quick"),

    # NEW — direct Sell submit endpoint (business-wide; prefers local view)
    path("scan-sold/submit/", _need_biz(_scan_sold_submit_view), name="scan_sold_submit"),
    path("api/scan-sold/submit/", _need_biz(_scan_sold_submit_view), name="api_scan_sold_submit"),
]

# -------------------- JSON APIs (NO require_business wrapper) --------------------
urlpatterns += [
    # Core stock/scan/sell
    path("api/scan-in/", _scan_in_api, name="api_scan_in"),
    path("api/scan-sold/", _scan_sold_api, name="api_scan_sold"),

    # STATUS — support hyphen + underscore
    path("api/stock-status/", _api_stock_status_view, name="api_stock_status"),
    path("api/stock_status/", _api_stock_status_view),  # alias

    # Mark sold (no Sale row)
    path("api/mark-sold/", _mark_sold_view, name="api_mark_sold"),

    # Backfill Sale (create Sale row even if inventory already SOLD)
    path("api/backfill-sale/", _backfill_sale_view, name="api_backfill_sale"),
    path("api/backfill_sale/", _backfill_sale_view),  # alias

    # Stock list JSON (hyphen + underscore)
    path("api/stock-list/", _api_stock_list_view, name="api_stock_list"),
    path("api/stock_list/", _api_stock_list_view),  # alias
]

# Orders — pages + APIs
urlpatterns += [
    path("place-order/", manager_required(_need_biz(_place_order_page)), name="place_order_page"),
    path("orders/new/", manager_required(_need_biz(_place_order_page)), name="place_order"),
    path("orders/", manager_required(_need_biz(_orders_list_view)), name="orders_list"),
    path("orders/<int:po_id>/invoice/", manager_required(_need_biz(_po_invoice)), name="po_invoice"),
    path("orders/<int:po_id>/download/", manager_required(_need_biz(_po_invoice)), name="po_invoice_download"),

    # JSON API (safe default if not implemented)
    path("api/orders/", manager_required(_need_biz(_orders_list_api)), name="orders_list_api"),

    path("api/place-order/", manager_required(_need_biz(_api_place_order)), name="api_place_order"),
    path("api/order-price/<int:product_id>/", manager_required(_need_biz(_api_order_price)), name="api_order_price"),

    # ---- Product price update (correct canonical + back-compat redirects) ----
    path("api/product/update-price/", manager_required(_need_biz(_api_product_update_price)), name="api_product_update_price"),
    path("api/product/update-price/<int:product_id>/",
         RedirectView.as_view(pattern_name="inventory:api_product_update_price", permanent=False)),
    path("api/product/update_price/<int:product_id>/",
         RedirectView.as_view(pattern_name="inventory:api_product_update_price", permanent=False)),
    path("api/product/update_price/",
         RedirectView.as_view(pattern_name="inventory:api_product_update_price", permanent=False)),

    path("api/stock-models/", manager_required(_need_biz(_api_stock_models)), name="api_stock_models"),
]

# ---- JSON Product Create API ----
urlpatterns += [
    path("api/product/create/", manager_required(_need_biz(_api_product_create)), name="api_product_create"),
]

# ---------------------------- Docs URLs ----------------------------
urlpatterns += [
    path("docs/", _need_biz(_docs_home_view), name="docs_home"),
    path("docs/new/invoice/", manager_required(_need_biz(_doc_new_invoice)), name="doc_new_invoice"),
    path("docs/new/quote/", manager_required(_need_biz(_doc_new_quote)), name="doc_new_quote"),
    path("docs/<int:pk>/", _need_biz(_doc_detail), name="doc_detail"),
    path("docs/<int:pk>/download/pdf/", manager_required(_need_biz(_doc_download_pdf)), name="doc_download_pdf"),
    path("docs/<int:pk>/download/xlsx/", manager_required(_need_biz(_doc_download_excel)), name="doc_download_excel"),
    path("docs/<int:pk>/send/email/", manager_required(_need_biz(_doc_send_email)), name="doc_send_email"),
    path("docs/<int:pk>/send/whatsapp/", manager_required(_need_biz(_doc_send_whatsapp)), name="doc_send_whatsapp"),
]

# ---------------------------- Dashboard/API routes ----------------------------
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

    # AFTER – APIs return JSON even if no active business. (Pages remain guarded.)
    path("api/time-checkin/", _time_checkin_view, name="api_time_checkin"),
    path("api/geo-ping/", _geo_ping_view, name="api_geo_ping"),

    path("api/timeclock/bootstrap/", _need_biz(_timeclock_bootstrap_view), name="api_timeclock_bootstrap"),
    path("api/timeclock/event/", _need_biz(_timeclock_event_view), name="api_timeclock_event"),

    # Tasks & audit
    path("api/task-submit/", _need_biz(_api_task_submit), name="api_task_submit"),
    path("api/task-status/", _need_biz(_api_task_status), name="api_task_status"),
    path("api/audit-verify/", _need_biz(_api_audit_verify), name="api_audit_verify"),

    # NEW — single-source inventory summary for dashboard cards
    path("api/summary/", _need_biz(_inventory_summary_view), name="inventory_api_summary"),
]

# ---------------------------------------------------------------------
# Time pages — wired to api_views
# ---------------------------------------------------------------------
urlpatterns += [
    path("time/check-in/", _need_biz(_time_checkin_page), name="time_checkin"),
    path("time/logs/", _need_biz(_time_logs_page), name="time_logs"),
    path("timelogs/", _redirect_to("inventory:time_logs"), name="timelogs_short"),
    path("time/log/", _redirect_to("inventory:time_logs")),
]

# ---------------------------------------------------------------------
# Product creator — PAGE (ADMIN/MANAGER)
# ---------------------------------------------------------------------
urlpatterns += [
    path("products/new/", manager_required(_need_biz(product_new_entry)), name="product_new_entry"),
    path("merch/products/new/", manager_required(_need_biz(product_new_entry)), name="merch_product_create"),
    path("products/new/generic/", _redirect_to("inventory:product_new_entry"), name="product_create"),
    path("product/new/", _redirect_to("inventory:product_new_entry"), name="product_create_short"),

    path("phones/products/new/",   manager_required(_need_biz(_product_create_for_mode_factory("phones"))),   name="product_create_phones"),
    path("pharmacy/products/new/", manager_required(_need_biz(_product_create_for_mode_factory("pharmacy"))), name="product_create_pharmacy"),
    path("liquor/products/new/",   manager_required(_need_biz(_product_create_for_mode_factory("liquor"))),   name="product_create_liquor"),
    path("grocery/products/new/",  manager_required(_need_biz(_product_create_for_mode_factory("grocery"))),  name="product_create_grocery"),
    path("clothing/products/new/", manager_required(_need_biz(_product_create_for_mode_factory("clothing"))), name="product_create_clothing"),

    # v2 merch router — left undecorated to avoid auth/guard loops
    path("merch/products/new/v2/", prodv2.product_create_v2_router, name="merch_product_new"),
    path("merch/products/new/v2/<str:category>/", prodv2.product_create_v2_router, name="merch_product_new_v2_cat"),

    # Direct v2 edit/delete
    path("merch/products/<int:pk>/edit/", manager_required(_need_biz(prodv2.product_edit_v2)), name="product_edit_v2"),
    path("merch/products/<int:pk>/delete/", manager_required(_need_biz(prodv2.product_delete_v2)), name="product_delete_v2"),

    # clothing v2 (explicit)
    path("clothing/products/new/v2/", manager_required(_need_biz(prodv2.product_create_clothing_v2)), name="clothing_product_new_v2"),
    path("clothing/products/<int:pk>/edit/", manager_required(_need_biz(prodv2.product_edit_clothing_v2)), name="clothing_product_edit_v2"),

    # liquor v2 (explicit)
    path("liquor/products/new/v2/", manager_required(_need_biz(prodv2.product_create_liquor_v2)), name="liquor_product_new_v2"),
    path("liquor/products/<int:pk>/edit/", manager_required(_need_biz(prodv2.product_edit_liquor_v2)), name="liquor_product_edit_v2"),
]

# Manager Locations + Alerts pages
urlpatterns += [
    path("locations/", manager_required(_need_biz(_locations_view)), name="locations"),
    path("alerts/", _need_biz(_alerts_page), name="alerts_feed"),
    path("capture-gps/", manager_required(_need_biz(_capture_gps)), name="capture_gps"),
]
