# inventory/views_pharmacy.py
"""
Pharmacy vertical views: batch management, sales, expiry tracking, and dashboard.
"""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


# ==============================================================================
# DASHBOARD
# ==============================================================================

@login_required
@require_business
def pharmacy_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Main pharmacy dashboard showing key metrics and alerts with date filtering.
    """
    business: Business = request.business
    today = timezone.now().date()
    
    # ===== DATE FILTERING =====
    # Parse date range from query params (Today, 7d, Month, Custom)
    from hq.utils_dates import get_period_from_request
    from datetime import datetime
    
    range_param = request.GET.get("range", "today")
    start_date = None
    end_date = None
    period_label = "Today"
    
    if range_param == "today":
        start_date = end_date = today
        period_label = "Today"
    elif range_param == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
        period_label = "Last 7 Days"
    elif range_param == "month":
        start_date = today.replace(day=1)
        end_date = today
        period_label = "This Month"
    elif range_param == "custom":
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            period_label = f"{start_date} to {end_date}"
        except (ValueError, TypeError):
            # Fallback to today
            start_date = end_date = today
            period_label = "Today"
            range_param = "today"
    
    # Get all active batches (not filtered by date - current stock status)
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False
    ).select_related("merch_product")
    
    # Stock metrics (current state, not time-filtered)
    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)
    
    # Near expiry (next 30 days)
    near_expiry_batches = batches.filter(
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30)
    ).order_by("expiry_date")[:10]
    
    # Expired batches
    expired_batches = batches.filter(expiry_date__lt=today).order_by("expiry_date")[:10]
    
    # Low stock batches
    low_stock_batches = batches.filter(quantity__lte=F("reorder_level")).order_by("quantity")[:10]
    
    # ===== SALES METRICS (filtered by selected period) =====
    # Convert dates to datetime range for filtering
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
    
    # Filter sales by period and exclude deleted/reversed sales
    period_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__gte=start_dt,
        sold_at__lte=end_dt,
        is_deleted=False,  # Exclude soft-deleted sales from metrics
        is_reversed=False  # Exclude reversed sales from metrics
    )
    
    period_revenue = period_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    period_sales_count = period_sales.count()
    
    # Calculate period profit
    period_profit = Decimal("0.00")
    for sale in period_sales:
        period_profit += sale.profit
    
    # Average sale value
    avg_sale_value = period_revenue / period_sales_count if period_sales_count > 0 else Decimal("0.00")
    
    # ===== PAYMENT MIX (for selected period) =====
    # Using same payment method constants as phones vertical
    payment_mix_data = {
        "CASH": {"count": 0, "amount": Decimal("0.00")},
        "BANK": {"count": 0, "amount": Decimal("0.00")},
        "MOBILE_MONEY": {"count": 0, "amount": Decimal("0.00")},
    }
    
    for sale in period_sales:
        method = (sale.payment_method or "CASH").upper()
        if method == "CASH":
            payment_mix_data["CASH"]["count"] += 1
            payment_mix_data["CASH"]["amount"] += sale.total_amount
        elif method == "BANK":
            payment_mix_data["BANK"]["count"] += 1
            payment_mix_data["BANK"]["amount"] += sale.total_amount
        elif method in ("MOBILE_MONEY", "MOBILEMONEY"):
            payment_mix_data["MOBILE_MONEY"]["count"] += 1
            payment_mix_data["MOBILE_MONEY"]["amount"] += sale.total_amount
    
    # ===== PRODUCT TYPE BREAKDOWN =====
    # Count medicines vs other products
    products_all = MerchProduct.objects.filter(
        business=business,
        kind="pharmacy",
        is_active=True
    )
    products_count = products_all.count()
    
    # Check if product_type field exists (will add in migration)
    medicine_count = products_all.filter(
        product_type="MEDICINE"
    ).count() if hasattr(MerchProduct, 'product_type') else products_count
    
    other_count = products_all.filter(
        product_type="OTHER"
    ).count() if hasattr(MerchProduct, 'product_type') else 0
    
    # ===== TOP PRODUCTS (for selected period) =====
    # Aggregate sales by product for the period
    top_products_data = []
    # Get sales grouped by batch/product
    sales_by_batch = period_sales.values(
        'batch__merch_product__id',
        'batch__merch_product__name',
        'batch__merch_product__category'
    ).annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum('total_amount'),
        sales_count=Count('id')
    ).order_by('-total_revenue')[:10]
    
    for item in sales_by_batch:
        # Calculate profit for this product across all sales in period
        product_sales = period_sales.filter(batch__merch_product__id=item['batch__merch_product__id'])
        product_profit = sum(sale.profit for sale in product_sales)
        
        # Get category display name
        category_code = item['batch__merch_product__category'] or 'general'
        category_display = dict(PharmacyCategory.choices).get(category_code, 'General')
        
        top_products_data.append({
            'name': item['batch__merch_product__name'],
            'category': category_display,
            'category_code': category_code,
            'quantity': item['total_qty'],
            'revenue': item['total_revenue'],
            'profit': product_profit,
            'sales_count': item['sales_count'],
        })
    
    # ===== TOP CATEGORIES (for selected period) =====
    top_categories_data = []
    # Group by category
    sales_by_category = period_sales.values(
        'batch__merch_product__category'
    ).annotate(
        total_qty=Sum('quantity'),
        total_revenue=Sum('total_amount'),
        sales_count=Count('id')
    ).order_by('-total_revenue')
    
    for item in sales_by_category:
        category_code = item['batch__merch_product__category'] or 'general'
        category_display = dict(PharmacyCategory.choices).get(category_code, 'General')
        
        # Calculate profit for this category
        category_sales = period_sales.filter(batch__merch_product__category=category_code)
        category_profit = sum(sale.profit for sale in category_sales)
        
        top_categories_data.append({
            'category': category_display,
            'category_code': category_code,
            'quantity': item['total_qty'],
            'revenue': item['total_revenue'],
            'profit': category_profit,
            'sales_count': item['sales_count'],
        })
    
    # Calculate total for percentages
    total_category_revenue = sum(cat['revenue'] for cat in top_categories_data)
    for cat in top_categories_data:
        cat['revenue_pct'] = (
            float(cat['revenue']) / float(total_category_revenue) * 100
            if total_category_revenue > 0 else 0
        )
    
    # ===== COSTS FOR PERIOD =====
    # Integrate with wallet/costs system
    period_costs = Decimal("0.00")
    try:
        from wallet.models import Txn, TxnType
        
        # Get all costs for pharmacy vertical in this period
        costs_queryset = Txn.objects.filter(
            business=business,
            type=TxnType.COST,
            effective_date__gte=start_date,
            effective_date__lte=end_date,
        )
        
        # Try to filter by vertical if meta supports it
        # For now, sum all costs (can be refined later with meta filtering)
        period_costs = costs_queryset.aggregate(total=Sum('amount'))['total'] or Decimal("0.00")
    except Exception:
        pass  # Gracefully handle if wallet app not available
    
    # ===== COSMETICS TRACKING =====
    # Track cosmetics (skin care, hair care, beauty, personal care, etc.) separately
    # Note: PharmacyCategory is already imported at the top from models_pharmacy
    
    cosmetics_categories = [
        PharmacyCategory.SKIN_CARE,
        PharmacyCategory.HAIR_CARE,
        PharmacyCategory.PERSONAL_CARE,
        PharmacyCategory.BEAUTY_MAKEUP,
        PharmacyCategory.BABY_CARE,
        PharmacyCategory.ORAL_CARE,
    ]
    
    # Cosmetics sales for period
    cosmetics_sales = period_sales.filter(
        batch__merch_product__category__in=cosmetics_categories
    )
    
    cosmetics_revenue = Decimal("0.00")
    for sale in cosmetics_sales:
        cosmetics_revenue += sale.total_amount
    
    cosmetics_revenue_pct = (
        (float(cosmetics_revenue) / float(period_revenue) * 100) if period_revenue > 0 else 0
    )
    
    # Cosmetics products in stock
    cosmetics_products = products_all.filter(
        category__in=cosmetics_categories
    ).count()
    
    # Top cosmetics brands (simple extraction from product names)
    top_cosmetics_brands = []
    try:
        from .pharmacy_constants import get_all_brands
        
        known_brands = get_all_brands()
        brand_revenue = {}
        
        for sale in cosmetics_sales:
            product_name = sale.batch.merch_product.name.lower()
            
            # Check if any known brand appears in the product name
            for brand in known_brands:
                if brand.lower() in product_name:
                    brand_revenue[brand] = brand_revenue.get(brand, Decimal("0.00")) + sale.total_amount
                    break
        
        # Sort by revenue, top 5
        top_cosmetics_brands = sorted(
            [{"name": brand, "revenue": rev} for brand, rev in brand_revenue.items()],
            key=lambda x: x["revenue"],
            reverse=True
        )[:5]
    except Exception:
        pass  # Gracefully handle if pharmacy_constants not available
    
    # ===== SAFE SUBSCRIPTION HANDLING =====
    # Never let missing subscription crash the dashboard
    subscription = None
    try:
        if hasattr(business, 'subscription'):
            subscription = business.subscription
    except Exception:
        pass  # Business has no subscription - perfectly fine
    
    # ===== PERSONALIZED DASHBOARD ENHANCEMENTS =====
    # Initialize with safe defaults
    ctx_enhancements = {
        "DASHBOARD_QUOTES": {"quotes": []},
        "quotes_json": "[]",  # Safe default for template
    }
    
    try:
        import json
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_quotes import get_todays_quotes
        
        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, business)
        
        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, 'logo') and business.logo:
            brand_logo_url = business.logo.url
        
        # Yesterday summary (show once per day) - only when viewing "today"
        yesterday_summary = None
        if range_param == "today" and should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, business)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)
        
        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)
        
        # Extract quote texts for JavaScript rotation
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json = json.dumps(quote_texts)
        
        ctx_enhancements.update({
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": business.name if business else "Pharmacy Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "DASHBOARD_QUOTES": daily_quotes,
            "quotes_json": quotes_json,
        })
    except Exception:
        pass  # Gracefully degrade if helpers not available, defaults already set
    
    ctx = {
        # Navigation context (for base template)
        "active_tab": "home",  # Highlights the dashboard/home tab in mobile nav
        
        # Stock metrics (current state)
        "total_batches": total_batches,
        "total_stock_value": total_stock_value,
        "products_count": products_count,
        "total_products": products_count,  # Alias for template compatibility
        "medicine_count": medicine_count,
        "other_count": other_count,
        
        # Alert counts
        "near_expiry_count": near_expiry_batches.count(),
        "expired_count": expired_batches.count(),
        "low_stock_count": low_stock_batches.count(),
        
        # Period metrics (filtered by date range)
        "period_revenue": period_revenue,
        "period_profit": period_profit,
        "period_costs": period_costs,
        "period_sales_count": period_sales_count,
        "avg_sale_value": avg_sale_value,
        
        # Date filter context
        "range_param": range_param,
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        
        # Payment mix for the period
        "payment_mix": payment_mix_data,
        
        # Top products & categories analytics
        "top_products": top_products_data,
        "top_categories": top_categories_data,
        
        # Alert lists
        "near_expiry_batches": near_expiry_batches,
        "expired_batches": expired_batches,
        "low_stock_batches": low_stock_batches,
        
        # Cosmetics tracking (premium feature)
        "cosmetics_revenue": cosmetics_revenue,
        "cosmetics_revenue_pct": cosmetics_revenue_pct,
        "cosmetics_products": cosmetics_products,
        "top_cosmetics_brands": top_cosmetics_brands,
        
        # Subscription (safe - None if not available)
        "subscription": subscription,
        
        # Backward compatibility (today's metrics for legacy templates)
        "today_revenue": period_revenue if range_param == "today" else Decimal("0.00"),
        "today_profit": period_profit if range_param == "today" else Decimal("0.00"),
        "today_sales_count": period_sales_count if range_param == "today" else 0,
    }
    
    # Merge enhancements from above (includes quotes)
    ctx.update(ctx_enhancements)
    
    return render(request, "verticals/pharmacy/dashboard.html", ctx)


# ==============================================================================
# GAMIFIED STOCK IN (Vertical-aware)
# ==============================================================================

@login_required
@require_business
def pharmacy_stock_in(request: HttpRequest) -> HttpResponse:
    """
    Gamified Stock In panel for pharmacy vertical.
    Single-page form for adding new stock with validation and celebration.
    """
    business: Business = request.business
    
    if request.method == "POST":
        # Extract form data
        sku = request.POST.get("sku", "").strip()
        product_name = request.POST.get("product_name", "").strip()
        category = request.POST.get("category", "").strip()  # Category from dropdown
        quantity = request.POST.get("quantity", "0")
        cost_price = request.POST.get("cost_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        manufacture_date_str = request.POST.get("manufacture_date", "")
        expiry_date_str = request.POST.get("expiry_date", "")
        batch_number = request.POST.get("batch_number", "").strip()
        supplier = request.POST.get("supplier", "").strip()
        description = request.POST.get("description", "").strip()
        reorder_level = request.POST.get("reorder_level", "10")
        
        # Validation
        errors = []
        if not product_name:
            errors.append("Product name is required.")
        if not batch_number:
            errors.append("Batch number is required.")
        if not expiry_date_str:
            errors.append("Expiry date is required.")
        
        # Validate category against allowed values
        VALID_CATEGORIES = [
            "medicine", "supplements", "skin_care", "hair_care", "body_care",
            "baby_care", "oral_care", "perfumes", "deodorants", "makeup",
            "soap_hygiene", "first_aid", "other"
        ]
        if not category:
            errors.append("Category is required.")
        elif category not in VALID_CATEGORIES:
            errors.append(f"Invalid category '{category}'. Please select from the dropdown.")
        
        try:
            qty = int(quantity)
            if qty <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = 0
        
        try:
            cost = Decimal(cost_price)
            if cost < 0:
                errors.append("Cost price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid cost price.")
            cost = Decimal("0.00")
        
        try:
            selling = Decimal(selling_price)
            if selling < 0:
                errors.append("Selling price cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Invalid selling price.")
            selling = Decimal("0.00")
        
        # Parse dates
        try:
            expiry_date = timezone.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            errors.append("Invalid expiry date format.")
            expiry_date = None
        
        manufacture_date = None
        if manufacture_date_str:
            try:
                manufacture_date = timezone.datetime.strptime(manufacture_date_str, "%Y-%m-%d").date()
                if expiry_date and manufacture_date >= expiry_date:
                    errors.append("Manufacture date must be before expiry date.")
            except (ValueError, TypeError):
                errors.append("Invalid manufacture date format.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect(request.path)
        
        # Create or get product
        with transaction.atomic():
            product, created = MerchProduct.objects.get_or_create(
                business=business,
                name=product_name,
                kind="pharmacy",
                defaults={
                    "sku": sku,
                    "is_active": True,
                    "category": category,  # Use category field
                    "cost_price": cost,
                    "selling_price": selling,
                }
            )
            
            # If product exists, optionally update prices and category
            if not created:
                # Update if prices or category changed
                if product.cost_price != cost or product.selling_price != selling or product.category != category:
                    product.cost_price = cost
                    product.selling_price = selling
                    product.category = category
                    product.save()
            
            # Check for duplicate batch
            existing_batch = PharmacyBatch.objects.filter(
                business=business,
                merch_product=product,
                batch_number=batch_number,
                expiry_date=expiry_date
            ).first()
            
            if existing_batch:
                # Update existing batch quantity
                existing_batch.quantity += qty
                existing_batch.cost_price = cost
                existing_batch.selling_price = selling
                if supplier:
                    existing_batch.supplier = supplier
                existing_batch.save()
                messages.success(
                    request,
                    f"✅ Stock updated! Added {qty} units to existing batch. Total: {existing_batch.quantity}"
                )
            else:
                # Create new batch
                batch = PharmacyBatch.objects.create(
                    business=business,
                    merch_product=product,
                    batch_number=batch_number,
                    expiry_date=expiry_date,
                    quantity=qty,
                    cost_price=cost,
                    selling_price=selling,
                    supplier=supplier,
                    received_date=manufacture_date or timezone.now().date(),
                    reorder_level=int(reorder_level),
                )
                messages.success(
                    request,
                    f"🎉 Stock added successfully! {product_name} - {qty} units (Batch: {batch_number})"
                )
            
            # Store success flag in session for celebration UI
            request.session["stock_in_success"] = True
            request.session["last_product_name"] = product_name
            request.session["last_quantity"] = qty
        
        return redirect("pharmacy:stock_in")
    
    # GET: Show form
    success_data = None
    if request.session.get("stock_in_success"):
        success_data = {
            "product_name": request.session.get("last_product_name"),
            "quantity": request.session.get("last_quantity"),
        }
        del request.session["stock_in_success"]
        if "last_product_name" in request.session:
            del request.session["last_product_name"]
        if "last_quantity" in request.session:
            del request.session["last_quantity"]
    
    # Define 13 pharmacy & cosmetics categories for dropdown
    category_options = [
        {"value": "medicine", "label": "Medicine"},
        {"value": "supplements", "label": "Supplements"},
        {"value": "skin_care", "label": "Skin Care"},
        {"value": "hair_care", "label": "Hair Care"},
        {"value": "body_care", "label": "Body Care"},
        {"value": "baby_care", "label": "Baby Care"},
        {"value": "oral_care", "label": "Oral Care"},
        {"value": "perfumes", "label": "Perfumes"},
        {"value": "deodorants", "label": "Deodorants"},
        {"value": "makeup", "label": "Makeup"},
        {"value": "soap_hygiene", "label": "Soap & Hygiene"},
        {"value": "first_aid", "label": "First Aid"},
        {"value": "other", "label": "Other"},
    ]
    
    ctx = {
        "success_data": success_data,
        "category_options": category_options,
    }
    
    return render(request, "verticals/pharmacy/stock_in.html", ctx)


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
# GAMIFIED SELL (Vertical-aware)
# ==============================================================================

@login_required
@require_business
def pharmacy_sell(request: HttpRequest) -> HttpResponse:
    """
    Gamified Sell panel for pharmacy vertical.
    3-step wizard: Select Product → Payment → Confirm
    """
    business: Business = request.business
    
    if request.method == "POST":
        batch_id = request.POST.get("batch_id")
        quantity = request.POST.get("quantity", "1")
        payment_method = request.POST.get("payment_method", "CASH")
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        prescription_number = request.POST.get("prescription_number", "").strip()
        notes = request.POST.get("notes", "").strip()
        
        # Validation
        if not batch_id:
            messages.error(request, "Please select a product to sell.")
            return redirect(request.path)
        
        try:
            qty = int(quantity)
            if qty <= 0:
                messages.error(request, "Quantity must be at least 1.")
                return redirect(request.path)
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity.")
            return redirect(request.path)
        
        try:
            batch = PharmacyBatch.objects.get(id=batch_id, business=business)
        except PharmacyBatch.DoesNotExist:
            messages.error(request, "Invalid product selected.")
            return redirect(request.path)
        
        # Check expiry
        if batch.is_expired:
            messages.error(request, f"Cannot sell expired product (expired on {batch.expiry_date}).")
            return redirect(request.path)
        
        # Check stock
        if qty > batch.quantity:
            messages.error(
                request,
                f"Insufficient stock. Requested {qty}, available {batch.quantity}."
            )
            return redirect(request.path)
        
        # Create sale with wallet & commission integration
        with transaction.atomic():
            sale = PharmacySale.objects.create(
                business=business,
                batch=batch,
                quantity=qty,
                unit_price=batch.selling_price,
                unit_cost=batch.cost_price,
                payment_method=payment_method,
                customer_name=customer_name,
                customer_phone=customer_phone,
                prescription_number=prescription_number,
                sold_by=request.user,
                notes=notes,
            )
            
            # Decrement stock
            batch.decrement_stock(qty)
            
            # ===== WALLET & COMMISSION INTEGRATION =====
            # Wire into existing wallet/commission system similar to phones
            try:
                from wallet.services import add_txn
                from wallet.models import TxnType, Ledger
                from tenants.models import Membership
                
                # Add revenue to business admin wallet
                add_txn(
                    agent=request.user,
                    amount=sale.total_amount,
                    type=TxnType.SALE,
                    note=f"Pharmacy sale: {batch.merch_product.name} x{qty}",
                    reference=f"PHARM-SALE-{sale.id}",
                    effective_date=sale.sold_at.date(),
                    ledger=Ledger.ADMIN,
                    meta={"sale_id": sale.id, "product": batch.merch_product.name},
                )
                
                # Calculate and add agent commission if user is an agent
                membership = Membership.objects.filter(
                    business=business,
                    user=request.user,
                    role="agent",
                    status="active"
                ).first()
                
                if membership:
                    # Get commission rate (default 12% of selling price)
                    from sales.models import CommissionConfig
                    config = CommissionConfig.objects.filter(
                        business=business,
                        is_active=True
                    ).first()
                    
                    commission_rate = config.default_rate if config else Decimal("12.00")
                    commission_amount = (sale.total_amount * commission_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                    
                    if commission_amount > Decimal("0.00"):
                        add_txn(
                            agent=request.user,
                            amount=commission_amount,
                            type=TxnType.COMMISSION,
                            note=f"Commission for pharmacy sale #{sale.id}",
                            reference=f"PHARM-COMM-{sale.id}",
                            effective_date=sale.sold_at.date(),
                            ledger=Ledger.AGENT,
                            meta={"sale_id": sale.id, "rate": str(commission_rate)},
                        )
            except Exception as e:
                logger.warning(f"Failed to create wallet transactions for pharmacy sale {sale.id}: {e}")
            
            # Send WhatsApp notifications
            _send_sale_notifications(sale, business)
            
            # Check and notify low stock
            _check_and_notify_low_stock(batch, business)
        
        # Store success data in session
        request.session["sell_success"] = True
        request.session["last_sale_product"] = batch.merch_product.name
        request.session["last_sale_qty"] = qty
        request.session["last_sale_amount"] = float(sale.total_amount)
        request.session["last_sale_profit"] = float(sale.profit)
        
        messages.success(
            request,
            f"✅ Sale completed: {batch.merch_product.name} x{qty} for MWK {sale.total_amount:,.2f}"
        )
        return redirect("pharmacy:sell")
    
    # GET: Show form
    success_data = None
    if request.session.get("sell_success"):
        success_data = {
            "product_name": request.session.get("last_sale_product"),
            "quantity": request.session.get("last_sale_qty"),
            "amount": request.session.get("last_sale_amount"),
            "profit": request.session.get("last_sale_profit"),
        }
        del request.session["sell_success"]
        for key in ["last_sale_product", "last_sale_qty", "last_sale_amount", "last_sale_profit"]:
            if key in request.session:
                del request.session[key]
    
    # Get available batches (in stock, not expired)
    today = timezone.now().date()
    batches = PharmacyBatch.objects.filter(
        business=business,
        is_archived=False,
        quantity__gt=0,
        expiry_date__gte=today
    ).select_related("merch_product").order_by("expiry_date", "merch_product__name")
    
    # Prepare batch data for template
    batch_data = []
    for batch in batches:
        # Get category display name
        category_code = batch.merch_product.category or 'general'
        category_display = dict(PharmacyCategory.choices).get(category_code, 'General')
        
        batch_data.append({
            "id": batch.id,
            "product_name": batch.merch_product.name,
            "category": category_display,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "price": float(batch.selling_price),
            "cost": float(batch.cost_price),
            "expiry_date": str(batch.expiry_date),
            "days_to_expiry": batch.days_to_expiry,
        })
    
    ctx = {
        "success_data": success_data,
        "batches": batch_data,
    }
    
    return render(request, "verticals/pharmacy/sell.html", ctx)


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
    """List pharmacy sales (excluding soft-deleted by default)."""
    business: Business = request.business
    
    # Get active tab from query params (for template tab highlighting)
    active_tab = request.GET.get("tab", "all")
    
    # Filter out deleted sales by default (managers can see them if needed)
    show_deleted = request.GET.get("show_deleted") == "1"
    sales = PharmacySale.objects.filter(business=business).select_related(
        "batch__merch_product",
        "sold_by"
    )
    
    if not show_deleted:
        sales = sales.filter(is_deleted=False)
    
    sales = sales.order_by("-sold_at")[:200]  # Increased limit
    
    return render(
        request,
        "verticals/pharmacy/sale_list.html",
        {
            "sales": sales,
            "show_deleted": show_deleted,
            "active_tab": active_tab,
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


# ==============================================================================
# MANAGER TOOLS: EDIT, DELETE, UNDO
# ==============================================================================

def _is_manager(request, business) -> bool:
    """Check if user is a manager for this business."""
    try:
        from tenants.models import Membership
        return Membership.objects.filter(
            business=business,
            user=request.user,
            role__in=["manager", "owner"],
            status="active"
        ).exists()
    except Exception:
        return request.user.is_staff or request.user.is_superuser


@login_required
@require_business
def sale_edit(request: HttpRequest, sale_id: int) -> HttpResponse:
    """Edit a pharmacy sale (managers only)."""
    business: Business = request.business
    
    # Check manager permission
    if not _is_manager(request, business):
        messages.error(request, "Only managers can edit sales.")
        return redirect("pharmacy:sale_list")
    
    sale = get_object_or_404(PharmacySale, id=sale_id, business=business)
    
    # Don't allow editing deleted or reversed sales
    if sale.is_deleted or sale.is_reversed:
        messages.error(request, "Cannot edit a deleted or reversed sale.")
        return redirect("pharmacy:sale_list")
    
    if request.method == "POST":
        new_quantity = int(request.POST.get("quantity", sale.quantity))
        new_payment_method = request.POST.get("payment_method", sale.payment_method)
        
        # Validate quantity
        if new_quantity <= 0:
            messages.error(request, "Quantity must be at least 1.")
            return redirect(request.path)
        
        # Calculate stock change
        qty_delta = new_quantity - sale.quantity
        
        with transaction.atomic():
            # Adjust batch stock
            batch = sale.batch
            if qty_delta > 0:
                # Selling more - check if enough stock
                if qty_delta > batch.quantity:
                    messages.error(
                        request,
                        f"Insufficient stock to increase quantity. Available: {batch.quantity}"
                    )
                    return redirect(request.path)
                batch.quantity -= qty_delta
            else:
                # Selling less - restock
                batch.quantity += abs(qty_delta)
            
            batch.save()
            
            # Update sale
            old_qty = sale.quantity
            old_payment = sale.payment_method
            
            sale.quantity = new_quantity
            sale.payment_method = new_payment_method
            sale.save()  # This will recalculate total_amount via save() override
            
            # Log the edit in audit logs
            try:
                from audit.models import AuditLog
                AuditLog.objects.create(
                    business=business,
                    user=request.user,
                    action="EDIT_PHARMACY_SALE",
                    resource_type="PharmacySale",
                    resource_id=sale.id,
                    details={
                        "sale_id": sale.id,
                        "product": sale.batch.merch_product.name,
                        "old_quantity": old_qty,
                        "new_quantity": new_quantity,
                        "old_payment_method": old_payment,
                        "new_payment_method": new_payment_method,
                    }
                )
            except Exception:
                pass  # Audit logging is optional
        
        messages.success(request, f"Sale #{sale.id} updated successfully.")
        return redirect("pharmacy:sale_list")
    
    # GET: show edit form
    ctx = {
        "sale": sale,
        "payment_methods": PharmacySale.PAYMENT_METHOD_CHOICES,
    }
    return render(request, "verticals/pharmacy/sale_edit.html", ctx)


@login_required
@require_business
@require_POST
def sale_delete(request: HttpRequest, sale_id: int) -> HttpResponse:
    """Soft delete a pharmacy sale (managers only)."""
    business: Business = request.business
    
    # Check manager permission
    if not _is_manager(request, business):
        messages.error(request, "Only managers can delete sales.")
        return redirect("pharmacy:sale_list")
    
    sale = get_object_or_404(PharmacySale, id=sale_id, business=business)
    
    # Don't allow deleting already deleted sales
    if sale.is_deleted:
        messages.warning(request, "Sale is already deleted.")
        return redirect("pharmacy:sale_list")
    
    with transaction.atomic():
        # Restock the batch
        batch = sale.batch
        batch.quantity += sale.quantity
        batch.save()
        
        # Soft delete the sale
        sale.is_deleted = True
        sale.deleted_at = timezone.now()
        sale.deleted_by = request.user
        sale.save()
        
        # Reverse wallet transactions if they exist
        try:
            from wallet.services import reverse_sale_txns
            reverse_sale_txns(
                business=business,
                reference=f"PHARM-SALE-{sale.id}",
                note=f"Deleted pharmacy sale #{sale.id}",
                agent=request.user
            )
        except Exception as e:
            logger.warning(f"Failed to reverse wallet transactions for deleted sale {sale.id}: {e}")
        
        # Log the deletion
        try:
            from audit.models import AuditLog
            AuditLog.objects.create(
                business=business,
                user=request.user,
                action="DELETE_PHARMACY_SALE",
                resource_type="PharmacySale",
                resource_id=sale.id,
                details={
                    "sale_id": sale.id,
                    "product": sale.batch.merch_product.name,
                    "quantity": sale.quantity,
                    "amount": float(sale.total_amount),
                }
            )
        except Exception:
            pass
    
    messages.success(request, f"Sale #{sale.id} deleted successfully. Stock has been restored.")
    return redirect("pharmacy:sale_list")


@login_required
@require_business
@require_POST
def sale_undo(request: HttpRequest, sale_id: int) -> HttpResponse:
    """Undo/reverse a pharmacy sale (managers only)."""
    business: Business = request.business
    
    # Check manager permission
    if not _is_manager(request, business):
        messages.error(request, "Only managers can undo sales.")
        return redirect("pharmacy:sale_list")
    
    sale = get_object_or_404(PharmacySale, id=sale_id, business=business)
    
    # Don't allow undoing already reversed or deleted sales
    if sale.is_reversed:
        messages.warning(request, "Sale has already been reversed.")
        return redirect("pharmacy:sale_list")
    
    if sale.is_deleted:
        messages.warning(request, "Cannot undo a deleted sale.")
        return redirect("pharmacy:sale_list")
    
    with transaction.atomic():
        # Restock the batch
        batch = sale.batch
        batch.quantity += sale.quantity
        batch.save()
        
        # Mark original sale as reversed
        sale.is_reversed = True
        sale.save()
        
        # Create a reversal sale record (negative amounts for accounting)
        reversal = PharmacySale.objects.create(
            business=business,
            batch=batch,
            quantity=-sale.quantity,  # Negative to indicate reversal
            unit_price=sale.unit_price,
            unit_cost=sale.unit_cost,
            payment_method=sale.payment_method,
            sold_by=request.user,
            notes=f"Reversal of sale #{sale.id}",
            reversal_of=sale,
        )
        
        # Reverse wallet transactions
        try:
            from wallet.services import add_txn
            from wallet.models import TxnType, Ledger
            
            # Reverse revenue
            add_txn(
                agent=request.user,
                amount=-sale.total_amount,  # Negative amount
                type=TxnType.SALE,
                note=f"Reversal of pharmacy sale #{sale.id}",
                reference=f"PHARM-REVERSAL-{reversal.id}",
                effective_date=timezone.now().date(),
                ledger=Ledger.ADMIN,
                meta={"reversal_of": sale.id, "original_sale": sale.id},
            )
            
            # Reverse commission if it was paid
            try:
                from tenants.models import Membership
                membership = Membership.objects.filter(
                    business=business,
                    user=sale.sold_by,
                    role="agent",
                    status="active"
                ).first()
                
                if membership:
                    from sales.models import CommissionConfig
                    config = CommissionConfig.objects.filter(
                        business=business,
                        is_active=True
                    ).first()
                    
                    commission_rate = config.default_rate if config else Decimal("12.00")
                    commission_amount = (sale.total_amount * commission_rate / Decimal("100.00")).quantize(Decimal("0.01"))
                    
                    if commission_amount > Decimal("0.00"):
                        add_txn(
                            agent=sale.sold_by,
                            amount=-commission_amount,  # Negative to reverse
                            type=TxnType.COMMISSION,
                            note=f"Reversal of commission for sale #{sale.id}",
                            reference=f"PHARM-COMM-REV-{reversal.id}",
                            effective_date=timezone.now().date(),
                            ledger=Ledger.AGENT,
                            meta={"reversal_of": sale.id, "rate": str(commission_rate)},
                        )
            except Exception as e:
                logger.warning(f"Failed to reverse commission for sale {sale.id}: {e}")
        except Exception as e:
            logger.warning(f"Failed to reverse wallet transactions for sale {sale.id}: {e}")
        
        # Log the undo
        try:
            from audit.models import AuditLog
            AuditLog.objects.create(
                business=business,
                user=request.user,
                action="UNDO_PHARMACY_SALE",
                resource_type="PharmacySale",
                resource_id=sale.id,
                details={
                    "original_sale_id": sale.id,
                    "reversal_sale_id": reversal.id,
                    "product": sale.batch.merch_product.name,
                    "quantity": sale.quantity,
                    "amount": float(sale.total_amount),
                }
            )
        except Exception:
            pass
    
    messages.success(
        request,
        f"Sale #{sale.id} reversed successfully. Stock restored and transactions reversed."
    )
    return redirect("pharmacy:sale_list")

