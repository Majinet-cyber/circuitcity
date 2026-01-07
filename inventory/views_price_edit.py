"""
PHASE 4: Price editing views for unsold inventory items (Manager-only)
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpRequest
from django.db import transaction

from tenants.decorators import require_business
from inventory.models import InventoryItem
from audit.services_price_corrections import edit_unsold_item_prices


@login_required
@require_business
@require_http_methods(["POST"])
def edit_stock_prices(request: HttpRequest, item_id: int) -> JsonResponse:
    """
    API endpoint to edit prices on unsold inventory item.

    Manager-only. Returns JSON with success/error status.
    """
    business = getattr(request, "business", None)
    if not business:
        return JsonResponse({"success": False, "error": "No active business"}, status=400)

    # Check manager permission
    user = request.user
    is_manager = False
    if hasattr(user, "profile"):
        is_manager = user.profile.is_manager or user.is_staff

    if not is_manager:
        return JsonResponse({"success": False, "error": "Only managers can edit prices"}, status=403)

    # Get item
    try:
        item = InventoryItem.objects.select_related("product").get(pk=item_id, business=business, is_active=True)
    except InventoryItem.DoesNotExist:
        return JsonResponse({"success": False, "error": "Item not found"}, status=404)

    # Check item is not sold
    if item.status == "SOLD":
        return JsonResponse(
            {"success": False, "error": "Cannot edit prices on sold items. Use sales price adjustment instead."},
            status=400,
        )

    # Parse inputs
    try:
        new_order_price_str = request.POST.get("order_price", "").strip()
        new_selling_price_str = request.POST.get("selling_price", "").strip()
        reason = request.POST.get("reason", "").strip()

        new_order_price = Decimal(new_order_price_str) if new_order_price_str else None
        new_selling_price = Decimal(new_selling_price_str) if new_selling_price_str else None

        if not reason:
            return JsonResponse({"success": False, "error": "Reason is required"}, status=400)

        if not new_order_price and not new_selling_price:
            return JsonResponse({"success": False, "error": "Must change at least one price"}, status=400)

    except (ValueError, InvalidOperation) as e:
        return JsonResponse({"success": False, "error": f"Invalid price format: {str(e)}"}, status=400)

    # Execute price edit
    try:
        result = edit_unsold_item_prices(
            item=item,
            new_order_price=new_order_price,
            new_selling_price=new_selling_price,
            reason=reason,
            edited_by=user,
            business=business,
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Prices updated successfully",
                "audit_id": result["audit_id"],
                "old_order_price": str(result["old_order_price"]),
                "old_selling_price": str(result["old_selling_price"]) if result["old_selling_price"] else None,
                "new_order_price": str(result["new_order_price"]),
                "new_selling_price": str(result["new_selling_price"]) if result["new_selling_price"] else None,
            }
        )

    except (ValueError, PermissionError) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)
