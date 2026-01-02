# inventory/views_pharmacy_enhanced.py
"""
Enhanced pharmacy dashboard with cosmetics support and gamification.
This module extends the base pharmacy views with premium features.
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
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.models import Business
from tenants.utils import require_business

from .models import MerchProduct
from .models_pharmacy import PharmacyBatch, PharmacySale, PharmacyCategory
from .pharmacy_constants import calculate_pharmacy_badges

logger = logging.getLogger(__name__)


@login_required
@require_business
def pharmacy_dashboard_enhanced(request: HttpRequest) -> HttpResponse:
    """
    Premium pharmacy dashboard with:
    - Date-filtered metrics
    - Cosmetics tracking
    - Gamification badges
    - Unified cost calculation (COGS + Admin Wallet)
    """
    business: Business = request.business
    today = timezone.now().date()

    # ===== DATE FILTERING =====
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
        from datetime import datetime

        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            period_label = f"{start_date} to {end_date}"
        except (ValueError, TypeError):
            start_date = end_date = today
            period_label = "Today"
            range_param = "today"

    # ===== CURRENT STOCK METRICS (not time-filtered) =====
    batches = PharmacyBatch.objects.filter(business=business, is_archived=False).select_related("merch_product")

    total_batches = batches.count()
    total_stock_value = sum(b.stock_value_selling for b in batches)

    # Alerts (current state)
    near_expiry_count = sum(1 for b in batches if b.days_to_expiry <= 30 and not b.is_expired)
    expired_count = sum(1 for b in batches if b.is_expired)
    low_stock_count = sum(1 for b in batches if b.is_low_stock)

    # Products count
    total_products = MerchProduct.objects.filter(business=business, kind="pharmacy", is_active=True).count()

    # ===== PERIOD-FILTERED SALES METRICS =====
    sales_qs = PharmacySale.objects.filter(
        business=business, sale_date__gte=start_date, sale_date__lte=end_date, is_reversed=False
    ).select_related("batch", "batch__merch_product")

    period_sales_count = sales_qs.count()

    # Calculate revenue, COGS, and profit
    period_revenue = Decimal("0.00")
    period_cogs = Decimal("0.00")

    for sale in sales_qs:
        period_revenue += sale.total_amount
        period_cogs += sale.cost_of_goods_sold

    # Get admin wallet costs for this period (if available)
    period_admin_costs = _get_admin_wallet_costs(business, start_date, end_date)
    period_costs = period_cogs + period_admin_costs
    period_profit = period_revenue - period_costs

    # ===== COSMETICS TRACKING =====
    cosmetics_categories = [
        PharmacyCategory.SKIN_CARE,
        PharmacyCategory.BODY_CARE,
        PharmacyCategory.HAIR_CARE,
        PharmacyCategory.PERFUME,
        PharmacyCategory.PERSONAL_CARE,
    ]

    # Cosmetics sales for period
    cosmetics_sales = sales_qs.filter(batch__merch_product__category__in=cosmetics_categories)

    cosmetics_revenue = sum(s.total_amount for s in cosmetics_sales)
    cosmetics_revenue_pct = (cosmetics_revenue / period_revenue * 100) if period_revenue > 0 else 0

    # Cosmetics products in stock
    cosmetics_products = MerchProduct.objects.filter(
        business=business, kind="pharmacy", category__in=cosmetics_categories, is_active=True
    ).count()

    # Top cosmetics brands (approximate - using product names)
    top_cosmetics_brands = _get_top_cosmetics_brands(cosmetics_sales)

    # ===== GAMIFICATION BADGES =====
    all_batches_fresh = all(b.days_to_expiry > 30 for b in batches)

    pharmacy_data = {
        "near_expiry_count": near_expiry_count,
        "cosmetics_revenue_pct": cosmetics_revenue_pct,
        "batches_count": total_batches,
        "all_batches_fresh": all_batches_fresh,
    }

    badges = calculate_pharmacy_badges(pharmacy_data)

    # ===== TEMPLATE CONTEXT =====
    context = {
        # Period
        "range_param": range_param,
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        # Current stock metrics
        "total_batches": total_batches,
        "total_stock_value": total_stock_value,
        "total_products": total_products,
        # Period metrics
        "period_revenue": period_revenue,
        "period_costs": period_costs,
        "period_cogs": period_cogs,
        "period_admin_costs": period_admin_costs,
        "period_profit": period_profit,
        "period_sales_count": period_sales_count,
        # Alerts
        "near_expiry_count": near_expiry_count,
        "expired_count": expired_count,
        "low_stock_count": low_stock_count,
        # Cosmetics
        "cosmetics_revenue": cosmetics_revenue,
        "cosmetics_revenue_pct": cosmetics_revenue_pct,
        "cosmetics_products": cosmetics_products,
        "top_cosmetics_brands": top_cosmetics_brands,
        # Gamification
        "badges": badges,
    }

    return render(request, "verticals/pharmacy/dashboard.html", context)


def _get_admin_wallet_costs(business: Business, start_date, end_date) -> Decimal:
    """
    Get admin wallet costs for the period.
    Reuses existing wallet transaction logic if available.
    """
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        from wallet.utils_costs import ensure_monthly_recurring_costs
        from django.db.models import Sum

        # Ensure recurring costs are auto-created for current month (idempotent)
        try:
            from datetime import date

            today = timezone.now().date()
            month_start = date(today.year, today.month, 1)
            ensure_monthly_recurring_costs(business, month_start)
        except Exception as e:
            logger.warning(f"Could not auto-create recurring costs: {e}")

        # Get admin costs (both once-off and recurring instances) for the period
        admin_costs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
            effective_date__gte=start_date,
            effective_date__lte=end_date,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        return abs(admin_costs)  # Expenses are stored as negative, return positive
    except ImportError:
        # Wallet app not available
        return Decimal("0.00")
    except Exception as e:
        logger.warning(f"Could not fetch admin wallet costs: {e}")
        return Decimal("0.00")


def _get_top_cosmetics_brands(cosmetics_sales) -> list[dict]:
    """
    Extract top cosmetics brands from sales.
    Simple heuristic: look for known brand names in product names.
    """
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
    top_brands = sorted(
        [{"name": brand, "revenue": rev} for brand, rev in brand_revenue.items()],
        key=lambda x: x["revenue"],
        reverse=True,
    )[:5]

    return top_brands
