# inventory/services_sales.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Any

from django.db import transaction
from django.utils import timezone

from tenants.utils import get_active_business, assert_owns
from .models import InventoryItem, Location


# ---- helpers --------------------------------------------------------------

def _digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _status_label(model) -> str:
    """
    Resolve the 'SOLD' enum/code on InventoryItem in a tolerant way.
    Supports:
      - class Status(Enum): SOLD = "SOLD"
      - STATUS_SOLD = "SOLD"
      - plain 'SOLD' string field.
    """
    # Enum-like (django choices or python Enum)
    try:
        if hasattr(model, "Status") and getattr(model.Status, "SOLD", None) is not None:
            val = model.Status.SOLD
            return getattr(val, "value", str(val))
    except Exception:
        pass
    # Constant
    if hasattr(model, "STATUS_SOLD"):
        return str(getattr(model, "STATUS_SOLD"))
    # Fallback literal
    return "SOLD"


def _status_in_stock(model) -> str:
    try:
        if hasattr(model, "Status") and getattr(model.Status, "IN_STOCK", None) is not None:
            val = model.Status.IN_STOCK
            return getattr(val, "value", str(val))
    except Exception:
        pass
    if hasattr(model, "STATUS_IN_STOCK"):
        return str(getattr(model, "STATUS_IN_STOCK"))
    return "IN_STOCK"


def _is_soldish(item: Any) -> bool:
    """
    Broad SOLD detector that copes with many schemas.
    """
    try:
        status_val = str(getattr(item, "status", "") or "").strip().lower()
    except Exception:
        status_val = ""
    try:
        qty_val = int(getattr(item, "quantity", getattr(item, "qty", 0)) or 0)
    except Exception:
        qty_val = 0

    return any([
        bool(getattr(item, "sold_at", None)),
        bool(getattr(item, "is_sold", False)),
        status_val in {"sold", "completed", "closed"},
        (hasattr(item, "in_stock") and getattr(item, "in_stock") is False),
        (hasattr(item, "available") and getattr(item, "available") is False),
        (hasattr(item, "availability") and not getattr(item, "availability")),
        qty_val <= 0,
    ])


def _product_display(item: InventoryItem) -> Optional[str]:
    p = getattr(item, "product", None)
    if p is None:
        return None
    for name in ("display_name", "model", "name"):
        v = getattr(p, name, None)
        if v:
            return str(v)
    return str(p)


@dataclass
class SaleResult:
    ok: bool
    code: str
    message: str
    item_id: Optional[int] = None
    imei: Optional[str] = None
    product: Optional[str] = None
    location: Optional[str] = None
    sold_at: Optional[str] = None
    price: Optional[str] = None


# ---- single source of truth ----------------------------------------------

@transaction.atomic
def mark_item_sold(
    request,
    *,
    imei: str,
    price: Decimal,
    sold_at: Optional[date] = None,
    location_id: Optional[int] = None,
    commission_pct: Optional[Decimal] = None,
) -> SaleResult:
    """
    Atomically mark a single IMEI as SOLD for the active tenant.
    This is the single source of truth for the 'sell' action.
    Does NOT create a sales.Sale; it only updates inventory safely.
    """
    biz = get_active_business(request)
    if not biz:
        return SaleResult(False, "no_business", "No active business selected.")

    imei = _digits_only(imei or "")
    if len(imei) != 15:
        return SaleResult(False, "bad_imei", "IMEI must be exactly 15 digits.")

    # Row-level lock to serialize concurrent sells of the same IMEI
    qs = (
        InventoryItem.objects
        .select_for_update()
        .select_related("product", "current_location")
        .filter(business=biz, imei=imei)
    )
    item = qs.first()
    if not item:
        return SaleResult(False, "not_found", "This IMEI is not in your stock.")

    assert_owns(item, request)

    # Compute status codes (string-compare case-insensitively)
    sold_code = str(_status_label(InventoryItem))
    in_stock_code = str(_status_in_stock(InventoryItem))
    cur_status = str(getattr(item, "status", "") or "")

    if _is_soldish(item) or cur_status.strip().casefold() == sold_code.strip().casefold():
        return SaleResult(
            False, "already_sold", "This IMEI is already marked as SOLD.",
            item_id=item.id, imei=item.imei,
            product=_product_display(item),
            location=(getattr(getattr(item, "current_location", None), "name", None)),
            sold_at=(getattr(item, "sold_at", None) or None) and item.sold_at.isoformat(),
            price=str(getattr(item, "sold_price", None) or getattr(item, "selling_price", "") or ""),
        )

    # If your workflow enforces statuses, only allow in-stock items
    if cur_status and cur_status.strip().casefold() != in_stock_code.strip().casefold():
        # If the record looks in-stock by other flags, allow through; otherwise block.
        looks_in_stock = not _is_soldish(item)
        if not looks_in_stock:
            return SaleResult(False, "invalid_state", f"Item is in state '{cur_status}', not available for sale.")

    # Values to stamp
    when = sold_at or timezone.localdate()
    loc_id = location_id or getattr(item, "current_location_id", None)

    # Map tolerant field names & common flags
    to_update: dict[str, Any] = {"status": sold_code}
    if hasattr(item, "sold_at"):
        to_update["sold_at"] = when
    # prefer specific price fields, fall back to generic price if that’s all you have
    if hasattr(item, "sold_price"):
        to_update["sold_price"] = price
    elif hasattr(item, "selling_price"):
        to_update["selling_price"] = price
    elif hasattr(item, "price"):
        to_update["price"] = price
    # commission (optional)
    if hasattr(item, "commission_pct") and commission_pct is not None:
        to_update["commission_pct"] = commission_pct

    # ownership / actor
    user = getattr(request, "user", None)
    if hasattr(item, "sold_by_id") and user is not None and getattr(user, "is_authenticated", False):
        to_update["sold_by_id"] = user.id

    # location (keep last known as where sale occurred)
    if loc_id and hasattr(item, "current_location_id"):
        to_update["current_location_id"] = loc_id

    # availability flags (don’t touch is_active here)
    if hasattr(item, "is_sold"):
        to_update["is_sold"] = True
    if hasattr(item, "sold"):
        to_update["sold"] = True
    if hasattr(item, "in_stock"):
        to_update["in_stock"] = False
    if hasattr(item, "available"):
        to_update["available"] = False
    if hasattr(item, "availability"):
        to_update["availability"] = False

    # quantity: set to max(qty-1, 0) if present
    if hasattr(item, "quantity"):
        try:
            to_update["quantity"] = max(0, int(getattr(item, "quantity") or 0) - 1)
        except Exception:
            to_update["quantity"] = 0
    elif hasattr(item, "qty"):
        try:
            to_update["qty"] = max(0, int(getattr(item, "qty") or 0) - 1)
        except Exception:
            to_update["qty"] = 0

    # Persist
    for k, v in to_update.items():
        setattr(item, k, v)
    item.save(update_fields=list(to_update.keys()))

    # Friendly return payload
    loc_name = None
    if loc_id:
        loc_name = Location.objects.filter(id=loc_id).values_list("name", flat=True).first()
    if not loc_name:
        loc_name = getattr(getattr(item, "current_location", None), "name", None)

    return SaleResult(
        True, "ok", "Item marked as SOLD.",
        item_id=item.id,
        imei=item.imei,
        product=_product_display(item),
        location=loc_name,
        sold_at=getattr(item, "sold_at", None) and item.sold_at.isoformat() or when.isoformat(),
        price=str(price),
    )
