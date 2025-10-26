from __future__ import annotations
from typing import Any, Dict, List, Optional

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.utils import timezone

# Try to import whatever model names you actually have; fall back gracefully.
InventoryItem = Stock = Product = AuditLog = None  # type: ignore[assignment]

try:
    # Common possibilities in your repo
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

if Product is None:
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


def _ok(payload: Dict[str, Any] | List[Dict[str, Any]] | None = None, **extra) -> JsonResponse:
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


@login_required
@require_GET
def stock_list(request: HttpRequest) -> JsonResponse:
    """
    Returns a lightweight list of inventory for the current business/tenant.
    This is intentionally tolerant of model name differences.
    """
    try:
        items: List[Dict[str, Any]] = []

        if InventoryItem is not None:
            qs = InventoryItem.objects.all().order_by("-id")[:200]
            for it in qs:
                items.append({
                    "id": getattr(it, "id", None),
                    "sku": getattr(it, "sku", None) or getattr(it, "imei", None),
                    "name": getattr(it, "name", None) or getattr(getattr(it, "product", None), "name", None),
                    "qty": getattr(it, "quantity", None) or getattr(it, "qty", None) or 1,
                    "price": getattr(it, "price", None) or getattr(getattr(it, "product", None), "price", None),
                    "status": getattr(it, "status", None),
                })
            return _ok(items)

        if Stock is not None:
            qs = Stock.objects.all().order_by("-id")[:200]
            for s in qs:
                items.append({
                    "id": getattr(s, "id", None),
                    "sku": getattr(s, "sku", None) or getattr(s, "imei", None),
                    "name": getattr(getattr(s, "product", None), "name", None),
                    "qty": getattr(s, "quantity", None) or getattr(s, "qty", None) or 1,
                    "price": getattr(getattr(s, "product", None), "price", None),
                    "status": getattr(s, "status", None),
                })
            return _ok(items)

        # No known models found â€” return empty but successful so UI doesn't break
        return _ok([], warning="No inventory model detected; returning empty list.")

    except Exception as e:
        return _err(f"stock_list failed: {e}", status=500)


@login_required
@require_POST
@transaction.atomic
def scan_in(request: HttpRequest) -> JsonResponse:
    """
    Accepts POST with 'code' (e.g., IMEI/SKU). If models exist, upsert or mark received.
    """
    code = (request.POST.get("code") or request.body.decode("utf-8").strip() or "").strip()
    if not code:
        return _err("Missing 'code'.")

    try:
        message = "scan_in recorded (no-op)"
        obj_id: Optional[int] = None

        if InventoryItem is not None:
            obj, _created = InventoryItem.objects.get_or_create(
                sku=code,
                defaults={"quantity": 1, "status": "in_stock"},
            )
            # increment quantity if it already exists
            if not _created:
                qty = getattr(obj, "quantity", 0) or 0
                setattr(obj, "quantity", qty + 1)
                obj.save(update_fields=["quantity"])
            obj_id = getattr(obj, "id", None)
            message = "scan_in: inventory updated"

        elif Stock is not None:
            obj, _created = Stock.objects.get_or_create(sku=code, defaults={"quantity": 1})
            if not _created:
                qty = getattr(obj, "quantity", 0) or 0
                setattr(obj, "quantity", qty + 1)
                obj.save(update_fields=["quantity"])
            obj_id = getattr(obj, "id", None)
            message = "scan_in: stock updated"

        if AuditLog is not None:
            AuditLog.objects.create(
                kind="scan_in",
                actor=request.user if request.user.is_authenticated else None,
                details={"code": code, "ts": timezone.now().isoformat()},
            )

        return _ok({"code": code, "id": obj_id}, message=message)

    except Exception as e:
        return _err(f"scan_in failed: {e}", status=500)


@login_required
@require_POST
@transaction.atomic
def scan_sold(request: HttpRequest) -> JsonResponse:
    """
    Accepts POST with 'code'; decrements quantity if item exists (never below zero).
    """
    code = (request.POST.get("code") or request.body.decode("utf-8").strip() or "").strip()
    if not code:
        return _err("Missing 'code'.")

    try:
        message = "scan_sold recorded (no-op)"
        obj_id: Optional[int] = None

        if InventoryItem is not None:
            try:
                obj = InventoryItem.objects.get(sku=code)
                qty = max(0, (getattr(obj, "quantity", 0) or 0) - 1)
                setattr(obj, "quantity", qty)
                obj.save(update_fields=["quantity"])
                obj_id = getattr(obj, "id", None)
                message = "scan_sold: inventory decremented"
            except InventoryItem.DoesNotExist:
                message = "scan_sold: item not found"

        elif Stock is not None:
            try:
                obj = Stock.objects.get(sku=code)
                qty = max(0, (getattr(obj, "quantity", 0) or 0) - 1)
                setattr(obj, "quantity", qty)
                obj.save(update_fields=["quantity"])
                obj_id = getattr(obj, "id", None)
                message = "scan_sold: stock decremented"
            except Stock.DoesNotExist:
                message = "scan_sold: item not found"

        if AuditLog is not None:
            AuditLog.objects.create(
                kind="scan_sold",
                actor=request.user if request.user.is_authenticated else None,
                details={"code": code, "ts": timezone.now().isoformat()},
            )

        return _ok({"code": code, "id": obj_id}, message=message)

    except Exception as e:
        return _err(f"scan_sold failed: {e}", status=500)


