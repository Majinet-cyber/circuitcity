# inventory/api_views.py
from __future__ import annotations

from typing import Any, Dict, List
import json
import re
import importlib
from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

# -----------------------------------------------------------------------------
# Tenants helpers (role/tenant aware)
# -----------------------------------------------------------------------------
def _try_import(modpath: str, attr: str | None = None):
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None

scoped = _try_import("circuitcity.tenants.utils", "scoped") or \
         _try_import("tenants.utils", "scoped") or (lambda qs, _request: qs)

get_active_business = _try_import("circuitcity.tenants.utils", "get_active_business") or \
                      _try_import("tenants.utils", "get_active_business") or (lambda _r: None)

# -----------------------------------------------------------------------------
# Single-source-of-truth scope + queryset helpers
# (required for keeping Dashboard, Scan IN, and Stock List in sync)
# -----------------------------------------------------------------------------
# IMPORTANT: avoid name shadowing; keep imported callables with *_func suffixes.
_active_scope_func = _try_import("inventory.scope", "active_scope")
_stock_qs_for_request_func = _try_import("inventory.scope", "stock_queryset_for_request")

def _active_scope(request: HttpRequest) -> tuple[int | None, int | None]:
    """
    Returns (business_id, location_id) for current request, using inventory.scope.active_scope
    when available; otherwise falls back to request/session-derived values.
    """
    if callable(_active_scope_func):
        try:
            return _active_scope_func(request)  # type: ignore[misc]
        except Exception:
            pass
    # Fallback: try to infer from request/session
    biz = get_active_business(request)
    biz_id = getattr(biz, "id", None)
    loc_id = getattr(request, "active_location_id", None) or getattr(getattr(request, "active_location", None), "id", None)
    return biz_id, loc_id

def _stock_queryset_for_request(request: HttpRequest):
    """
    Canonical queryset for 'items currently in stock' for the active scope.
    If inventory.scope.stock_queryset_for_request is present, use it.
    Else, derive a best-effort fallback that respects business/location and common fields.
    """
    if callable(_stock_qs_for_request_func):
        try:
            return _stock_qs_for_request_func(request)  # type: ignore[misc]
        except Exception:
            pass

    # ----- Best-effort fallback (keeps old behavior but scoped) -----
    InventoryItem = Stock = None  # late import below
    try:
        from .models import InventoryItem as _InventoryItem  # type: ignore
        InventoryItem = _InventoryItem
    except Exception:
        pass
    if InventoryItem is None:
        try:
            from .models import Stock as _Stock  # type: ignore
            Stock = _Stock
        except Exception:
            pass

    model = InventoryItem or Stock
    if model is None:
        return None

    qs = scoped(model.objects.all(), request)

    # Discover fields defensively
    try:
        fields = {f.name for f in model._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        fields = set()

    # Business scoping (if not already applied by scoped())
    biz_id, loc_id = _active_scope(request)
    if biz_id and ("business" in fields or "business_id" in fields):
        try:
            qs = qs.filter(business_id=biz_id)
        except Exception:
            try:
                qs = qs.filter(business__id=biz_id)
            except Exception:
                pass

    # Location scoping (optional)
    if loc_id:
        for fk in ("current_location", "location", "store", "branch"):
            if fk in fields or f"{fk}_id" in fields:
                try:
                    qs = qs.filter(**{f"{fk}_id": loc_id})
                    break
                except Exception:
                    try:
                        qs = qs.filter(**{fk: loc_id})
                        break
                    except Exception:
                        continue

    # Exclude sold/inactive/archived by default
    if "sold_at" in fields:
        qs = qs.filter(sold_at__isnull=True)
    if "is_active" in fields:
        qs = qs.filter(is_active=True)
    if "archived" in fields:
        qs = qs.filter(archived=False)
    if "status" in fields:
        try:
            qs = qs.exclude(status__iexact="sold")
        except Exception:
            pass

    # Useful joins
    joinable = [j for j in ("product", "current_location", "location", "store", "business") if j in fields]
    if joinable:
        try:
            qs = qs.select_related(*joinable)
        except Exception:
            pass

    return qs


# -----------------------------------------------------------------------------
# Try to import inventory models (be defensive)
# -----------------------------------------------------------------------------
InventoryItem = Stock = Product = AuditLog = Location = None  # type: ignore[assignment]

try:
    from .models import InventoryItem as _InventoryItem  # type: ignore
    InventoryItem = _InventoryItem
except Exception:
    pass

if InventoryItem is None:
    try:
        from .models import Stock as _Stock  # type: ignore
        Stock = _Stock
    except Exception:
        pass

try:
    from .models import Product as _Product  # type: ignore
    Product = _Product
except Exception:
    pass

try:
    from .models import AuditLog as _AuditLog  # type: ignore
    AuditLog = _AuditLog
except Exception:
    pass

try:
    from .models import Location as _Location  # type: ignore
    Location = _Location
except Exception:
    pass


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
IMEI_RX = re.compile(r"^\d{15}$")

def _ok(payload: Any = None, **extra) -> JsonResponse:
    data: Dict[str, Any] = {"ok": True}
    if payload is not None:
        data["data"] = payload
    if extra:
        data.update(extra)
    return JsonResponse(data, status=200)

def _err(msg: str, status: int = 400, **extra) -> JsonResponse:
    data = {"ok": False, "error": msg}
    if extra:
        data.update(extra)
    return JsonResponse(data, status=status)

def _tester_html(title: str, post_path: str) -> HttpResponse:
    # Minimal form that works even without static/templates
    return HttpResponse(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;margin:2rem;line-height:1.5">
  <h2>{title}</h2>
  <form method="post" action="{post_path}">
    <label>Code / IMEI / SKU:
      <input name="code" required autofocus style="padding:.4rem;border:1px solid #ccc;border-radius:.4rem">
    </label>
    <button type="submit" style="margin-left:.5rem;padding:.4rem .8rem">Submit</button>
  </form>
  <p style="opacity:.75;margin-top:1rem">
    Tip: <code>curl -X POST -d "code=12345" {post_path}</code>
  </p>
</body></html>""",
        content_type="text/html",
    )

def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    try:
        if request.body:
            return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        pass
    return {}

def _get_code(request: HttpRequest) -> str:
    """
    Extract code from JSON or form:
    accepts keys: imei, code, sku, serial (first non-empty).
    """
    data = _parse_json_body(request)
    for key in ("imei", "code", "sku", "serial"):
        v = (data.get(key) or request.POST.get(key) or "").strip()
        if v:
            return v
    raw = request.POST.get("code") or ""
    return (raw or "").strip()

def _get_qty(obj) -> int:
    return int(getattr(obj, "quantity", getattr(obj, "qty", 0)) or 0)

def _set_qty(obj, value: int) -> None:
    if hasattr(obj, "quantity"):
        setattr(obj, "quantity", value)
    elif hasattr(obj, "qty"):
        setattr(obj, "qty", value)

def _set_if_has(obj, field: str, value) -> None:
    if hasattr(obj, field):
        setattr(obj, field, value)

def _find_by_code(model, code: str):
    """Find by common identifiers (sku/imei/serial/code)."""
    for field in ("sku", "imei", "serial", "code"):
        if hasattr(model, field):
            try:
                return model.objects.get(**{field: code})
            except model.DoesNotExist:  # type: ignore[attr-defined]
                continue
    return None

def _get_or_create_by_code(model, code: str):
    """Get or create by common identifiers; prefers `sku`, then `imei`, …"""
    for field in ("sku", "imei", "serial", "code"):
        if hasattr(model, field):
            obj, created = model.objects.get_or_create(**{field: code})
            return obj, created
    obj = model()  # type: ignore[call-arg]
    created = True
    return obj, created

def _get_location_from_item(it):
    """
    Prefer 'current_location' but fall back to 'location'.
    Returns (id, name) or (None, None).
    """
    loc = None
    if hasattr(it, "current_location"):
        loc = getattr(it, "current_location", None)
    if not loc and hasattr(it, "location"):
        loc = getattr(it, "location", None)
    if loc:
        return getattr(loc, "id", None), getattr(loc, "name", None)
    return None, None

def _serialize_item(it) -> Dict[str, Any]:
    product = getattr(it, "product", None)
    business = getattr(it, "business", None)
    loc_id, loc_name = _get_location_from_item(it)

    def _first_present(*names: str):
        for n in names:
            if hasattr(it, n):
                v = getattr(it, n, None)
                if v:
                    return v
        return None

    return {
        "id": getattr(it, "id", None),
        "sku": _first_present("sku", "imei", "serial", "code"),
        "name": getattr(it, "name", None) or getattr(product, "name", None),
        "qty": getattr(it, "quantity", getattr(it, "qty", None)),
        "price": getattr(it, "price", None) or getattr(product, "price", None),
        "status": getattr(it, "status", None),
        "location": {"id": loc_id, "name": loc_name} if loc_id or loc_name else None,
        "business_id": getattr(business, "id", None),
    }

def _attach_business_and_location(obj, request: HttpRequest) -> None:
    """
    If object has 'business' and/or 'location/current_location' fields, set them if possible.
    """
    b = get_active_business(request)
    if b is not None:
        _set_if_has(obj, "business", b)

    data = _parse_json_body(request)
    loc_id = data.get("location_id") or request.POST.get("location_id") or request.GET.get("location_id")
    if loc_id and Location is not None:
        try:
            loc = Location.objects.get(pk=int(loc_id))
            _set_if_has(obj, "current_location", loc)
            _set_if_has(obj, "location", loc)
        except Exception:
            pass

def _audit(kind: str, request: HttpRequest, **details) -> None:
    if AuditLog is None:
        return
    try:
        AuditLog.objects.create(
            kind=kind,
            actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            details={**details, "ts": timezone.now().isoformat()},
        )
    except Exception:
        pass

def _defaults_for_ui(request: HttpRequest) -> Dict[str, Any]:
    """
    Defaults the front-end expects to unlock inputs.
    """
    defaults: Dict[str, Any] = {
        "sold_date_default": date.today().isoformat(),
        "commission_default": 0.0,
        "location_default": None,
        "auto_submit_default": False,
    }
    # If you have locations, return a simple list and pick first as default
    if Location is not None:
        try:
            qs = scoped(Location.objects.all(), request).order_by("name")
            locs = [{"id": l.id, "name": getattr(l, "name", f"Loc #{l.id}")} for l in qs[:50]]
            defaults["locations"] = locs
            if locs and defaults["location_default"] is None:
                defaults["location_default"] = locs[0]["id"]
        except Exception:
            pass
    return defaults


# -----------------------------------------------------------------------------
# Simple PAGE endpoints (so /inventory/scan-in/, /scan-sold/, etc. resolve)
# -----------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def scan_in_page(_request: HttpRequest) -> HttpResponse:
    return _tester_html("Scan In", "/inventory/scan-in/")

@login_required
@require_http_methods(["GET"])
def scan_sold_page(_request: HttpRequest) -> HttpResponse:
    return _tester_html("Scan Sold", "/inventory/scan-sold/")

@login_required
@require_http_methods(["GET"])
def place_order_page(_request: HttpRequest) -> HttpResponse:
    return _tester_html("Place Order", "/inventory/place-order/")

@login_required
@require_http_methods(["GET"])
def time_logs(_request: HttpRequest) -> JsonResponse:
    return _ok({"logs": [], "now": timezone.now().isoformat()})


# -----------------------------------------------------------------------------
# API endpoints
# -----------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def stock_list(request: HttpRequest) -> JsonResponse:
    """
    Canonical stock list API (JSON).
    Uses the SINGLE SOURCE OF TRUTH queryset to match Dashboard & Scan flows.
    """
    try:
        qs = _stock_queryset_for_request(request)
        if qs is None:
            return _ok([], warning="No inventory model detected; returning empty list.")

        # Stable ordering
        try:
            qs = qs.order_by("-id")
        except Exception:
            pass

        # Limit (defensive: 1..200)
        try:
            limit = int(request.GET.get("limit", "200"))
            limit = max(1, min(200, limit))
        except Exception:
            limit = 200

        items: List[Dict[str, Any]] = []
        for it in qs[:limit]:
            items.append(_serialize_item(it))

        biz_id, loc_id = _active_scope(request)
        return _ok(
            items,
            count=getattr(qs, "count", lambda: len(items))(),
            scope={"business_id": biz_id, "location_id": loc_id},
        )
    except Exception as e:
        return _err(f"stock_list failed: {e}", status=500)


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_in(request: HttpRequest):
    """
    API for scanning items into stock.

    GET  -> return defaults so the UI can enable inputs immediately.
    POST -> Upsert item by code and increment quantity.
    """
    if request.method == "GET":
        return _ok({"note": "scan_in ready"}, **_defaults_for_ui(request))

    code = _get_code(request)
    if not code:
        return _err("Missing 'code'.")

    try:
        model = InventoryItem or Stock
        if model is None:
            return _err("No inventory model available.", status=501)

        obj, created = _get_or_create_by_code(model, code)
        _attach_business_and_location(obj, request)

        if created and hasattr(obj, "status") and not getattr(obj, "status", None):
            try:
                setattr(obj, "status", "in_stock")
            except Exception:
                pass

        qty_now = _get_qty(obj)
        _set_qty(obj, qty_now + 1 if qty_now >= 0 else 1)
        try:
            obj.save()
        except Exception:
            for field in ("sku", "imei", "serial", "code"):
                if hasattr(obj, field):
                    setattr(obj, field, code)
                    break
            obj.save()

        _audit("scan_in", request, code=code, id=getattr(obj, "id", None))
        return _ok({"code": code, "id": getattr(obj, "id", None)}, message="scan_in: inventory updated")
    except Exception as e:
        return _err(f"scan_in failed: {e}", status=500)


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def scan_sold(request: HttpRequest):
    """
    API for scanning items out (sold).

    GET  -> return defaults so the UI can enable IMEI/price/commission/location.
    POST -> Decrement quantity if item exists (never below zero).
    """
    if request.method == "GET":
        return _ok({"note": "scan_sold ready"}, **_defaults_for_ui(request))

    code = _get_code(request)
    if not code:
        return _err("Missing 'code'.")

    try:
        model = InventoryItem or Stock
        if model is None:
            return _err("No inventory model available.", status=501)

        obj = _find_by_code(model, code)
        if obj is None:
            _audit("scan_sold_missing", request, code=code)
            # Still ok: the UI can warn but continue workflow
            return _ok({"code": code, "id": None}, message="scan_sold: item not found")

        _attach_business_and_location(obj, request)

        qty_now = _get_qty(obj)
        new_qty = max(0, qty_now - 1)
        _set_qty(obj, new_qty)
        try:
            if hasattr(obj, "quantity"):
                obj.save(update_fields=["quantity"])
            else:
                obj.save()
        except Exception:
            obj.save()

        _audit("scan_sold", request, code=code, id=getattr(obj, "id", None), qty=new_qty)
        return _ok({"code": code, "id": getattr(obj, "id", None), "qty": new_qty}, message="scan_sold: inventory decremented")
    except Exception as e:
        return _err(f"scan_sold failed: {e}", status=500)


# Finalize SELL with price/commission/date/location
@login_required
@require_POST
@transaction.atomic
def api_mark_sold(request: HttpRequest):
    """
    Accepts (JSON or form):
      - imei (or code/sku/serial)
      - price (number), commission (number), sold_date (YYYY-MM-DD), location_id
    Decrements stock if present and echoes fields back.
    """
    data = _parse_json_body(request)
    code = (data.get("imei") or data.get("code") or data.get("sku") or data.get("serial")
            or request.POST.get("imei") or request.POST.get("code") or "").strip()
    if not code:
        return _err("Missing 'imei' (or code/sku/serial).")

    price = data.get("price") or request.POST.get("price")
    commission = data.get("commission") or request.POST.get("commission")
    sold_date = (data.get("sold_date") or request.POST.get("sold_date") or date.today().isoformat())
    location_id = data.get("location_id") or request.POST.get("location_id")

    if not IMEI_RX.match(code) and len(code) < 4:
        return _err("Invalid IMEI/code.", status=400)

    model = InventoryItem or Stock
    if model is None:
        return _err("No inventory model available.", status=501)

    obj = _find_by_code(model, code)
    if obj is None:
        _audit("mark_sold_missing", request, code=code)
        return _ok(
            {"code": code, "price": price, "commission": commission, "sold_date": sold_date, "location_id": location_id},
            message="Marked as SOLD (demo: item not found).",
        )

    if location_id:
        try:
            request.POST = request.POST.copy()
            request.POST["location_id"] = str(location_id)
        except Exception:
            pass
    _attach_business_and_location(obj, request)

    qty_now = _get_qty(obj)
    _set_qty(obj, max(0, qty_now - 1))

    if price is not None:
        try:
            _set_if_has(obj, "sale_price", float(price))
        except Exception:
            pass
    if commission is not None:
        try:
            _set_if_has(obj, "commission", float(commission))
        except Exception:
            pass
    try:
        if hasattr(obj, "quantity"):
            obj.save(update_fields=["quantity", "sale_price", "commission"])
        else:
            obj.save()
    except Exception:
        obj.save()

    _audit(
        "mark_sold",
        request,
        code=code,
        price=price,
        commission=commission,
        sold_date=sold_date,
        location_id=location_id,
    )

    return _ok(
        {
            "code": code,
            "price": price,
            "commission": commission,
            "sold_date": sold_date,
            "location_id": location_id,
            "remaining_qty": _get_qty(obj),
        },
        message="Marked as SOLD.",
    )


# -----------------------------------------------------------------------------
#  Restock Heatmap (canonical path: /inventory/api/restock-heatmap/)
# -----------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def restock_heatmap(request: HttpRequest) -> JsonResponse:
    """
    Minimal-but-valid payload for a heatmap component.
    Replace with real aggregation when ready.
    """
    payload = {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "series": [{"name": "Restocks", "data": [0, 0, 0, 0, 0, 0, 0]}],
    }
    return _ok(payload)

@login_required
@require_http_methods(["GET"])
def restock_heatmap_api(request: HttpRequest) -> JsonResponse:
    """
    Gateway endpoint used by urls.py; ALWAYS returns 200.
    Delegates to any present implementation (inventory.api or this module).
    """
    # Try project-provided implementations first
    for modpath, attr in [
        ("inventory.api", "restock_heatmap_api"),
        ("inventory.api", "api_stock_health"),
        ("circuitcity.inventory.api", "restock_heatmap_api"),
        ("circuitcity.inventory.api", "api_stock_health"),
        ("inventory.views_api", "restock_heatmap_api"),
        ("inventory.views_dashboard", "restock_heatmap_api"),
    ]:
        fn = _try_import(modpath, attr)
        if callable(fn):
            try:
                return fn(request)  # type: ignore[misc]
            except Exception:
                break  # fall through to local stub

    # Fall back to local stub
    return restock_heatmap(request)
