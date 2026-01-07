# inventory/views_liquor_rollback.py
"""
Liquor Sale Rollback Views
===========================
Views for rolling back liquor sales.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from tenants.utils import require_business
from sales.services.rollback_verticals import LiquorRollbackService, VerticalRollbackError


@login_required
@require_business
@require_POST
def liquor_rollback_sale(request: HttpRequest, sale_id: int) -> HttpResponse:
    """
    Rollback a liquor sale (POST only).

    NO HTTP 500s - all errors are caught and displayed as messages.
    """
    business = request.business
    user = request.user

    # Get form data
    reason = request.POST.get("reason", "OTHER").upper()
    refunded = request.POST.get("refunded") == "yes"
    return_to_stock = request.POST.get("return_to_stock") == "yes"
    notes = request.POST.get("notes", "").strip()

    # Parse refunded amount safely
    try:
        refunded_amount_str = request.POST.get("refunded_amount", "0").replace(",", "").strip()
        refunded_amount = Decimal(refunded_amount_str) if refunded_amount_str else Decimal("0")
    except (ValueError, Exception):
        messages.error(request, "❌ Invalid refund amount")
        return redirect("liquor:sales_list")

    try:
        result = LiquorRollbackService.rollback_liquor_sale(
            sale_id=sale_id,
            user=user,
            business=business,
            reason=reason,
            refunded=refunded,
            refunded_amount=refunded_amount,
            return_to_stock=return_to_stock,
            notes=notes,
        )

        messages.success(request, f"✅ Liquor sale #{sale_id} rolled back successfully!")

        if result.get("stock_restored"):
            messages.info(request, "✅ Stock quantities restored")

        if refunded and refunded_amount > 0:
            messages.info(request, f"✅ Refund recorded: MK {refunded_amount:,.2f}")

        return redirect("liquor:sales_list")

    except VerticalRollbackError as e:
        messages.error(request, f"❌ Rollback failed: {str(e)}")
        return redirect("liquor:sales_list")
    except Exception as e:
        messages.error(request, "❌ An unexpected error occurred. Please try again.")
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error rolling back liquor sale {sale_id}: {e}", exc_info=True)
        return redirect("liquor:sales_list")


@login_required
@require_business
def liquor_rollback_confirm(request: HttpRequest, sale_id: int) -> HttpResponse:
    """
    Show confirmation page for rolling back a liquor sale.
    """
    business = request.business

    try:
        from inventory.models_verticals import LiquorSale

        sale = get_object_or_404(LiquorSale.objects.select_related("product", "sold_by"), pk=sale_id, business=business)

        # Check if already rolled back
        already_rolled_back = hasattr(sale, "is_rolled_back") and sale.is_rolled_back

        # Check permissions
        from tenants.models import Membership

        try:
            membership = Membership.objects.get(user=request.user, business=business)
            can_rollback = membership.role.upper() in ["MANAGER", "OWNER", "ADMIN"]
        except Membership.DoesNotExist:
            can_rollback = False

        from inventory.utils_pricing import format_currency

        context = {
            "sale": sale,
            "can_rollback": can_rollback and not already_rolled_back,
            "already_rolled_back": already_rolled_back,
            "sale_price_formatted": format_currency(sale.total_price),
        }

        return render(request, "inventory/liquor/rollback_confirm.html", context)

    except Exception as e:
        messages.error(request, f"❌ Unable to load sale: {str(e)}")
        return redirect("liquor:sales_list")
