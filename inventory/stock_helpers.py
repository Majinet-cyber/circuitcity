# circuitcity/inventory/stock_helpers.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import logging, re

from django.db import transaction
from django.utils import timezone

from .models import InventoryItem

log = logging.getLogger(__name__)

IMEI_RE = re.compile(r"\d+")

def normalize_code(raw: str) -> str:
    """Keep digits only; many scanners add spaces/dashes."""
    if not raw:
        return ""
    return "".join(IMEI_RE.findall(str(raw))).strip()

@dataclass(frozen=True)
class ScanResult:
    ok: bool
    code: str
    message: str
    item_id: Optional[int] = None
    imei: Optional[str] = None
    status: Optional[str] = None
    location_id: Optional[int] = None

def _not_found(imei:str) -> ScanResult:
    return ScanResult(False, "NOT_FOUND", "No item with this IMEI for this business.", None, imei, None, None)

def _not_in_stock(it:InventoryItem) -> ScanResult:
    return ScanResult(False, "NOT_IN_STOCK", "Item exists but is not in stock.", it.id, it.imei, it.status, getattr(it, "location_id", None))

def _already_sold(it:InventoryItem) -> ScanResult:
    return ScanResult(False, "ALREADY_SOLD", "Item already sold.", it.id, it.imei, it.status, getattr(it, "location_id", None))

def _sold_ok(it:InventoryItem) -> ScanResult:
    return ScanResult(True, "OK", "Item moved to SOLD.", it.id, it.imei, it.status, getattr(it, "location_id", None))

def status_constants():
    """Centralize status strings/enums once."""
    IN_STOCK = getattr(InventoryItem, "Status", None)
    if IN_STOCK and hasattr(InventoryItem.Status, "IN_STOCK") and hasattr(InventoryItem.Status, "SOLD"):
        return InventoryItem.Status.IN_STOCK, InventoryItem.Status.SOLD
    # fallback strings if you use CharField without Django Enum
    return "in_stock", "sold"

def get_active_business(request):
    return getattr(request, "business", None) or getattr(request, "active_business", None)

def get_active_location_id(request):
    for k in ("active_location_id","location_id","store_id","current_location_id"):
        v = getattr(request, k, None)
        if v is not None: return v
    sess = getattr(request, "session", {}) or {}
    for k in ("active_location_id","location_id","store_id","current_location_id"):
        v = sess.get(k)
        if v is not None: return v
    return None

def find_item(business, imei: str, location_id: int|None = None) -> Optional[InventoryItem]:
    qs = InventoryItem.objects.filter(business=business, imei=imei)
    if location_id:
        # Prefer exact location if available, but donâ€™t hide the item if location id mismatched.
        obj = qs.filter(location_id=location_id).first()
        return obj or qs.first()
    return qs.first()

@transaction.atomic
def mark_imei_sold(*, business, imei_raw: str, user, location_id: int|None=None) -> ScanResult:
    imei = normalize_code(imei_raw)
    if not imei:
        return ScanResult(False, "BAD_INPUT", "IMEI/Barcode missing or invalid.")

    item = (
        InventoryItem.objects.select_for_update()
        .filter(business=business, imei=imei)
        .first()
    )
    if not item:
        return _not_found(imei)

    IN_STOCK, SOLD = status_constants()

    if item.status == SOLD:
        return _already_sold(item)
    if item.status != IN_STOCK:
        return _not_in_stock(item)

    # transition
    item.status = SOLD
    if hasattr(item, "sold_at"):
        item.sold_at = timezone.now()
    if hasattr(item, "sold_by_id"):
        item.sold_by = user
    if location_id and hasattr(item, "location_id") and not item.location_id:
        item.location_id = location_id

    update_fields = ["status"]
    for f in ("sold_at","sold_by","location"):
        if hasattr(item, f):
            update_fields.append(f)
    item.save(update_fields=update_fields)

    log.info("scan_sold: SOLD item_id=%s imei=%s by=%s", item.id, imei, getattr(user, "id", None))
    return _sold_ok(item)

def probe_status(*, business, imei_raw: str, location_id: int|None=None) -> dict:
    """Used by /api/stock-status/ â€” canonical, no UI logic here."""
    imei = normalize_code(imei_raw)
    if not imei:
        return {"ok": False, "code": "BAD_INPUT", "message": "Missing IMEI/barcode."}

    it = find_item(business, imei, location_id)
    if not it:
        return {"ok": False, "code": "NOT_FOUND", "message": "No match for this IMEI."}

    IN_STOCK, SOLD = status_constants()
    state = "in_stock" if it.status == IN_STOCK else ("sold" if it.status == SOLD else str(it.status))
    return {
        "ok": True,
        "code": "OK",
        "status": state,
        "item_id": it.id,
        "imei": it.imei,
        "location_id": getattr(it, "location_id", None),
    }


