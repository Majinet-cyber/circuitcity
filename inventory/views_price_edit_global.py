# inventory/views_price_edit_global.py
"""
Global Price Edit Views - Manager-only feature across ALL verticals
Handles both product price updates and sale line price corrections
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from inventory.helpers import get_active_business
from inventory.models import MerchProduct
from inventory.models_verticals import CementSale, GrocerySale, LiquorSale
from inventory.services.pricing import (
    update_cement_sale_price,
    update_grocery_sale_price,
    update_liquor_sale_price,
    update_product_selling_price,
)
from tenants.decorators import require_business
from tenants.utils import manager_required

try:
    from inventory.models_pharmacy import PharmacySale
    from inventory.services.pricing import update_pharmacy_sale_price
except ImportError:
    PharmacySale = None
    update_pharmacy_sale_price = None

try:
    from inventory.models_verticals import ClothingSale
    from inventory.services.pricing import update_clothing_sale_price
except ImportError:
    ClothingSale = None
    update_clothing_sale_price = None


@login_required
@require_business
@manager_required
@require_http_methods(["POST"])
def edit_product_price(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    Edit the current selling price of a product (affects future sales).

    Manager-only. Works across all verticals.
    Returns JSON with success/error status.
    """
    business = get_active_business(request)

    # Get product
    try:
        product = MerchProduct.objects.get(pk=product_id, business=business, is_active=True)
    except MerchProduct.DoesNotExist:
        return JsonResponse({"success": False, "error": "Product not found"}, status=404)

    # Parse inputs
    try:
        new_price_str = request.POST.get("new_price", "").strip()
        reason = request.POST.get("reason", "").strip()

        if not new_price_str:
            return JsonResponse({"success": False, "error": "New price is required"}, status=400)

        new_price = Decimal(new_price_str)

    except (ValueError, InvalidOperation) as e:
        return JsonResponse({"success": False, "error": f"Invalid price format: {str(e)}"}, status=400)

    # Execute price update
    try:
        result = update_product_selling_price(
            business=business,
            product=product,
            new_price=new_price,
            user=request.user,
            reason=reason,
            location=getattr(request.user, "location", None),
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Price updated: MK {result['old_price']} → MK {result['new_price']}",
                "old_price": str(result["old_price"]),
                "new_price": str(result["new_price"]),
                "audit_log_id": result["audit_log_id"],
            }
        )

    except (ValidationError, PermissionDenied) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)


@login_required
@require_business
@manager_required
@require_http_methods(["POST"])
def edit_sale_price(request: HttpRequest, vertical: str, sale_id: int) -> JsonResponse:
    """
    Edit the unit selling price on a historical sale (affects revenue/profit).

    Manager-only. Works across all verticals.
    Routes to appropriate vertical-specific function.
    Returns JSON with success/error status.

    Args:
        vertical: One of: cement, liquor, grocery, pharmacy, clothing
        sale_id: Primary key of the sale
    """
    business = get_active_business(request)

    # Parse inputs
    try:
        new_unit_price_str = request.POST.get("new_unit_price", "").strip()
        reason = request.POST.get("reason", "").strip()

        if not new_unit_price_str:
            return JsonResponse({"success": False, "error": "New unit price is required"}, status=400)

        new_unit_price = Decimal(new_unit_price_str)

    except (ValueError, InvalidOperation) as e:
        return JsonResponse({"success": False, "error": f"Invalid price format: {str(e)}"}, status=400)

    # Route to appropriate vertical handler
    try:
        if vertical == "cement":
            sale = CementSale.objects.select_related("product").get(pk=sale_id, business=business)
            result = update_cement_sale_price(
                business=business, sale=sale, new_unit_price=new_unit_price, user=request.user, reason=reason
            )

        elif vertical == "liquor":
            sale = LiquorSale.objects.select_related("product").get(pk=sale_id, business=business)
            result = update_liquor_sale_price(
                business=business, sale=sale, new_unit_price=new_unit_price, user=request.user, reason=reason
            )

        elif vertical == "grocery":
            sale = GrocerySale.objects.select_related("product").get(pk=sale_id, business=business)
            result = update_grocery_sale_price(
                business=business, sale=sale, new_unit_price=new_unit_price, user=request.user, reason=reason
            )

        elif vertical == "pharmacy" and PharmacySale:
            sale = PharmacySale.objects.select_related("batch__product").get(pk=sale_id, business=business)
            result = update_pharmacy_sale_price(
                business=business, sale=sale, new_unit_price=new_unit_price, user=request.user, reason=reason
            )

        elif vertical == "clothing" and ClothingSale:
            sale = ClothingSale.objects.select_related("product").get(pk=sale_id, business=business)
            result = update_clothing_sale_price(
                business=business, sale=sale, new_unit_price=new_unit_price, user=request.user, reason=reason
            )

        else:
            return JsonResponse({"success": False, "error": f"Unsupported vertical: {vertical}"}, status=400)

        return JsonResponse(
            {
                "success": True,
                "message": f"Sale price updated: MK {result['old_unit_price']} → MK {result['new_unit_price']}",
                "old_unit_price": str(result["old_unit_price"]),
                "new_unit_price": str(result["new_unit_price"]),
                "old_total": str(result.get("old_total_price", result.get("old_total_amount", 0))),
                "new_total": str(result.get("new_total_price", result.get("new_total_amount", 0))),
                "quantity": result.get("quantity", 1),
                "audit_log_id": result["audit_log_id"],
            }
        )

    except (CementSale.DoesNotExist, LiquorSale.DoesNotExist, GrocerySale.DoesNotExist):
        return JsonResponse({"success": False, "error": "Sale not found"}, status=404)
    except (ValidationError, PermissionDenied) as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Unexpected error: {str(e)}"}, status=500)


@login_required
@require_business
@manager_required
def view_price_change_history(request: HttpRequest) -> JsonResponse:
    """
    View price change audit log for the business.

    Manager-only. Returns JSON with recent price changes.
    """
    from inventory.services.pricing import get_price_change_history

    business = get_active_business(request)
    product_id = request.GET.get("product_id")
    limit = int(request.GET.get("limit", 50))

    product = None
    if product_id:
        try:
            product = MerchProduct.objects.get(pk=product_id, business=business)
        except MerchProduct.DoesNotExist:
            pass

    changes = get_price_change_history(business, product=product, limit=limit)

    data = []
    for change in changes:
        data.append(
            {
                "id": change.id,
                "scope": change.get_scope_display(),
                "old_price": str(change.old_price),
                "new_price": str(change.new_price),
                "difference": str(change.price_difference),
                "change_pct": str(change.price_change_pct),
                "reason": change.reason,
                "user": change.user.username if change.user else None,
                "created_at": change.created_at.isoformat(),
                "product_name": change.product.name if change.product else None,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "changes": data,
            "count": len(data),
        }
    )
