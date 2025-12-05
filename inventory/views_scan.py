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


def _business_default_location_id(request, locations: list[dict[str, Any]]) -> Optional[int]:
    """
    If your Location model has `is_default=True` for a business, prefer that.
    """
    if not Location or not locations:
        return None
    try:
        biz = _get_active_business(request)
        if biz is None:
            return None
        if _model_has_field(Location, "is_default"):
            loc = Location.objects.filter(is_default=True).filter(
                **({ "business": biz } if _model_has_field(Location, "business") else {})
            ).first()
            if loc:
                return getattr(loc, "id", None)
    except Exception:
        return None
    return None


def _pick_default_location(request, locations: list[dict[str, Any]]) -> tuple[Optional[int], Optional[str]]:
    """
    Choose a default location from the already business-filtered list of dicts
    (each dict has {'id', 'name'}).
      1) agent's home location (if present in the list)
      2) business default (is_default=True) if available
      3) a location whose name == active business name
      4) first location
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

    # 2) Business default
    def_id = _business_default_location_id(request, locations)
    if def_id is not None:
        for it in locations:
            if it.get("id") == def_id:
                return it["id"], it["name"]

    # 3) Match by business name
    biz = _get_active_business(request)
    biz_name = getattr(biz, "name", None)
    if biz_name:
        bn = str(biz_name).strip().lower()
        for it in locations:
            if str(it.get("name", "")).strip().lower() == bn:
                return it["id"], it["name"]

    # 4) First available
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

        # expose both "default_location" (dict) AND the *_id/*_name fields to satisfy older templates
        default_location_dict = (
            {"id": default_loc_id, "name": default_loc_name} if default_loc_id else None
        )

        # NEW: Get phone brands for Brand → Model filtering (PHONES businesses only)
        phone_brands = []
        try:
            from inventory.phone_catalog_seed import get_brands_for_business
            if biz:
                phone_brands = get_brands_for_business(biz)
        except Exception:
            pass

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_in"),
                "products": products,                   # for Product select (list of dicts)
                "locations": locations,                 # restricted to active business (list of dicts)
                "default_location": default_location_dict,
                "default_location_id": default_loc_id,  # for data-* attributes
                "default_location_name": default_loc_name,
                "active_business_name": getattr(biz, "name", None),
                "lock_location": True,                  # UI hint: render disabled + hidden mirror input for agents
                "received_date_default": date.today(),  # default date "today"
                "phone_brands": phone_brands,           # List of brands for PHONES businesses
                "phone_brands_api_url": reverse_lazy("inventory:api_phone_brands"),  # Brand API endpoint
                "phone_models_api_url": reverse_lazy("inventory:api_phone_models"),  # Model API endpoint (filtered)
                "rules": {
                    "imei_length": 15,
                    "require_product": True,
                    "order_price_autofill": True,        # template can use this to auto-fill from product
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

        default_location_dict = (
            {"id": default_loc_id, "name": default_loc_name} if default_loc_id else None
        )

        ctx.update(
            {
                "post_url": reverse_lazy("inventory:api_scan_sold"),
                "products": products,
                "locations": locations,                 # dropdown limited to active business
                "default_location": default_location_dict,
                "default_location_id": default_loc_id,
                "default_location_name": default_loc_name,
                "active_business_name": getattr(biz, "name", None),
                "lock_location": False,                 # allow managers to change on Sell
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

    # ===== DUPLICATE IMEI CHECK: Never stock the same device twice =====
    # Check if this IMEI already exists for this business (regardless of status)
    existing_item = InventoryItem._base_manager.filter(business=biz, imei=imei15).first()
    if existing_item:
        return JsonResponse({
            "ok": False,
            "error": "This IMEI already exists in your records. We never stock the same device twice.",
            "existing_item_id": getattr(existing_item, "id", None),
            "existing_status": getattr(existing_item, "status", None)
        }, status=400)

    # Resolve product_id (could be from generic Product or PhoneProductCatalog)
    product_id = None
    phone_catalog_id = None
    order_price_value = None
    
    try:
        # Check if phone_catalog_id provided (preferred for phones vertical)
        phone_catalog_id = body.get("phone_catalog_id") or body.get("catalog_product_id")
        if phone_catalog_id:
            phone_catalog_id = int(phone_catalog_id)
            # Fetch PhoneProductCatalog to get default cost price
            try:
                from inventory.models_phone_products import PhoneProductCatalog
                catalog_product = PhoneProductCatalog.objects.get(id=phone_catalog_id, business=biz)
                if catalog_product.default_cost_price:
                    order_price_value = catalog_product.default_cost_price
                # If there's a linked Product, use it; otherwise leave product_id as None
                # (phones may not have a Product FK, only catalog reference)
            except Exception:
                pass  # PhoneProductCatalog not found or import failed; continue
        
        # Fallback: generic product_id
        if not phone_catalog_id:
            pid_raw = body.get("product_id") or body.get("product")
            if pid_raw not in (None, "", 0, "0"):
                product_id = int(pid_raw)
    except Exception:
        pass  # Invalid IDs; continue with None

    # Parse order_price from body (overrides catalog default)
    try:
        order_price_raw = body.get("order_price")
        if order_price_raw not in (None, "", "0"):
            from decimal import Decimal
            order_price_value = Decimal(str(order_price_raw))
    except Exception:
        pass  # Keep catalog default or 0

    # Default to 0 if still None
    if order_price_value is None:
        from decimal import Decimal
        order_price_value = Decimal("0.00")

    # Gather business-scoped locations and pick default if none provided
    locations = _locations_for_active_business(request)
    default_loc_id, _default_loc_name = _pick_default_location(request, locations)

    # Parse requested location and **enforce** it belongs to active business; otherwise fallback to default
    def _as_int(val):
        try:
            return int(val)
        except Exception:
            return None

    requested_loc_id = _as_int(body.get("location_id") or body.get("location"))
    allowed_ids = {loc["id"] for loc in locations if loc.get("id") is not None}
    loc_id = requested_loc_id if (requested_loc_id in allowed_ids) else default_loc_id

    if not loc_id:
        return JsonResponse({"ok": False, "error": "No valid location available"}, status=400)

    # Parse received_at date (default to today)
    received_at_value = None
    try:
        received_raw = body.get("received_at")
        if received_raw:
            from datetime import datetime
            received_at_value = datetime.strptime(received_raw, "%Y-%m-%d").date()
    except Exception:
        pass
    if not received_at_value:
        from datetime import date
        received_at_value = date.today()

    # ===== CREATE NEW INVENTORY ITEM (no longer idempotent upsert) =====
    try:
        with transaction.atomic():
            item = InventoryItem.objects.create(
                business=biz,
                imei=imei15,
                product_id=product_id,  # May be None for phones using only catalog
                order_price=order_price_value,
                status="IN_STOCK",
                current_location_id=loc_id,
                is_active=True,
                received_at=received_at_value,
                sold_at=None,
            )
            
            # Optional: Assign to requesting agent if checkbox checked
            if body.get("assigned_to_me") and not request.user.is_staff:
                item.assigned_agent = request.user
                item.save(update_fields=["assigned_agent"])
            
    except Exception as e:
        return JsonResponse({
            "ok": False,
            "error": f"Failed to create inventory item: {e.__class__.__name__}: {e}"
        }, status=500)

    payload = {
        "ok": True,
        "created": True,
        "item_id": item.id,
        "imei": imei15,
        "product_id": item.product_id,
        "location_id": item.current_location_id,
        "status": item.status,
        "order_price": str(item.order_price),
        "received_at": str(item.received_at),
    }
    return JsonResponse(payload, status=200)


# ---------------------------------------------------------------------
# API: Get brands for phone intake (used for Brand dropdown)
# ---------------------------------------------------------------------
@never_cache
@login_required
def api_phone_brands(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get available phone brands for the active business.
    Returns brands from PhoneProductCatalog.
    
    Returns:
        JSON: {"brands": ["TECNO", "ITEL", "SAMSUNG", ...]}
    """
    try:
        from inventory.models_phone_products import PhoneProductCatalog
        from inventory.phone_catalog_seed import get_brands_for_business
    except ImportError:
        return JsonResponse({"error": "PhoneProductCatalog not available"}, status=500)
    
    biz = _get_active_business(request)
    if not getattr(biz, "id", None):
        return JsonResponse({"error": "No active business selected"}, status=400)
    
    try:
        brands = get_brands_for_business(biz)
        return JsonResponse({"brands": brands})
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch brands: {e}"}, status=500)


# ---------------------------------------------------------------------
# API: Get models for a brand (used for Model dropdown, filtered by Brand)
# ---------------------------------------------------------------------
@never_cache
@login_required
def api_phone_models(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to get phone models for a specific brand.
    
    Query params:
        brand: Brand name (e.g., "TECNO", "ITEL", "SAMSUNG")
    
    Returns:
        JSON: {
            "models": [
                {
                    "id": 1,
                    "model_name": "Spark 40",
                    "variant_label": "4+128",
                    "ram_gb": 4,
                    "rom_gb": 128,
                    "default_cost_price": "450000.00",
                    "default_selling_price": "550000.00",
                    "display_name": "TECNO Spark 40 (4+128)"
                },
                ...
            ]
        }
    """
    try:
        from inventory.models_phone_products import PhoneProductCatalog
        from inventory.phone_catalog_seed import get_models_for_brand
    except ImportError:
        return JsonResponse({"error": "PhoneProductCatalog not available"}, status=500)
    
    biz = _get_active_business(request)
    if not getattr(biz, "id", None):
        return JsonResponse({"error": "No active business selected"}, status=400)
    
    brand = request.GET.get("brand", "").strip()
    if not brand:
        return JsonResponse({"error": "Brand parameter required"}, status=400)
    
    try:
        models = get_models_for_brand(biz, brand)
        
        # Convert Decimal to string for JSON serialization
        for model in models:
            if model.get("default_cost_price"):
                model["default_cost_price"] = str(model["default_cost_price"])
            if model.get("default_selling_price"):
                model["default_selling_price"] = str(model["default_selling_price"])
        
        return JsonResponse({"models": models})
    except Exception as e:
        return JsonResponse({"error": f"Failed to fetch models: {e}"}, status=500)
