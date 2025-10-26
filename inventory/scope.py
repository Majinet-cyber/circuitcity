# inventory/scope.py
from __future__ import annotations

from typing import Optional, Tuple, Iterable, Any, Callable, Set
import importlib

from django.http import HttpRequest
from django.db.models import QuerySet


# ------------------------------
# Safe optional import helper
# ------------------------------
def _try_import(modpath: str, attr: str | None = None):
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None


# ------------------------------
# Tenant helpers (optional; no-ops if missing)
# ------------------------------
scoped: Callable[[QuerySet, HttpRequest], QuerySet] = (
    _try_import("circuitcity.tenants.utils", "scoped")
    or _try_import("tenants.utils", "scoped")
    or (lambda qs, _r: qs)
)

get_active_business = (
    _try_import("circuitcity.tenants.utils", "get_active_business")
    or _try_import("tenants.utils", "get_active_business")
    or (lambda _r: None)
)


# ------------------------------
# Small utilities
# ------------------------------
def _field_names(model) -> Set[str]:
    """Return the set of concrete field names for a model (safe)."""
    try:
        return {f.name for f in model._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        return set()

def _as_int_or_none(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None

def _first_present_attr(obj: Any, keys: Iterable[str]):
    for k in keys:
        try:
            v = getattr(obj, k, None)
        except Exception:
            v = None
        if v is not None:
            return v
    return None


# ------------------------------
# Model resolution â€” single source of truth
# ------------------------------
def get_inventory_model():
    """
    Resolve the concrete inventory model without importing a specific class
    at module-import time. We try common names in order.
    """
    models_mod = (
        _try_import("inventory.models")
        or _try_import("circuitcity.inventory.models")
    )
    if not models_mod:
        return None

    for name in ("InventoryItem", "Inventory", "Stock"):
        model = getattr(models_mod, name, None)
        if model is not None:
            return model
    return None


# ------------------------------
# Active scope helpers
# ------------------------------
# Common attribute/session/query aliases across the codebase family
_BIZ_ATTRS = ("business_id", "tenant_id")
_LOC_ATTRS = ("active_location_id", "location_id", "store_id")

_SESS_BIZ = ("active_business_id", "business_id", "tenant_id", "current_business_id")
_SESS_LOC = ("active_location_id", "location_id", "store_id", "current_location_id")

_GET_BIZ = ("biz", "business", "business_id", "tenant", "tenant_id")
_GET_LOC = ("loc", "location", "location_id", "store", "store_id", "branch", "warehouse_id")


def active_scope(request: HttpRequest) -> Tuple[Optional[int], Optional[int]]:
    """
    Returns (business_id, location_id) from:
      tenants helper -> request attrs -> session -> GET aliases.
    Tolerates missing middleware and old links.
    """
    # 1) tenants helper (preferred)
    try:
        biz_obj = get_active_business(request)
    except Exception:
        biz_obj = None

    biz_id = getattr(biz_obj, "id", None)

    # 2) request attributes (middleware / view bootstrap)
    if biz_id is None:
        biz_id = _first_present_attr(request, _BIZ_ATTRS)
    loc_id = _first_present_attr(request, _LOC_ATTRS)

    # 3) session fallbacks
    sess = getattr(request, "session", {}) or {}
    if biz_id is None:
        for k in _SESS_BIZ:
            v = sess.get(k)
            if v is not None:
                biz_id = v
                break
    if loc_id is None:
        for k in _SESS_LOC:
            v = sess.get(k)
            if v is not None:
                loc_id = v
                break

    # 4) GET aliases (keep old links alive)
    if biz_id is None:
        for k in _GET_BIZ:
            v = request.GET.get(k)
            if v:
                biz_id = _as_int_or_none(v) or v  # accept non-int ids if needed
                break
    if loc_id is None:
        for k in _GET_LOC:
            v = request.GET.get(k)
            if v:
                loc_id = _as_int_or_none(v) or v
                break

    # normalize to ints when possible
    biz_id = _as_int_or_none(biz_id) if biz_id is not None else None
    loc_id = _as_int_or_none(loc_id) if loc_id is not None else None
    return biz_id, loc_id


# ------------------------------
# Canonical queryset builder
# ------------------------------
def stock_queryset_for_request(request: HttpRequest) -> QuerySet:
    """
    Build the canonical inventory queryset:
      - tenant/role scoped
      - filtered by active business
      - optionally filtered by location/current_location
      - excludes sold/inactive/archived records by default
      - supports ?status=all|available|selling|sold|archived (case-insensitive)
      - adds select_related for common relations

    This is the ONE place that defines what â€œin stockâ€ means.
    """
    Model = get_inventory_model()
    if Model is None:
        raise RuntimeError("No inventory model found (InventoryItem/Inventory/Stock).")

    # use base manager to avoid surprise default manager filters
    manager = getattr(Model, "_base_manager", Model.objects)
    qs: QuerySet = manager.all()

    # Apply tenant/role scoping if available
    try:
        qs = scoped(qs, request)
    except Exception:
        pass

    fields = _field_names(Model)
    biz_id, loc_id = active_scope(request)

    # ---------- Business filter ----------
    if biz_id is not None and ("business" in fields or "business_id" in fields):
        try:
            qs = qs.filter(business_id=biz_id)
        except Exception:
            try:
                qs = qs.filter(business__id=biz_id)
            except Exception:
                pass

    # ---------- Location filter (prefer current_location) ----------
    if loc_id is not None:
        for fk in ("current_location", "location", "store", "branch", "warehouse"):
            if fk in fields or f"{fk}_id" in fields:
                # try *_id first for speed/clarity; fall back to relation
                try:
                    qs = qs.filter(**{f"{fk}_id": loc_id})
                    break
                except Exception:
                    try:
                        qs = qs.filter(**{fk: loc_id})
                        break
                    except Exception:
                        continue

    # ---------- Status normalization ----------
    # Default behavior: show items that are *available / in stock*
    raw_status = (request.GET.get("status") or "").strip().lower()

    if raw_status in ("", "ai", "all"):
        # No explicit status filter; we'll still exclude sold/archived/inactive below
        pass
    elif raw_status in ("available", "in_stock", "in-stock"):
        if "available" in fields:
            qs = qs.filter(available=True)
        elif "status" in fields:
            qs = qs.filter(status__in=["available", "in_stock", "in-stock", "IN_STOCK", "Available"])
    elif raw_status in ("selling",):
        if "status" in fields:
            qs = qs.filter(status__iexact="selling")
    elif raw_status in ("sold",):
        if "status" in fields:
            qs = qs.filter(status__iexact="sold")
        elif "sold_at" in fields:
            qs = qs.exclude(sold_at__isnull=True)
    elif raw_status in ("archived",):
        if "archived" in fields:
            qs = qs.filter(archived=True)

    # ---------- Exclude sold / inactive / archived by default ----------
    if raw_status not in ("sold", "archived"):
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

    # ---------- Useful joins ----------
    joins: Iterable[str] = [j for j in ("product", "current_location", "location", "business") if j in fields]
    if joins:
        try:
            qs = qs.select_related(*joins)
        except Exception:
            pass

    return qs


