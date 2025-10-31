# inventory/services/sales.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
import re

from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from inventory.models import InventoryItem
from sales.models import Sale
from tenants.models import Location

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

IMEI_RX = re.compile(r"^\d{14,17}$")


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _normalize_code(s: str) -> str:
    return (s or "").strip()


def _apply_unsold_filters(qs):
    """
    Conservative 'unsold' filters using only fields that exist on InventoryItem.
    """
    return (
        qs.filter(is_active=True)
        .filter(sold_at__isnull=True)
        .exclude(status__iexact="SOLD")
    )


def _find_item_for_sale(
    *, business, code: str
) -> Optional[InventoryItem]:
    """
    Locate a single in-stock item in the same business using 'code' as an IMEI.
    Rules:
      • Accepts any string, extracts digits, uses the last 15 as IMEI when len>=15
      • First try imei__endswith(d15), then exact imei match if provided
      • Only returns items that are active, not sold, and belong to the business
    """
    code = _normalize_code(code)
    digits = _digits(code)
    d15 = digits[-15:] if len(digits) >= 15 else digits

    base = _apply_unsold_filters(
        InventoryItem.objects.select_related("product", "current_location")
        .filter(business=business)
    )

    hit: Optional[InventoryItem] = None

    # Prefer strict/IMEI patterns when we have 14-17 digits
    if d15 and IMEI_RX.match(d15):
        hit = base.filter(imei__endswith=d15).first()
        if hit:
            return hit

    # Fallback: if user typed the exact stored IMEI (or shorter), try exact
    if code:
        hit = base.filter(imei=code).first()
        if hit:
            return hit

    return None


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------

@transaction.atomic
def mark_item_sold(
    *,
    code: str,
    price: Decimal,
    commission_pct: Decimal | int = 0,
    sold_at=None,
    location_id: int,
    user,
) -> Dict[str, Any]:
    """
    Single source of truth: marks one item as SOLD and returns new aggregates.
    Atomic and idempotent (raises if already sold).

    Parameters
    ----------
    code : str
        Scanner input (IMEI). We extract digits and use last-15 rule.
    price : Decimal
        Final sale price.
    commission_pct : Decimal|int
        Seller commission percentage (0 if not applicable).
    sold_at :
        Optional datetime; defaults to timezone.now().
    location_id : int
        The Location where the sale happened (must belong to same business).
    user :
        Request user (may be anonymous; we guard .is_authenticated).
    """
    if not location_id:
        raise ValidationError("Location is required.")

    # Lock the location row up front (validates business context)
    try:
        location = Location.objects.select_for_update().get(id=location_id)
    except ObjectDoesNotExist:
        raise ValidationError("Invalid location.")

    business = getattr(location, "business", None)
    if business is None:
        raise ValidationError("Location is not linked to a business.")

    # Resolve the item within the same business and lock it
    item = _find_item_for_sale(business=business, code=code)
    if item is None:
        raise ValidationError("No matching in-stock item was found for this code/IMEI.")

    # Lock the row to prevent race conditions during sale
    item = (
        InventoryItem.objects.select_for_update()
        .select_related("product", "current_location")
        .get(pk=item.pk)
    )

    # Idempotency / state checks
    if item.sold_at is not None or str(item.status).upper() == "SOLD":
        raise ValidationError("Item is already sold.")

    # Build the Sale payload (only using fields that we know exist)
    sale_kwargs = {
        "business": business,
        "item": item,
        "product": item.product,
        "location": location,
        "seller": user if getattr(user, "is_authenticated", False) else None,
        "price": price,
        "commission_pct": commission_pct or 0,
        "sold_at": sold_at or timezone.now(),
    }

    sale = Sale.objects.create(**sale_kwargs)

    # Flip inventory state using only existing fields
    item.status = "SOLD"
    item.sold_at = sale.sold_at
    # Persist relation if your model has it (your InventoryItem DOES have `sale`)
    item.sale = sale
    # Note: there is no 'sold_price' or 'sold_location' field on InventoryItem in your DB
    item.save(update_fields=["status", "sold_at", "sale"])

    # Fresh aggregates for UI
    qs_instock = _apply_unsold_filters(
        InventoryItem.objects.filter(business=business)
    )
    qs_sold = InventoryItem.objects.filter(
        business=business, status__iexact="SOLD"
    )

    sum_order = qs_instock.aggregate(total=Sum("order_price"))["total"] or Decimal(0)
    sum_selling = qs_instock.aggregate(total=Sum("selling_price"))["total"] or Decimal(0)

    return {
        "sale_id": sale.id,
        "item_id": item.id,
        "counts": {
            "items_in_stock": qs_instock.count(),
            "sold_count": qs_sold.count(),
        },
        "sums": {
            "sum_order": sum_order,
            "sum_selling": sum_selling,
        },
        "item": {
            "imei": item.imei,
            "product": str(item.product) if item.product else None,
            "location": str(location),
            "sold_at": sale.sold_at,
            "price": price,
        },
    }
