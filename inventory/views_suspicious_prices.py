# inventory/views_suspicious_prices.py
"""
Manager-only page to find and fix suspicious phone prices.
"""
from __future__ import annotations

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from tenants.utils import get_active_business
from core.decorators import manager_required
from inventory.models import InventoryItem
from inventory.utils_pricing import validate_phone_selling_price
from django.conf import settings


@login_required
@manager_required
def phones_suspicious_prices(request: HttpRequest) -> HttpResponse:
    """
    Manager-only page to list and fix suspicious phone prices.

    Shows unsold phones where selling_price < MIN_PHONE_SELLING_PRICE_MK.
    """
    business = get_active_business(request)
    if not business:
        messages.error(request, "No active business selected.")
        return redirect("inventory:inventory_dashboard")

    # Check if this is a phones business
    from inventory.business_kinds import BusinessKind

    if getattr(business, "business_kind", None) != BusinessKind.PHONES:
        messages.error(request, "This page is only available for phones businesses.")
        return redirect("inventory:stock_list")

    min_price = Decimal(str(getattr(settings, "MIN_PHONE_SELLING_PRICE_MK", 10000)))

    # Get suspicious items (unsold, with selling_price > 0 but < threshold)
    suspicious_items = (
        InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True,
            selling_price__isnull=False,
            selling_price__gt=0,
            selling_price__lt=min_price,
        )
        .select_related("product", "current_location")
        .order_by("-id")[:100]
    )

    # Get count for badge
    suspicious_count = suspicious_items.count()

    context = {
        "business": business,
        "suspicious_items": suspicious_items,
        "suspicious_count": suspicious_count,
        "min_price": min_price,
        "is_manager": True,
    }

    return render(request, "inventory/phones_suspicious_prices.html", context)


@login_required
@manager_required
@transaction.atomic
def fix_suspicious_price(request: HttpRequest, item_id: int) -> JsonResponse:
    """
    Manager-only API endpoint to fix suspicious price by multiplying by 1000.

    Only works for unsold items.
    Creates audit log entry.
    """
    business = get_active_business(request)
    if not business:
        return JsonResponse({"ok": False, "error": "No active business"}, status=400)

    try:
        item = InventoryItem.objects.select_for_update().get(
            pk=item_id, business=business, status="IN_STOCK", is_active=True
        )
    except InventoryItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item not found or already sold"}, status=404)

    old_price = item.selling_price
    if not old_price or old_price <= 0:
        return JsonResponse({"ok": False, "error": "No selling price to fix"}, status=400)

    min_price = Decimal(str(getattr(settings, "MIN_PHONE_SELLING_PRICE_MK", 10000)))
    if old_price >= min_price:
        return JsonResponse({"ok": False, "error": "Price is not suspicious"}, status=400)

    # Fix: multiply by 1000
    new_price = old_price * 1000

    # Update using model method (handles audit logging)
    try:
        item.apply_instock_update(new_price=float(new_price), by_user=request.user)

        # Create additional audit entry for the fix
        try:
            from inventory.models import AuditLog

            AuditLog.objects.create(
                action="PRICE_FIX",
                by_user=request.user,
                item_id=item.id,
                details={
                    "reason": "Auto fix suspicious price ×1000",
                    "old_price": float(old_price),
                    "new_price": float(new_price),
                    "imei": item.imei,
                },
            )
        except Exception:
            pass  # Audit logging is optional

        return JsonResponse(
            {
                "ok": True,
                "item_id": item.id,
                "old_price": float(old_price),
                "new_price": float(new_price),
                "message": f"Price fixed: MK {old_price:,.0f} → MK {new_price:,.0f}",
            }
        )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
