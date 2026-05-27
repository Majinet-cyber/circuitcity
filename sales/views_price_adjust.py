"""
PHASE 4: Price adjustment views for sold items (Manager-only)
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, HttpRequest
from django.shortcuts import get_object_or_404

from tenants.decorators import require_business
from sales.models import Sale
from audit.services_price_corrections import adjust_sold_item_price


@login_required
@require_business
@require_http_methods(["POST"])
def adjust_sale_price(request: HttpRequest, sale_id: int) -> JsonResponse:
    """
    API endpoint to adjust price on sold item.

    Manager-only. Creates adjustment record (doesn't modify original Sale).
    Returns JSON with success/error status and commission delta.
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
        return JsonResponse({"success": False, "error": "Only managers can adjust sold item prices"}, status=403)

    # Get sale
    try:
        sale = Sale.objects.select_related("item", "agent", "location").get(pk=sale_id, item__business=business)
    except Sale.DoesNotExist:
        return JsonResponse({"success": False, "error": "Sale not found"}, status=404)

    # Parse inputs
    try:
        new_selling_price_str = request.POST.get("selling_price", "").strip()
        new_cost_price_str = request.POST.get("cost_price", "").strip()
        reason = request.POST.get("reason", "").strip()

        new_selling_price = Decimal(new_selling_price_str) if new_selling_price_str else None
        new_cost_price = Decimal(new_cost_price_str) if new_cost_price_str else None

        if not reason:
            return JsonResponse({"success": False, "error": "Reason is required"}, status=400)

        if not new_selling_price and not new_cost_price:
            return JsonResponse({"success": False, "error": "Must change at least one price"}, status=400)

    except (ValueError, InvalidOperation) as e:
        return JsonResponse({"success": False, "error": f"Invalid price format: {str(e)}"}, status=400)

    # Execute price adjustment
    try:
        result = adjust_sold_item_price(
            sale=sale,
            new_selling_price=new_selling_price,
            new_cost_price=new_cost_price,
            reason=reason,
            adjusted_by=user,
            business=business,
        )

        # Format commission delta for display
        commission_delta = result["commission_delta"]
        commission_delta_display = ""
        if commission_delta > 0:
            commission_delta_display = f"+K{commission_delta:.2f}"
        elif commission_delta < 0:
            commission_delta_display = f"-K{abs(commission_delta):.2f}"
        else:
            commission_delta_display = "K0.00"

        return JsonResponse(
            {
                "success": True,
                "message": "Price adjusted successfully",
                "adjustment_id": result["adjustment_id"],
                "original_selling_price": str(result["original_selling_price"]),
                "new_selling_price": str(result["new_selling_price"]),
                "original_cost_price": str(result["original_cost_price"]) if result["original_cost_price"] else None,
                "new_cost_price": str(result["new_cost_price"]) if result["new_cost_price"] else None,
                "commission_delta": str(commission_delta),
                "commission_delta_display": commission_delta_display,
                "commission_txn_id": result["commission_txn_id"],
            }
        )

    except (ValueError, PermissionError) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)
