# circuitcity/inventory/views_scan.py
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

from django.http import JsonResponse, HttpRequest
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.db import transaction, IntegrityError

# ---------------------------------------------------------------------
# Safe dynamic imports (works if your models live in different apps)
# ---------------------------------------------------------------------
def _safe_import(*candidates: str):
    """
    Try a list of 'app.Model' dotted names and return the first model that imports.
    This lets us work even if your model is named Product vs CatalogProduct, etc.
    """
    import importlib
    for dotted in candidates:
        try:
            app_label, model_name = dotted.split(".", 1)
            m = importlib.import_module(f"{app_label}.models")
            return getattr(m, model_name)
        except Exception:
            continue
    return None


# Try common names from your codebase
Product = _safe_import("inventory.Product", "inventory.ModelsProduct", "sales.Product", "core.Product")
Location = _safe_import("inventory.Location", "tenants.Location", "tenants.Store", "tenants.Branch")
InventoryItem = _safe_import("inventory.InventoryItem",)

# Optional tenant/business resolver
def _get_active_business(request):
    try:
        from tenants.utils import get_active_business  # type: ignore
        return get_active_business(request)
    except Exception:
        # Fallback: some codebases attach .business on the request
        return getattr(request, "business", None)


# ---------------------------------------------------------------------
# Small field/meta helpers
# ---------------------------------------------------------------------
def _model_has_field(model, field_name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == field_name for f in model._meta.get_fields())
    except Exception:
        return hasattr(model, field_name)  # very defensive fallback


def _safe_order_by(qs, model, preferred_field: str):
    if _model_has_field(model, preferred_field):
        return qs.order_by(preferred_field)
    return qs.order_by("id")


# ---------------------------------------------------------------------
# User/location helpers
# ---------------------------------------------------------------------
def _agent_home_location_id(request) -> Optional[int]:
    """
    Try to read the agent's preferred/home location ID from profile.
    """
    try:
        prof = getattr(request.user, "agent_profile", None)
        lid = getattr(prof, "location_id", None)
        if lid:
            return int(lid)
    except Exception:
        pass
    return None


def _locations_for_active_business(request) -> list[dict[str, Any]]:
    """
    Return [{'id': ..., 'name': ...}, ...] for locations in the active business.
    Safe if Location model doesn't exist.
    """
    if not Location:
        return []
    try:
        qs = Location.objects.all()
        biz = _get_active_business(request)
        for fld in ("business", "tenant", "organization"):
            if _model_has_field(Location, fld) and biz is not None:
                qs = qs.filter(**{fld: biz})
                break
        order_by = "name" if _model_has_field(Location, "name") else "id"
        qs = qs.order_by(order_by)
        return [{"id": getattr(l, "id", None), "name": getattr(l, "name", str(l))} for l in qs[:200]]
    except Exception:
        return []


def _pick_default_location(request, locations: list[dict[str, Any]]) -> tuple[Optional[int], Optional[str]]:
    """
    Choose a default location from the already business-filtered list of dicts
    (each dict has {'id', 'name'}).
      1) agent's home location (if present in the list)
      2) a location whose name == active business name
      3) first location
    Returns (id, name) or (None, None) if list empty.
    """
    if not locations:
        return None, None

    # 1) Agent home location by id
    pref_id = _agent_home_location_id(request)
    if pref_id is not None:
        for it in locations:
            if it.get("id") == pref_id:
                return it["id"], it["name"]

    # 2) Match by business name
    biz = _get_active_business(request)
    biz_name = getattr(biz, "name", None)
    if biz_name:
        bn = str(biz_name).strip().lower()
        for it in locations:
            if str(it.get("name", "")).strip().lower() == bn:
                return it["id"], it["name"]

    # 3) First available
    first = locations[0]
    return first.get("id"), first.get("name")


# ---------------------------------------------------------------------
# Code / IMEI helpers
# ---------------------------------------------------------------------
_IMEI_RX = re.compile(r"^\d{15}$")

def _digits(s: str | None) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())

def _normalize_imei(raw: str | None) -> str:
    d = _digits(raw)
    return d[-15:] if len(d) >= 15 else d  # prefer last 15 for pasted long strings

def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        # Also accept form-encoded posts
        return {k: v for k, v in request.POST.items()}


# ---------------------------------------------------------------------
# Query helpers used by both ScanIn and ScanSold pages
# ---------------------------------------------------------------------
def _query_products(request) -> list[dict[str, Any]]:
    if not Product:
        return []
    try:
        business = _get_active_business(request)
        qs = Product.objects.all()

        # If the Product model is tenant-scoped, prefer filtering to the active business
        for tenant_field in ("business", "tenant", "organization"):
            if _model_has_field(Product, tenant_field) and business is not None:
                qs = qs.filter(**{tenant_field: business})
                break

        # Prefer 'active' filter if present
        if _model_has_field(Product, "active"):
            qs = qs.filter(active=True)

        qs = _safe_order_by(qs, Product, "name")[:500]

        items: list[dict[str, Any]] = []
        for p in qs:
            items.append(
                {
                    "id": getattr(p, "id", None),
                    "name": getattr(p, "name", str(p)),
                    # Provide a default order price if your model has it
                    "default_order_price": (
                        getattr(p, "order_price", None)
                        or getattr(p, "default_cost", None)
                        or getattr(p, "cost", None)
                        or getattr(p, "price", None)
                    ),
                }
            )
        return items
    except Exception:
        return []


def _query_locations(request) -> list[dict[str, Any]]:
    locs = _locations_for_active_business(request)
    return locs


# ---------------------------------------------------------------------
# Idempotent Scan-In upsert using unscoped manager
# ---------------------------------------------------------------------
def _scan_in_upsert(active_biz, imei15: str, defaults: dict[str, Any]):
    """
    Idempotent create-or-fetch for Scan-In.
    Uses the model's _base_manager to avoid tenant/scope filters interfering.
    Respects schema differences by checking fields before setting.
    """
    if not InventoryItem:
        raise RuntimeError("InventoryItem model not found")

    # Strip defaults to only fields that exist
    safe_defaults: dict[str, Any] = {}
    for k, v in (defaults or {}).items():
        if _model_has_field(InventoryItem, k):
            safe_defaults[k] = v

    try:
        with transaction.atomic():
            item, created = InventoryItem._base_manager.get_or_create(
                business=active_biz,
                imei=imei15,
                defaults=safe_defaults,
            )
    except IntegrityError:
        # UNIQUE(business_id, imei) collides, fetch existing row
        item = InventoryItem._base_manager.get(business=active_biz, imei=imei15)
        created = False

    # Ensure key fields are correct even when not created
    dirty = []

    # Status -> IN_STOCK if status field exists and not already IN_STOCK
    if _model_has_field(InventoryItem, "status"):
        if getattr(item, "status", None) != "IN_STOCK":
            setattr(item, "status", "IN_STOCK")
            dirty.append("status")

    # is_active True if the column exists
    if _model_has_field(InventoryItem, "is_active"):
        if getattr(item, "is_active", None) is not True:
            setattr(item, "is_active", True)
            dirty.append("is_active")

    # sold_at -> NULL if exists (freshly scanned-in should not be sold)
    if _model_has_field(InventoryItem, "sold_at"):
        if getattr(item, "sold_at", None) is not None:
            setattr(item, "sold_at", None)
            dirty.append("sold_at")

    # Location (prefer current_location_id, then location_id)
    loc_id = safe_defaults.get("current_location_id") or safe_defaults.get("location_id")
    if loc_id:
        if _model_has_field(InventoryItem, "current_location_id"):
            if getattr(item, "current_location_id", None) != loc_id:
                setattr(item, "current_location_id", loc_id)
                dirty.append("current_location_id")
        elif _model_has_field(InventoryItem, "location_id"):
            if getattr(item, "location_id", None) != loc_id:
                setattr(item, "location_id", loc_id)
                dirty.append("location_id")

    if dirty:
        try:
            item.save(update_fields=dirty)
        except Exception:
            # Fallback if some backends need a full save
            item.save()

    return item, created


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------
class ScanInView(TemplateView):
    template_name = "inventory/scan_in.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        products = _query_products(request)
        locations = _query_locations(request)
        default_loc_id, default_loc_name = _pick_default_location(request, locations)
        biz = _get_active_business(request)

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_in"),
                "products": products,                 # for Product select
                "locations": locations,               # restricted to active business
                "default_location_id": default_loc_id,
                "default_location_name": default_loc_name,
                "active_business_name": getattr(biz, "name", None),
                "lock_location": True,                # UI hint: render disabled + hidden mirror input
                "received_date_default": date.today(),  # default date “today”
                "rules": {
                    "imei_length": 15,
                    "require_product": True,
                    "order_price_autofill": True,      # template can use this to auto-fill from product
                },
            }
        )
        return ctx


class ScanSoldView(TemplateView):
    template_name = "inventory/scan_sold.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        products = _query_products(request)
        locations = _query_locations(request)
        default_loc_id, default_loc_name = _pick_default_location(request, locations)
        biz = _get_active_business(request)

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_sold"),
                "products": products,
                "locations": locations,               # still a dropdown, but only within active business
                "default_location_id": default_loc_id,
                "default_location_name": default_loc_name,
                "active_business_name": getattr(biz, "name", None),
                "lock_location": False,               # UI hint: allow changing on Sell
                "rules": {
                    "imei_length": 15,
                    "require_product": True,
                },
            }
        )
        return ctx


# ---------------------------------------------------------------------
# API: Scan-In (idempotent, location-locked to active business)
# Wire this in urls.py as name="inventory:api_scan_in"
# ---------------------------------------------------------------------
@never_cache
@csrf_exempt  # remove if you enforce CSRF; your site already injects CSRF meta
@login_required
def api_scan_in(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    if not InventoryItem:
        return JsonResponse({"ok": False, "error": "InventoryItem model not available"}, status=500)

    body = _json_body(request)

    raw_imei = (body.get("imei") or body.get("code") or body.get("barcode") or "").strip()
    imei15 = _normalize_imei(raw_imei)
    if not _IMEI_RX.match(imei15):
        return JsonResponse({"ok": False, "error": "Invalid IMEI; must be 15 digits"}, status=400)

    # Resolve active business
    biz = _get_active_business(request)
    if not getattr(biz, "id", None):
        return JsonResponse({"ok": False, "error": "No active business selected"}, status=400)

    # Resolve product_id if provided
    product_id = None
    try:
        pid_raw = body.get("product_id") or body.get("product")
        if pid_raw not in (None, "", 0, "0"):
            product_id = int(pid_raw)
    except Exception:
        product_id = None

    # Gather business-scoped locations and pick default if none provided
    locations = _locations_for_active_business(request)
    default_loc_id, _default_loc_name = _pick_default_location(request, locations)

    loc_id = body.get("location_id") or body.get("location") or default_loc_id
    try:
        loc_id = int(loc_id) if loc_id not in (None, "", "0") else None
    except Exception:
        loc_id = None

    # Build defaults respecting your schema
    defaults: dict[str, Any] = {"status": "IN_STOCK"}
    if product_id and _model_has_field(InventoryItem, "product_id"):
        defaults["product_id"] = product_id
    if loc_id:
        if _model_has_field(InventoryItem, "current_location_id"):
            defaults["current_location_id"] = loc_id
        elif _model_has_field(InventoryItem, "location_id"):
            defaults["location_id"] = loc_id
    if _model_has_field(InventoryItem, "is_active"):
        defaults["is_active"] = True
    if _model_has_field(InventoryItem, "sold_at"):
        defaults["sold_at"] = None

    try:
        item, created = _scan_in_upsert(biz, imei15, defaults)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Scan-in failed: {e.__class__.__name__}: {e}"}, status=500)

    payload = {
        "ok": True,
        "created": bool(created),
        "item_id": getattr(item, "id", None),
        "imei": imei15,
        "product_id": getattr(item, "product_id", None) if _model_has_field(InventoryItem, "product_id") else product_id,
        "location_id": (
            getattr(item, "current_location_id", None)
            if _model_has_field(InventoryItem, "current_location_id")
            else (getattr(item, "location_id", None) if _model_has_field(InventoryItem, "location_id") else None)
        ),
        "status": getattr(item, "status", None) if _model_has_field(InventoryItem, "status") else None,
    }
    return JsonResponse(payload, status=200)
