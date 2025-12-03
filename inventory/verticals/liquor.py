from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, OuterRef, Subquery
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import (
    LiquorSale, LiquorCredit, PaymentMethod, LiquorShiftStock, MonthlySalesTarget
)
from inventory.models import MerchProduct

from . import base

# Import Subscription model for safe access
try:
    from tenants.models import Subscription
except ImportError:
    Subscription = None

# Import wallet models for admin cost aggregation
try:
    from wallet.models import WalletTransaction, Ledger, TxnType
except ImportError:
    WalletTransaction = None
    Ledger = None
    TxnType = None


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def dashboard(request):
    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")
    
    if location is None:
        location = getattr(request, "location", None)
    
    # Basic product metrics
    metrics = base.merch_metrics(business, BusinessKind.LIQUOR)
    shots_enabled = base.merch_queryset(business, BusinessKind.LIQUOR).filter(has_shots=True).count()
    
    # Date range for financial KPIs (default: last 30 days)
    now = timezone.now()
    days_back = int(request.GET.get("days", 30))
    start_date = now - timedelta(days=days_back)
    
    # Financial KPIs
    sales_qs = LiquorSale.objects.filter(
        business=business,
        sold_at__gte=start_date
    )
    
    # Revenue (exclude free sales)
    revenue = sales_qs.exclude(is_free=True).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    
    # Inventory costs (cost of goods sold)
    inventory_costs = sales_qs.aggregate(total=Sum("total_cost"))["total"] or Decimal("0.00")
    
    # Admin costs from wallet (if available)
    admin_costs_period = Decimal("0.00")
    if WalletTransaction and Ledger and TxnType:
        try:
            admin_qs = WalletTransaction.objects.filter(
                ledger=Ledger.COMPANY,
                business=business,
                type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
            )
            
            # Fixed monthly costs (sum of all recurring)
            fixed_monthly = admin_qs.filter(is_recurring=True).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
            fixed_monthly = abs(fixed_monthly)  # Costs stored as negative
            
            # Once-off costs in the period
            once_off_period = admin_qs.filter(
                is_recurring=False,
                created_at__gte=start_date,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            once_off_period = abs(once_off_period)
            
            admin_costs_period = fixed_monthly + once_off_period
        except Exception:
            # If there's any error accessing wallet models, just use 0
            admin_costs_period = Decimal("0.00")
    
    # Total costs and net profit
    total_costs = inventory_costs + admin_costs_period
    net_profit = revenue - total_costs
    
    # Keep old variables for backward compatibility
    costs = inventory_costs
    profit = revenue - costs
    
    # Payment mix (counts and amounts) - including credit sales
    total_revenue = revenue  # for percentage calculation
    payment_mix = []
    credit_sales_amount = Decimal("0.00")
    
    # Cash and other payment methods
    for method_code, method_label in PaymentMethod.choices:
        method_sales = sales_qs.filter(payment_method=method_code, is_free=False, is_credit=False)
        count = method_sales.count()
        amount = method_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
        if count > 0:
            pct = int((amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
            payment_mix.append({
                "method": method_label,
                "count": count,
                "amount": amount,
                "percent": pct,
            })
    
    # Credit sales (separate category)
    credit_sales = sales_qs.filter(is_credit=True, is_free=False)
    credit_count = credit_sales.count()
    credit_sales_amount = credit_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    if credit_count > 0:
        credit_pct = int((credit_sales_amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
        payment_mix.append({
            "method": "Credit",
            "count": credit_count,
            "amount": credit_sales_amount,
            "percent": credit_pct,
        })
    
    # Calculate credit ratio and warning
    credit_ratio = int((credit_sales_amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
    credit_warning = credit_ratio > 10
    
    # Get open credits for ticker
    open_credits = (
        LiquorCredit.objects.filter(business=business, status="open")
        .order_by("-created_at")[:20]
    )
    
    # Stock metrics
    liquor_products = MerchProduct.objects.filter(
        business=business,
        kind=BusinessKind.LIQUOR,
        is_active=True
    )
    
    # Count distinct product SKUs
    total_bottle_skus = liquor_products.count()
    
    # Total bottles in stock
    # Stock is tracked in LiquorShiftStock snapshots with bottles_count field
    # Get the most recent closing (or opening) snapshot for each product
    latest_snapshots = LiquorShiftStock.objects.filter(
        product=OuterRef('pk'),
        shift__business=business
    ).order_by('-recorded_at')
    
    # Get products with their latest stock count
    products_with_stock = liquor_products.filter(
        track_inventory=True
    ).annotate(
        latest_bottles=Subquery(
            latest_snapshots.values('bottles_count')[:1]
        )
    )
    
    # Sum up all the bottle counts (using 0 for products with no snapshots)
    total_bottles_in_stock = 0
    for product in products_with_stock:
        if product.latest_bottles is not None:
            total_bottles_in_stock += product.latest_bottles
    
    # Days of cover estimate (current stock / average daily bottle sales)
    # LiquorSale model has a 'quantity' field for bottles sold
    avg_daily_bottles_sold = 0
    total_bottles_sold = sales_qs.filter(unit="bottle").aggregate(total=Sum("quantity"))["total"] or 0
    if days_back > 0 and total_bottles_sold > 0:
        avg_daily_bottles_sold = total_bottles_sold / days_back
    
    days_of_cover = 0
    if avg_daily_bottles_sold > 0 and total_bottles_in_stock > 0:
        days_of_cover = int(total_bottles_in_stock / avg_daily_bottles_sold)
    
    # Safely get subscription (may not exist)
    subscription = None
    if business and Subscription:
        try:
            subscription = business.subscription
        except Subscription.DoesNotExist:
            subscription = None
        except AttributeError:
            subscription = None
    
    # Safely get membership (may not exist)
    membership = getattr(request, "membership", None)
    
    # ========== GOAL 5: Monthly Sales Target (Stock-Aware) ==========
    # Get current year/month
    year = now.year
    month = now.month
    
    # Fetch or create monthly target for this liquor business/location
    target_obj, _ = MonthlySalesTarget.objects.get_or_create(
        business=business,
        location=location,
        vertical="liquor",
        year=year,
        month=month,
        defaults={
            "target_units": 0,
            "target_revenue": Decimal("0.00"),
        },
    )
    
    # Compute actual units sold in current calendar month
    # Use first day of month to now
    from datetime import datetime
    month_start = datetime(year, month, 1)
    month_start = timezone.make_aware(month_start) if timezone.is_naive(month_start) else month_start
    
    month_sales_qs = LiquorSale.objects.filter(
        business=business,
        sold_at__gte=month_start,
        sold_at__lte=now,
    )
    if location:
        # If product has location, filter by it (though LiquorSale doesn't have location FK directly)
        # For now, just count all sales for this business in the month
        pass
    
    # Count bottles sold (primary unit for liquor)
    actual_units_month = month_sales_qs.filter(unit="bottle").aggregate(
        total=Sum("quantity")
    )["total"] or 0
    
    # Stock awareness: Check if target is realistic given current stock
    total_stock_units = total_bottles_in_stock  # Already computed above
    stock_warning = False
    stock_warning_message = ""
    
    if target_obj.target_units > 0 and target_obj.target_units > total_stock_units:
        stock_warning = True
        stock_warning_message = (
            f"Your target ({target_obj.target_units} bottles) is higher than current stock "
            f"({total_stock_units} bottles). Consider increasing stock or adjusting the target."
        )
    
    # Compute progress and remaining units
    target_units = target_obj.target_units
    progress_pct = 0
    remaining_units = 0
    
    if target_units > 0:
        progress_pct = min(100, int((actual_units_month / target_units) * 100))
        remaining_units = max(0, target_units - actual_units_month)
    
    # Inspirational message
    target_message = ""
    if target_units == 0:
        target_message = "Set this month's target in the Stock page to stay motivated."
    elif remaining_units == 0:
        target_message = "🎉 You hit this month's target. Great work!"
    elif remaining_units <= 5:
        sale_word = "sale" if remaining_units == 1 else "sales"
        target_message = f"You're {remaining_units} {sale_word} away from this month's target. 💪"
    else:
        sale_word = "sale" if remaining_units == 1 else "sales"
        target_message = f"Keep going – {remaining_units} {sale_word} left to reach your monthly target."

    ctx.update(
        {
            "hero_title": "Liquor & Bar",
            "hero_blurb": "Monitor bottle counts, shot packs, and wallet balances in one place.",
            
            # Basic product metrics
            "product_count": metrics["total"],
            "active_product_count": metrics["active"],
            "scan_required_count": metrics["scan_required"],
            "inventory_tracked_count": metrics["inventory_tracked"],
            "shots_enabled_count": shots_enabled,
            "recent_products": metrics["recent"],
            
            # Financial KPIs (enhanced with admin costs)
            "period_days": days_back,
            "revenue": revenue,
            "costs": costs,  # Legacy: inventory costs only
            "profit": profit,  # Legacy: revenue - inventory costs
            "inventory_costs": inventory_costs,  # New: explicit inventory costs
            "admin_costs": admin_costs_period,  # New: admin/operational costs
            "total_costs": total_costs,  # New: inventory + admin
            "net_profit": net_profit,  # New: revenue - total costs
            "payment_mix": payment_mix,
            "credit_ratio": credit_ratio,
            "credit_warning": credit_warning,
            
            # Credit tracking
            "open_credits": open_credits,
            
            # Stock KPIs
            "total_bottle_skus": total_bottle_skus,
            "total_bottles_in_stock": total_bottles_in_stock,
            "days_of_cover": days_of_cover,
            
            # Safe subscription & membership
            "subscription": subscription,
            "membership": membership,
            
            # Monthly sales target (Goal 5)
            "sales_target": target_obj,
            "actual_units_month": actual_units_month,
            "target_units": target_units,
            "progress_pct": progress_pct,
            "remaining_units": remaining_units,
            "stock_warning": stock_warning,
            "stock_warning_message": stock_warning_message,
            "total_stock_units": total_stock_units,
            "target_message": target_message,
            "current_year": year,
            "current_month": month,
            
            # UI flags
            "show_search": False,  # Liquor dashboard doesn't need search bar
            "active_tab": "home",  # For base.html mobile nav highlighting
        }
    )
    return render(request, "verticals/liquor/dashboard.html", ctx)
