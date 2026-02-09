from __future__ import annotations

from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render

from tenants.models import Business
from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind

# Use the comprehensive pharmacy dashboard from views_pharmacy
from inventory.views_pharmacy import pharmacy_dashboard
from inventory.models_pharmacy import PharmacyBatch


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def dashboard(request):
    """Pharmacy dashboard - delegates to views_pharmacy.pharmacy_dashboard"""
    return pharmacy_dashboard(request)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def hub(request):
    """
    Pharmacy & Cosmetics Hub - Navigation center for the pharmacy vertical.
    Shows tiles/cards for accessing key features: dashboard, stock-in, sell, batches, etc.
    Enhanced with first-glance badge counts on each category card.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    business: Business = request.business
    today = timezone.now().date()

    # Get basic counts for display
    batches = PharmacyBatch.objects.filter(business=business, is_archived=False).select_related("merch_product")

    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)

    # Products count
    from inventory.models import MerchProduct

    products_count = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True).count()
    
    # ===== BADGE COUNTS FOR CARDS =====
    # Near Expiry: batches expiring in next 30 days
    near_expiry_count = batches.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30)
    ).count()
    
    # Expired Batches: batches that have already expired
    expired_count = batches.filter(expiry_date__lt=today).count()
    
    # Low Stock: batches at or below reorder threshold
    from django.db.models import F
    low_stock_count = batches.filter(quantity__lte=F("reorder_level")).count()
    
    # Active batches count (for "View Batches" card)
    active_batches_count = total_batches
    
    # Sales History: last 30 days transaction count
    thirty_days_ago = today - timedelta(days=30)
    from inventory.models_pharmacy import PharmacySale
    recent_sales_count = PharmacySale.objects.filter(
        business=business,
        sold_at__date__gte=thirty_days_ago,
        sold_at__date__lte=today,
        is_deleted=False,
        is_reversed=False,
    ).count()

    ctx = {
        "total_batches": total_batches,
        "total_stock_value": total_stock_value,
        "products_count": products_count,
        # Badge counts for cards
        "near_expiry_count": near_expiry_count,
        "expired_count": expired_count,
        "low_stock_count": low_stock_count,
        "active_batches_count": active_batches_count,
        "recent_sales_count": recent_sales_count,
    }

    return render(request, "verticals/pharmacy/hub.html", ctx)


# ==============================================================================
# SALES HISTORY, EXPORT, AND TREND API
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def sales_history(request):
    """
    Sales History page for pharmacy with filters, pagination, and export.
    Shows all pharmacy sales with date range filtering and search.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q
    from inventory.models_pharmacy import PharmacySale

    business: Business = request.business

    # Build base queryset
    sales_qs = PharmacySale.objects.filter(business=business).select_related("batch", "batch__merch_product", "sold_by")

    # Parse filter parameters
    start_date = request.GET.get("start", "")
    end_date = request.GET.get("end", "")
    search_query = request.GET.get("q", "")
    sale_id = request.GET.get("sale_id", "")

    # Apply date filters
    if start_date:
        try:
            from datetime import datetime

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass

    # Apply search filter (product name, batch number, customer name, cashier)
    if search_query:
        sales_qs = sales_qs.filter(
            Q(batch__merch_product__name__icontains=search_query)
            | Q(batch__batch_number__icontains=search_query)
            | Q(customer_name__icontains=search_query)
            | Q(customer_phone__icontains=search_query)
            | Q(prescription_number__icontains=search_query)
            | Q(sold_by__username__icontains=search_query)
        )

    # Highlight specific sale if sale_id provided
    highlighted_sale_id = None
    if sale_id:
        try:
            highlighted_sale_id = int(sale_id)
            if not sales_qs.filter(id=highlighted_sale_id).exists():
                highlighted_sale_id = None
        except ValueError:
            pass

    # Order by most recent first
    sales_qs = sales_qs.order_by("-sold_at")

    # Pagination
    page = request.GET.get("page", 1)
    paginator = Paginator(sales_qs, 50)  # 50 sales per page

    try:
        sales_page = paginator.page(page)
    except PageNotAnInteger:
        sales_page = paginator.page(1)
    except EmptyPage:
        sales_page = paginator.page(paginator.num_pages)

    # Summary stats for filtered results
    summary = sales_qs.aggregate(
        total_revenue=Sum("total_amount"),
        total_cost=Sum("unit_cost") * Sum("quantity"),  # Approximate
        total_sales=Count("id"),
        total_items=Sum("quantity"),
    )

    ctx = {
        "business": business,
        "sales": sales_page,
        "start_date": start_date,
        "end_date": end_date,
        "search_query": search_query,
        "highlighted_sale_id": highlighted_sale_id,
        "summary": summary,
        "page_title": "Sales History",
    }

    return render(request, "verticals/pharmacy/sales_history.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def sales_export_csv(request):
    """
    Export filtered pharmacy sales to CSV.
    Respects all the same filters as sales_history view.
    """
    import csv
    from django.http import HttpResponse
    from django.db.models import Q
    from inventory.models_pharmacy import PharmacySale
    from django.utils import timezone

    business: Business = request.business

    # Build queryset with same filters as sales_history
    sales_qs = PharmacySale.objects.filter(business=business).select_related("batch", "batch__merch_product", "sold_by")

    # Apply filters
    start_date = request.GET.get("start", "")
    end_date = request.GET.get("end", "")
    search_query = request.GET.get("q", "")

    if start_date:
        try:
            from datetime import datetime

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__date__lte=end_dt)
        except ValueError:
            pass

    if search_query:
        sales_qs = sales_qs.filter(
            Q(batch__merch_product__name__icontains=search_query)
            | Q(batch__batch_number__icontains=search_query)
            | Q(customer_name__icontains=search_query)
            | Q(sold_by__username__icontains=search_query)
        )

    sales_qs = sales_qs.order_by("-sold_at")

    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="pharmacy_sales_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow(
        [
            "Timestamp",
            "Date",
            "Time",
            "Sale ID",
            "Item",
            "Batch Number",
            "Expiry Date",
            "Qty",
            "Unit Price",
            "Total",
            "Payment Method",
            "Customer Name",
            "Customer Phone",
            "Prescription",
            "Cashier",
        ]
    )

    # Write data rows
    for sale in sales_qs:
        batch = sale.batch
        product = batch.merch_product if batch else None
        local_timestamp = timezone.localtime(sale.sold_at)

        writer.writerow(
            [
                local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                local_timestamp.strftime("%Y-%m-%d"),
                local_timestamp.strftime("%H:%M:%S"),
                sale.id,
                product.name if product else "",
                batch.batch_number if batch else "",
                batch.expiry_date.strftime("%Y-%m-%d") if batch and batch.expiry_date else "",
                sale.quantity,
                f"{sale.unit_price:.2f}",
                f"{sale.total_amount:.2f}",
                sale.get_payment_method_display()
                if hasattr(sale, "get_payment_method_display")
                else sale.payment_method,
                sale.customer_name or "",
                sale.customer_phone or "",
                sale.prescription_number or "",
                sale.sold_by.username if sale.sold_by else "System",
            ]
        )

    return response


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def fast_sell(request):
    """
    Fast Sell page for pharmacy - barcode scanner + instant sell.
    Uses front camera for barcode scanning with BarcodeDetector API fallback.
    """
    from django.http import JsonResponse
    from inventory.utils_scope import get_visible_actor

    business: Business = request.business

    # Get role flags for template
    is_manager, is_agent, actor_user = get_visible_actor(request)

    ctx = {
        "business": business,
        "page_title": "Fast Sell",
        "vertical": "pharmacy",
        "vertical_name": "Pharmacy",
        "IS_MANAGER": is_manager,
        "IS_AGENT": is_agent,
    }

    return render(request, "verticals/pharmacy/fast_sell.html", ctx)


# Fast Sell API endpoints
@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def fast_sell_lookup_api(request):
    """API: Look up product/batch by barcode"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import lookup_product_by_barcode

    business: Business = request.business
    barcode = request.GET.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode required"}, status=400)

    result = lookup_product_by_barcode(business=business, vertical="pharmacy", barcode=barcode)

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def fast_sell_create_api(request):
    """API: Create a fast sale"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import create_fast_sell
    import json

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    business: Business = request.business

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    barcode = data.get("barcode", "").strip()
    quantity = int(data.get("quantity", 1))
    payment_method = data.get("payment_method", "cash")
    selling_price_str = data.get("selling_price")

    selling_price = None
    if selling_price_str:
        try:
            from decimal import Decimal

            selling_price = Decimal(str(selling_price_str))
        except:
            return JsonResponse({"ok": False, "error": "Invalid price"}, status=400)

    result = create_fast_sell(
        business=business,
        vertical="pharmacy",
        user=request.user,
        barcode=barcode,
        quantity=quantity,
        payment_method=payment_method,
        selling_price=selling_price,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def fast_sell_kpis_api(request):
    """API: Get Fast Sell KPIs"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import get_fast_sell_kpis

    business: Business = request.business
    date_range = request.GET.get("range", "today")

    result = get_fast_sell_kpis(
        business=business,
        vertical="pharmacy",
        date_range=date_range,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def sales_trend_json(request):
    """
    JSON endpoint for pharmacy sales trend data.
    Returns UNIT COUNTS (not revenue) suitable for Chart.js.
    All values are integers for clean chart display.
    """
    from django.http import JsonResponse
    from datetime import timedelta, datetime
    from inventory.models_pharmacy import PharmacySale

    business: Business = request.business

    # Parse date range from request
    range_param = request.GET.get("range", "7d")

    # Simple date parsing
    from django.utils import timezone as django_tz

    today = django_tz.now().date()

    if range_param == "today":
        start_date = today
        end_date = today
    elif range_param == "mtd":
        start_date = today.replace(day=1)
        end_date = today
    else:  # Default to 7d
        start_date = today - timedelta(days=6)
        end_date = today

    # Build sales queryset (exclude deleted/reversed sales)
    sales_qs = PharmacySale.objects.filter(
        business=business,
        is_deleted=False,
        is_reversed=False,
    )

    # Generate daily data for the date range
    labels = []
    units_sold_values = []  # Changed from count_values to be more explicit
    revenue_values = []

    current_date = start_date
    while current_date <= end_date:
        # Get sales for this day
        day_sales = sales_qs.filter(sold_at__date=current_date)
        
        # Units sold = sum of quantity (integer)
        day_units = day_sales.aggregate(total=Sum("quantity"))["total"] or 0
        
        # Revenue for optional display
        day_revenue = day_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

        labels.append(current_date.strftime("%b %d"))
        units_sold_values.append(int(day_units))  # Ensure integer
        revenue_values.append(float(day_revenue))

        current_date += timedelta(days=1)

    # Return with explicit units_sold key (count is legacy alias)
    return JsonResponse(
        {
            "labels": labels,
            "units_sold": units_sold_values,  # Primary metric (integer units)
            "count": units_sold_values,  # Legacy alias for backward compatibility
            "revenue": revenue_values,  # Optional for dual-axis charts
            "period": range_param,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timestamp": django_tz.now().isoformat(),
        }
    )


@login_required
@require_business
@require_business_kind(BusinessKind.PHARMACY)
def rollback_sale(request, sale_id):
    """
    Rollback/cancel a pharmacy sale and restore batch inventory.
    Manager-only feature for correcting mistakes.
    """
    from django.http import JsonResponse
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.db import transaction
    from inventory.models_pharmacy import PharmacySale
    from inventory.utils_scope import get_visible_actor

    business: Business = request.business

    # Check if user is manager
    is_manager, is_agent, actor_user = get_visible_actor(request)
    if not is_manager:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Only managers can rollback sales"}, status=403)
        messages.error(request, "Only managers can rollback sales")
        return redirect("verticals:pharmacy_sales_history")

    # Get the sale
    try:
        sale = PharmacySale.objects.get(id=sale_id, business=business)
    except PharmacySale.DoesNotExist:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale not found"}, status=404)
        messages.error(request, "Sale not found")
        return redirect("verticals:pharmacy_sales_history")

    # Check if already deleted
    if sale.is_deleted:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale already cancelled"}, status=400)
        messages.error(request, "Sale already cancelled")
        return redirect("verticals:pharmacy_sales_history")

    if request.method == "POST":
        with transaction.atomic():
            # Restore batch inventory
            batch = sale.batch
            batch.quantity_remaining += sale.quantity
            batch.save(update_fields=["quantity_remaining"])

            # Mark sale as deleted
            sale.is_deleted = True
            sale.deleted_at = timezone.now()
            sale.deleted_by = request.user
            sale.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

        return JsonResponse(
            {"ok": True, "message": f"Sale #{sale_id} rolled back successfully. Batch inventory restored."}
        )

    # GET request: show confirmation
    messages.error(request, "Invalid request method")
    return redirect("verticals:pharmacy_sales_history")
