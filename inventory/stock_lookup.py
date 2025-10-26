# inventory/stock_lookup.py
from __future__ import annotations
from typing import Optional, Tuple
from django.db import transaction
from django.utils import timezone

try:
    # Adjust this import to your actual model
    from .models import InventoryItem  # fields: business, code, location, sold_at, order_price, selling_price, status
except Exception as e:
    raise RuntimeError("Update the model import in inventory/stock_lookup.py to match your project") from e


def normalize_code(raw: str) -> str:
    return "".join(ch for ch in (raw or "").strip() if ch.isdigit())[:15]


def find_unsold_unit(
    *, business_id: int, code: str
) -> Tuple[Optional[InventoryItem], Optional[int]]:
    """
    Find an UNSOLD unit for this business, regardless of location.
    Returns (item, location_id_if_found)
    """
    code = normalize_code(code)
    if not code:
        return None, None

    qs = (InventoryItem.objects
          .select_related("location")
          .filter(business_id=business_id, code=code)
          .order_by("id"))

    # Prefer truly unsold rows
    item = qs.filter(sold_at__isnull=True).first()
    if item:
        return item, (item.location_id if hasattr(item, "location_id") else None)

    # Nothing to sell
    return None, None


@transaction.atomic
def mark_as_sold_anywhere(
    *,
    business_id: int,
    code: str,
    sold_price: float,
    sold_location_id: Optional[int],
    sold_by_id: int,
    sold_at=None,
) -> dict:
    """
    Mark the unit as SOLD even if it was stocked at a different location.
    Records original_location_id and sold_location_id if fields exist.
    """
    sold_at = sold_at or timezone.now()
    code = normalize_code(code)

    item, original_loc_id = find_unsold_unit(business_id=business_id, code=code)
    if not item:
        return {"ok": False, "error": "IMEI not in stock for this business."}

    # Persist provenance if model supports it
    if hasattr(item, "original_location_id") and not getattr(item, "original_location_id"):
        item.original_location_id = original_loc_id
    if hasattr(item, "sold_location_id"):
        item.sold_location_id = sold_location_id
    if hasattr(item, "sold_by_id"):
        item.sold_by_id = sold_by_id
    if hasattr(item, "selling_price") and sold_price is not None:
        item.selling_price = sold_price
    if hasattr(item, "status"):
        item.status = "SOLD"
    item.sold_at = sold_at
    item.save(update_fields=[
        *(["original_location_id"] if hasattr(item, "original_location_id") else []),
        *(["sold_location_id"] if hasattr(item, "sold_location_id") else []),
        *(["sold_by_id"] if hasattr(item, "sold_by_id") else []),
        *(["selling_price"] if hasattr(item, "selling_price") else []),
        *(["status"] if hasattr(item, "status") else []),
        "sold_at",
        # always update updated_at if you have it via auto_now; no need to list
    ])

    return {
        "ok": True,
        "code": code,
        "item_id": item.id,
        "original_location_id": original_loc_id,
        "sold_location_id": sold_location_id,
        "sold_at": sold_at.isoformat(),
    }






