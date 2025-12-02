# inventory/views_pharmacy.py
"""
Pharmacy vertical views: batch management, sales, expiry tracking, and dashboard.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Count, Q, F
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.models import Business
from tenants.utils import require_business, get_active_business

from .models import MerchProduct
from .models_pharmacy import (
    PharmacyProductInfo,
    PharmacyBatch,
    PharmacySale,
    PharmacyProductForm,
    PharmacyCategory,
)


# ==============================================================================
# DASHBOARD
# ==============================================================================

@login_required
@require_business
def pharmacy_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main pharmacy dashboard showing key metrics and alerts.
    """
    business: Business = request.business
    
    # Get all active batches
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False
    ).select_related("merch_product")
    
    # Metrics
    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)
    
    # Near expiry (next 30 days)
    today = timezone.now().date()
    near_expiry_batches = batches.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30)
    ).order_by("expiry_date")[:10]
    
    # Expired batches
    expired_batches = batches.filter(expiry_date__lt=today).order_by("expiry_date")[:10]
    
    # Low stock batches
    low_stock_batches = batches.filter(quantity__lte=F("reorder_level")).order_by("quantity")[:10]
    
    # Today's sales
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__gte=today_start
    )
    
    today_revenue = today_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    today_sales_count = today_sales.count()
    
    # Calculate today's profit
    today_profit = Decimal("0.00")
    for sale in today_sales:
        today_profit += sale.profit
    
    # Products count
    products_count = MerchProduct.objects.filter(
        business=business,
        kind="pharmacy",
        is_active=True
    ).count()
    
    return render(
        request,
        "verticals/pharmacy/dashboard.html",
        {
            "total_batches": total_batches,
            "total_stock_value": total_stock_value,
            "products_count": products_count,
            "near_expiry_count": near_expiry_batches.count(),
            "expired_count": expired_batches.count(),
            "low_stock_count": low_stock_batches.count(),
            "today_revenue": today_revenue,
            "today_profit": today_profit,
            "today_sales_count": today_sales_count,
            "near_expiry_batches": near_expiry_batches,
            "expired_batches": expired_batches,
            "low_stock_batches": low_stock_batches,
        },
    )


# ==============================================================================
# BATCH MANAGEMENT
# ==============================================================================

@login_required
@require_business
def batch_list(request: HttpRequest) -> HttpResponse:
    """List all pharmacy batches with filters."""
    business: Business = request.business
    
    # Query params for filtering
    show_archived = request.GET.get("archived") == "1"
    product_id = request.GET.get("product")
    
    batches = PharmacyBatch.objects.filter(business=business).select_related("merch_product")
    
    if not show_archived:
        batches = batches.filter(is_archived=False)
    
    if product_id:
        batches = batches.filter(merch_product_id=product_id)
    
    batches = batches.order_by("expiry_date", "batch_number")
    
    # Products for filter dropdown
    products = MerchProduct.objects.filter(
        business=business,
        kind="pharmacy",
        is_active=True
    ).order_by("name")
    
    return render(
        request,
        "verticals/pharmacy/batch_list.html",
        {
            "batches": batches,
            "products": products,
            "show_archived": show_archived,
            "selected_product": product_id,
        },
    )


@login_required
@require_business
def batch_create(request: HttpRequest) -> HttpResponse:
    """Create a new pharmacy batch."""
    business: Business = request.business
    
    if request.method == "POST":
        # Extract form data
        product_id = request.POST.get("product")
        batch_number = request.POST.get("batch_number", "").strip()
        expiry_date_str = request.POST.get("expiry_date")
        quantity = request.POST.get("quantity", "0")
        reorder_level = request.POST.get("reorder_level", "10")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        supplier = request.POST.get("supplier", "").strip()
        received_date_str = request.POST.get("received_date") or str(timezone.now().date())
        
        # Validation
        if not product_id or not batch_number or not expiry_date_str:
            messages.error(request, "Product, batch number, and expiry date are required.")
            return redirect(request.path)
        
        try:
            product = MerchProduct.objects.get(id=product_id, business=business, kind="pharmacy")
        except MerchProduct.DoesNotExist:
            messages.error(request, "Invalid product selected.")
            return redirect(request.path)
        
        try:
            expiry_date = timezone.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            received_date = timezone.datetime.strptime(received_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect(request.path)
        
        # Check for duplicate
        if PharmacyBatch.objects.filter(
            business=business,
            merch_product=product,
            batch_number=batch_number,
            expiry_date=expiry_date
        ).exists():
            messages.error(request, "A batch with this number and expiry date already exists.")
            return redirect(request.path)
        
        # Create batch
        batch = PharmacyBatch.objects.create(
            business=business,
            merch_product=product,
            batch_number=batch_number,
            expiry_date=expiry_date,
            quantity=int(quantity),
            reorder_level=int(reorder_level),
            cost_price=Decimal(cost_price),
            selling_price=Decimal(selling_price),
            supplier=supplier,
            received_date=received_date,
        )
        
        messages.success(request, f"Batch {batch.batch_number} created successfully.")
        return redirect("inventory:pharmacy_batch_list")
    
    # GET: show form
    products = MerchProduct.objects.filter(
        business=business,
        kind="pharmacy",
        is_active=True
    ).order_by("name")
    
    return render(
        request,
        "verticals/pharmacy/batch_form.html",
        {
            "products": products,
            "action": "Create",
        },
    )


@login_required
@require_business
def batch_edit(request: HttpRequest, batch_id: int) -> HttpResponse:
    """Edit an existing pharmacy batch."""
    business: Business = request.business
    batch = get_object_or_404(PharmacyBatch, id=batch_id, business=business)
    
    if request.method == "POST":
        # Update fields
        batch.batch_number = request.POST.get("batch_number", batch.batch_number).strip()
        
        expiry_date_str = request.POST.get("expiry_date")
        if expiry_date_str:
            try:
                batch.expiry_date = timezone.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, "Invalid expiry date format.")
                return redirect(request.path)
        
        batch.quantity = int(request.POST.get("quantity", batch.quantity))
        batch.reorder_level = int(request.POST.get("reorder_level", batch.reorder_level))
        batch.cost_price = Decimal(request.POST.get("cost_price", batch.cost_price))
        batch.selling_price = Decimal(request.POST.get("selling_price", batch.selling_price))
        batch.supplier = request.POST.get("supplier", batch.supplier).strip()
        
        received_date_str = request.POST.get("received_date")
        if received_date_str:
            try:
                batch.received_date = timezone.datetime.strptime(received_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        
        batch.save()
        messages.success(request, f"Batch {batch.batch_number} updated.")
        return redirect("inventory:pharmacy_batch_list")
    
    # GET: show form
    return render(
        request,
        "verticals/pharmacy/batch_form.html",
        {
            "batch": batch,
            "action": "Edit",
        },
    )


# ==============================================================================
# HELPERS
# ==============================================================================

def _send_sale_notifications(sale: PharmacySale, business: Business) -> None:
    """
    Send WhatsApp notifications for a pharmacy sale.
    Notifies managers and agents (if applicable).
    """
    try:
        from notifications import whatsapp_service
        from tenants.models import Membership
    except ImportError:
        return  # Skip if modules not available
    
    # Prepare sale info
    sale_info = {
        "product_name": sale.batch.merch_product.name,
        "quantity": sale.quantity,
        "amount": float(sale.total_amount),
        "location_name": "pharmacy",
    }
    
    # Notify managers
    manager_memberships = Membership.objects.filter(
        business=business,
        role__in=["manager", "owner"]
    ).select_related("user")
    
    for membership in manager_memberships:
        try:
            whatsapp_service.notify_manager_sale(
                membership.user,
                business,
                sale_info
            )
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to manager {membership.user_id}: {e}")
    
    # Notify agent (if sale was made by an agent)
    if sale.sold_by:
        try:
            # Check if user is an agent
            agent_membership = Membership.objects.filter(
                business=business,
                user=sale.sold_by,
                role="agent"
            ).first()
            
            if agent_membership:
                # Calculate commission (if applicable)
                # For now, use a simple 5% commission on profit
                commission = sale.profit * Decimal("0.05")
                
                whatsapp_service.notify_agent_commission(
                    sale.sold_by,
                    business,
                    sale_info,
                    commission
                )
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to agent {sale.sold_by.id}: {e}")


def _check_and_notify_low_stock(batch: PharmacyBatch, business: Business) -> None:
    """
    Check if batch is now low stock after a sale and notify managers.
    """
    if not batch.is_low_stock:
        return
    
    try:
        from notifications import whatsapp_service
        from tenants.models import Membership
    except ImportError:
        return
    
    # Notify managers
    manager_memberships = Membership.objects.filter(
        business=business,
        role__in=["manager", "owner"]
    ).select_related("user")
    
    for membership in manager_memberships:
        try:
            whatsapp_service.notify_manager_low_stock(
                membership.user,
                business,
                batch.merch_product.name,
                batch.quantity,
                batch.reorder_level
            )
        except Exception as e:
            logger.error(f"Failed to send low stock WhatsApp to manager {membership.user_id}: {e}")


# ==============================================================================
# SALES
# ==============================================================================

@login_required
@require_business
def sale_create(request: HttpRequest) -> HttpResponse:
    """Create a pharmacy sale (with batch validation)."""
    business: Business = request.business
    
    if request.method == "POST":
        batch_id = request.POST.get("batch")
        quantity = int(request.POST.get("quantity", 1))
        payment_method = request.POST.get("payment_method", "CASH")
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        prescription_number = request.POST.get("prescription_number", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Validation
        if not batch_id:
            messages.error(request, "Please select a batch.")
            return redirect(request.path)
        
        try:
            batch = PharmacyBatch.objects.get(id=batch_id, business=business)
        except PharmacyBatch.DoesNotExist:
            messages.error(request, "Invalid batch selected.")
            return redirect(request.path)
        
        # Check expiry
        if batch.is_expired:
            messages.error(request, f"Cannot sell expired batch (expired on {batch.expiry_date}).")
            return redirect(request.path)
        
        # Check stock
        if quantity > batch.quantity:
            messages.error(
                request,
                f"Insufficient stock. Requested {quantity}, available {batch.quantity}."
            )
            return redirect(request.path)
        
        # Create sale and decrement stock
        with transaction.atomic():
            sale = PharmacySale.objects.create(
                business=business,
                batch=batch,
                quantity=quantity,
                unit_price=batch.selling_price,
                unit_cost=batch.cost_price,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
                prescription_number=prescription_number,
                sold_by=request.user,
                notes=notes,
            )
            
            batch.decrement_stock(quantity)
            
            # Send WhatsApp notifications
            _send_sale_notifications(sale, business)
            
            # Check and notify low stock
            _check_and_notify_low_stock(batch, business)
        
        messages.success(
            request,
            f"Sale recorded: {batch.merch_product.name} x{quantity} for {sale.total_amount:,.2f}"
        )
        return redirect("inventory:pharmacy_dashboard")
    
    # GET: show form
    # Only show batches with stock, not expired
    today = timezone.now().date()
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False,
        quantity__gt=0,
        expiry_date__gte=today
    ).select_related("merch_product").order_by("expiry_date", "merch_product__name")
    
    return render(
        request,
        "verticals/pharmacy/sale_form.html",
        {
            "batches": batches,
        },
    )


@login_required
@require_business
def sale_list(request: HttpRequest) -> HttpResponse:
    """List pharmacy sales."""
    business: Business = request.business
    
    sales = PharmacySale.objects.filter(business=business).select_related(
        "batch__merch_product",
        "sold_by"
    ).order_by("-sold_at")[:100]
    
    return render(
        request,
        "verticals/pharmacy/sale_list.html",
        {
            "sales": sales,
        },
    )


# ==============================================================================
# EXPIRY & STOCK ALERTS
# ==============================================================================

@login_required
@require_business
def near_expiry_list(request: HttpRequest) -> HttpResponse:
    """List batches near expiry (next 30 days)."""
    business: Business = request.business
    
    today = timezone.now().date()
    days = int(request.GET.get("days", 30))
    
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False,
        quantity__gt=0,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=days)
    ).select_related("merch_product").order_by("expiry_date")
    
    return render(
        request,
        "verticals/pharmacy/near_expiry.html",
        {
            "batches": batches,
            "days": days,
        },
    )


@login_required
@require_business
def expired_list(request: HttpRequest) -> HttpResponse:
    """List expired batches."""
    business: Business = request.business
    
    today = timezone.now().date()
    batches = PharmacyBatch.objects.filter(
        business=business,
        expiry_date__lt=today,
        quantity__gt=0  # Still have stock
    ).select_related("merch_product").order_by("expiry_date")
    
    return render(
        request,
        "verticals/pharmacy/expired.html",
        {
            "batches": batches,
        },
    )


@login_required
@require_business
def low_stock_list(request: HttpRequest) -> HttpResponse:
    """List batches with low stock."""
    business: Business = request.business
    
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False,
        quantity__lte=F("reorder_level")
    ).select_related("merch_product").order_by("quantity")
    
    return render(
        request,
        "verticals/pharmacy/low_stock.html",
        {
            "batches": batches,
        },
    )


# ==============================================================================
# AJAX / API endpoints
# ==============================================================================

@login_required
@require_business
def api_batch_info(request: HttpRequest, batch_id: int) -> JsonResponse:
    """Get batch info as JSON (for AJAX forms)."""
    business: Business = request.business
    
    try:
        batch = PharmacyBatch.objects.get(id=batch_id, business=business)
    except PharmacyBatch.DoesNotExist:
        return JsonResponse({"error": "Batch not found"}, status=404)
    
    return JsonResponse({
        "id": batch.id,
        "product_name": batch.merch_product.name,
        "batch_number": batch.batch_number,
        "expiry_date": str(batch.expiry_date),
        "quantity": batch.quantity,
        "selling_price": float(batch.selling_price),
        "cost_price": float(batch.cost_price),
        "is_expired": batch.is_expired,
        "days_to_expiry": batch.days_to_expiry,
    })

