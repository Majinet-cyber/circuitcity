# inventory/lookup.py
from __future__ import annotations

import re
from typing import Iterable, Tuple, Optional

from django.db import models
from django.db.models import Q

# ---- Lazy imports (no hard crashes at import time) ---------------------------
try:
    from tenants.utils import get_active_business  # canonical if available
except Exception:  # pragma: no cover
    def get_active_business(_request):
        return None

try:
    from .models import InventoryItem as _InventoryItem, Location as _Location
    InventoryItem = _InventoryItem
    Location = _Location
except Exception:  # pragma: no cover
    InventoryItem = None  # type: ignore
    Location = None  # type: ignore


# =============================================================================
# Normalization helpers
# =============================================================================
IMEI_RX = re.compile(r"^\d{15}$")


def _digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def _normalize_code(raw: Optional[str]) -> str:
    """
    Normalize any scanned code:
      - Trim spaces
      - If IMEI-ish, keep only digits (many scanners add spaces/dashes)
    Otherwise return as-is trimmed (for non-IMEI codes like SKU/serial).
    """
    s = (raw or "").strip()
    d = _digits(s)
    # If the digits look like a 15-length IMEI (or longer where IMEI is a substring), prioritize digits
    # Keep last 15 digits for safety (some stickers include extra chars)
    if len(d) >= 15:
        return d[-15:]
    return s


# =============================================================================
# Model/schema helpers
# =============================================================================
def _fieldnames(model) -> set[str]:
    try:
        return {f.name for f in model._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        return set()


def _hasf(model, name: str) -> bool:
    return name in _fieldnames(model)


def _candidate_code_fields(model) -> Iterable[str]:
    """
    Order matters: we try IMEI-ish fields first, then common code holders.
    """
    names = _fieldnames(model)
    order = [
        "imei", "imei1", "imei_1",
        "barcode", "serial",
        "sku", "code",
        "name",
    ]
    return [n for n in order if n in names]


def _manager(model):
    return getattr(model, "objects", None) or getattr(model, "_base_manager", None)


def _is_soldish(obj) -> bool:
    """
    A tolerant predicate to exclude anything already sold/closed/unavailable.
    """
    status_val = str(getattr(obj, "status", "") or "").strip().lower()
    qty = None
    for k in ("quantity", "qty"):
        if hasattr(obj, k):
            try:
                qty = int(getattr(obj, k) or 0)
            except Exception:
                qty = None
            break

    return any([
        bool(getattr(obj, "sold_at", None)),
        bool(getattr(obj, "is_sold", False)),
        status_val in {"sold", "completed", "closed"},
        (hasattr(obj, "in_stock") and getattr(obj, "in_stock") is False),
        (hasattr(obj, "available") and getattr(obj, "available") is False),
        (hasattr(obj, "availability") and not getattr(obj, "availability")),
        (qty is not None and qty <= 0),
    ])


# =============================================================================
# Scoping
# =============================================================================
def scoped_stock_queryset(request):
    """
    Start from a tenant-scoped queryset.
    Priority:
      1) InventoryItem.objects (TenantManager) if present
      2) InventoryItem._base_manager and filter by active business id
    Applies a conservative active/non-archived filter when fields exist.
    """
    if InventoryItem is None:
        return None

    mgr = _manager(InventoryItem)
    if mgr is None:
        return None

    qs = mgr.all()

    # Prefer the active business from request; if tenant manager already scopes,
    # this filter is harmless; if not, it constrains to current business.
    biz = get_active_business(request)
    if biz is not None:
        bfid = None
        if _hasf(InventoryItem, "business_id"):
            bfid = "business_id"
        elif _hasf(InventoryItem, "business"):
            bfid = "business"
        if bfid:
            try:
                qs = qs.filter(Q(**{bfid: getattr(biz, "id", biz)}))
            except Exception:
                pass

    # Only active/not-archived if those fields exist
    if _hasf(InventoryItem, "is_active"):
        qs = qs.filter(is_active=True)
    if _hasf(InventoryItem, "archived"):
        qs = qs.filter(archived=False)

    return qs


def _apply_location_filter(qs, location_id) -> models.QuerySet:
    """
    Apply a strict location filter if the model exposes any common location FK.
    """
    if not location_id:
        return qs

    for fk in ("current_location_id", "location_id", "store_id", "branch_id", "warehouse_id"):
        if _hasf(qs.model, fk):
            try:
                return qs.filter(**{fk: location_id})
            except Exception:
                continue

    # If only the relation exists (no *_id), try that
    for fk in ("current_location", "location", "store", "branch", "warehouse"):
        if _hasf(qs.model, fk):
            try:
                return qs.filter(**{fk: location_id})
            except Exception:
                continue
    return qs


def _exclude_soldish_q(qs: models.QuerySet) -> models.QuerySet:
    """
    Narrow qs down to rows that are likely in stock.
    """
    names = _fieldnames(qs.model)

    # sold_at is null
    if "sold_at" in names:
        try:
            qs = qs.filter(sold_at__isnull=True)
        except Exception:
            pass

    # status != SOLD
    if "status" in names:
        try:
            qs = qs.exclude(status__iexact="sold")
        except Exception:
            pass

    # booleans that imply availability
    for fname, expect in (("is_sold", False), ("in_stock", True), ("available", True), ("availability", True)):
        if fname in names:
            try:
                qs = qs.filter(**{fname: expect})
            except Exception:
                pass

    # quantity > 0 (soft)
    if "quantity" in names:
        try:
            qs = qs.filter(Q(quantity__gt=0) | Q(quantity__isnull=True))
        except Exception:
            pass
    if "qty" in names:
        try:
            qs = qs.filter(Q(qty__gt=0) | Q(qty__isnull=True))
        except Exception:
            pass

    return qs


# =============================================================================
# Finders
# =============================================================================
def _first_match(qs: models.QuerySet, model, code: str, digits: str) -> Tuple[Optional[object], Optional[str]]:
    """
    Try a series of exact, then partial matches across candidate fields.
    Returns (obj, matched_field_name) or (None, None).
    """
    fields = list(_candidate_code_fields(model))

    # 1) IMEI exact (only if digits look like 15-digit IMEI)
    if IMEI_RX.match(digits):
        for f in fields:
            if f.startswith("imei"):
                try:
                    o = qs.filter(**{f: digits}).first()
                    if o:
                        return o, f
                except Exception:
                    continue

    # 2) Exact code in any candidate field
    for f in fields:
        try:
            o = qs.filter(**{f: code}).first()
            if o:
                return o, f
        except Exception:
            continue

    # 3) Partial fallback (use last 6+ digits or the code, whichever is longer)
    snippet = digits if len(digits) >= 6 else code
    if len(snippet) >= 6:
        for f in fields:
            try:
                o = qs.filter(**{f"{f}__icontains": snippet}).first()
                if o:
                    return o, f
            except Exception:
                continue

    return None, None


def find_in_stock_by_code(
    request,
    raw_code: str,
    *,
    business_wide_fallback: bool = True,
    requested_location_id: Optional[int] = None,
) -> Tuple[Optional[object], Optional[str]]:
    """
    Tolerant finder for Scan Sold / Stock checks.

    Passes:
      1) Strict: selected location (if provided) + in-stock filtering
      2) Business-wide fallback: ignores location entirely, still excludes sold-ish

    Returns: (object_or_None, matched_field_name_or_None)
    """
    if InventoryItem is None:
        return None, None

    code = _normalize_code(raw_code)
    digits = _digits(code)

    # ---------- PASS 1: strictly within requested location ----------
    qs = scoped_stock_queryset(request)
    if qs is not None:
        qs1 = _exclude_soldish_q(qs)
        if requested_location_id:
            qs1 = _apply_location_filter(qs1, requested_location_id)

        obj, matched = _first_match(qs1, qs.model, code, digits)
        if obj is not None and not _is_soldish(obj):
            return obj, matched

    # ---------- PASS 2: business-wide (ignore location) ----------
    if business_wide_fallback:
        # Start from an unfiltered manager but still clamp to business id (no location)
        mgr = _manager(InventoryItem)
        if mgr is not None:
            qs2 = mgr.all()
            biz = get_active_business(request)
            if biz is not None:
                try:
                    if _hasf(InventoryItem, "business_id"):
                        qs2 = qs2.filter(business_id=getattr(biz, "id", None))
                    elif _hasf(InventoryItem, "business"):
                        qs2 = qs2.filter(business=biz)
                except Exception:
                    pass

            qs2 = _exclude_soldish_q(qs2)

            obj2, matched2 = _first_match(qs2, InventoryItem, code, digits)
            if obj2 is not None and not _is_soldish(obj2):
                return obj2, matched2

    return None, None


# Convenience strict IMEI lookup (exact 15 digits only)
def find_in_stock_by_imei(request, imei_raw: str, *, requested_location_id: Optional[int] = None):
    """
    Exact 15-digit IMEI lookup, with the same two-pass strategy.
    """
    if InventoryItem is None:
        return None, None

    digits = _digits(imei_raw or "")
    if len(digits) != 15:
        return None, None

    # Pass 1 — strict + location
    qs = scoped_stock_queryset(request)
    if qs is not None:
        qs1 = _exclude_soldish_q(qs)
        if requested_location_id:
            qs1 = _apply_location_filter(qs1, requested_location_id)

        for f in ("imei", "imei1", "imei_1"):
            if _hasf(qs.model, f):
                try:
                    obj = qs1.filter(**{f: digits}).first()
                    if obj and not _is_soldish(obj):
                        return obj, f
                except Exception:
                    continue

    # Pass 2 — business-wide
    mgr = _manager(InventoryItem)
    if mgr is not None:
        qs2 = mgr.all()
        biz = get_active_business(request)
        if biz is not None:
            try:
                if _hasf(InventoryItem, "business_id"):
                    qs2 = qs2.filter(business_id=getattr(biz, "id", None))
                elif _hasf(InventoryItem, "business"):
                    qs2 = qs2.filter(business=biz)
            except Exception:
                pass
        qs2 = _exclude_soldish_q(qs2)

        for f in ("imei", "imei1", "imei_1"):
            if _hasf(InventoryItem, f):
                try:
                    obj = qs2.filter(**{f: digits}).first()
                    if obj and not _is_soldish(obj):
                        return obj, f
                except Exception:
                    continue

    return None, None
