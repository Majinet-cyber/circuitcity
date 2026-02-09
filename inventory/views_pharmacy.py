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
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Sum, Count, Q, F, DecimalField
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
    batches = PharmacyBatch.objects.filter(business=business, is_archived=False).select_related("merch_product")

    # Stock metrics (current state, not time-filtered)
    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)

    # Near expiry (next 30 days)
    near_expiry_batches = batches.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30)).order_by(
        "expiry_date"
    )[:10]

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
        is_reversed=False,  # Exclude reversed sales from metrics
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
    # Use standardized payment mix helper for consistency across all verticals
    from dashboard.helpers_payments import get_payment_mix

    payment_mix_list = get_payment_mix(
        business=business,
        start_date=start_date,
        end_date=end_date,
        user=None,  # Global view for managers
        vertical="pharmacy",
    )

    # ===== PRODUCT TYPE BREAKDOWN =====
    # Count medicines vs other products
    products_all = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True)
    products_count = products_all.count()

    # Check if product_type field exists (will add in migration)
    medicine_count = (
        products_all.filter(product_type="MEDICINE").count()
        if hasattr(MerchProduct, "product_type")
        else products_count
    )

    other_count = products_all.filter(product_type="OTHER").count() if hasattr(MerchProduct, "product_type") else 0

    # ===== TOP PRODUCTS (for selected period) =====
    # Aggregate sales by product for the period
    top_products_data = []
    # Get sales grouped by batch/product
    sales_by_batch = (
        period_sales.values("batch__merch_product__id", "batch__merch_product__name", "batch__merch_product__category")
        .annotate(total_qty=Sum("quantity"), total_revenue=Sum("total_amount"), sales_count=Count("id"))
        .order_by("-total_revenue")[:10]
    )

    for item in sales_by_batch:
        # Calculate profit for this product across all sales in period
        product_sales = period_sales.filter(batch__merch_product__id=item["batch__merch_product__id"])
        product_profit = sum(sale.profit for sale in product_sales)

        # Get category display name
        category_code = item["batch__merch_product__category"] or "general"
        category_display = dict(PharmacyCategory.choices).get(category_code, "General")

        top_products_data.append(
            {
                "name": item["batch__merch_product__name"],
                "category": category_display,
                "category_code": category_code,
                "quantity": item["total_qty"],
                "revenue": item["total_revenue"],
                "profit": product_profit,
                "sales_count": item["sales_count"],
            }
        )

    # ===== TOP CATEGORIES (for selected period) =====
    top_categories_data = []
    # Group by category
    sales_by_category = (
        period_sales.values("batch__merch_product__category")
        .annotate(total_qty=Sum("quantity"), total_revenue=Sum("total_amount"), sales_count=Count("id"))
        .order_by("-total_revenue")
    )

    for item in sales_by_category:
        category_code = item["batch__merch_product__category"] or "general"
        category_display = dict(PharmacyCategory.choices).get(category_code, "General")

        # Calculate profit for this category
        category_sales = period_sales.filter(batch__merch_product__category=category_code)
        category_profit = sum(sale.profit for sale in category_sales)

        top_categories_data.append(
            {
                "category": category_display,
                "category_code": category_code,
                "quantity": item["total_qty"],
                "revenue": item["total_revenue"],
                "profit": category_profit,
                "sales_count": item["sales_count"],
            }
        )

    # Calculate total for percentages
    total_category_revenue = sum(cat["revenue"] for cat in top_categories_data)
    for cat in top_categories_data:
        cat["revenue_pct"] = (
            float(cat["revenue"]) / float(total_category_revenue) * 100 if total_category_revenue > 0 else 0
        )

    # ===== COSTS FOR PERIOD (COGS + ADMIN COSTS) =====
    # CRITICAL FIX: Total Costs = COGS (cost of goods sold) + Admin Wallet Costs
    # COGS = Sum of (cost_price * quantity) for all sales in period
    period_cogs = Decimal("0.00")
    period_admin_costs = Decimal("0.00")

    # Calculate COGS from sales
    for sale in period_sales:
        # COGS = unit_cost * quantity
        period_cogs += sale.unit_cost * sale.quantity

    # Get admin costs from wallet (rent, salaries, utilities, etc.)
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        from wallet.utils_costs import ensure_monthly_recurring_costs

        # Ensure recurring costs are auto-created for current month (idempotent)
        try:
            from datetime import date as dt_date

            today = timezone.now().date()
            month_start = dt_date(today.year, today.month, 1)
            ensure_monthly_recurring_costs(business, month_start)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Could not auto-create recurring costs: {e}")

        # Get all admin costs for this period (both once-off and recurring instances)
        costs_queryset = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
            effective_date__gte=start_date,
            effective_date__lte=end_date,
        )

        # Sum costs (they're stored as negative, so take absolute value)
        period_admin_costs = abs(costs_queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))
    except Exception:
        pass  # Gracefully handle if wallet app not available

    # Total Costs = COGS + Admin Costs
    period_costs = period_cogs + period_admin_costs

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
    cosmetics_sales = period_sales.filter(batch__merch_product__category__in=cosmetics_categories)

    cosmetics_revenue = Decimal("0.00")
    for sale in cosmetics_sales:
        cosmetics_revenue += sale.total_amount

    cosmetics_revenue_pct = (float(cosmetics_revenue) / float(period_revenue) * 100) if period_revenue > 0 else 0

    # Cosmetics products in stock
    cosmetics_products = products_all.filter(category__in=cosmetics_categories).count()

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
            reverse=True,
        )[:5]
    except Exception:
        pass  # Gracefully handle if pharmacy_constants not available

    # ===== SAFE SUBSCRIPTION HANDLING =====
    # Never let missing subscription crash the dashboard
    subscription = None
    try:
        if hasattr(business, "subscription"):
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
        from dashboard.helpers_yesterday import (
            get_yesterday_summary,
            should_show_yesterday_summary,
            mark_yesterday_summary_shown,
        )
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, business)

        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, "logo") and business.logo:
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

        ctx_enhancements.update(
            {
                "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
                "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
                "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
                "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
                "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
                "DASHBOARD_BRAND_TITLE": business.name if business else "Pharmacy Dashboard",
                "YESTERDAY_SUMMARY": yesterday_summary,
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json,
            }
        )
    except Exception:
        pass  # Gracefully degrade if helpers not available, defaults already set

    # ===== ADDITIONAL KPIs FOR ENHANCED DASHBOARD =====
    # Calculate stock value at cost (sum of cost_price * quantity for all batches)
    # CRITICAL FIX: Use aggregate for efficiency instead of iterating
    from django.db.models import F as DjangoF
    from django.db.models.functions import Coalesce
    
    # Stock value at cost (safe handling of NULL prices)
    total_stock_value_cost = batches.aggregate(
        total=Sum(
            Coalesce(DjangoF("cost_price"), Decimal("0")) * DjangoF("quantity"),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )["total"] or Decimal("0")
    
    # Potential revenue (stock value at selling price)
    potential_revenue = batches.aggregate(
        total=Sum(
            Coalesce(DjangoF("selling_price"), Decimal("0")) * DjangoF("quantity"),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )["total"] or Decimal("0")
    
    # ===== DETAILED OPERATIONAL SUMMARIES =====
    # In-stock items (batches with quantity > 0)
    in_stock_count = batches.filter(quantity__gt=0).count()
    
    # Out of stock items (batches with quantity = 0)
    out_of_stock_count = batches.filter(quantity=0).count()
    
    # Total products count (already calculated above as products_count)
    
    # Active batches count (non-archived)
    active_batches_count = batches.count()
    
    # Today's sales amount (already calculated if range_param == 'today')
    today_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__date=today,
        is_deleted=False,
        is_reversed=False,
    )
    today_sales_amount = today_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    today_sales_count_actual = today_sales.count()
    
    # This month's sales amount
    month_start = today.replace(day=1)
    month_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__date__gte=month_start,
        sold_at__date__lte=today,
        is_deleted=False,
        is_reversed=False,
    )
    month_sales_amount = month_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    month_sales_count = month_sales.count()
    
    # Last 7 days units sold total
    seven_days_ago = today - timedelta(days=6)
    last_7_days_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__date__gte=seven_days_ago,
        sold_at__date__lte=today,
        is_deleted=False,
        is_reversed=False,
    )
    last_7_days_units = last_7_days_sales.aggregate(total=Sum("quantity"))["total"] or 0
    
    # Top category by revenue (last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    recent_sales = PharmacySale.objects.filter(
        business=business,
        sold_at__gte=timezone.make_aware(datetime.combine(thirty_days_ago, datetime.min.time())),
        is_deleted=False,
        is_reversed=False,
    )
    
    top_category_name = "N/A"
    if top_categories_data:
        top_category_name = top_categories_data[0]["category"]
    
    # Fast movers (top products by quantity in last 30 days)
    fast_movers = (
        recent_sales.values("batch__merch_product__name")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:3]
    )
    fast_movers_count = fast_movers.count()
    
    # "What Needs Attention" lists
    expiring_soon_items = near_expiry_batches[:5]  # Top 5 expiring soon
    
    # Out of stock products (quantity = 0)
    out_of_stock_products = products_all.filter(quantity_in_stock=0)[:5]
    out_of_stock_items = []
    for product in out_of_stock_products:
        category_display = dict(PharmacyCategory.choices).get(product.category or "general", "General")
        out_of_stock_items.append({
            "name": product.name,
            "category_display": category_display,
        })
    
    # Low stock items
    low_stock_items = low_stock_batches[:5]  # Top 5 low stock

    ctx = {
        # Navigation context (for base template)
        "active_tab": "home",  # Highlights the dashboard/home tab in mobile nav
        # Stock metrics (current state)
        "total_batches": total_batches,
        "total_stock_value": total_stock_value,  # At selling price (legacy)
        "total_stock_value_cost": total_stock_value_cost,  # At cost price (FIXED)
        "potential_revenue": potential_revenue,  # Stock value at selling price (new key)
        "products_count": products_count,
        "total_products": products_count,  # Alias for template compatibility
        "medicine_count": medicine_count,
        "other_count": other_count,
        # Alert counts
        "near_expiry_count": near_expiry_batches.count(),
        "expired_count": expired_batches.count(),
        "low_stock_count": low_stock_batches.count(),
        # ===== DETAILED OPERATIONAL SUMMARIES =====
        "in_stock_count": in_stock_count,  # Items with qty > 0
        "out_of_stock_count": out_of_stock_count,  # Items with qty = 0
        "active_batches_count": active_batches_count,  # Non-archived batches
        "today_sales_amount": today_sales_amount,  # Today's revenue
        "today_sales_count_actual": today_sales_count_actual,  # Today's transaction count
        "month_sales_amount": month_sales_amount,  # This month's revenue
        "month_sales_count": month_sales_count,  # This month's transaction count
        "last_7_days_units": last_7_days_units,  # Last 7 days units sold total
        # Period metrics (filtered by date range)
        "period_revenue": period_revenue,
        "period_profit": period_profit,
        "period_costs": period_costs,
        "period_cogs": period_cogs,  # Cost of goods sold (inventory cost)
        "period_admin_costs": period_admin_costs,  # Admin wallet costs (rent, salaries, etc.)
        "period_sales_count": period_sales_count,
        "avg_sale_value": avg_sale_value,
        # Date filter context
        "range_param": range_param,
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        # Payment mix for the period (standardized format for shared partial)
        "payment_mix": payment_mix_list,
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
        "today_revenue": today_sales_amount,  # Use actual today's sales
        "today_profit": period_profit if range_param == "today" else Decimal("0.00"),
        "today_sales_count": today_sales_count_actual,  # Use actual today's count
        # ===== ENHANCED DASHBOARD KPIs =====
        "top_category_name": top_category_name,
        "fast_movers_count": fast_movers_count,
        "fast_movers": list(fast_movers),  # Fast moving products (top 3)
        # What Needs Attention panels
        "expiring_soon_items": expiring_soon_items,
        "out_of_stock_items": out_of_stock_items,
        "low_stock_items": low_stock_items,
    }

    # Merge enhancements from above (includes quotes)
    ctx.update(ctx_enhancements)

    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context

    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "verticals/pharmacy/dashboard.html", ctx)


# ==============================================================================
# STOCK IN - NEW GAMIFIED FLOW (PHARMACY vs COSMETICS)
# ==============================================================================


@login_required
@require_business
def pharmacy_stock_in_choice(request: HttpRequest) -> HttpResponse:
    """
    Stock In landing page with choice between Pharmacy and Cosmetics.
    Part of the new gamified, organized stock-in UX.
    """
    return render(request, "verticals/pharmacy/stock_in_choice.html", {})


@login_required
@require_business
def pharmacy_stock_in_catalog(request: HttpRequest, category: str) -> HttpResponse:
    """
    Show curated product catalog for the selected category (pharmacy or cosmetics).
    Users click product cards to quickly add stock with minimal typing.
    """
    business: Business = request.business
    
    # Determine category and products
    is_pharmacy = category.lower() == "pharmacy"
    
    if is_pharmacy:
        category_name = "Pharmacy"
        category_icon = "💊"
        
        # Curated pharmacy products
        products = [
            {"name": "Paracetamol 500mg", "category": "analgesic", "category_display": "Pain Relief", "icon": "💊"},
            {"name": "Ibuprofen 400mg", "category": "analgesic", "category_display": "Pain Relief", "icon": "💊"},
            {"name": "Amoxicillin 500mg", "category": "antibiotic", "category_display": "Antibiotic", "icon": "💊"},
            {"name": "Amoxicillin 250mg", "category": "antibiotic", "category_display": "Antibiotic", "icon": "💊"},
            {"name": "ORS Sachets", "category": "gastrointestinal", "category_display": "Gastrointestinal", "icon": "💧"},
            {"name": "Cough Syrup", "category": "respiratory", "category_display": "Respiratory", "icon": "🍯"},
            {"name": "Vitamin C Tablets", "category": "vitamin", "category_display": "Vitamin", "icon": "🍊"},
            {"name": "Multivitamins", "category": "vitamin", "category_display": "Vitamin", "icon": "💊"},
            {"name": "Antacid Tablets", "category": "gastrointestinal", "category_display": "Gastrointestinal", "icon": "💊"},
            {"name": "Antihistamine", "category": "antihistamine", "category_display": "Antihistamine", "icon": "💊"},
            {"name": "Malaria Test Kit (RDT)", "category": "antiparasitic", "category_display": "Diagnostic", "icon": "🔬"},
            {"name": "Aspirin", "category": "analgesic", "category_display": "Pain Relief", "icon": "💊"},
            {"name": "Ciprofloxacin", "category": "antibiotic", "category_display": "Antibiotic", "icon": "💊"},
            {"name": "Metronidazole", "category": "antiparasitic", "category_display": "Antiparasitic", "icon": "💊"},
            {"name": "Albendazole", "category": "antiparasitic", "category_display": "Antiparasitic", "icon": "💊"},
            {"name": "Panadol Extra", "category": "analgesic", "category_display": "Pain Relief", "icon": "💊"},
            {"name": "Throat Lozenges", "category": "respiratory", "category_display": "Respiratory", "icon": "🍬"},
            {"name": "Eye Drops", "category": "drops", "category_display": "Eye Care", "icon": "👁️"},
            {"name": "Ear Drops", "category": "drops", "category_display": "Ear Care", "icon": "💧"},
            {"name": "First Aid Kit", "category": "general", "category_display": "General", "icon": "🏥"},
        ]
    else:
        category_name = "Cosmetics"
        category_icon = "💄"
        
        # Curated cosmetics products
        products = [
            {"name": "Body Lotion", "category": "skin_care", "category_display": "Skin Care", "icon": "🧴"},
            {"name": "Vaseline Petroleum Jelly", "category": "skin_care", "category_display": "Skin Care", "icon": "🧴"},
            {"name": "Face Wash", "category": "skin_care", "category_display": "Skin Care", "icon": "🧼"},
            {"name": "Shampoo", "category": "hair_care", "category_display": "Hair Care", "icon": "🧴"},
            {"name": "Conditioner", "category": "hair_care", "category_display": "Hair Care", "icon": "🧴"},
            {"name": "Hair Oil", "category": "hair_care", "category_display": "Hair Care", "icon": "🧴"},
            {"name": "Deodorant", "category": "personal_care", "category_display": "Personal Care", "icon": "💨"},
            {"name": "Perfume", "category": "beauty_makeup", "category_display": "Fragrance", "icon": "🌸"},
            {"name": "Lipstick", "category": "beauty_makeup", "category_display": "Makeup", "icon": "💄"},
            {"name": "Foundation", "category": "beauty_makeup", "category_display": "Makeup", "icon": "💄"},
            {"name": "Sunscreen SPF 50", "category": "skin_care", "category_display": "Skin Care", "icon": "☀️"},
            {"name": "Moisturizer", "category": "skin_care", "category_display": "Skin Care", "icon": "🧴"},
            {"name": "Hand Cream", "category": "skin_care", "category_display": "Skin Care", "icon": "✋"},
            {"name": "Toothpaste", "category": "oral_care", "category_display": "Oral Care", "icon": "🦷"},
            {"name": "Toothbrush", "category": "oral_care", "category_display": "Oral Care", "icon": "🪥"},
            {"name": "Mouthwash", "category": "oral_care", "category_display": "Oral Care", "icon": "💧"},
            {"name": "Baby Lotion", "category": "baby_care", "category_display": "Baby Care", "icon": "👶"},
            {"name": "Baby Powder", "category": "baby_care", "category_display": "Baby Care", "icon": "👶"},
            {"name": "Diaper Rash Cream", "category": "baby_care", "category_display": "Baby Care", "icon": "👶"},
            {"name": "Soap Bar", "category": "personal_care", "category_display": "Personal Care", "icon": "🧼"},
            {"name": "Shower Gel", "category": "personal_care", "category_display": "Personal Care", "icon": "🧴"},
            {"name": "Nail Polish", "category": "beauty_makeup", "category_display": "Makeup", "icon": "💅"},
            {"name": "Mascara", "category": "beauty_makeup", "category_display": "Makeup", "icon": "💄"},
            {"name": "Eyeliner", "category": "beauty_makeup", "category_display": "Makeup", "icon": "💄"},
        ]
    
    ctx = {
        "category": category,
        "category_name": category_name,
        "category_icon": category_icon,
        "is_pharmacy": is_pharmacy,
        "products": products,
    }
    
    return render(request, "verticals/pharmacy/stock_in_catalog.html", ctx)


@login_required
@require_business
@require_POST
def pharmacy_stock_in_catalog_save(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to save stock from the catalog flow.
    Reuses existing stock_in_pharmacy service for consistency.
    """
    import json
    from inventory.services.pharmacy_sale import stock_in_pharmacy
    
    business: Business = request.business
    location = getattr(request, "location", None)
    
    try:
        data = json.loads(request.body)
        
        product_name = data.get("product_name")
        category = data.get("category")
        quantity = int(data.get("quantity", 1))
        cost_price = Decimal(str(data.get("cost_price", 0)))
        selling_price = Decimal(str(data.get("selling_price", 0)))
        expiry_date_str = data.get("expiry_date")
        batch_number = data.get("batch_number")
        
        # Validate required fields
        if not product_name or not category:
            return JsonResponse({"ok": False, "error": "Product name and category are required"}, status=400)
        
        if quantity <= 0:
            return JsonResponse({"ok": False, "error": "Quantity must be greater than 0"}, status=400)
        
        if cost_price < 0 or selling_price < 0:
            return JsonResponse({"ok": False, "error": "Prices cannot be negative"}, status=400)
        
        # Parse expiry date if provided
        expiry_date = None
        if expiry_date_str:
            try:
                from datetime import datetime
                expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Invalid expiry date format"}, status=400)
        
        # Use the existing service layer to save stock
        result = stock_in_pharmacy(
            business=business,
            product_name=product_name,
            category=category,
            user=request.user,
            quantity=quantity,
            unit="piece",  # Catalog flow uses base units
            cost_price=cost_price,
            selling_price=selling_price,
            batch_number=batch_number or None,
            expiry_date=expiry_date,
            barcode=None,  # No barcode in catalog flow
            supplier=None,
            location=location,
            notes=f"Added via catalog (category: {category})",
        )
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error in pharmacy_stock_in_catalog_save: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": "Internal server error"}, status=500)


# ==============================================================================
# GAMIFIED STOCK IN WIZARD (Card-Based Flow - LEGACY)
# ==============================================================================


@login_required
@require_business
def pharmacy_stock_in_wizard(request: HttpRequest) -> HttpResponse:
    """
    NEW: Gamified wizard-based stock-in flow with card selections.
    Multi-step process: Category → Subcategory/Product → Details → Save
    Uses session to track wizard state across steps.
    """
    from inventory.pharmacy_constants import (
        get_top_categories,
        get_subcategories_for_category,
        get_items_for_subcategory,
        get_items_for_top_category,
    )

    business: Business = request.business

    # Handle form submission
    if request.method == "POST":
        action = request.POST.get("action", "next")

        # Jump action - allow user to jump to any previous step (clickable breadcrumb)
        if action == "jump":
            target_step = int(request.POST.get("jump_to_step", 0))
            current_step = int(request.POST.get("wizard_step", 0))

            # Only allow jumping backwards (to completed steps)
            if target_step < current_step:
                request.session["pharmacy_wizard_step"] = target_step
                # Clear selections for steps after the target
                if target_step <= 0:
                    request.session.pop("pharmacy_wizard_mode", None)
                    request.session.pop("pharmacy_wizard_category", None)
                    request.session.pop("pharmacy_wizard_subcategory", None)
                    request.session.pop("pharmacy_wizard_item", None)
                elif target_step <= 1:
                    request.session.pop("pharmacy_wizard_category", None)
                    request.session.pop("pharmacy_wizard_subcategory", None)
                    request.session.pop("pharmacy_wizard_item", None)
                elif target_step <= 2:
                    request.session.pop("pharmacy_wizard_subcategory", None)
                    request.session.pop("pharmacy_wizard_item", None)
                elif target_step <= 3:
                    request.session.pop("pharmacy_wizard_item", None)

            return redirect("pharmacy:stock_in_wizard")

        # Back button - decrement step
        if action == "back":
            current_step = int(request.POST.get("wizard_step", 0))
            request.session["pharmacy_wizard_step"] = max(0, current_step - 1)
            # Clear selections if going back to earlier steps
            if current_step <= 1:
                request.session.pop("pharmacy_wizard_mode", None)
            if current_step <= 2:
                request.session.pop("pharmacy_wizard_category", None)
            if current_step <= 3:
                request.session.pop("pharmacy_wizard_subcategory", None)
                request.session.pop("pharmacy_wizard_item", None)
            return redirect("pharmacy:stock_in_wizard")

        # Save action - final step
        if action == "save":
            return _handle_wizard_save(request, business)

        # Next button - advance to next step
        current_step = int(request.POST.get("wizard_step", 0))

        if current_step == 0:
            # Step 0: Mode selected (Pharmacy or Cosmetics)
            selected_mode = request.POST.get("selected_mode", "").strip()
            if selected_mode:
                request.session["pharmacy_wizard_mode"] = selected_mode
                request.session["pharmacy_wizard_step"] = 1
            return redirect("pharmacy:stock_in_wizard")

        elif current_step == 1:
            # Step 1: Category selected
            selected_category = request.POST.get("selected_category", "").strip()
            if selected_category:
                request.session["pharmacy_wizard_category"] = selected_category
                request.session["pharmacy_wizard_step"] = 2
            return redirect("pharmacy:stock_in_wizard")

        elif current_step == 2:
            # Step 2: Subcategory or Item selected
            selected_subcategory = request.POST.get("selected_subcategory", "").strip()
            selected_item = request.POST.get("selected_item", "").strip()

            if selected_subcategory:
                request.session["pharmacy_wizard_subcategory"] = selected_subcategory
                request.session["pharmacy_wizard_step"] = 3
            elif selected_item:
                request.session["pharmacy_wizard_item"] = selected_item
                request.session["pharmacy_wizard_step"] = 4  # Skip to details

            return redirect("pharmacy:stock_in_wizard")

        elif current_step == 3:
            # Step 3: Specific item selected (for subcategories)
            selected_item = request.POST.get("selected_item", "").strip()
            if selected_item:
                request.session["pharmacy_wizard_item"] = selected_item
                request.session["pharmacy_wizard_step"] = 4
            return redirect("pharmacy:stock_in_wizard")

    # GET: Display current step
    step = request.session.get("pharmacy_wizard_step", 0)
    wizard_mode = request.session.get("pharmacy_wizard_mode", "")
    selected_category = request.session.get("pharmacy_wizard_category", "")
    selected_subcategory = request.session.get("pharmacy_wizard_subcategory", "")
    selected_item = request.session.get("pharmacy_wizard_item", "")

    # Check for success flag
    success_data = None
    if request.session.get("pharmacy_wizard_success"):
        success_data = {
            "product_name": request.session.get("last_product_name"),
            "quantity": request.session.get("last_quantity"),
        }
        # Clear success data
        request.session.pop("pharmacy_wizard_success", None)
        request.session.pop("last_product_name", None)
        request.session.pop("last_quantity", None)
        # Reset wizard
        request.session["pharmacy_wizard_step"] = 0
        request.session.pop("pharmacy_wizard_mode", None)
        request.session.pop("pharmacy_wizard_category", None)
        request.session.pop("pharmacy_wizard_subcategory", None)
        request.session.pop("pharmacy_wizard_item", None)

    # Build context based on current step
    # Get membership for base template (prevents AttributeError on request.membership)
    from tenants.models import Membership
    membership = (
        Membership.objects.filter(user=request.user, business=business).first()
        if request.user.is_authenticated
        else None
    )
    
    ctx = {
        "step": step,
        "success_data": success_data,
        "wizard_mode": wizard_mode,
        "selected_category": selected_category,
        "selected_subcategory": selected_subcategory,
        "selected_item": selected_item,
        "active_tab": "stock_in",  # For base template navigation highlighting
        "membership": membership,  # For base template role display
    }

    if step == 0:
        # Step 0: Show Pharmacy vs Cosmetics mode selection (TEXT ONLY - no icons)
        ctx["mode_options"] = [
            {"key": "pharmacy", "label": "Pharmacy", "description": "Medicines & medical supplies"},
            {"key": "cosmetics", "label": "Cosmetics", "description": "Beauty & personal care products"},
        ]

    elif step == 1:
        # Step 1: Show top-level categories filtered by mode
        all_categories = get_top_categories()

        # Filter categories based on mode
        if wizard_mode == "cosmetics":
            # Show cosmetics subcategories directly as top-level categories
            from inventory.pharmacy_constants import COSMETICS_SUBCATEGORIES, get_prefills_for_cosmetics_category

            categories_to_show = COSMETICS_SUBCATEGORIES

            # Add product counts for cosmetics categories
            cosmetics_category_codes = [
                PharmacyCategory.SKIN_CARE,
                PharmacyCategory.HAIR_CARE,
                PharmacyCategory.PERSONAL_CARE,
                PharmacyCategory.BEAUTY_MAKEUP,
                PharmacyCategory.BABY_CARE,
                PharmacyCategory.ORAL_CARE,
            ]

            # Map wizard keys to model enum values
            wizard_to_model_map = {
                "skin_care": PharmacyCategory.SKIN_CARE,
                "hair_care": PharmacyCategory.HAIR_CARE,
                "body_care": PharmacyCategory.PERSONAL_CARE,  # Map body_care to personal_care
                "perfumes": PharmacyCategory.BEAUTY_MAKEUP,  # Map perfumes to beauty_makeup
                "mens_grooming": PharmacyCategory.PERSONAL_CARE,
                "makeup": PharmacyCategory.BEAUTY_MAKEUP,
                "other_cosmetics": PharmacyCategory.OTHER,
            }

            # Add counts to each category (DB products + prefills)
            for cat in categories_to_show:
                model_category = wizard_to_model_map.get(cat["key"])
                db_count = 0
                if model_category:
                    # Get existing DB products
                    existing_products = list(
                        MerchProduct.objects.filter(
                            business=business, kind="pharmacy", category=model_category, is_active=True
                        ).values_list("name", flat=True)
                    )
                    db_count = len(existing_products)

                    # Get prefills for this category
                    prefills = get_prefills_for_cosmetics_category(cat["key"])

                    # Normalize names for comparison (case-insensitive, strip whitespace)
                    existing_normalized = {name.lower().strip() for name in existing_products}

                    # Count prefills not already in DB
                    prefill_count = sum(1 for p in prefills if p.lower().strip() not in existing_normalized)

                    cat["product_count"] = db_count + prefill_count
                else:
                    # Fallback: just count prefills
                    prefills = get_prefills_for_cosmetics_category(cat["key"])
                    cat["product_count"] = len(prefills)

            ctx["top_categories"] = categories_to_show

        elif wizard_mode == "pharmacy":
            # Show all pharmacy categories (exclude cosmetics)
            categories_to_show = [cat for cat in all_categories if cat["key"] != "cosmetics"]

            # Add product counts for pharmacy categories (approximate based on wizard structure)
            # Since wizard categories don't map 1:1 to model categories, we'll show total pharmacy products
            total_pharmacy_products = (
                MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True)
                .exclude(
                    category__in=[
                        PharmacyCategory.SKIN_CARE,
                        PharmacyCategory.HAIR_CARE,
                        PharmacyCategory.PERSONAL_CARE,
                        PharmacyCategory.BEAUTY_MAKEUP,
                        PharmacyCategory.BABY_CARE,
                        PharmacyCategory.ORAL_CARE,
                    ]
                )
                .count()
            )

            # Distribute count info across categories (show total for now)
            for cat in categories_to_show:
                cat["product_count"] = total_pharmacy_products

            ctx["top_categories"] = categories_to_show
        else:
            # Fallback: show all
            ctx["top_categories"] = all_categories

    elif step == 2:
        # Step 2: Show subcategories or items based on selected category (after mode and category selection)
        category_labels = {cat["key"]: cat["label"] for cat in get_top_categories()}

        # Handle cosmetics subcategories labels
        if wizard_mode == "cosmetics":
            from inventory.pharmacy_constants import COSMETICS_SUBCATEGORIES

            cosmetics_labels = {sub["key"]: sub["label"] for sub in COSMETICS_SUBCATEGORIES}
            ctx["selected_category_label"] = cosmetics_labels.get(selected_category, selected_category)
        else:
            ctx["selected_category_label"] = category_labels.get(selected_category, selected_category)

        subcategories = get_subcategories_for_category(selected_category)
        if subcategories:
            ctx["subcategories"] = subcategories
        else:
            # Direct items for this category
            # FIXED: For cosmetics, ALWAYS show DB products + prefills + custom option
            if wizard_mode == "cosmetics":
                from inventory.pharmacy_constants import get_prefills_for_cosmetics_category, COSMETICS_SUBCATEGORIES

                # Validate that selected_category is a valid cosmetics subcategory
                valid_cosmetics_keys = [sub["key"] for sub in COSMETICS_SUBCATEGORIES]
                if selected_category not in valid_cosmetics_keys:
                    # Fallback: treat as "other_cosmetics"
                    logger.warning(f"Invalid cosmetics category: {selected_category}, using other_cosmetics")
                    selected_category = "other_cosmetics"
                    request.session["pharmacy_wizard_category"] = "other_cosmetics"

                # Map wizard subcategory keys to model category enum values
                wizard_to_model_map = {
                    "skin_care": PharmacyCategory.SKIN_CARE,
                    "hair_care": PharmacyCategory.HAIR_CARE,
                    "body_care": PharmacyCategory.PERSONAL_CARE,
                    "perfumes": PharmacyCategory.BEAUTY_MAKEUP,
                    "mens_grooming": PharmacyCategory.PERSONAL_CARE,
                    "makeup": PharmacyCategory.BEAUTY_MAKEUP,
                    "other_cosmetics": PharmacyCategory.OTHER,
                }

                model_category = wizard_to_model_map.get(selected_category)

                # Get prefills for this category (ALWAYS, even if model category not found)
                prefills = get_prefills_for_cosmetics_category(selected_category)

                if model_category:
                    # Fetch existing products for this business + category
                    existing_products = list(
                        MerchProduct.objects.filter(
                            business=business, kind="pharmacy", category=model_category, is_active=True
                        ).values_list("name", flat=True)
                    )

                    # Normalize for deduplication (case-insensitive)
                    existing_normalized = {name.lower().strip() for name in existing_products}

                    # Build items list: DB products first, then prefills not in DB
                    items = [{"name": name, "icon": "✨"} for name in existing_products]

                    for prefill_name in prefills:
                        if prefill_name.lower().strip() not in existing_normalized:
                            items.append({"name": prefill_name, "icon": "💡", "is_prefill": True})
                else:
                    # No model mapping found: just show all prefills (no DB filter)
                    items = [{"name": name, "icon": "💡", "is_prefill": True} for name in prefills]

                # ALWAYS add "+ Add Custom Product" option at the end
                items.append({"name": "+ Add Custom Product", "icon": "📝", "is_custom": True})

                # CRITICAL: Ensure items list is never empty
                if len(items) == 1:  # Only custom option
                    # Add a fallback message item (won't be selectable, just informational)
                    items.insert(0, {"name": "Generic Product", "icon": "📦", "is_prefill": True})

                ctx["items"] = items
            else:
                # Pharmacy mode: use standard items
                items = get_items_for_top_category(selected_category)
                # Safety: if no items found, add a custom option
                if not items:
                    items = [{"name": "+ Add Custom Product", "icon": "📝"}]
                ctx["items"] = items

    elif step == 3:
        # Step 3: Show specific items for selected subcategory
        category_labels = {cat["key"]: cat["label"] for cat in get_top_categories()}
        ctx["selected_category_label"] = category_labels.get(selected_category, selected_category)

        subcategories = get_subcategories_for_category(selected_category)
        subcat_labels = {sub["key"]: sub["label"] for sub in subcategories}
        ctx["selected_subcategory_label"] = subcat_labels.get(selected_subcategory, selected_subcategory)

        ctx["show_item_selection"] = True

        # For cosmetics, show existing products + prefills as clickable cards + "Other" option
        if wizard_mode == "cosmetics" and selected_subcategory:
            from inventory.pharmacy_constants import get_prefills_for_cosmetics_category

            # Map wizard subcategory keys to model category enum values
            wizard_to_model_map = {
                "skin_care": PharmacyCategory.SKIN_CARE,
                "hair_care": PharmacyCategory.HAIR_CARE,
                "body_care": PharmacyCategory.PERSONAL_CARE,
                "perfumes": PharmacyCategory.BEAUTY_MAKEUP,
                "mens_grooming": PharmacyCategory.PERSONAL_CARE,
                "makeup": PharmacyCategory.BEAUTY_MAKEUP,
                "other_cosmetics": PharmacyCategory.OTHER,
            }

            model_category = wizard_to_model_map.get(selected_subcategory)

            # Get prefills for this category (ALWAYS, even if model category not found)
            prefills = get_prefills_for_cosmetics_category(selected_subcategory)

            if model_category:
                # Fetch existing products for this business + category
                existing_products = list(
                    MerchProduct.objects.filter(
                        business=business, kind="pharmacy", category=model_category, is_active=True
                    ).values_list("name", flat=True)
                )

                # Normalize for deduplication (case-insensitive)
                existing_normalized = {name.lower().strip() for name in existing_products}

                # Build items list: DB products first, then prefills not in DB
                items = [{"name": name, "icon": "✨"} for name in existing_products]

                for prefill_name in prefills:
                    if prefill_name.lower().strip() not in existing_normalized:
                        items.append({"name": prefill_name, "icon": "💡", "is_prefill": True})
            else:
                # No model mapping: try standard items, or show all prefills
                items = get_items_for_subcategory(selected_category, selected_subcategory)
                if not items or len(items) == 0:
                    # Fall back to prefills
                    items = [{"name": name, "icon": "💡", "is_prefill": True} for name in prefills]

            # ALWAYS add "+ Add Custom Product" option at the end
            items.append({"name": "+ Add Custom Product", "icon": "📝", "is_custom": True})

            # CRITICAL: Ensure items list is never empty
            if len(items) == 1:  # Only custom option
                # Add a fallback message item
                items.insert(0, {"name": "Generic Product", "icon": "📦", "is_prefill": True})

            ctx["items"] = items
        else:
            # For pharmacy mode, use the standard brand items
            ctx["items"] = get_items_for_subcategory(selected_category, selected_subcategory)

    return render(request, "verticals/pharmacy/stock_in_wizard.html", ctx)


def _handle_wizard_save(request: HttpRequest, business: Business) -> HttpResponse:
    """
    Handle the final save step of the pharmacy wizard.
    NOW USES SERVICE LAYER for clean, atomic operations.
    """
    try:
        # Get wizard mode from session FIRST (needed for product_name fallback)
        wizard_mode = request.session.get("pharmacy_wizard_mode", "pharmacy")
        selected_category = request.session.get("pharmacy_wizard_category", "")
        selected_subcategory = request.session.get("pharmacy_wizard_subcategory", "")
        selected_item = request.session.get("pharmacy_wizard_item", "")

        # Extract form data - support both field naming conventions
        # product_name: from form, or fallback to selected_item from session
        product_name = (
            request.POST.get("product_name", "").strip() or 
            request.POST.get("selected_item", "").strip() or 
            selected_item
        )
        quantity = request.POST.get("quantity", "0")
        # Support both buying_price (test convention) and cost_price (view convention)
        cost_price = request.POST.get("cost_price") or request.POST.get("buying_price", "0")
        selling_price = request.POST.get("selling_price", "0")
        batch_number = request.POST.get("batch_number", "").strip()
        expiry_date_str = request.POST.get("expiry_date", "")
        supplier = request.POST.get("supplier", "").strip()
        has_barcode = request.POST.get("has_barcode", "no")
        barcode_value = request.POST.get("barcode", "").strip()

        # Determine if this is cosmetics
        is_cosmetics = wizard_mode == "cosmetics" or selected_category == "cosmetics"

        # Map wizard subcategory to pharmacy_config category
        # This maps the wizard UI categories to the service layer categories
        from inventory.pharmacy_config import PharmacyCategory as ConfigCategory

        wizard_to_config_map = {
            "skin_care": ConfigCategory.COSMETICS,
            "hair_care": ConfigCategory.COSMETICS,
            "body_care": ConfigCategory.COSMETICS,
            "perfumes": ConfigCategory.COSMETICS,
            "mens_grooming": ConfigCategory.COSMETICS,
            "makeup": ConfigCategory.COSMETICS,
            "other_cosmetics": ConfigCategory.OTHER,
            # Medicine categories
            "medicines": ConfigCategory.TABLETS_CAPSULES,  # Default for medicines
            "tablets": ConfigCategory.TABLETS_CAPSULES,
            "syrup": ConfigCategory.SYRUP,
            "ointment": ConfigCategory.OINTMENT,
            "drops": ConfigCategory.DROPS,
        }

        # Determine service layer category
        if wizard_mode == "cosmetics":
            service_category = wizard_to_config_map.get(selected_subcategory, ConfigCategory.COSMETICS)
        else:
            service_category = wizard_to_config_map.get(selected_category, ConfigCategory.OTHER)

        # Also map to PharmacyCategory enum for backward compatibility
        wizard_to_model_map = {
            "skin_care": PharmacyCategory.SKIN_CARE,
            "hair_care": PharmacyCategory.HAIR_CARE,
            "body_care": PharmacyCategory.PERSONAL_CARE,
            "perfumes": PharmacyCategory.BEAUTY_MAKEUP,
            "mens_grooming": PharmacyCategory.PERSONAL_CARE,
            "makeup": PharmacyCategory.BEAUTY_MAKEUP,
            "other_cosmetics": PharmacyCategory.OTHER,
        }

        if wizard_mode == "cosmetics" and selected_subcategory:
            product_category = wizard_to_model_map.get(selected_subcategory, PharmacyCategory.OTHER)
        elif wizard_mode == "cosmetics" and selected_category:
            product_category = wizard_to_model_map.get(selected_category, PharmacyCategory.OTHER)
        else:
            product_category = "medicine"  # Default

        # Basic validation
        errors = []
        if not product_name:
            errors.append("Product name is required.")

        # Parse and validate quantity
        try:
            qty = int(quantity)
            if qty <= 0:
                errors.append("Quantity must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Invalid quantity.")
            qty = 0

        # Parse and validate prices
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

        # Parse expiry date (required for pharmacy/medicines, optional for cosmetics)
        expiry_date = None
        if expiry_date_str:
            try:
                expiry_date = timezone.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                errors.append("Invalid expiry date format.")

        # Expiry date validation: REQUIRED for pharmacy (medicines), OPTIONAL for cosmetics
        if not is_cosmetics and not expiry_date:
            errors.append("Expiry date is required for medicines.")

        # Normalize barcode if provided
        final_barcode = None
        if has_barcode == "yes" and barcode_value:
            from inventory.utils_barcodes import validate_barcode, normalize_barcode

            is_valid, error_msg = validate_barcode(barcode_value)
            if not is_valid:
                errors.append(f"Invalid barcode: {error_msg}")
            else:
                final_barcode = normalize_barcode(barcode_value)

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("pharmacy:stock_in_wizard")

        # USE SERVICE LAYER for atomic, clean stock-in operation
        from inventory.services.pharmacy_sale import stock_in_pharmacy

        try:
            # Use detailed category for cosmetics mode, simplified category otherwise
            category_for_service = product_category if wizard_mode == "cosmetics" else service_category
            
            result = stock_in_pharmacy(
                business=business,
                product_name=product_name,
                category=category_for_service,
                user=request.user,
                quantity=qty,
                unit="piece",  # Wizard uses base units by default
                cost_price=cost,
                selling_price=selling,
                batch_number=batch_number or None,  # Auto-generated if empty
                expiry_date=expiry_date,
                barcode=final_barcode,
                supplier=supplier or None,
                location=getattr(request, "location", None),
                notes=None,
            )

            if result["ok"]:
                messages.success(request, result["message"])
            else:
                messages.error(request, result.get("error", "Stock-in failed"))
                return redirect("pharmacy:stock_in_wizard")

        except ValidationError as e:
            messages.error(request, str(e))
            return redirect("pharmacy:stock_in_wizard")
        except Exception as e:
            logger.error(f"Wizard stock-in error: {e}", exc_info=True)
            messages.error(request, f"❌ Error: {str(e)}")
            return redirect("pharmacy:stock_in_wizard")

        # Store success flag in session
        request.session["pharmacy_wizard_success"] = True
        request.session["last_product_name"] = product_name
        request.session["last_quantity"] = qty

        return redirect("pharmacy:stock_in_wizard")

    except ValidationError as e:
        # Django model validation errors
        messages.error(request, f"Validation error: {str(e)}")
        logger.error(f"Validation error in pharmacy wizard save: {e}")
        return redirect("pharmacy:stock_in_wizard")

    except IntegrityError as e:
        # Database integrity errors (e.g., duplicate, constraint violation)
        messages.error(
            request, "Database error: This item may already exist or there's a data conflict. Please check your input."
        )
        logger.error(f"Integrity error in pharmacy wizard save: {e}")
        return redirect("pharmacy:stock_in_wizard")

    except Exception as e:
        # Catch-all for any other errors - NEVER return 500
        messages.error(
            request, f"An unexpected error occurred while saving. Please try again or contact support. Error: {str(e)}"
        )
        logger.exception(f"Unexpected error in pharmacy wizard save: {e}")
        return redirect("pharmacy:stock_in_wizard")


# ==============================================================================
# GAMIFIED STOCK IN (Vertical-aware - LEGACY FORM-BASED)
# ==============================================================================


@login_required
@require_business
def pharmacy_stock_in(request: HttpRequest) -> HttpResponse:
    """
    LEGACY: Form-based stock-in (kept as fallback).
    Single-page form for adding new stock with validation and celebration.
    NEW USERS SHOULD USE pharmacy_stock_in_wizard INSTEAD.
    
    NOW WITH SERVER-DRIVEN NAVIGATION: Works without JavaScript.
    Query params: ?step=1&category=medicine
    """
    business: Business = request.business
    
    # ===== SERVER-DRIVEN STEP NAVIGATION =====
    # Read query parameters for step and category
    step = int(request.GET.get("step", "1"))
    selected_category = request.GET.get("category", "").strip()
    
    # Query products if category is selected (for Step 2)
    products_list = []
    suggested_cards = []
    if selected_category:
        products_list = MerchProduct.objects.filter(
            business=business,
            kind="pharmacy",
            category=selected_category,
            is_active=True
        ).order_by("name")[:40]  # Limit to 40 products for performance
        
        # NEW: Compute suggested products for smart recommendations
        from inventory.pharmacy_suggestions import get_suggestions_for_category
        
        seed = get_suggestions_for_category(selected_category)
        
        # Build a lookup dict of existing products by normalized name
        existing_qs = MerchProduct.objects.filter(
            business=business,
            kind="pharmacy",
            category=selected_category,
            is_active=True
        )
        existing_by_name = {p.name.strip().lower(): p for p in existing_qs}
        
        # Build suggested_cards with exists flag and product_id
        for s in seed:
            key = s["name"].strip().lower()
            p = existing_by_name.get(key)
            suggested_cards.append({
                "name": s["name"],
                "brand": s.get("brand", ""),
                "unit": s.get("unit", ""),
                "exists": bool(p),
                "product_id": p.id if p else None,
            })

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

        # NEW: Barcode workflow
        has_barcode = request.POST.get("has_barcode", "no")
        barcode_value = request.POST.get("barcode", "").strip()

        # Validation
        errors = []
        if not product_name:
            errors.append("Product name is required.")
        if not batch_number:
            errors.append("Batch number is required.")
        if not expiry_date_str:
            errors.append("Expiry date is required.")

        # NEW: Barcode validation (conditional)
        if has_barcode == "yes":
            if not barcode_value:
                errors.append("Barcode is required when 'Has Barcode' is Yes.")
            else:
                from inventory.utils_barcodes import validate_barcode, normalize_barcode

                is_valid, error_msg = validate_barcode(barcode_value)
                if not is_valid:
                    errors.append(f"Invalid barcode: {error_msg}")
                else:
                    barcode_value = normalize_barcode(barcode_value)

        # Validate category against allowed values
        VALID_CATEGORIES = [
            "medicine",
            "supplements",
            "skin_care",
            "hair_care",
            "body_care",
            "baby_care",
            "oral_care",
            "perfumes",
            "deodorants",
            "makeup",
            "soap_hygiene",
            "first_aid",
            "other",
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
                    "spec_label": "",  # CRITICAL: Always set spec_label (prevents NULL constraint)
                    "cost_price": cost,
                    "selling_price": selling,
                },
            )

            # If product exists, optionally update prices and category
            if not created:
                # Update if prices or category changed
                if product.cost_price != cost or product.selling_price != selling or product.category != category:
                    product.cost_price = cost
                    product.selling_price = selling
                    product.category = category
                    product.save()

            # NEW: Store barcode if provided
            if has_barcode == "yes" and barcode_value:
                from inventory.utils_barcodes import set_barcode

                set_barcode(product, barcode_value)
                product.save()

            # Check for duplicate batch
            existing_batch = PharmacyBatch.objects.filter(
                business=business, merch_product=product, batch_number=batch_number, expiry_date=expiry_date
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
                    request, f"✅ Stock updated! Added {qty} units to existing batch. Total: {existing_batch.quantity}"
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
                    request, f"🎉 Stock added successfully! {product_name} - {qty} units (Batch: {batch_number})"
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
        # Server-driven navigation
        "step": step,
        "selected_category": selected_category,
        "products_list": products_list,
        "suggested_cards": suggested_cards,  # NEW: Smart product suggestions
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
    products = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True).order_by("name")

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
            business=business, merch_product=product, batch_number=batch_number, expiry_date=expiry_date
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
    products = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True).order_by("name")

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
    manager_memberships = Membership.objects.filter(business=business, role__in=["manager", "owner"]).select_related(
        "user"
    )

    for membership in manager_memberships:
        try:
            whatsapp_service.notify_manager_sale(membership.user, business, sale_info)
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to manager {membership.user_id}: {e}")

    # Notify agent (if sale was made by an agent)
    if sale.sold_by:
        try:
            # Check if user is an agent
            agent_membership = Membership.objects.filter(business=business, user=sale.sold_by, role="agent").first()

            if agent_membership:
                # Calculate commission (if applicable)
                # For now, use a simple 5% commission on profit
                commission = sale.profit * Decimal("0.05")

                whatsapp_service.notify_agent_commission(sale.sold_by, business, sale_info, commission)
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
    manager_memberships = Membership.objects.filter(business=business, role__in=["manager", "owner"]).select_related(
        "user"
    )

    for membership in manager_memberships:
        try:
            whatsapp_service.notify_manager_low_stock(
                membership.user, business, batch.merch_product.name, batch.quantity, batch.reorder_level
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
            messages.error(request, f"Insufficient stock. Requested {qty}, available {batch.quantity}.")
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
                    business=business, user=request.user, role="agent", status="active"
                ).first()

                if membership:
                    # Get commission rate (default 12% of selling price)
                    from sales.models import CommissionConfig

                    config = CommissionConfig.objects.filter(business=business, is_active=True).first()

                    commission_rate = config.default_rate if config else Decimal("12.00")
                    commission_amount = (sale.total_amount * commission_rate / Decimal("100.00")).quantize(
                        Decimal("0.01")
                    )

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
            request, f"✅ Sale completed: {batch.merch_product.name} x{qty} for MWK {sale.total_amount:,.2f}"
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
    batches = (
        PharmacyBatch.objects.filter(business=business, is_archived=False, quantity__gt=0, expiry_date__gte=today)
        .select_related("merch_product")
        .order_by("expiry_date", "merch_product__name")
    )

    # Prepare batch data for template
    batch_data = []
    for batch in batches:
        # Get category display name
        category_code = batch.merch_product.category or "general"
        category_display = dict(PharmacyCategory.choices).get(category_code, "General")

        batch_data.append(
            {
                "id": batch.id,
                "product_name": batch.merch_product.name,
                "category": category_display,
                "batch_number": batch.batch_number,
                "quantity": batch.quantity,
                "price": float(batch.selling_price),
                "cost": float(batch.cost_price),
                "expiry_date": str(batch.expiry_date),
                "days_to_expiry": batch.days_to_expiry,
            }
        )

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
            messages.error(request, f"Insufficient stock. Requested {quantity}, available {batch.quantity}.")
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

        # Gamified success message
        messages.success(
            request,
            f"🟢 Sale recorded 🎉\n"
            f"Stock updated · Revenue added · Well done!\n"
            f"{batch.merch_product.name} x{quantity} | Total: MWK {sale.total_amount:,.2f}",
        )
        return redirect("inventory:pharmacy_dashboard")

    # GET: show form
    # Only show batches with stock, not expired
    today = timezone.now().date()
    batches = (
        PharmacyBatch.objects.filter(business=business, is_archived=False, quantity__gt=0, expiry_date__gte=today)
        .select_related("merch_product")
        .order_by("expiry_date", "merch_product__name")
    )

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
    sales = PharmacySale.objects.filter(business=business).select_related("batch__merch_product", "sold_by")

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

    batches = (
        PharmacyBatch.objects.filter(
            business=business,
            is_archived=False,
            quantity__gt=0,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=days),
        )
        .select_related("merch_product")
        .order_by("expiry_date")
    )

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
    batches = (
        PharmacyBatch.objects.filter(business=business, expiry_date__lt=today, quantity__gt=0)  # Still have stock
        .select_related("merch_product")
        .order_by("expiry_date")
    )

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

    batches = (
        PharmacyBatch.objects.filter(business=business, is_archived=False, quantity__lte=F("reorder_level"))
        .select_related("merch_product")
        .order_by("quantity")
    )

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

    return JsonResponse(
        {
            "id": batch.id,
            "product_name": batch.merch_product.name,
            "batch_number": batch.batch_number,
            "expiry_date": str(batch.expiry_date),
            "quantity": batch.quantity,
            "selling_price": float(batch.selling_price),
            "cost_price": float(batch.cost_price),
            "is_expired": batch.is_expired,
            "days_to_expiry": batch.days_to_expiry,
        }
    )


# ==============================================================================
# MANAGER TOOLS: EDIT, DELETE, UNDO
# ==============================================================================


def _is_manager(request, business) -> bool:
    """Check if user is a manager for this business."""
    try:
        from tenants.models import Membership

        return Membership.objects.filter(
            business=business, user=request.user, role__in=["manager", "owner"], status="active"
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
                    messages.error(request, f"Insufficient stock to increase quantity. Available: {batch.quantity}")
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
                    },
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
                agent=request.user,
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
                },
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
                    business=business, user=sale.sold_by, role="agent", status="active"
                ).first()

                if membership:
                    from sales.models import CommissionConfig

                    config = CommissionConfig.objects.filter(business=business, is_active=True).first()

                    commission_rate = config.default_rate if config else Decimal("12.00")
                    commission_amount = (sale.total_amount * commission_rate / Decimal("100.00")).quantize(
                        Decimal("0.01")
                    )

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
                },
            )
        except Exception:
            pass

    messages.success(request, f"Sale #{sale.id} reversed successfully. Stock restored and transactions reversed.")
    return redirect("pharmacy:sale_list")


# ==============================================================================
# SIMPLE UI VIEWS (NEW)
# ==============================================================================


@login_required
@require_business
def pharmacy_stock_in_simple(request: HttpRequest) -> HttpResponse:
    """
    Simple stock-in page with search and top items.
    Mobile-first, uses partials and service layer.
    """
    business: Business = request.business

    # Get top products (most stocked in last 30 days)
    from datetime import timedelta

    thirty_days_ago = timezone.now() - timedelta(days=30)

    top_products = (
        MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True)
        .annotate(
            recent_stock_count=Count("pharmacy_batches", filter=Q(pharmacy_batches__created_at__gte=thirty_days_ago))
        )
        .filter(recent_stock_count__gt=0)
        .order_by("-recent_stock_count")[:8]
    )

    # Handle search
    search_query = request.GET.get("q", "").strip()
    products = []

    if search_query:
        products = MerchProduct.objects.filter(
            business=business, kind="pharmacy", is_active=True, name__icontains=search_query
        ).order_by("name")[:20]

    ctx = {
        "active_business": business,
        "active_location": getattr(request, "location", None),
        "top_products": top_products,
        "products": products,
        "search_query": search_query,
    }

    return render(request, "verticals/pharmacy/stock_in_simple.html", ctx)


@login_required
@require_business
def pharmacy_sell_simple(request: HttpRequest) -> HttpResponse:
    """
    Simple fast sell page with search and top items.
    Mobile-first, uses partials and service layer.
    """
    business: Business = request.business

    # Get top products (most sold in last 30 days)
    from datetime import timedelta

    thirty_days_ago = timezone.now() - timedelta(days=30)

    top_products = (
        MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True)
        .annotate(
            recent_sales_count=Count(
                "pharmacy_batches__sales", filter=Q(pharmacy_batches__sales__sold_at__gte=thirty_days_ago)
            )
        )
        .filter(recent_sales_count__gt=0)
        .order_by("-recent_sales_count")[:8]
    )

    ctx = {
        "active_business": business,
        "active_location": getattr(request, "location", None),
        "top_products": top_products,
    }

    return render(request, "verticals/pharmacy/sell_simple.html", ctx)


# ==============================================================================
# API ENDPOINTS (NEW)
# ==============================================================================


@login_required
@require_business
def api_product_search(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for product search (used by live search).
    Returns JSON with product data including packaging info.
    """
    business: Business = request.business
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse({"products": []})

    products = MerchProduct.objects.filter(
        business=business, kind="pharmacy", is_active=True, name__icontains=query
    ).order_by("name")[:20]

    products_data = []
    for p in products:
        products_data.append(
            {
                "id": p.id,
                "name": p.name,
                "category": getattr(p, "category", None),
                "base_unit_label": getattr(p, "base_unit_label", None) or p.unit or "piece",
                "unit": p.unit,
                "strip_size": getattr(p, "strip_size", None),
                "box_size": getattr(p, "box_size", None),
                "tablets_per_box": getattr(p, "tablets_per_box", None),
                "quantity_in_stock": p.quantity_in_stock,
                "price": float(p.price) if p.price else 0,
            }
        )

    return JsonResponse({"products": products_data})


@login_required
@require_business
def api_products_by_category(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to fetch products filtered by category.
    Used by stock-in custom form to show existing products after category selection.
    Returns JSON with product data (id, name, brand, sku, price, in_stock).
    """
    business: Business = request.business
    category = request.GET.get("category", "").strip()

    if not category:
        return JsonResponse({"error": "Category parameter required"}, status=400)

    # Fetch products for this business + category (limit 40, active only)
    products = (
        MerchProduct.objects.filter(
            business=business,
            kind="pharmacy",
            category=category,
            is_active=True,
        )
        .order_by("name")[:40]
    )

    products_data = []
    for p in products:
        # Calculate total stock from batches
        total_stock = PharmacyBatch.objects.filter(
            business=business,
            merch_product=p,
        ).aggregate(total=Sum("quantity"))["total"] or 0

        products_data.append({
            "id": p.id,
            "name": p.name,
            "brand": getattr(p, "spec_label", "") or "",  # spec_label is used for brand/variant
            "sku": p.sku or "",
            "price": str(p.selling_price) if p.selling_price else "0.00",
            "in_stock": int(total_stock),
        })

    return JsonResponse({"products": products_data})


@login_required
@require_business
@require_POST
def api_stock_in(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for stock-in via the simple UI.
    Uses the service layer (pharmacy_sale.stock_in_pharmacy).
    """
    import json
    from inventory.services.pharmacy_sale import stock_in_pharmacy
    from inventory import pharmacy_config

    business: Business = request.business
    location = getattr(request, "location", None)

    try:
        data = json.loads(request.body)
        product_id = data.get("product_id")
        quantity = int(data.get("quantity", 1))
        unit = data.get("unit", "piece")
        expiry_date_str = data.get("expiry_date")
        batch_number = data.get("batch_number")
        cost_price = data.get("cost_price")
        selling_price = data.get("selling_price")

        if not product_id:
            return JsonResponse({"success": False, "error": "Product ID required"}, status=400)

        product = get_object_or_404(MerchProduct, id=product_id, business=business, kind="pharmacy")

        # Parse expiry date if provided
        expiry_date = None
        if expiry_date_str:
            from datetime import datetime

            try:
                expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Use product's existing prices if not provided
        if not cost_price:
            cost_price = product.cost_price or Decimal("0")
        else:
            cost_price = Decimal(cost_price)

        if not selling_price:
            selling_price = product.selling_price or Decimal("0")
        else:
            selling_price = Decimal(selling_price)

        # Call service layer with correct signature
        result = stock_in_pharmacy(
            business=business,
            product_name=product.name,
            category=product.category or "other",
            user=request.user,
            quantity=quantity,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            expiry_date=expiry_date,
            batch_number=batch_number,
            strip_size=product.strip_size,
            box_size=product.box_size,
            tablets_per_box=product.tablets_per_box,
            location=location,
        )

        # Refresh product to get updated stock
        product.refresh_from_db()

        return JsonResponse(
            {
                "success": True,
                "batch_id": result["batch_id"],
                "new_stock": result["current_batch_stock_base_units"],
                "message": result["message"],
            }
        )

    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Stock-in API error: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Stock-in failed"}, status=500)


@login_required
@require_business
@require_POST
def api_sell(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for selling via the simple UI.
    Uses the service layer (pharmacy_sale.sell_pharmacy).
    """
    import json
    from inventory.services.pharmacy_sale import sell_pharmacy, OutOfStockError

    business: Business = request.business
    location = getattr(request, "location", None)

    try:
        data = json.loads(request.body)
        items = data.get("items", [])
        payment_method = data.get("payment_method", "cash")

        if not items:
            return JsonResponse({"success": False, "error": "No items in cart"}, status=400)

        # Process each item
        sales = []
        for item in items:
            product_id = item.get("productId")
            quantity = int(item.get("quantity", 1))
            unit = item.get("unit", "piece")

            product = get_object_or_404(MerchProduct, id=product_id, business=business, kind="pharmacy")

            # Call service layer with correct signature
            result = sell_pharmacy(
                business=business,
                product_id=product.id,
                user=request.user,
                quantity=quantity,
                unit=unit,
                payment_method=payment_method.upper(),
            )

            sales.append(
                {
                    "product": product.name,
                    "quantity": quantity,
                    "unit": unit,
                    "sold_from_batches": result["sold_from_batches"],
                }
            )

        return JsonResponse({"success": True, "sales": sales, "total_items": len(sales)})

    except OutOfStockError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"Sell API error: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Sale failed"}, status=500)


@login_required
@require_business
@require_POST
def api_add_product_suggestion(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to add a suggested product to the catalog (idempotent).
    
    POST /pharmacy/api/product-suggestions/add/
    Payload:
        - category: Category code (e.g., "medicine", "skin_care")
        - name: Product name
        - brand: Optional brand name
        - unit: Optional unit (e.g., "tabs", "ml")
    
    Returns:
        {
            "ok": true,
            "product_id": 123,
            "created": true/false,
            "name": "Product Name"
        }
    """
    import json
    
    business: Business = request.business
    
    try:
        data = json.loads(request.body)
        category = data.get("category", "").strip()
        name = data.get("name", "").strip()
        brand = data.get("brand", "").strip()
        unit = data.get("unit", "").strip()
        
        # Validation
        if not category:
            return JsonResponse({"ok": False, "error": "Category is required"}, status=400)
        if not name:
            return JsonResponse({"ok": False, "error": "Product name is required"}, status=400)
        
        # Validate category against allowed values
        VALID_CATEGORIES = [
            "medicine", "supplements", "skin_care", "hair_care", "body_care",
            "baby_care", "oral_care", "perfumes", "deodorants", "makeup",
            "soap_hygiene", "first_aid", "other",
        ]
        if category not in VALID_CATEGORIES:
            return JsonResponse({"ok": False, "error": f"Invalid category: {category}"}, status=400)
        
        # Check if product already exists (case-insensitive lookup)
        existing_product = MerchProduct.objects.filter(
            business=business,
            kind="pharmacy",
            category=category,
            name__iexact=name
        ).first()
        
        if existing_product:
            # Product already exists - return it
            return JsonResponse({
                "ok": True,
                "product_id": existing_product.id,
                "created": False,
                "name": existing_product.name,
            })
        
        # Create new product
        with transaction.atomic():
            product = MerchProduct.objects.create(
                business=business,
                name=name,
                kind="pharmacy",
                category=category,
                is_active=True,
                spec_label="",  # Required field
                unit=unit if unit else "piece",
            )
            
            # Optionally store brand info (if you have a brand field or want to use description)
            # For now, we'll just create the basic product
            
        return JsonResponse({
            "ok": True,
            "product_id": product.id,
            "created": True,
            "name": product.name,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Add product suggestion error: {e}", exc_info=True)
        return JsonResponse({"ok": False, "error": "Failed to add product"}, status=500)
