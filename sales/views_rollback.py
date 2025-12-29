# sales/views_rollback.py
"""
Sale Rollback Views
===================
Views for rolling back sales across all verticals.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from tenants.utils import require_business
from sales.models import Sale, SaleRollback, RollbackReason
from sales.services.rollback import RollbackService, RollbackError
from sales.services.phone_sale_edit import PhoneSaleEditService, SaleEditError


@login_required
@require_business
def rollback_home(request: HttpRequest) -> HttpResponse:
    """
    Rollback home page - search and select a sale to rollback.
    """
    business = request.business
    user = request.user
    
    # Get recent sales (last 30)
    recent_sales = (
        Sale.objects
        .filter(item__business=business, is_rolled_back=False)
        .select_related("item", "item__product", "agent", "location")
        .order_by("-created_at")[:30]
    )
    
    # Get recent rollbacks
    recent_rollbacks = RollbackService.get_rollback_history(business, limit=10)
    
    # Get rollback stats
    stats = RollbackService.get_rollback_stats(business, days=30)
    
    context = {
        "recent_sales": recent_sales,
        "recent_rollbacks": recent_rollbacks,
        "stats": stats,
    }
    
    return render(request, "sales/rollback_home.html", context)


@login_required
@require_business
def rollback_search(request: HttpRequest) -> JsonResponse:
    """
    AJAX endpoint to search for sales.
    """
    business = request.business
    query = request.GET.get("q", "").strip()
    
    if not query:
        return JsonResponse({"results": []})
    
    # Search by IMEI, receipt, SKU, customer name/phone
    sales = (
        Sale.objects
        .filter(item__business=business, is_rolled_back=False)
        .filter(
            Q(item__imei__icontains=query) |
            Q(item__barcode__icontains=query) |
            Q(pk__icontains=query)
        )
        .select_related("item", "item__product", "agent", "location")
        .order_by("-created_at")[:20]
    )
    
    results = []
    for sale in sales:
        results.append({
            "id": sale.pk,
            "item_name": str(sale.item.product) if sale.item.product else "Unknown",
            "imei": getattr(sale.item, "imei", ""),
            "price": float(sale.price),
            "agent": sale.agent.get_full_name() or sale.agent.username,
            "sold_at": sale.sold_at.isoformat(),
            "created_at": sale.created_at.isoformat(),
        })
    
    return JsonResponse({"results": results})


@login_required
@require_business
def rollback_confirm(request: HttpRequest, sale_id: int) -> HttpResponse:
    """
    Confirm rollback page - show sale details and action choice (rollback or edit).
    
    NO HTTP 500s - all errors are caught and displayed as messages.
    """
    business = request.business
    user = request.user
    
    try:
        sale = get_object_or_404(
            Sale.objects.select_related("item", "item__product", "agent", "location"),
            pk=sale_id,
            item__business=business
        )
    except Exception as e:
        messages.error(request, f"Sale not found or inaccessible: {str(e)}")
        return redirect("sales:rollback_home")
    
    # Check if user can rollback
    can_rollback, error_msg = RollbackService.can_rollback(sale, user, business)
    
    # Check if user can edit
    can_edit, edit_error_msg = PhoneSaleEditService.can_edit_sale(sale, user, business)
    
    # Check if this is a phone sale (for edit functionality)
    # Phones use InventoryItem with IMEI tracking
    is_phone_sale = hasattr(sale.item, 'imei')
    
    # Also check business kind as fallback
    if not is_phone_sale:
        try:
            from inventory.authz import resolve_business_kind
            business_kind = resolve_business_kind(business=business).lower()
            is_phone_sale = business_kind == "phones"
        except Exception:
            pass
    
    # Get action choice from query param or session
    action = request.GET.get("action", "").lower()
    
    if request.method == "POST" and can_rollback and action == "rollback":
        reason = request.POST.get("reason", "").upper()
        refunded = request.POST.get("refunded") == "yes"
        return_to_stock = request.POST.get("return_to_stock") == "yes"
        notes = request.POST.get("notes", "").strip()
        
        # Parse refunded amount safely
        try:
            refunded_amount_str = request.POST.get("refunded_amount", "0").replace(",", "").strip()
            refunded_amount = Decimal(refunded_amount_str) if refunded_amount_str else Decimal("0")
        except (ValueError, Exception) as e:
            messages.error(request, f"Invalid refund amount: {str(e)}")
            refunded_amount = Decimal("0")
        
        try:
            rollback = RollbackService.rollback_sale(
                sale=sale,
                user=user,
                business=business,
                reason=reason,
                refunded=refunded,
                refunded_amount=refunded_amount,
                return_to_stock=return_to_stock,
                notes=notes,
            )
            
            messages.success(
                request,
                f"✅ Sale #{sale.pk} rolled back successfully! "
                f"Rollback ID: {rollback.pk}"
            )
            return redirect("sales:rollback_home")
            
        except RollbackError as e:
            messages.error(request, f"❌ Rollback failed: {str(e)}")
        except Exception as e:
            messages.error(request, f"❌ Unexpected error during rollback: {str(e)}")
            # Log for debugging but don't expose internal errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Rollback error for sale {sale_id}: {e}", exc_info=True)
    
    # Format sale price for display
    try:
        sale_price_formatted = f"MK {sale.price:,.2f}"
    except Exception:
        sale_price_formatted = f"MK {sale.price}"
    
    context = {
        "sale": sale,
        "can_rollback": can_rollback,
        "can_edit": can_edit and is_phone_sale,
        "error_msg": error_msg,
        "edit_error_msg": edit_error_msg if not can_edit else "",
        "rollback_reasons": RollbackReason.choices,
        "sale_price_formatted": sale_price_formatted,
        "action": action,
        "is_phone_sale": is_phone_sale,
    }
    
    return render(request, "sales/rollback_confirm.html", context)


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def edit_phone_sale(request: HttpRequest, sale_id: int) -> HttpResponse:
    """
    Edit phone sale details (price and IMEI) without rolling back.
    
    NO HTTP 500s - all errors are caught and displayed as messages.
    """
    business = request.business
    user = request.user
    
    try:
        sale = get_object_or_404(
            Sale.objects.select_related("item", "item__product", "agent", "location"),
            pk=sale_id,
            item__business=business
        )
    except Exception as e:
        messages.error(request, f"Sale not found or inaccessible: {str(e)}")
        return redirect("sales:rollback_home")
    
    # Check if user can edit
    can_edit, error_msg = PhoneSaleEditService.can_edit_sale(sale, user, business)
    
    if not can_edit:
        messages.error(request, f"Cannot edit sale: {error_msg}")
        return redirect("sales:rollback_confirm", sale_id=sale_id)
    
    if request.method == "POST":
        # Get form data
        selling_price_str = request.POST.get("selling_price", "").replace(",", "").strip()
        new_imei = request.POST.get("imei", "").strip()
        
        # Parse selling price
        try:
            new_selling_price = Decimal(selling_price_str) if selling_price_str else Decimal("0")
        except (ValueError, Exception) as e:
            messages.error(request, f"Invalid selling price: {str(e)}")
            return redirect("sales:edit_phone_sale", sale_id=sale_id)
        
        if new_selling_price < 0:
            messages.error(request, "Selling price must be >= 0")
            return redirect("sales:edit_phone_sale", sale_id=sale_id)
        
        # Check if price is below cost (warning only)
        item = sale.item
        order_price = getattr(item, 'order_price', Decimal("0"))
        if new_selling_price < order_price:
            # Show warning but allow saving
            messages.warning(
                request,
                f"⚠️ Selling price (MK {new_selling_price:,.2f}) is below cost price "
                f"(MK {order_price:,.2f}). This is allowed but may indicate an error."
            )
        
        try:
            # Edit the sale
            updated_sale = PhoneSaleEditService.edit_phone_sale(
                sale_id=sale_id,
                business=business,
                user=user,
                new_selling_price=new_selling_price,
                new_imei=new_imei if new_imei else None,
            )
            
            messages.success(
                request,
                f"✅ Sale #{sale.pk} updated successfully! "
                f"Price: MK {new_selling_price:,.2f}"
            )
            return redirect("sales:rollback_confirm", sale_id=sale_id)
            
        except SaleEditError as e:
            messages.error(request, f"❌ Could not update sale: {str(e)}")
        except Exception as e:
            messages.error(request, f"❌ Unexpected error: {str(e)}")
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Edit sale error for sale {sale_id}: {e}", exc_info=True)
    
    # Format sale price for display
    try:
        sale_price_formatted = f"MK {sale.price:,.2f}"
    except Exception:
        sale_price_formatted = f"MK {sale.price}"
    
    # Get current IMEI
    current_imei = getattr(sale.item, 'imei', '') or ''
    
    # Get order price for cost comparison
    order_price = getattr(sale.item, 'order_price', Decimal("0"))
    
    context = {
        "sale": sale,
        "can_edit": can_edit,
        "error_msg": error_msg,
        "sale_price_formatted": sale_price_formatted,
        "current_imei": current_imei,
        "order_price": order_price,
    }
    
    return render(request, "sales/edit_phone_sale.html", context)


@login_required
@require_business
def rollback_detail(request: HttpRequest, rollback_id: int) -> HttpResponse:
    """
    View details of a completed rollback.
    """
    business = request.business
    
    rollback = get_object_or_404(
        SaleRollback.objects.select_related(
            "sale",
            "sale__item",
            "sale__item__product",
            "sale__agent",
            "created_by"
        ),
        pk=rollback_id,
        sale__item__business=business
    )
    
    context = {
        "rollback": rollback,
    }
    
    return render(request, "sales/rollback_detail.html", context)

