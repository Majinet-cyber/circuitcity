from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, OuterRef, Subquery
from django.shortcuts import render, redirect
from django.utils import timezone

from tenants.utils import require_business

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_verticals import (
    LiquorSale,
    LiquorCredit,
    LiquorCreditStatus,
    PaymentMethod,
    LiquorShiftStock,
    MonthlySalesTarget,
)
from inventory.models import MerchProduct
from inventory.liquor_seed import create_default_liquor_catalog, should_seed_liquor_products

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

    # Auto-seed liquor products if this is a new liquor business with no products
    if should_seed_liquor_products(business):
        try:
            create_default_liquor_catalog(business, location)
        except Exception:
            # Silently fail if seeding doesn't work - don't break the dashboard
            pass

    # Basic product metrics
    metrics = base.merch_metrics(business, BusinessKind.LIQUOR)
    shots_enabled = base.merch_queryset(business, BusinessKind.LIQUOR).filter(has_shots=True).count()

    # Date range for financial KPIs (default: last 30 days)
    now = timezone.now()
    days_back = int(request.GET.get("days", 30))
    start_date = now - timedelta(days=days_back)

    # Financial KPIs
    sales_qs = LiquorSale.objects.filter(business=business, sold_at__gte=start_date)

    # Revenue (exclude free sales AND outstanding credit sales)
    # Credit sales only count as revenue when the credit is SETTLED (cleared/paid)
    revenue = sales_qs.exclude(is_free=True).exclude(is_credit=True).aggregate(total=Sum("total_price"))[
        "total"
    ] or Decimal("0.00")

    # Add settled credit revenue (credits that have been cleared/paid)
    settled_credits_revenue = LiquorCredit.objects.filter(
        business=business, status=LiquorCreditStatus.SETTLED, settled_at__gte=start_date
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    revenue += settled_credits_revenue

    # Inventory costs (cost of goods sold - exclude outstanding credits)
    inventory_costs = sales_qs.exclude(is_credit=True).aggregate(total=Sum("total_cost"))["total"] or Decimal("0.00")

    # Add costs from settled credits
    settled_credits_cost = LiquorCredit.objects.filter(
        business=business, status=LiquorCreditStatus.SETTLED, settled_at__gte=start_date, related_sale__isnull=False
    ).aggregate(total=Sum("related_sale__total_cost"))["total"] or Decimal("0.00")
    inventory_costs += settled_credits_cost

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
            fixed_monthly = admin_qs.filter(is_recurring=True).aggregate(total=Sum("amount"))["total"] or Decimal(
                "0.00"
            )
            fixed_monthly = abs(fixed_monthly)  # Costs stored as negative

            # Once-off costs in the period
            once_off_period = admin_qs.filter(
                is_recurring=False,
                created_at__gte=start_date,
            ).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
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
    # NEW: Beautiful format matching clothing dashboard
    total_revenue = revenue  # for percentage calculation
    payment_mix = []
    payment_mix_old = []  # Keep old format for backward compatibility
    credit_sales_amount = Decimal("0.00")

    # Cash and other payment methods
    for method_code, method_label in PaymentMethod.choices:
        method_sales = sales_qs.filter(payment_method=method_code, is_free=False, is_credit=False)
        count = method_sales.count()
        amount = method_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
        if count > 0:
            pct = int((amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
            # New format for beautiful UI
            payment_mix.append(
                {
                    "method": method_label,
                    "method_code": method_code.lower(),
                    "count": count,
                    "amount": float(amount),
                    "percentage": pct,
                }
            )
            # Old format for backward compatibility
            payment_mix_old.append(
                {
                    "method": method_label,
                    "count": count,
                    "amount": amount,
                    "percent": pct,
                }
            )

    # Credit sales (separate category)
    credit_sales = sales_qs.filter(is_credit=True, is_free=False)
    credit_count = credit_sales.count()
    credit_sales_amount = credit_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    if credit_count > 0:
        credit_pct = int((credit_sales_amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
        # New format
        payment_mix.append(
            {
                "method": "Credit",
                "method_code": "credit",
                "count": credit_count,
                "amount": float(credit_sales_amount),
                "percentage": credit_pct,
            }
        )
        # Old format
        payment_mix_old.append(
            {
                "method": "Credit",
                "count": credit_count,
                "amount": credit_sales_amount,
                "percent": credit_pct,
            }
        )

    # Calculate credit ratio and warning
    credit_ratio = int((credit_sales_amount / total_revenue * 100).quantize(Decimal("1"))) if total_revenue else 0
    credit_warning = credit_ratio > 10

    # Get open credits for ticker
    open_credits = (
        LiquorCredit.objects.filter(business=business)
        .exclude(status=LiquorCreditStatus.SETTLED)
        .exclude(status=LiquorCreditStatus.CANCELLED)
        .order_by("-created_at")[:20]
    )

    # Stock metrics
    liquor_products = MerchProduct.objects.filter(business=business, kind=BusinessKind.LIQUOR, is_active=True)

    # Count distinct product SKUs
    total_bottle_skus = liquor_products.count()

    # Total bottles in stock
    # Stock is tracked in LiquorShiftStock snapshots with bottles_count field
    # Get the most recent closing (or opening) snapshot for each product
    latest_snapshots = LiquorShiftStock.objects.filter(product=OuterRef("pk"), shift__business=business).order_by(
        "-recorded_at"
    )

    # Get products with their latest stock count
    products_with_stock = liquor_products.filter(track_inventory=True).annotate(
        latest_bottles=Subquery(latest_snapshots.values("bottles_count")[:1])
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
    actual_units_month = month_sales_qs.filter(unit="bottle").aggregate(total=Sum("quantity"))["total"] or 0

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

    # Prepare context for normalization (will be applied at the end)
    ctx_enhancements = {}

    # ===== NEW: Personalized dashboard enhancements (quotes & greetings) =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_quotes import get_todays_quotes
        import json as json_lib

        # Personalized greeting (changes 3x daily: morning, afternoon, evening)
        greeting_ctx = get_personalized_greeting(request.user, business)

        # Brand header context
        brand_logo_url = None
        if business and hasattr(business, "logo") and business.logo:
            brand_logo_url = business.logo.url

        # Hourly quotes (rotates every hour)
        daily_quotes = get_todays_quotes(request.user, count=10)

        # Extract quote texts for JavaScript rotation
        quote_texts = [q.get("text", "") for q in daily_quotes.get("quotes", []) if q.get("text")]
        quotes_json = json_lib.dumps(quote_texts)

        ctx_enhancements.update(
            {
                "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
                "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
                "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
                "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
                "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
                "DASHBOARD_BRAND_TITLE": business.name if business else "Liquor Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    # ========== Rotating Dashboard Insights (Goal 3) ==========
    # Compute fast-moving products, locations, agents, and payment mix for chart rotation
    insights_window = timedelta(days=30)
    insights_start = now - insights_window

    # Fast products (top 5 by quantity sold)
    fast_products_data = (
        LiquorSale.objects.filter(business=business, sold_at__gte=insights_start)
        .values("product__name")
        .annotate(qty=Sum("quantity"))
        .order_by("-qty")[:5]
    )
    fast_products_json = json.dumps(
        [{"label": item["product__name"] or "Unknown", "value": int(item["qty"])} for item in fast_products_data]
    )

    # Fast locations (top 5 by revenue)
    fast_locations_data = []
    if location:
        # If we have location tracking, aggregate by location
        try:
            from inventory.models import Location

            fast_locations_data = (
                LiquorSale.objects.filter(business=business, sold_at__gte=insights_start, shift__location__isnull=False)
                .values("shift__location__name")
                .annotate(revenue=Sum("total_price"))
                .order_by("-revenue")[:5]
            )
            fast_locations_json = json.dumps(
                [
                    {"label": item["shift__location__name"] or "Unknown", "value": float(item["revenue"])}
                    for item in fast_locations_data
                ]
            )
        except Exception:
            fast_locations_json = json.dumps([])
    else:
        fast_locations_json = json.dumps([])

    # Fast agents (top 5 by revenue)
    fast_agents_data = (
        LiquorSale.objects.filter(business=business, sold_at__gte=insights_start, sold_by__isnull=False)
        .values("sold_by__username", "sold_by__first_name", "sold_by__last_name")
        .annotate(revenue=Sum("total_price"))
        .order_by("-revenue")[:5]
    )
    fast_agents_json = json.dumps(
        [
            {
                "label": (
                    f"{item['sold_by__first_name']} {item['sold_by__last_name']}".strip()
                    or item["sold_by__username"]
                    or "Unknown"
                ),
                "value": float(item["revenue"]),
            }
            for item in fast_agents_data
        ]
    )

    # Payment mix (aggregate by payment method)
    payment_mix_data = (
        LiquorSale.objects.filter(business=business, sold_at__gte=insights_start, is_free=False)
        .values("payment_method")
        .annotate(total=Sum("total_price"))
        .order_by("-total")
    )
    payment_mix_json = json.dumps(
        [
            {
                "label": dict(PaymentMethod.choices).get(item["payment_method"], item["payment_method"]),
                "value": float(item["total"]),
            }
            for item in payment_mix_data
        ]
    )

    # ========== NEW: Barman Attribution Alerts ==========
    # For agents: show count of pending attributions assigned to them
    # For managers/barmen: show count of all pending attributions
    from sales.models import LiquorSaleAttribution
    from core.context import _extract_roles_for

    roles = _extract_roles_for(request.user, business)
    is_barman = request.user.groups.filter(name=f"biz:{business.pk}:LIQUOR_BARMAN").exists()

    pending_attributions_count = 0
    reconciled_today_count = 0
    attributed_sales_total = Decimal("0.00")

    # Define today_start for attribution queries
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now

    if roles.is_agent and not roles.is_manager:
        # Agent view: Show attributions assigned to them
        agent_attributions = LiquorSaleAttribution.objects.filter(business=business, attributed_to=request.user)

        pending_attributions_count = agent_attributions.filter(status=LiquorSaleAttribution.STATUS_PENDING).count()

        reconciled_today_count = agent_attributions.filter(
            status=LiquorSaleAttribution.STATUS_RECONCILED, reconciled_at__gte=today_start
        ).count()

        attributed_sales_total = agent_attributions.filter(
            created_at__gte=start_date, created_at__lt=end_date
        ).aggregate(total=Sum("sale_amount"))["total"] or Decimal("0.00")

    elif roles.is_manager or is_barman:
        # Manager/Barman view: Show all pending attributions
        all_attributions = LiquorSaleAttribution.objects.filter(business=business)

        pending_attributions_count = all_attributions.filter(status=LiquorSaleAttribution.STATUS_PENDING).count()

        reconciled_today_count = all_attributions.filter(
            status=LiquorSaleAttribution.STATUS_RECONCILED, reconciled_at__gte=today_start
        ).count()

    # Check if agent records are balanced (no pending attributions)
    records_balanced = pending_attributions_count == 0

    ctx.update(
        {
            "hero_title": "Liquor & Bar",
            "hero_blurb": "Monitor bottle counts, shot packs, and wallet balances in one place.",
            # Barman Attribution Alerts
            "pending_attributions_count": pending_attributions_count,
            "reconciled_today_count": reconciled_today_count,
            "records_balanced": records_balanced,
            "attributed_sales_total": attributed_sales_total,
            "is_barman": is_barman,
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
            "payment_mix_period": f"Last {days_back} days" if days_back > 1 else "Today",
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
            # Rotating insights data (Goal 3)
            "fast_products_json": fast_products_json,
            "fast_locations_json": fast_locations_json,
            "fast_agents_json": fast_agents_json,
            "payment_mix_json": payment_mix_json,
            **ctx_enhancements,  # Merge dashboard enhancements
        }
    )

    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context

    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "verticals/liquor/dashboard.html", ctx)


# ==============================================================================
# SALES HISTORY, EXPORT, AND TREND API
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sales_history(request):
    """
    Sales History page for liquor with filters, pagination, and export.
    Shows all liquor sales with date range filtering and search.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Build base queryset
    sales_qs = LiquorSale.objects.filter(business=business).select_related("product", "sold_by")

    # Location filtering
    if location and hasattr(LiquorSale, "location"):
        sales_qs = sales_qs.filter(location=location)

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

    # Apply search filter (product name, notes, cashier)
    if search_query:
        sales_qs = sales_qs.filter(
            Q(product__name__icontains=search_query)
            | Q(product__category__icontains=search_query)
            | Q(notes__icontains=search_query)
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
        total_revenue=Sum("total_price"),
        total_cost=Sum("total_cost"),
        total_sales=Count("id"),
        total_items=Sum("quantity"),
    )

    ctx.update(
        {
            "sales": sales_page,
            "start_date": start_date,
            "end_date": end_date,
            "search_query": search_query,
            "highlighted_sale_id": highlighted_sale_id,
            "summary": summary,
            "page_title": "Sales History",
        }
    )

    return render(request, "verticals/liquor/sales_history.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sales_export_csv(request):
    """
    Export filtered liquor sales to CSV.
    Respects all the same filters as sales_history view.
    """
    import csv
    from django.http import HttpResponse

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Build queryset with same filters as sales_history
    sales_qs = LiquorSale.objects.filter(business=business).select_related("product", "sold_by")

    if location and hasattr(LiquorSale, "location"):
        sales_qs = sales_qs.filter(location=location)

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
            Q(product__name__icontains=search_query)
            | Q(product__category__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(sold_by__username__icontains=search_query)
        )

    sales_qs = sales_qs.order_by("-sold_at")

    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="liquor_sales_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow(
        [
            "Timestamp",
            "Date",
            "Time",
            "Sale ID",
            "Item",
            "Category",
            "Unit",
            "Qty",
            "Unit Price",
            "Total",
            "Sale Type",
            "Payment Method",
            "Cashier",
            "Notes",
        ]
    )

    # Write data rows
    for sale in sales_qs:
        product = sale.product
        local_timestamp = timezone.localtime(sale.sold_at)

        writer.writerow(
            [
                local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                local_timestamp.strftime("%Y-%m-%d"),
                local_timestamp.strftime("%H:%M:%S"),
                sale.id,
                product.name or "",
                getattr(product, "category", "") or "",
                sale.get_unit_display() if hasattr(sale, "get_unit_display") else sale.unit,
                sale.quantity,
                f"{sale.unit_price:.2f}",
                f"{sale.total_price:.2f}",
                sale.get_sale_type_display() if hasattr(sale, "get_sale_type_display") else sale.sale_type,
                sale.get_payment_method_display()
                if hasattr(sale, "get_payment_method_display")
                else sale.payment_method,
                sale.sold_by.username if sale.sold_by else "System",
                sale.notes or "",
            ]
        )

    return response


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def fast_sell(request):
    """
    Fast Sell page for liquor - barcode scanner + instant sell.
    Uses front camera for barcode scanning with BarcodeDetector API fallback.

    BARMAN SUPPORT: If user is a barman, they can assign sales to agents.
    """
    from django.http import JsonResponse
    from django.contrib.auth import get_user_model
    from core.context import _extract_roles_for

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Check if user is barman
    User = get_user_model()
    is_barman = request.user.groups.filter(name=f"biz:{business.pk}:LIQUOR_BARMAN").exists()

    # Get list of liquor agents (for barman to assign sales)
    liquor_agents = []
    if is_barman:
        # Get all users who have AGENT role for this business
        agent_group_name = f"biz:{business.pk}:AGENT"
        liquor_agents = (
            User.objects.filter(groups__name=agent_group_name)
            .values("id", "first_name", "last_name", "username")
            .distinct()
        )

    ctx.update(
        {
            "page_title": "Fast Sell",
            "vertical": "liquor",
            "vertical_name": "Liquor",
            "is_barman": is_barman,
            "liquor_agents": list(liquor_agents),
        }
    )

    return render(request, "verticals/liquor/fast_sell.html", ctx)


@login_required
def fast_sell_page(request):
    """
    Fast Sell page for liquor - gated by authentication, business, and vertical.
    Uses login_required as outermost decorator so unauthenticated users get 302 redirect.
    """
    from django.http import HttpResponseForbidden
    from django.shortcuts import redirect
    from django.urls import reverse
    from tenants.models import Business

    # 1) Must have active business (middleware OR session)
    business = getattr(request, "active_business", None)

    if business is None:
        bid = request.session.get("active_business_id")
        if not bid:
            return redirect(reverse("tenants:choose_business"))
        business = Business.objects.filter(id=bid).first()
        if business is None:
            return redirect(reverse("tenants:choose_business"))

    # 2) Must be liquor vertical
    if getattr(business, "business_kind", None) != BusinessKind.LIQUOR:
        return HttpResponseForbidden("Wrong business vertical.")

    # Use base_context to provide required context for template
    ctx = base.base_context(request)

    # Check if user is barman
    is_barman = False
    liquor_agents = []
    from django.contrib.auth import get_user_model

    User = get_user_model()
    is_barman = request.user.groups.filter(name=f"biz:{business.pk}:LIQUOR_BARMAN").exists()

    # Get list of liquor agents (for barman to assign sales)
    if is_barman:
        agent_group_name = f"biz:{business.pk}:AGENT"
        liquor_agents = (
            User.objects.filter(groups__name=agent_group_name)
            .values("id", "first_name", "last_name", "username")
            .distinct()
        )

    ctx.update(
        {
            "page_title": "Fast Sell",
            "vertical": "liquor",
            "vertical_name": "Liquor",
            "lookup_url_name": "verticals:liquor_fast_sell_lookup",
            "sell_url_name": "verticals:liquor_fast_sell_sell",
            "is_barman": is_barman,
            "liquor_agents": list(liquor_agents),
            "active_tab": "fast_sell",  # Template may use this
        }
    )
    return render(request, "verticals/liquor/fast_sell.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def barman_invite(request):
    """
    Invite a new barman (bartender/agent) or bar manager to the liquor business.
    Manager-only feature.
    """
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.contrib.auth import get_user_model
    from django import forms
    from tenants.utils_people import attach_user_to_business
    from tenants.services.invites import create_agent_invite
    from core.context import _extract_roles_for

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Check if user is manager (full manager, not bar manager)
    roles = _extract_roles_for(request.user, business)
    if not roles.is_manager or roles.is_bar_manager:
        # Bar managers cannot invite - only full managers
        messages.error(request, "Only full managers can invite team members")
        return redirect("verticals:liquor_dashboard")

    class BarmanInviteForm(forms.Form):
        username = forms.CharField(max_length=150, help_text="Unique username for login")
        email = forms.EmailField(required=False)
        first_name = forms.CharField(max_length=150, required=False)
        last_name = forms.CharField(max_length=150, required=False)
        password = forms.CharField(widget=forms.PasswordInput, min_length=6)
        role = forms.ChoiceField(
            choices=[
                ("AGENT", "Bartender/Agent"),
                ("BAR_MANAGER", "Bar Manager"),
            ],
            initial="AGENT",
            help_text="Bar Manager can manage bartenders and oversee operations, but cannot delete/archive",
        )

    if request.method == "POST":
        form = BarmanInviteForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            role = data.get("role", "AGENT")
            User = get_user_model()

            # Check if username already exists
            if User.objects.filter(username=data["username"]).exists():
                messages.error(request, f"Username '{data['username']}' already exists")
            else:
                try:
                    # Create user
                    user = User.objects.create_user(
                        username=data["username"],
                        email=data.get("email", ""),
                        password=data["password"],
                        first_name=data.get("first_name", ""),
                        last_name=data.get("last_name", ""),
                    )

                    # Attach to business with appropriate role
                    if role == "BAR_MANAGER":
                        attach_user_to_business(user, business, "BAR_MANAGER")
                        messages.success(request, f"Bar Manager '{user.username}' invited successfully!")
                    else:
                        attach_user_to_business(user, business, "LIQUOR_BARMAN")
                        messages.success(request, f"Bartender '{user.username}' invited successfully!")

                    return redirect("verticals:liquor_dashboard")
                except Exception as e:
                    messages.error(request, f"Failed to create user: {e}")
        else:
            messages.error(request, "Please correct the errors below")
    else:
        form = BarmanInviteForm()

    ctx.update(
        {
            "page_title": "Invite Team Member",
            "form": form,
        }
    )

    return render(request, "verticals/liquor/barman_invite.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def barman_reconciliation(request):
    """
    Barman/Manager reconciliation screen.
    Shows sales attributed to agents and allows marking them as reconciled.
    """
    from django.contrib import messages
    from sales.models import LiquorSaleAttribution
    from django.db.models import Sum, Count
    from core.context import _extract_roles_for

    ctx = base.base_context(request)
    business = ctx.get("business")

    # Check if user is barman or manager
    roles = _extract_roles_for(request.user, business)
    is_barman = request.user.groups.filter(name=f"biz:{business.pk}:LIQUOR_BARMAN").exists()

    if not (roles.is_manager or is_barman):
        messages.error(request, "Access denied")
        return redirect("verticals:liquor_dashboard")

    # Get filter parameters
    date_filter = request.GET.get("date", "today")
    status_filter = request.GET.get("status", "all")

    # Base queryset
    attributions_qs = LiquorSaleAttribution.objects.filter(business=business).select_related(
        "attributed_to", "attributed_by", "reconciled_by"
    )

    # Apply filters
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if date_filter == "today":
        attributions_qs = attributions_qs.filter(created_at__gte=today_start)
    elif date_filter == "week":
        week_start = today_start - timedelta(days=7)
        attributions_qs = attributions_qs.filter(created_at__gte=week_start)
    elif date_filter == "month":
        month_start = today_start.replace(day=1)
        attributions_qs = attributions_qs.filter(created_at__gte=month_start)

    if status_filter == "pending":
        attributions_qs = attributions_qs.filter(status=LiquorSaleAttribution.STATUS_PENDING)
    elif status_filter == "reconciled":
        attributions_qs = attributions_qs.filter(status=LiquorSaleAttribution.STATUS_RECONCILED)

    # Group by agent
    agent_summaries = (
        attributions_qs.values(
            "attributed_to__id", "attributed_to__first_name", "attributed_to__last_name", "attributed_to__username"
        )
        .annotate(
            total_sales=Count("id"),
            total_amount=Sum("sale_amount"),
            pending_count=Count("id", filter=Q(status=LiquorSaleAttribution.STATUS_PENDING)),
            reconciled_count=Count("id", filter=Q(status=LiquorSaleAttribution.STATUS_RECONCILED)),
        )
        .order_by("-total_amount")
    )

    # Get detailed attributions for display
    attributions = attributions_qs.order_by("-created_at")[:100]

    ctx.update(
        {
            "page_title": "Barman Reconciliation",
            "agent_summaries": agent_summaries,
            "attributions": attributions,
            "date_filter": date_filter,
            "status_filter": status_filter,
            "is_barman": is_barman,
        }
    )

    return render(request, "verticals/liquor/barman_reconciliation.html", ctx)


# Fast Sell API endpoints
@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def fast_sell_lookup_api(request):
    """API: Look up product by barcode"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import lookup_product_by_barcode

    business = base.base_context(request).get("business")
    barcode = request.GET.get("barcode", "").strip()

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode required"}, status=400)

    result = lookup_product_by_barcode(business=business, vertical="liquor", barcode=barcode)

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def fast_sell_create_api(request):
    """API: Create a fast sale (Quick Sell) for liquor by barcode"""
    from django.http import JsonResponse
    from inventory.services.liquor_sale import create_liquor_sale_by_barcode, OutOfStockError
    from inventory.views_liquor import get_or_start_active_shift
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from tenants.models import Location
    import json
    import logging

    logger = logging.getLogger(__name__)

    def _payload(request):
        """Safe payload parser that handles both JSON and form POST"""
        if request.content_type and "application/json" in request.content_type:
            try:
                return json.loads((request.body or b"{}").decode("utf-8"))
            except json.JSONDecodeError:
                return {}
        return request.POST

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    business = base.base_context(request).get("business")

    # Get location from request attribute, session, or first active location
    location = getattr(request, "location", None)
    if not location:
        location_id = getattr(request, "active_location_id", None)
        if not location_id:
            location_id = request.session.get("active_location_id")
        if location_id:
            try:
                location = Location.objects.get(pk=location_id, business=business)
            except Location.DoesNotExist:
                location = None

    data = _payload(request)

    barcode = data.get("barcode", "").strip()
    quantity_str = data.get("quantity", "1")
    try:
        quantity = int(quantity_str)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid quantity"}, status=400)

    unit = data.get("unit", "bottle")  # "bottle", "shot", or "glass"
    selling_price_str = data.get("selling_price")

    # Map payment_method to sale_type (for backward compatibility)
    payment_method = data.get("payment_method", "cash")
    sale_type = data.get("sale_type", "cash")  # "cash" or "credit"
    # If payment_method is provided but sale_type is not, use payment_method
    if "payment_method" in data and "sale_type" not in data:
        # payment_method values: "cash", "bank", "mobile_money"
        # sale_type values: "cash", "credit"
        # For fast sell, payment_method "cash" means cash sale
        sale_type = "cash"  # Fast sell is always cash sales

    customer_name = data.get("customer_name", "").strip()
    customer_phone = data.get("customer_phone", "").strip()
    notes = data.get("notes", "").strip()

    # Payment mix (optional)
    cash_amount = Decimal(str(data.get("cash_amount", "0") or "0"))
    bank_amount = Decimal(str(data.get("bank_amount", "0") or "0"))
    mobile_money_amount = Decimal(str(data.get("mobile_money_amount", "0") or "0"))

    if not barcode:
        return JsonResponse({"ok": False, "error": "Barcode is required"}, status=400)

    if quantity < 1:
        return JsonResponse({"ok": False, "error": "Quantity must be at least 1"}, status=400)

    selling_price = None
    if selling_price_str:
        try:
            selling_price = Decimal(str(selling_price_str))
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Invalid price"}, status=400)

    # Get or auto-start active shift
    try:
        active_shift = get_or_start_active_shift(request.user, business, location)
    except Exception as e:
        logger.warning(f"Failed to get/start shift for liquor sale: {e}")
        active_shift = None

    # Parse agent_id from payload (supporting multiple aliases)
    agent_id = None
    for key in ["attributed_to_agent_id", "agent_id", "assigned_agent_id", "attributed_agent_id"]:
        if key in data:
            try:
                agent_id = int(data[key])
                break
            except (ValueError, TypeError):
                continue

    try:
        # Wrap sale creation and attribution in a single transaction
        with transaction.atomic():
            result = create_liquor_sale_by_barcode(
                business=business,
                user=request.user,
                barcode=barcode,
                quantity=quantity,
                unit=unit,
                unit_price=selling_price,
                sale_type=sale_type,
                customer_name=customer_name if customer_name else None,
                customer_phone=customer_phone if customer_phone else None,
                notes=notes if notes else None,
                cash_amount=cash_amount,
                bank_amount=bank_amount,
                mobile_money_amount=mobile_money_amount,
                payment_method=payment_method,
                shift=active_shift,
            )

            # Create attribution if agent_id is provided
            if agent_id and result.get("ok") and result.get("sale_id"):
                from sales.models import LiquorSaleAttribution
                from django.contrib.auth import get_user_model
                from inventory.models_verticals import LiquorSale

                User = get_user_model()

                try:
                    # Verify agent exists
                    agent = User.objects.get(pk=agent_id)

                    # Get the sale to retrieve sale amount
                    sale = LiquorSale.objects.get(pk=result["sale_id"])

                    # Create or update attribution (idempotent)
                    LiquorSaleAttribution.objects.update_or_create(
                        liquor_sale_id=sale.id,
                        defaults={
                            "business": business,
                            "attributed_by": request.user,
                            "attributed_to": agent,
                            "sale_amount": sale.total_price,
                            "status": LiquorSaleAttribution.STATUS_PENDING,
                        },
                    )
                except User.DoesNotExist:
                    logger.warning(f"Agent with id {agent_id} not found for attribution")
                    # Don't fail the sale if agent is not found, just log it
                except LiquorSale.DoesNotExist:
                    logger.warning(f"Sale with id {result['sale_id']} not found for attribution")
                    # This shouldn't happen, but log it if it does

        return JsonResponse(result)

    except OutOfStockError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        # Catch TransactionManagementError and other DB errors
        logger.error(
            f"Error in liquor fast sell: {e}",
            exc_info=True,
            extra={
                "business_id": business.id if business else None,
                "barcode": barcode,
                "quantity": quantity,
                "user_id": request.user.id if request.user.is_authenticated else None,
            },
        )
        # Never show raw DB errors to users
        if "select_for_update" in str(e).lower() or "transaction" in str(e).lower():
            return JsonResponse({"ok": False, "error": "Sale failed: Database error. Please try again."}, status=500)
        return JsonResponse({"ok": False, "error": f"Sale failed: {str(e)}"}, status=500)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def fast_sell_kpis_api(request):
    """API: Get Fast Sell KPIs"""
    from django.http import JsonResponse
    from inventory.services.fast_sell import get_fast_sell_kpis

    business = base.base_context(request).get("business")
    date_range = request.GET.get("range", "today")

    result = get_fast_sell_kpis(
        business=business,
        vertical="liquor",
        date_range=date_range,
    )

    return JsonResponse(result)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def barman_agents_api(request):
    """API: Get list of liquor agents (for barman to assign sales)"""
    from django.http import JsonResponse
    from django.contrib.auth import get_user_model

    business = base.base_context(request).get("business")

    # Get all users who have AGENT role for this business
    User = get_user_model()
    agent_group_name = f"biz:{business.pk}:AGENT"
    agents = (
        User.objects.filter(groups__name=agent_group_name)
        .values("id", "first_name", "last_name", "username")
        .distinct()
    )

    return JsonResponse({"ok": True, "agents": list(agents)})


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def barman_reconciliation_toggle_api(request):
    """API: Toggle reconciliation status of an attribution"""
    from django.http import JsonResponse
    from sales.models import LiquorSaleAttribution
    import json

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    business = base.base_context(request).get("business")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    attribution_id = data.get("attribution_id")
    new_status = data.get("status")  # "pending" or "reconciled"

    try:
        attribution = LiquorSaleAttribution.objects.get(id=attribution_id, business=business)

        if new_status == "reconciled":
            attribution.mark_reconciled(request.user)
        elif new_status == "pending":
            attribution.mark_pending()
        else:
            return JsonResponse({"ok": False, "error": "Invalid status"}, status=400)

        return JsonResponse({"ok": True, "message": "Status updated"})
    except LiquorSaleAttribution.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Attribution not found"}, status=404)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def sales_trend_json(request):
    """
    JSON endpoint for liquor sales trend data.
    Returns data suitable for Chart.js.
    """
    from django.http import JsonResponse

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Parse date range from request
    range_param = request.GET.get("range", "7d")

    # Use base helper to compute date range
    date_range_ctx = base.parse_date_range_from_request(request)
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]

    # Build sales queryset
    sales_qs = LiquorSale.objects.filter(business=business)

    if location and hasattr(LiquorSale, "location"):
        sales_qs = sales_qs.filter(location=location)

    # Generate daily data for the date range
    labels = []
    revenue_values = []
    count_values = []

    current_date = start_date
    while current_date < end_date:
        # Get sales for this day
        day_sales = sales_qs.filter(sold_at__date=current_date)
        day_revenue = day_sales.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
        day_count = day_sales.count()

        labels.append(current_date.strftime("%b %d"))
        revenue_values.append(float(day_revenue))
        count_values.append(day_count)

        current_date += timedelta(days=1)

    # Add cache-busting metadata
    return JsonResponse(
        {
            "labels": labels,
            "revenue": revenue_values,
            "count": count_values,
            "period": range_param,
            "start_date": start_date.isoformat(),
            "end_date": (end_date - timedelta(days=1)).isoformat(),
            "timestamp": timezone.now().isoformat(),
        }
    )


@login_required
@require_business
@require_business_kind(BusinessKind.LIQUOR)
def rollback_sale(request, sale_id):
    """
    Rollback/cancel a liquor sale and restore inventory.
    Manager-only feature for correcting mistakes.
    """
    from django.http import JsonResponse
    from django.contrib import messages
    from django.db import transaction
    from core.context import _extract_roles_for

    business = base.base_context(request).get("business")

    # Check if user is manager
    roles = _extract_roles_for(request.user, business)
    if not roles.is_manager:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Only managers can rollback sales"}, status=403)
        messages.error(request, "Only managers can rollback sales")
        return redirect("verticals:liquor_sales_history")

    # Get the sale
    try:
        sale = LiquorSale.objects.get(id=sale_id, business=business)
    except LiquorSale.DoesNotExist:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale not found"}, status=404)
        messages.error(request, "Sale not found")
        return redirect("verticals:liquor_sales_history")

    # Check if already cancelled (if field exists)
    if hasattr(sale, "is_cancelled") and sale.is_cancelled:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Sale already cancelled"}, status=400)
        messages.error(request, "Sale already cancelled")
        return redirect("verticals:liquor_sales_history")

    if request.method == "POST":
        with transaction.atomic():
            # Restore inventory if product tracks inventory
            product = sale.product
            if product.track_inventory:
                product.quantity_in_stock += sale.quantity
                product.save(update_fields=["quantity_in_stock"])

            # Mark sale as cancelled (if field exists) or delete
            if hasattr(sale, "is_cancelled"):
                sale.is_cancelled = True
                sale.cancelled_at = timezone.now()
                sale.cancelled_by = request.user
                sale.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by"])
            else:
                # Fallback: soft delete by adding notes
                sale.notes = f"[CANCELLED by {request.user.username} on {timezone.now()}] {sale.notes}"
                sale.save(update_fields=["notes"])

        return JsonResponse({"ok": True, "message": f"Sale #{sale_id} rolled back successfully. Inventory restored."})

    # GET request: show confirmation
    messages.error(request, "Invalid request method")
    return redirect("verticals:liquor_sales_history")
