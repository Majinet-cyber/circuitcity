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
    Confirm rollback page - show sale details and rollback form.
    """
    business = request.business
    user = request.user
    
    sale = get_object_or_404(
        Sale.objects.select_related("item", "item__product", "agent", "location"),
        pk=sale_id,
        item__business=business
    )
    
    # Check if user can rollback
    can_rollback, error_msg = RollbackService.can_rollback(sale, user, business)
    
    if request.method == "POST" and can_rollback:
        reason = request.POST.get("reason", "").upper()
        refunded = request.POST.get("refunded") == "yes"
        refunded_amount = Decimal(request.POST.get("refunded_amount", "0") or "0")
        return_to_stock = request.POST.get("return_to_stock") == "yes"
        notes = request.POST.get("notes", "").strip()
        
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
                f"Sale #{sale.pk} has been rolled back successfully. "
                f"Rollback ID: {rollback.pk}"
            )
            return redirect("sales:rollback_home")
            
        except RollbackError as e:
            messages.error(request, f"Rollback failed: {str(e)}")
        except Exception as e:
            messages.error(request, f"Unexpected error during rollback: {str(e)}")
    
    context = {
        "sale": sale,
        "can_rollback": can_rollback,
        "error_msg": error_msg,
        "rollback_reasons": RollbackReason.choices,
    }
    
    return render(request, "sales/rollback_confirm.html", context)


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

