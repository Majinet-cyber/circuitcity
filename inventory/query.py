# circuitcity/inventory/query.py
from __future__ import annotations

from datetime import timedelta
from typing import Optional, Tuple, Any

import re
from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

# --- Inventory models (current project shapes) ---
try:
    from .models import InventoryItem, Product, Location  # type: ignore
except Exception:  # pragma: no cover
    InventoryItem = None  # type: ignore
    Product = None  # type: ignore
    Location = None  # type: ignore

# Try to import Sale model (optional; we’ll guard its usage)
try:
    from sales.models import Sale  # type: ignore
except Exception:  # pragma: no cover
    Sale = None  # type: ignore

# Active business (single source of truth)
try:
    from tenants.utils import get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None


# ---------------------------------------------------------------------------
# Normalization helpers (shared by scan_in / scan_sold and search)
# ---------------------------------------------------------------------------
def _digits(raw: Optional[str | int]) -> str:
    if raw is None:
        return ""
    return re.sub(r"\D+", "", str(raw))


def _normalize_code(raw: Optional[str]) -> str:
    """
    Normalize scanned codes.
      • If 15+ digits present → keep last 15 (IMEI semantics)
      • Else uppercase trimmed string
    """
    if not raw:
        return ""
    s = str(raw).strip()
    d = _digits(s)
    if len(d) >= 15:
        return d[-15:]
    return s.upper()


def _sold_status_key(model) -> str:
    """
    Return the 'SOLD' key from a model.STATUS if present, else 'SOLD'.
    """
    try:
        choices = getattr(model, "STATUS", None)
        if isinstance(choices, (list, tuple)):
            for key, _label in choices:
                if str(key).upper() == "SOLD":
                    return str(key)
    except Exception:
        pass
    return "SOLD"


# ---------------------------------------------------------------------------
# Business scoping
# ---------------------------------------------------------------------------
def base_scope(request) -> Tuple[Optional[Any], Any]:
    """
    Returns (biz, qs) scoped to the active business.
    Uses InventoryItem (not a generic Inventory model).
    """
    if InventoryItem is None:
        return None, None

    biz = getattr(request, "active_business", None) or getattr(request, "business", None)
    qs = InventoryItem.objects.all()
    if biz:
        qs = qs.filter(business_id=getattr(biz, "pk", None))
    return biz, qs


# ---------------------------------------------------------------------------
# Stock list / search source of truth
# ---------------------------------------------------------------------------
def build_inventory_queryset(
    request,
    *,
    search: str = "",
    status: str = "all",
    include_archived: bool = False,
    location_id: int | None = None,
):
    """
    Single source of truth for Stock queries.

    Args:
      status ∈ {"all","in_stock","sold"}  (case-insensitive)
        - Maps to InventoryItem.STATUS keys: IN_STOCK / SOLD
      include_archived:
        - False → filter is_active=True (hide archived/soft-deleted)
      location_id:
        - Filters by current_location_id when provided
      search:
        - IMEI (exact or icontains), plus brand/model/product name match
    """
    biz, qs = base_scope(request)
    if qs is None:
        return None

    if not include_archived:
        qs = qs.filter(is_active=True)

    if location_id:
        qs = qs.filter(current_location_id=location_id)

    st = (status or "all").strip().lower()
    if st != "all":
        if st == "in_stock":
            qs = qs.filter(status="IN_STOCK")
        elif st == "sold":
            qs = qs.filter(status=_sold_status_key(InventoryItem))
        else:
            # Pass-through for custom statuses if they ever exist on the model
            qs = qs.filter(status__iexact=st)

    q = (search or "").strip()
    if q:
        # Support IMEI-like scans (normalize to last 15 digits)
        norm = _normalize_code(q)
        # If we have 15 digits, treat as an IMEI-first search.
        imei_criteria = Q()
        d = _digits(q)
        if len(d) >= 5:  # small optimization: only try imei icontains if some digits present
            if len(d) >= 15:
                imei_criteria = Q(imei=d[-15:])
            else:
                imei_criteria = Q(imei__icontains=d)

        text_criteria = (
            Q(product__name__icontains=q)
            | Q(product__brand__icontains=q)
            | Q(product__model__icontains=q)
        )

        # If the normalized form is not all digits (e.g., typed code), also attempt exact imei match
        if norm and not norm.isdigit():
            imei_criteria = imei_criteria | Q(imei=norm)

        qs = qs.filter(imei_criteria | text_criteria)

    # Always pull common relations for list views to avoid N+1s
    qs = qs.select_related("product", "current_location", "assigned_agent")

    return qs


# ---------------------------------------------------------------------------
# Dashboard rollups (safe if Sale model is absent)
# ---------------------------------------------------------------------------
def dashboard_counts(request):
    """
    Consistent with build_inventory_queryset:
      - products: DISTINCT products among active items
      - items_in_stock: active + IN_STOCK
      - sales_mtd: sum of Sale.final_amount for business since month start (0 if Sale missing)
    """
    biz, inv = base_scope(request)
    if inv is None:
        return {"products": 0, "items_in_stock": 0, "sales_mtd": 0}

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    items_in_stock = (
        inv.filter(status="IN_STOCK", is_active=True).count()
    )

    products = (
        inv.filter(is_active=True)
           .values("product_id")
           .distinct()
           .count()
    )

    if biz and Sale is not None:
        sales_mtd = (
            Sale.objects.filter(business_id=getattr(biz, "pk", None), sold_at__gte=month_start)
            .aggregate(total=Coalesce(Sum("final_amount"), 0))["total"]
            or 0
        )
    else:
        sales_mtd = 0

    return {
        "products": products,
        "items_in_stock": items_in_stock,
        "sales_mtd": sales_mtd,
    }


def sales_in_range(request, *, days: int = 7):
    """
    Sum of sales over the last N days for the active business.
    Returns 0 if no active business or Sale model is unavailable.
    """
    biz, _ = base_scope(request)
    if not biz or Sale is None:
        return 0
    since = timezone.now() - timedelta(days=days)
    return (
        Sale.objects.filter(business_id=getattr(biz, "pk", None), sold_at__gte=since)
        .aggregate(total=Coalesce(Sum("final_amount"), 0))["total"]
        or 0
    )


# ---------------------------------------------------------------------------
# Public convenience exports (if other modules prefer non-underscore names)
# ---------------------------------------------------------------------------
digits_only = _digits
normalize_code = _normalize_code
sold_status_key = _sold_status_key
