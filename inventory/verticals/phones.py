# inventory/verticals/phones.py
"""
Premium PHONES dashboard - the crown jewel of CircuitCity verticals.

Also includes accessories system (quantity-based, separate from IMEI phones).

Mirrors the premium Liquor dashboard patterns:
- Comprehensive KPIs with custom date range filtering
- Fast-moving models and top agents tracking  
- Sales trend visualization over 30 days
- Business panel with average metrics and sell-through rate
- Scoped to business + location + agents (same as Liquor)

PHONES uses the InventoryItem model where each phone is tracked with IMEI.
Sales are recorded by setting status="SOLD" and sold_at timestamp.

NEW in this version:
- Date range filtering: Today, Last 7 Days, This Month (MTD), Custom
- All KPIs respect the selected range
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg, F, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import InventoryItem, Product, Location
from . import base


def _parse_date_range(request):
    """
    Parse date range from query parameters.

    Supports:
    - ?range=today
    - ?range=7d (last 7 days)
    - ?range=mtd (month to date, DEFAULT)
    - ?range=custom&start=YYYY-MM-DD&end=YYYY-MM-DD

    Returns:
        tuple: (range_key, start_datetime, end_datetime, display_label)
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    range_param = request.GET.get("range", "mtd").lower()

    if range_param == "today":
        return ("today", today_start, today_end, "Today")

    elif range_param == "7d":
        start = today_start - timedelta(days=7)
        return ("7d", start, today_end, "Last 7 Days")

    elif range_param == "custom":
        # Parse custom dates from query params
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

            # Convert to timezone-aware datetimes
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

            label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"
            return ("custom", start_dt, end_dt, label)
        except (ValueError, TypeError):
            # Fall back to MTD if custom dates are invalid
            pass

    # Default: month-to-date
    month_start = today_start.replace(day=1)
    return ("mtd", month_start, today_end, "This Month")


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def dashboard(request):
    """
    Premium PHONES Dashboard - Crown Jewel Edition (with Date Filtering + Role-Based Scoping)

    Provides comprehensive business metrics for phone retailers:
    - Custom date range filtering (Today / Last 7 Days / MTD / Custom)
    - KPIs: Units Sold, Revenue, Costs, Profit, Profit Margin
    - Stock on hand with cost/selling value and potential profit
    - 30-day sales trend for visualization
    - Fast-moving models (top 5 by units sold)
    - Top agents leaderboard (top 5 by revenue)
    - Best sales day in selected period
    - Business panel with average metrics and sell-through rate

    ROLE-BASED VISIBILITY:
    - Managers: See GLOBAL numbers (all stock, all sales)
    - Agents: See ONLY their own numbers (their stock, their sales)

    Uses centralized metrics service for accurate cost/profit calculations.
    """
    from inventory.utils_scope import get_visible_actor, scope_sales_qs, scope_stock_qs, scope_costs_qs

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    if location is None:
        location = getattr(request, "location", None)

    # Determine user's visibility scope using middleware-set flags
    # CRITICAL: get_visible_actor uses request.is_manager_plus and request.is_agent_only
    # which are set by RoleResolutionMiddleware using tenants.utils_roles
    # This ensures managers NEVER downgrade to agent scope
    is_manager, is_agent, actor_user = get_visible_actor(request)

    # Add role flags to context for template use
    ctx["IS_MANAGER"] = is_manager
    ctx["IS_AGENT"] = is_agent

    # ==========================================================================
    # DATE RANGE PARSING (ALL OPTIONS RESTORED)
    # ==========================================================================
    # Use shared date range parser with ALL filter support
    date_range_ctx = base.parse_date_range_from_request(request)
    
    # Extract all values for context
    filter_mode = date_range_ctx.get("filter_mode")
    period = date_range_ctx.get("period")
    month = date_range_ctx.get("month")
    year = date_range_ctx.get("year")
    range_key = date_range_ctx["active_range"]
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]
    range_label = date_range_ctx["range_label"]
    custom_start = date_range_ctx.get("custom_start")
    custom_end = date_range_ctx.get("custom_end")

    # Current datetime for other calculations
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Last 30 days range (for trends and fast-moving analysis)
    last_30_days_start = today_start - timedelta(days=30)

    # Base queryset for sold items (scoped to business + role)
    # CRITICAL FIX: Include ALL sold items, not just those with sold_at timestamp
    # Legacy data may have status="SOLD" but NULL sold_at - these must still be counted
    # We filter is_active=True to exclude voided records (Data Correction feature)
    sold_items = InventoryItem.objects.filter(
        business=business, 
        status="SOLD",
        is_active=True,  # Exclude voided items
    ).select_related("product", "assigned_agent")

    # If location is set, optionally filter by location
    # (Following Liquor pattern where location filtering is optional)
    if location:
        sold_items = sold_items.filter(current_location=location)

    # CRITICAL: Apply agent scoping if user is an agent
    if is_agent:
        # Agents see only their own sales
        sold_items = sold_items.filter(assigned_agent=actor_user)

    # ==========================================================================
    # A) PREMIUM KPIs FOR SELECTED RANGE (using centralized metrics service)
    # ==========================================================================

    # Filter sales to the selected date range
    # CRITICAL FIX: Handle legacy data where sold_at may be NULL
    # For items with NULL sold_at, fall back to received_at for date filtering
    # This ensures historical sales are counted even if they lack sold_at timestamp
    from django.db.models import Case, When, F
    from django.db.models.functions import Coalesce as CoalesceFunc
    
    # Use sold_at if available, otherwise fall back to received_at (as datetime)
    # Note: received_at is a DateField, sold_at is a DateTimeField
    # We need to compare both as dates for proper filtering
    # If start_date/end_date are None (all-time), don't apply date filtering
    if start_date is not None and end_date is not None:
        range_sales = sold_items.filter(
            Q(sold_at__gte=start_date, sold_at__lt=end_date) |
            Q(sold_at__isnull=True, received_at__gte=start_date.date() if hasattr(start_date, 'date') else start_date, 
              received_at__lt=end_date.date() if hasattr(end_date, 'date') else end_date)
        )
    else:
        # All-time: include all sold items
        range_sales = sold_items

    # Units sold in selected range
    units_sold = range_sales.count()

    # Revenue (sum of selling prices)
    revenue = range_sales.aggregate(total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField()))[
        "total"
    ] or Decimal("0.00")

    # ==========================================================================
    # STOCK ON HAND (current, not date-filtered, scoped by role)
    # ==========================================================================
    stock_items = InventoryItem.objects.filter(business=business, status="IN_STOCK", is_active=True).select_related(
        "product"
    )

    if location:
        stock_items = stock_items.filter(current_location=location)

    # CRITICAL: Apply agent scoping if user is an agent
    if is_agent:
        # Agents see only their own stock
        stock_items = stock_items.filter(assigned_agent=actor_user)

    stock_on_hand = stock_items.count()

    # ==========================================================================
    # INVENTORY VALUE METRICS (what user expects for "Revenue" and "COGS")
    # ==========================================================================
    # For Phones dashboard, these KPIs must reflect inventory value (stock value)
    # "Revenue" = potential stock value (sum of selling_price for items in stock)
    # "COGS" = inventory cost basis (sum of cost_price/order_price for items in stock)
    stock_cost_value = stock_items.aggregate(
        total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    stock_selling_value = stock_items.aggregate(
        total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    # ==========================================================================
    # COSTS AND PROFIT (unified computation from ONE sales queryset)
    # ==========================================================================
    # CRITICAL: All KPIs must use the SAME base queryset for consistency
    # Revenue, COGS, and Profit all derive from range_sales (sold items in period)

    # COGS: Cost of goods sold (sum of order_price for sold items in period)
    cost_of_goods = range_sales.aggregate(
        total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    # Business Costs: Operational costs from Admin Wallet (same period)
    # CRITICAL: Agents should NOT see global business costs unless assignable to them
    from wallet.models import WalletTransaction, Ledger, TxnType

    # Convert datetime to date for effective_date comparison (only if dates provided)
    if start_date is not None and end_date is not None:
        period_start_date = start_date.date() if hasattr(start_date, "date") else start_date
        period_end_date = end_date.date() if hasattr(end_date, "date") else end_date
    else:
        # All-time: no date filtering
        period_start_date = None
        period_end_date = None

    if is_manager:
        # Managers see all business costs
        business_costs_query = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        )
        if period_start_date is not None and period_end_date is not None:
            business_costs_query = business_costs_query.filter(
                effective_date__gte=period_start_date,
                effective_date__lt=period_end_date,
            )
        business_costs_sum = business_costs_query.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")
        # Costs are stored as negative, so we take absolute value for display
        business_costs = abs(business_costs_sum)
    else:
        # Agents: Check if costs can be assigned to them
        # If WalletTransaction has assigned_to/agent/created_by, filter by that
        # Otherwise, show 0 (agents don't see global costs)
        business_costs_query = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        )
        if period_start_date is not None and period_end_date is not None:
            business_costs_query = business_costs_query.filter(
                effective_date__gte=period_start_date,
                effective_date__lt=period_end_date,
            )

        # Try to scope costs to agent if possible
        if hasattr(WalletTransaction, "assigned_to"):
            business_costs_query = business_costs_query.filter(assigned_to=actor_user)
        elif hasattr(WalletTransaction, "created_by"):
            business_costs_query = business_costs_query.filter(created_by=actor_user)
        else:
            # No agent-assignment field exists, agents see 0 costs
            business_costs_query = business_costs_query.none()

        business_costs_sum = business_costs_query.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")
        business_costs = abs(business_costs_sum)

    # Total Costs = COGS + Business Costs (MUST match breakdown)
    total_costs = cost_of_goods + business_costs

    # Profit = Revenue - Total Costs (using sales revenue, not stock value)
    profit = revenue - total_costs

    # Margin = (Profit / Revenue) * 100, guard against division by zero
    profit_margin = (profit / revenue * 100) if revenue > 0 else Decimal("0.00")

    # Compute absolute values for template display (Django doesn't have |abs filter)
    profit_abs = abs(profit)
    profit_margin_abs = abs(profit_margin)

    # ==========================================================================
    # PAYMENT MIX - Breakdown by payment method for selected period
    # ==========================================================================
    # CRITICAL: Payment Mix MUST be computed from the SAME range_sales queryset as Revenue
    # This ensures Payment Mix totals = Revenue KPI (consistency)

    payment_totals = range_sales.aggregate(
        cash=Coalesce(
            Sum("selling_price", filter=Q(payment_method="CASH")), Decimal("0.00"), output_field=DecimalField()
        ),
        bank=Coalesce(
            Sum("selling_price", filter=Q(payment_method="BANK")), Decimal("0.00"), output_field=DecimalField()
        ),
        mobile=Coalesce(
            Sum("selling_price", filter=Q(payment_method="MOBILE_MONEY")), Decimal("0.00"), output_field=DecimalField()
        ),
    )

    cash_amount = payment_totals["cash"] or Decimal("0.00")
    bank_amount = payment_totals["bank"] or Decimal("0.00")
    mobile_amount = payment_totals["mobile"] or Decimal("0.00")

    # Sanity check: Payment Mix should sum to Revenue (both from range_sales)
    payment_mix_total = cash_amount + bank_amount + mobile_amount
    # Allow for small rounding differences (< 1 MWK)
    if abs(payment_mix_total - revenue) > Decimal("1.00"):
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Payment Mix mismatch: Total={payment_mix_total}, Revenue={revenue}, Diff={payment_mix_total - revenue}"
        )

    # Calculate percentages (ensure they sum to exactly 100%)
    if revenue > 0:
        cash_pct = int(round((cash_amount / revenue) * 100))
        bank_pct = int(round((bank_amount / revenue) * 100))
        # Mobile gets the remainder to ensure exact 100%
        mobile_pct = 100 - cash_pct - bank_pct
    else:
        cash_pct = bank_pct = mobile_pct = 0

    payment_mix_data = [
        {"method": "Cash", "method_code": "CASH", "amount": cash_amount, "percentage": cash_pct},
        {"method": "Bank", "method_code": "BANK", "amount": bank_amount, "percentage": bank_pct},
        {"method": "Mobile Money", "method_code": "MOBILE_MONEY", "amount": mobile_amount, "percentage": mobile_pct},
    ]

    # ==========================================================================
    # STOCK POTENTIAL PROFIT (NEVER NEGATIVE)
    # ==========================================================================
    # Correct formula: sum over stock of max(0, selling_price - cost_price) * qty
    # For phones, qty is always 1 (individual items), so:
    # stock_potential_profit = sum(max(0, selling_price - order_price) for each item)

    stock_potential_profit = Decimal("0.00")
    for item in stock_items:
        # Get selling price and cost price, defaulting to 0 if None
        selling = item.selling_price or Decimal("0.00")
        cost = item.order_price or Decimal("0.00")
        # Contribution is max(0, profit_per_unit)
        contribution = max(Decimal("0.00"), selling - cost)
        stock_potential_profit += contribution

    # Package the main dashboard KPIs for the selected range
    # CRITICAL FIX: Revenue KPI MUST show sales revenue (not stock value)
    # This ensures Revenue matches Payment Mix totals (both derived from range_sales)
    dashboard_kpis = {
        # Period filter state (ALL OPTIONS RESTORED)
        "filter_mode": filter_mode,
        "period": period,
        "month": month,
        "year": year,
        "range_key": range_key,
        "range_label": range_label,
        "custom_start": custom_start,
        "custom_end": custom_end,
        "start_date": start_date.date() if start_date and hasattr(start_date, "date") else start_date,
        "end_date": end_date.date() if end_date and hasattr(end_date, "date") else end_date,
        "units_sold": units_sold,
        "stock_on_hand": stock_on_hand,
        # PRIMARY KPIs: All derived from range_sales (sold items in period)
        "revenue": revenue,  # Sales revenue (matches Payment Mix)
        "cost_of_goods": cost_of_goods,  # COGS for sold items
        "business_costs": business_costs,  # Operational costs
        "total_costs": total_costs,  # MUST equal COGS + Business Costs
        "profit": profit,  # Revenue - Total Costs
        "profit_margin": profit_margin,  # (Profit / Revenue) * 100
        # Pre-computed absolute values for template (Django lacks |abs filter)
        "profit_abs": profit_abs,
        "profit_margin_abs": profit_margin_abs,
        # Payment mix (must sum to revenue)
        "payment_mix": payment_mix_data,
        # STOCK METRICS: Separate from sales KPIs (for reference)
        "stock_cost_value": stock_cost_value,  # Inventory cost basis
        "stock_selling_value": stock_selling_value,  # Potential stock value
        "stock_potential_profit": stock_potential_profit,  # NEVER negative (max per item)
    }

    # ==========================================================================
    # B) ADDITIONAL INSIGHTS (still using 30-day window for trends/highlights)
    # ==========================================================================

    # --- SALES TREND - LAST 30 DAYS (line chart, never empty) ---
    # Always generate 30 days of data (with zeros if no sales) so chart always renders
    # CRITICAL FIX: Handle items with NULL sold_at by falling back to received_at
    # BUGFIX (Jan 2026): Corrected to show proper 30-day window (day -30 through day -1, NOT including today)
    # This ensures "Last 30 Days" means the completed 30 days before today
    sales_trend_data = []
    for i in range(30):
        day_start = today_start - timedelta(days=30 - i)  # Start from 30 days ago
        day_end = day_start + timedelta(days=1)
        day_date = day_start.date()
        day_end_date = day_end.date()
        
        # Include items with sold_at in range OR items with null sold_at but received_at in range
        day_sales = sold_items.filter(
            Q(sold_at__gte=day_start, sold_at__lt=day_end) |
            Q(sold_at__isnull=True, received_at=day_date)
        )
        day_units = day_sales.count()
        day_revenue = day_sales.aggregate(
            total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )["total"] or Decimal("0.00")

        sales_trend_data.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "units": day_units,
                "revenue": float(day_revenue),
            }
        )

    sales_trend_30d = sales_trend_data

    # --- FAST MOVING MODELS - TOP 5 BY UNITS SOLD (SELECTED RANGE) ---
    fast_models_query = (
        range_sales.values("product__brand", "product__model", "product__variant")
        .annotate(
            units=Count("id"), revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )
        .order_by("-units")[:5]
    )

    fast_models = []
    for item in fast_models_query:
        brand = item["product__brand"] or "Unknown"
        model = item["product__model"] or "Unknown"
        variant = item["product__variant"] or ""
        ram_rom = variant if variant else "N/A"

        fast_models.append(
            {
                "brand": brand,
                "model": model,
                "ram_rom": ram_rom,
                "units": item["units"],
                "revenue": item["revenue"],
            }
        )

    # --- TOP AGENTS - TOP 5 BY COMMISSION (SELECTED RANGE) ---
    # Use the centralized agent_earnings service for consistency
    try:
        from inventory.services.agent_earnings import get_top_agents

        top_agents_data = get_top_agents(
            business=business,
            start_date=start_date.date() if hasattr(start_date, "date") else start_date,
            end_date=end_date.date() if hasattr(end_date, "date") else end_date,
            location=location,
            limit=5,
        )

        top_agents = []
        for row in top_agents_data:
            top_agents.append(
                {
                    "agent_id": getattr(row, "agent_id", None),
                    "agent_name": row.agent_name,
                    "units": row.units_sold,
                    "revenue": row.total_revenue,
                    "commission": row.total_commission,
                }
            )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to use agent_earnings service, falling back to direct query: {e}")

        # Fallback to direct query if service fails
        top_agents_query = (
            range_sales.filter(assigned_agent__isnull=False)
            .values(
                "assigned_agent__id",
                "assigned_agent__first_name",
                "assigned_agent__last_name",
                "assigned_agent__username",
            )
            .annotate(
                units=Count("id"), revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
            )
            .order_by("-revenue")[:5]
        )

        top_agents = []
        for item in top_agents_query:
            first_name = item["assigned_agent__first_name"] or ""
            last_name = item["assigned_agent__last_name"] or ""
            username = item["assigned_agent__username"] or "Unknown"
            agent_name = f"{first_name} {last_name}".strip() or username

            top_agents.append(
                {
                    "agent_id": item["assigned_agent__id"],
                    "agent_name": agent_name,
                    "units": item["units"],
                    "revenue": item["revenue"],
                    "commission": Decimal("0.00"),  # No commission data in fallback
                }
            )

    # --- BEST SALES DAY IN SELECTED RANGE ---
    # CRITICAL FIX: Use COALESCE to handle items with NULL sold_at (fall back to received_at)
    best_day_query = (
        range_sales.extra(select={"day": "COALESCE(DATE(sold_at), received_at)"})
        .values("day")
        .annotate(
            day_units=Count("id"),
            day_revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField()),
        )
        .order_by("-day_revenue")
        .first()
    )

    best_sales_day = None
    if best_day_query:
        best_sales_day = {
            "date": best_day_query["day"],
            "units": best_day_query["day_units"],
            "revenue": best_day_query["day_revenue"],
        }

    # --- SALES BY PHONE MODEL - TOP 10 BY REVENUE (SELECTED RANGE) ---
    # Group sales by phone brand + model to show which models are selling
    sales_by_model_query = (
        range_sales.values("product__brand", "product__model")
        .annotate(
            units_sold=Count("id"), revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )
        .order_by("-revenue")[:10]  # Top 10 models by revenue
    )

    sales_by_model = []
    for item in sales_by_model_query:
        brand = item["product__brand"] or "Unknown"
        model = item["product__model"] or "Unknown"
        # Combine brand and model for display (e.g., "Tecno Pova 5", "Itel A58")
        model_name = f"{brand} {model}".strip()

        sales_by_model.append(
            {
                "model_name": model_name,
                "units_sold": item["units_sold"],
                "revenue": item["revenue"],
            }
        )

    # ==========================================================================
    # C) ACCESSORIES KPIs (OPTIONAL - separate system)
    # ==========================================================================
    # Fetch accessories KPIs for the same date range to show in dashboard
    accessories_kpis = None
    try:
        from inventory.models_accessories import AccessoryStockLog

        # Query accessories sales logs for the selected range
        acc_sale_logs = AccessoryStockLog.objects.filter(
            business=business, action="SALE", created_at__gte=start_date, created_at__lt=end_date
        )

        if location:
            acc_sale_logs = acc_sale_logs.filter(location=location)

        # Calculate accessories metrics
        acc_revenue = Decimal("0.00")
        acc_cost = Decimal("0.00")
        acc_units = 0

        for log in acc_sale_logs:
            qty = abs(log.quantity)
            acc_units += qty
            unit_cost = log.unit_cost or (log.product.default_order_price if log.product else Decimal("0.00"))
            unit_price = log.product.default_selling_price if log.product else Decimal("0.00")
            acc_cost += Decimal(qty) * unit_cost
            acc_revenue += Decimal(qty) * unit_price

        acc_profit = acc_revenue - acc_cost

        # Get accessories stock value
        from inventory.models_accessories import AccessoryStock

        acc_stock_qs = AccessoryStock.objects.filter(business=business, product__is_active=True)
        if location:
            acc_stock_qs = acc_stock_qs.filter(location=location)

        acc_stock_value = Decimal("0.00")
        for stock in acc_stock_qs.filter(qty_on_hand__gt=0):
            acc_stock_value += stock.stock_value

        accessories_kpis = {
            "revenue": acc_revenue,
            "profit": acc_profit,
            "stock_value": acc_stock_value,
            "units_sold": acc_units,
        }
    except Exception as e:
        # Gracefully degrade if accessories system not available
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Accessories KPIs not available: {e}")
        accessories_kpis = None

    # ==========================================================================
    # D) CONTEXT ASSEMBLY
    # ==========================================================================

    # Serialize data for JavaScript charts
    sales_trend_json = json.dumps(sales_trend_30d)

    # ===== NEW: Personalized dashboard enhancements (quotes & greetings) =====
    ctx_enhancements = {}
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
        quotes_json_data = json_lib.dumps(quote_texts)

        ctx_enhancements.update(
            {
                "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
                "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
                "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
                "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
                "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
                "DASHBOARD_BRAND_TITLE": business.name if business else "Phones Dashboard",
                "DASHBOARD_QUOTES": daily_quotes,
                "quotes_json": quotes_json_data,
            }
        )
    except Exception:
        # Gracefully degrade if helpers not available
        pass

    # Update context with dashboard data
    ctx.update(
        {
            "hero_title": "Phones & Electronics",
            "hero_blurb": "Track your phone sales, stock, and agents with premium KPIs and custom date filtering.",
            # NEW: Premium dashboard KPIs with date filtering
            "dashboard_kpis": dashboard_kpis,
            # Accessories KPIs (optional, separate system)
            "accessories_kpis": accessories_kpis,
            # Charts and trends (30-day window for visualization)
            "sales_trend_30d": sales_trend_30d,
            "sales_trend_json": sales_trend_json,
            "fast_models": fast_models,
            "top_agents": top_agents,
            "best_sales_day": best_sales_day,
            # NEW: Sales by phone model (respects date range filter)
            "sales_by_model": sales_by_model,
            # Role-based visibility flags
            "IS_MANAGER": is_manager,
            "IS_AGENT": is_agent,
            # UI flags
            "show_search": False,
            "active_tab": "home",
            **ctx_enhancements,  # Merge dashboard enhancements
        }
    )

    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context

    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "verticals/phones/dashboard.html", ctx)


# ==============================================================================
# SALES HISTORY, EXPORT, AND TREND API
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def sales_history(request):
    """
    Sales History page for phones with filters, pagination, and export.
    Shows all phone sales with date range filtering and search.
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from sales.models import Sale

    ctx = base.base_context(request)
    business = ctx.get("business")
    location = ctx.get("location")

    # Build base queryset - phones use Sale model
    sales_qs = Sale.objects.filter(item__business=business).select_related("item", "item__product", "agent", "location")

    # Location filtering
    if location:
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
            sales_qs = sales_qs.filter(sold_at__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__lte=end_dt)
        except ValueError:
            pass

    # Apply search filter (IMEI, brand, model, agent)
    if search_query:
        sales_qs = sales_qs.filter(
            Q(item__imei__icontains=search_query)
            | Q(item__product__brand__icontains=search_query)
            | Q(item__product__model__icontains=search_query)
            | Q(item__product__variant__icontains=search_query)
            | Q(agent__username__icontains=search_query)
            | Q(agent__first_name__icontains=search_query)
            | Q(agent__last_name__icontains=search_query)
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
        total_revenue=Sum("price"), total_cost=Sum("item__order_price"), total_sales=Count("id")
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

    return render(request, "verticals/phones/sales_history.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def sales_export_csv(request):
    """
    Export filtered phone sales to CSV.
    Respects all the same filters as sales_history view.
    """
    import csv
    from django.http import HttpResponse
    from sales.models import Sale

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Build queryset with same filters as sales_history
    sales_qs = Sale.objects.filter(item__business=business).select_related("item", "item__product", "agent", "location")

    if location:
        sales_qs = sales_qs.filter(location=location)

    # Apply filters
    start_date = request.GET.get("start", "")
    end_date = request.GET.get("end", "")
    search_query = request.GET.get("q", "")

    if start_date:
        try:
            from datetime import datetime

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            from datetime import datetime

            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sales_qs = sales_qs.filter(sold_at__lte=end_dt)
        except ValueError:
            pass

    if search_query:
        sales_qs = sales_qs.filter(
            Q(item__imei__icontains=search_query)
            | Q(item__product__brand__icontains=search_query)
            | Q(item__product__model__icontains=search_query)
            | Q(item__product__variant__icontains=search_query)
            | Q(agent__username__icontains=search_query)
        )

    sales_qs = sales_qs.order_by("-sold_at")

    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="phones_sales_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow(
        [
            "Timestamp",
            "Date",
            "Time",
            "Sale ID",
            "IMEI",
            "Brand",
            "Model",
            "Variant",
            "Price",
            "Cost",
            "Payment Method",
            "Agent",
            "Location",
        ]
    )

    # Write data rows
    for sale in sales_qs:
        item = sale.item
        product = item.product if item else None
        local_timestamp = timezone.localtime(sale.sold_at)

        writer.writerow(
            [
                local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                local_timestamp.strftime("%Y-%m-%d"),
                local_timestamp.strftime("%H:%M:%S"),
                sale.id,
                item.imei if item else "",
                product.brand if product else "",
                product.model if product else "",
                product.variant if product else "",
                f"{sale.price:.2f}",
                f"{item.order_price:.2f}" if item and item.order_price else "0.00",
                sale.get_payment_method_display()
                if hasattr(sale, "get_payment_method_display")
                else sale.payment_method,
                sale.agent.username if sale.agent else "System",
                sale.location.name if sale.location else "N/A",
            ]
        )

    return response


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def sales_trend_json(request):
    """
    JSON endpoint for phone sales trend data.
    Returns data suitable for Chart.js.

    CRITICAL: Uses role-based scoping to ensure managers see all data
    and agents see only their own data.
    """
    from django.http import JsonResponse
    from sales.models import Sale
    from inventory.utils_scope import get_visible_actor

    business = base.base_context(request).get("business")
    location = base.base_context(request).get("location")

    # Determine user's visibility scope
    is_manager, is_agent, actor_user = get_visible_actor(request)

    # Parse date range from request
    range_param = request.GET.get("range", "7d")

    # Use base helper to compute date range
    date_range_ctx = base.parse_date_range_from_request(request)
    start_date = date_range_ctx["start_date"]
    end_date = date_range_ctx["end_date"]

    # Build sales queryset with role-based scoping
    sales_qs = Sale.objects.filter(item__business=business)

    if location:
        sales_qs = sales_qs.filter(location=location)

    # CRITICAL: Apply agent scoping if user is an agent
    if is_agent and actor_user:
        sales_qs = sales_qs.filter(agent=actor_user)

    # Generate daily data for the date range
    labels = []
    revenue_values = []
    count_values = []

    current_date = start_date
    while current_date < end_date:
        # Get sales for this day
        day_sales = sales_qs.filter(sold_at__date=current_date)
        day_revenue = day_sales.aggregate(total=Sum("price"))["total"] or Decimal("0.00")
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
@require_business_kind(BusinessKind.PHONES)
def fast_sell(request):
    """
    Fast Sell page for phones vertical.

    Renders the universal Fast Sell template with phones-specific context.
    Uses barcode scanning and manual entry for quick sales.
    """
    ctx = base.base_context(request)
    ctx.update(
        {
            "vertical": "phones",
            "vertical_name": "Phones & Electronics",
            "page_title": "Fast Sell · Phones",
        }
    )
    return render(request, "verticals/phones/fast_sell.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def reports(request):
    """
    Phones Reports page - safe empty state implementation.
    Future: Will show detailed reports, analytics, and export options.
    """
    from django.contrib import messages

    ctx = base.base_context(request)
    business = ctx.get("business")

    # For now, just show an empty-state message
    # This prevents 404 errors when users click "Reports"
    messages.info(request, "Reports feature is coming soon! Use Sales History to export data in the meantime.")

    # Render a simple empty state template
    ctx.update(
        {
            "page_title": "Phones Reports",
            "empty_message": "Reports feature is under construction. Check back soon!",
            "sales_history_url": "verticals:phones_sales_history",
        }
    )

    return render(request, "verticals/phones/reports_empty.html", ctx)


# ==============================================================================
# ACCESSORIES SYSTEM (quantity-based, separate from IMEI phones)
# ==============================================================================
# Import accessories views from separate module
from .phones_accessories import (
    accessories_dashboard,
    accessories_stock_in,
    accessories_fast_sell,
    accessories_normal_sell,  # NEW: Manual sell page
    accessories_lookup_api,
    accessories_stock_in_api,
    accessories_sell_api,
)

# Export accessories views for URL routing
__all__ = [
    "dashboard",
    "sales_history",
    "sales_export_csv",
    "sales_trend_json",
    "reports",
    "accessories_dashboard",
    "accessories_stock_in",
    "accessories_fast_sell",
    "accessories_normal_sell",
    "accessories_lookup_api",
    "accessories_stock_in_api",
    "accessories_sell_api",
]
