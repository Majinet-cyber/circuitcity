from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.db.models import QuerySet, Sum, Count, Q, DecimalField, ExpressionWrapper, F, Value
from django.db.models.functions import Coalesce, TruncDate
from django.urls import reverse
from django.utils import timezone

# Reusable Decimal constants for consistent field types
DECIMAL_FIELD = DecimalField(max_digits=18, decimal_places=2)
DECIMAL_ZERO = Value(Decimal("0.00"), output_field=DECIMAL_FIELD)

from inventory.helpers import add_product_url_for_request, business_vertical, get_active_business
from inventory.models import MerchProduct
from tenants.scope import resolve_location_for_user, set_scope_in_session


def _get_location(location_id: Optional[int]):
    if not location_id:
        return None
    try:
        Location = apps.get_model("inventory", "Location")
    except Exception:
        return None
    return Location.objects.filter(pk=location_id).first()


def base_context(request) -> Dict[str, Any]:
    """
    Shared context for all vertical dashboards.
    Ensures we keep the tenant scope (business / location) in sync with session defaults.

    Provides vertical-aware URLs so liquor/gym/clothing contexts route correctly.
    """
    business = get_active_business(request)
    vertical = business_vertical(request)

    try:
        request.session["active_business_vertical"] = vertical
    except Exception:
        pass

    location_id = resolve_location_for_user(request)
    if business:
        set_scope_in_session(request, business_id=business.id, location_id=location_id)

    location = _get_location(location_id)
    location_label = getattr(location, "name", None) or ("All locations" if business else "No active location")

    # Vertical-aware URL overrides (Task 1A: Fix liquor stock/sell/hub URLs)
    if vertical == "liquor":
        url_home = reverse("verticals:liquor_dashboard")
        url_stock = reverse("liquor:stock_list")  # FIXED: Use stock_list not stock_overview
        url_sell = reverse("liquor:sell")
        url_scan_in = reverse("liquor:inventory_dashboard")  # Liquor Hub
    elif vertical == "gym":
        url_home = reverse("verticals:gym_dashboard")
        url_stock = reverse("inventory:stock_list")  # gym uses default for now
        url_sell = reverse("inventory:scan_sold")  # gym uses default for now
        url_scan_in = reverse("inventory:scan_in")
    elif vertical == "clothing":
        url_home = reverse("verticals:clothing_dashboard")
        url_stock = reverse("inventory:stock_list")  # clothing uses default for now
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")
    else:  # phones or default
        url_home = reverse("inventory:inventory_dashboard")
        url_stock = reverse("inventory:stock_list")
        url_sell = reverse("inventory:scan_sold")
        url_scan_in = reverse("inventory:scan_in")

    # Safely resolve common feature URLs (may not exist in all deployments)
    try:
        url_wallet = reverse("wallet:agent_wallet")
    except Exception:
        url_wallet = ""

    try:
        url_time_logs = reverse("inventory:time_logs")
    except Exception:
        url_time_logs = ""

    try:
        url_reports = reverse("reports:home")
    except Exception:
        url_reports = ""

    try:
        url_simulator = reverse("simulator:home")
    except Exception:
        url_simulator = ""

    ctx: Dict[str, Any] = {
        "business": business,
        "location": location,
        "location_label": location_label,
        "vertical": vertical,
        # Vertical-aware URLs (for sidebar & templates)
        "url_home": url_home,
        "url_stock": url_stock,
        "url_sell": url_sell,
        "url_scan_in": url_scan_in,
        # Legacy names (backward compatibility)
        "scan_in_url": url_scan_in,
        "scan_sold_url": url_sell,
        "stock_url": url_stock,
        "add_product_url": add_product_url_for_request(request),
        # Feature URLs (for More dropdown)
        "url_wallet": url_wallet,
        "url_time_logs": url_time_logs,
        "url_reports": url_reports,
        "url_simulator": url_simulator,
    }
    return ctx


def merch_queryset(business, kind: str) -> QuerySet[MerchProduct]:
    if not business:
        return MerchProduct.objects.none()
    return MerchProduct.objects.filter(business=business, kind=kind)


def merch_metrics(business, kind: str, *, recent_limit: int = 6) -> Dict[str, Any]:
    qs = merch_queryset(business, kind)
    recent = list(qs.order_by("-id")[:recent_limit])
    return {
        "total": qs.count(),
        "active": qs.filter(is_active=True).count(),
        "scan_required": qs.filter(scan_required=True).count(),
        "inventory_tracked": qs.filter(track_inventory=True).count(),
        "recent": recent,
    }


def _compute_date_range(period: str = "mtd", date_str: Optional[str] = None) -> tuple[date, date]:
    """
    Compute start and end dates for a given period.

    Args:
        period: One of "today", "7d", "mtd", "date"
        date_str: Specific date string (YYYY-MM-DD) when period="date"

    Returns:
        Tuple of (start_date, end_date) where end_date is exclusive (for range queries)
    """
    now = timezone.now()
    today = now.date()

    if period == "today":
        start_date = today
        end_date = today + timedelta(days=1)  # Exclusive end
    elif period == "7d":
        start_date = today - timedelta(days=6)  # Last 7 days including today
        end_date = today + timedelta(days=1)
    elif period == "date" and date_str:
        try:
            specific_date = date.fromisoformat(date_str)
            start_date = specific_date
            end_date = specific_date + timedelta(days=1)
        except (ValueError, TypeError):
            # Fallback to MTD if invalid date
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)
    else:  # "mtd" or default
        start_date = today.replace(day=1)
        end_date = today + timedelta(days=1)

    return start_date, end_date


def parse_date_range_from_request(request) -> Dict[str, Any]:
    """
    Parse date range parameters from request and return normalized data.

    This is a reusable helper for all vertical dashboards to parse date filters
    from GET parameters in a consistent way.

    Args:
        request: Django HttpRequest object

    Returns:
        Dictionary with:
            - active_range: str ("today" | "7d" | "mtd" | "date")
            - start_date: date object (inclusive)
            - end_date: date object (exclusive for range queries)
            - selected_date: date object or None (for "date" range only)
            - date_param: str or None (ISO date string for "date" range)
    """
    # Parse filter parameters from request
    range_param = request.GET.get("range", "mtd")  # Default to MTD
    date_param = request.GET.get("date", "")  # Specific date for "date" range

    # Validate range parameter
    valid_ranges = ["today", "7d", "mtd", "date"]
    if range_param not in valid_ranges:
        range_param = "mtd"

    # For "date" range, validate the date parameter
    selected_date = None
    if range_param == "date":
        if date_param:
            try:
                selected_date = date.fromisoformat(date_param)
            except ValueError:
                # Invalid date format, fall back to MTD
                range_param = "mtd"
                selected_date = None
                date_param = ""
        else:
            # No date provided, default to today
            selected_date = timezone.now().date()
            date_param = selected_date.isoformat()

    # Compute date range
    start_date, end_date = _compute_date_range(range_param, date_param)

    return {
        "active_range": range_param,
        "start_date": start_date,
        "end_date": end_date,
        "selected_date": selected_date,
        "date_param": date_param,
    }


def clothing_sales_queryset(
    business,
    location=None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = "mtd",
    date_str: Optional[str] = None,
) -> QuerySet:
    """
    Build a properly scoped ClothingSale queryset for the given business, location, and date range.
    This is a unified helper used by clothing_sales_metrics and sales_trend_json endpoints.

    Args:
        business: Business instance
        location: Optional location filter
        start_date: Optional explicit start date (inclusive)
        end_date: Optional explicit end date (exclusive)
        period: One of "today", "7d", "mtd", "date" (used if start/end not provided)
        date_str: Specific date string for period="date"

    Returns:
        Filtered QuerySet of ClothingSale objects
    """
    from datetime import datetime
    from inventory.models_verticals import ClothingSale

    # Determine date range
    if start_date is None or end_date is None:
        start_date, end_date = _compute_date_range(period, date_str)

    # Build base sales queryset with timezone-aware datetime filtering
    sales_qs = ClothingSale.objects.filter(
        business=business,
        sold_at__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time())),
        sold_at__lt=timezone.make_aware(datetime.combine(end_date, datetime.min.time())),
    )

    if location:
        # If ClothingSale has location field, filter by it
        if hasattr(ClothingSale, "location"):
            sales_qs = sales_qs.filter(location=location)

    return sales_qs


def clothing_sales_metrics(
    business,
    *,
    location=None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = "mtd",
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate comprehensive sales metrics for clothing vertical with date filtering.

    Args:
        business: Business instance
        location: Optional location filter
        start_date: Optional explicit start date (inclusive)
        end_date: Optional explicit end date (exclusive)
        period: One of "today", "7d", "mtd", "date" (used if start/end not provided)
        date_str: Specific date string for period="date"

    Returns:
        Dictionary with KPIs, payment mix, top models, sales trend, and overhead costs
    """
    from inventory.models_verticals import ClothingSale

    # Determine date range
    if start_date is None or end_date is None:
        start_date, end_date = _compute_date_range(period, date_str)

    # Build base sales queryset using unified helper
    sales_qs = clothing_sales_queryset(
        business=business,
        location=location,
        start_date=start_date,
        end_date=end_date,
        period=period,
        date_str=date_str,
    )

    # Revenue, Cost, Profit (Sales COGS)
    sales_aggregates = sales_qs.aggregate(
        revenue=Coalesce(Sum("total_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
        cost=Coalesce(Sum("total_cost"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
        total_sales=Count("id"),
    )

    revenue = sales_aggregates["revenue"] or Decimal("0.00")
    cost_of_goods = sales_aggregates["cost"] or Decimal("0.00")
    total_sales = sales_aggregates["total_sales"] or 0

    # Get overhead costs for the period
    try:
        from wallet.utils import compute_business_costs

        overhead_data = compute_business_costs(business, start_date, end_date - timedelta(days=1))
        overhead_costs = overhead_data["total"]
    except Exception:
        # Gracefully degrade if wallet module not available
        overhead_costs = Decimal("0.00")

    # Calculate profit (revenue - COGS - overhead)
    profit = revenue - cost_of_goods - overhead_costs

    # Payment Mix
    payment_mix = (
        sales_qs.values("payment_method")
        .annotate(total=Coalesce(Sum("total_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD), count=Count("id"))
        .order_by("-total")
    )

    payment_mix_data = []
    if revenue > 0:
        for pm in payment_mix:
            pct = (pm["total"] / revenue) * 100
            from inventory.models_verticals import ClothingSale as CS

            payment_mix_data.append(
                {
                    "method": pm["payment_method"],
                    "method_display": dict(CS._meta.get_field("payment_method").choices).get(
                        pm["payment_method"], pm["payment_method"]
                    ),
                    "total": pm["total"],
                    "count": pm["count"],
                    "percentage": round(pct, 1),
                }
            )

    # Top Models
    top_models = (
        sales_qs.values("product__name")
        .annotate(
            units_sold=Sum("quantity"), revenue=Coalesce(Sum("total_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD)
        )
        .order_by("-units_sold")[:5]
    )

    top_model = top_models[0] if top_models else None

    # Sales Trend - DB-grouped-by-day, then fill missing days in Python
    # Group sales by day using TruncDate (DB-level grouping)
    daily_sales = (
        sales_qs.annotate(sale_date=TruncDate("sold_at"))
        .values("sale_date")
        .annotate(
            revenue=Coalesce(Sum("total_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
            cost=Coalesce(Sum("total_cost"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
            units_sold=Coalesce(Sum("quantity"), 0),
            count=Count("id"),
        )
        .order_by("sale_date")
    )

    # Build a dictionary for quick lookup
    sales_by_date = {}
    for day_data in daily_sales:
        sale_date = day_data["sale_date"]
        if sale_date:
            sales_by_date[sale_date.isoformat()] = {
                "revenue": float(day_data["revenue"] or 0),
                "cost": float(day_data["cost"] or 0),
                "profit": float((day_data["revenue"] or 0) - (day_data["cost"] or 0)),
                "units_sold": int(day_data["units_sold"] or 0),
                "count": day_data["count"] or 0,
            }

    # Fill missing days in Python (no row-iteration, just date range iteration)
    sales_trend = []
    current_date = start_date
    while current_date < end_date:
        date_key = current_date.isoformat()
        day_data = sales_by_date.get(
            date_key, {"revenue": 0.0, "cost": 0.0, "profit": 0.0, "units_sold": 0, "count": 0}
        )

        sales_trend.append(
            {
                "date": current_date.strftime("%Y-%m-%d"),
                "date_short": current_date.strftime("%b %d"),
                "revenue": day_data["revenue"],
                "profit": day_data["profit"],
                "units_sold": day_data["units_sold"],
                "count": day_data["count"],
            }
        )

        current_date += timedelta(days=1)

    return {
        "revenue": revenue,
        "cost_of_goods": cost_of_goods,
        "overhead_costs": overhead_costs,
        "profit": profit,
        "total_sales": total_sales,
        "payment_mix_data": payment_mix_data,
        "top_models": top_models,
        "top_model": top_model,
        "sales_trend": sales_trend,
        "period_start": start_date,
        "period_end": end_date,
    }


def clothing_inventory_metrics(
    business,
    *,
    location=None,
) -> Dict[str, Any]:
    """
    Calculate inventory value metrics for clothing vertical.
    These reflect current stock values, not sales.

    Uses Coalesce to handle null prices and excludes archived/qty<=0 products.

    Args:
        business: Business instance
        location: Optional location filter (if MerchProduct has location field)

    Returns:
        Dictionary with inventory_value, retail_value, and expected_margin
    """
    from inventory.models import MerchProduct
    from inventory.business_kinds import BusinessKind

    # Build base queryset for clothing products with stock
    # Exclude archived and qty<=0 products
    products_qs = MerchProduct.objects.filter(
        business=business, kind=BusinessKind.CLOTHING, is_active=True, is_archived=False, quantity_in_stock__gt=0
    )

    # Note: MerchProduct doesn't have a location field in the base model,
    # but if it's added in the future, we can filter here
    # if location and hasattr(MerchProduct, 'location'):
    #     products_qs = products_qs.filter(location=location)

    # Use Coalesce to handle null prices (default to 0)
    # Calculate inventory value (cost basis) = sum(qty_on_hand * Coalesce(cost_price, 0))
    # Calculate retail value = sum(qty_on_hand * Coalesce(selling_price, 0))
    # Use ExpressionWrapper to ensure proper output_field for arithmetic operations
    line_cost = ExpressionWrapper(
        F("quantity_in_stock") * Coalesce(F("cost_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
        output_field=DECIMAL_FIELD,
    )

    line_retail = ExpressionWrapper(
        F("quantity_in_stock") * Coalesce(F("selling_price"), DECIMAL_ZERO, output_field=DECIMAL_FIELD),
        output_field=DECIMAL_FIELD,
    )

    inventory_agg = products_qs.aggregate(total=Coalesce(Sum(line_cost), DECIMAL_ZERO, output_field=DECIMAL_FIELD))

    retail_agg = products_qs.aggregate(total=Coalesce(Sum(line_retail), DECIMAL_ZERO, output_field=DECIMAL_FIELD))

    inventory_value = Decimal(str(inventory_agg["total"] or 0))
    retail_value = Decimal(str(retail_agg["total"] or 0))

    # Expected margin = retail_value - inventory_value
    expected_margin = retail_value - inventory_value

    return {
        "inventory_value": inventory_value,
        "retail_value": retail_value,
        "expected_margin": expected_margin,
    }


def phone_sales_metrics(
    business,
    *,
    location=None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period: str = "mtd",
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate comprehensive sales metrics for phones vertical with date filtering.

    Phones use InventoryItem model where each phone is tracked individually with IMEI.
    Sales are recorded by setting status="SOLD" and sold_at timestamp.

    Args:
        business: Business instance
        location: Optional location filter
        start_date: Optional explicit start date (inclusive)
        end_date: Optional explicit end date (exclusive)
        period: One of "today", "7d", "mtd", "date" (used if start/end not provided)
        date_str: Specific date string for period="date"

    Returns:
        Dictionary with KPIs, payment mix, stock metrics, top models, and top agents
    """
    from django.db.models.functions import Coalesce
    from inventory.models import InventoryItem

    # Determine date range
    if start_date is None or end_date is None:
        start_date, end_date = _compute_date_range(period, date_str)

    # Convert dates to timezone-aware datetimes for filtering
    start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
    end_dt = timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.min.time()))

    # Base queryset for sold items
    sold_items = InventoryItem.objects.filter(
        business=business,
        status="SOLD",
        sold_at__isnull=False,
        sold_at__gte=start_dt,
        sold_at__lt=end_dt,
    ).select_related("product", "assigned_agent")

    if location:
        sold_items = sold_items.filter(current_location=location)

    # Units sold
    units_sold = sold_items.count()

    # Revenue (sum of selling prices)
    revenue = sold_items.aggregate(total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField()))[
        "total"
    ] or Decimal("0.00")

    # Cost of Goods (sum of order prices for sold items)
    cost_of_goods = sold_items.aggregate(
        total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    # Business Costs (overhead from Admin Wallet)
    try:
        from wallet.utils import compute_business_costs

        overhead_data = compute_business_costs(business, start_date, end_date - timedelta(days=1))
        overhead_costs = overhead_data["total"]
    except Exception:
        overhead_costs = Decimal("0.00")

    # Total costs and profit
    total_costs = cost_of_goods + overhead_costs
    profit = revenue - total_costs
    profit_margin = (profit / revenue * 100) if revenue > 0 else Decimal("0.00")

    # Payment Mix
    payment_totals = sold_items.aggregate(
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

    # Calculate percentages
    if revenue > 0:
        cash_pct = int(round((cash_amount / revenue) * 100))
        bank_pct = int(round((bank_amount / revenue) * 100))
        mobile_pct = 100 - cash_pct - bank_pct
    else:
        cash_pct = bank_pct = mobile_pct = 0

    payment_mix_data = [
        {"method": "Cash", "method_code": "CASH", "amount": cash_amount, "percentage": cash_pct},
        {"method": "Bank", "method_code": "BANK", "amount": bank_amount, "percentage": bank_pct},
        {"method": "Mobile Money", "method_code": "MOBILE_MONEY", "amount": mobile_amount, "percentage": mobile_pct},
    ]

    # Stock on hand (current snapshot, not date-filtered)
    stock_items = InventoryItem.objects.filter(business=business, status="IN_STOCK", is_active=True)

    if location:
        stock_items = stock_items.filter(current_location=location)

    stock_on_hand = stock_items.count()

    # Stock value (sum of order prices for items in stock)
    stock_cost_value = stock_items.aggregate(
        total=Coalesce(Sum("order_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    stock_selling_value = stock_items.aggregate(
        total=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
    )["total"] or Decimal("0.00")

    # Top Models (by units sold in selected period)
    top_models = (
        sold_items.values("product__brand", "product__model", "product__variant")
        .annotate(
            units=Count("id"), revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )
        .order_by("-units")[:5]
    )

    top_models_list = []
    for item in top_models:
        brand = item["product__brand"] or "Unknown"
        model = item["product__model"] or "Unknown"
        variant = item["product__variant"] or ""

        top_models_list.append(
            {
                "brand": brand,
                "model": model,
                "variant": variant,
                "units": item["units"],
                "revenue": item["revenue"],
            }
        )

    # Top Agents (by number of sales, not revenue)
    # Calculate commission earned instead of revenue
    top_agents = (
        sold_items.filter(assigned_agent__isnull=False)
        .values(
            "assigned_agent__id", "assigned_agent__first_name", "assigned_agent__last_name", "assigned_agent__username"
        )
        .annotate(
            units=Count("id"), revenue=Coalesce(Sum("selling_price"), Decimal("0.00"), output_field=DecimalField())
        )
        .order_by("-units", "-revenue")[:5]
    )

    # Calculate commissions for top agents efficiently
    # Import Sale model to get commission data
    try:
        from sales.models import Sale
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Build filter for sales in the same period
        sale_filters = {"location__business": business}
        if start_date:
            sale_filters["sold_at__gte"] = start_date
        if end_date:
            sale_filters["sold_at__lt"] = end_date

        # Get commission totals per agent
        agent_commissions = (
            Sale.objects.filter(**sale_filters)
            .values("agent_id")
            .annotate(total_commission=Coalesce(Sum("commission_amount"), Decimal("0.00"), output_field=DecimalField()))
        )

        # Create lookup dict for quick access
        commission_by_agent = {item["agent_id"]: item["total_commission"] for item in agent_commissions}

    except (ImportError, Exception):
        # Fallback if Sale model doesn't exist or error occurs
        commission_by_agent = {}

    top_agents_list = []
    for item in top_agents:
        first_name = item["assigned_agent__first_name"] or ""
        last_name = item["assigned_agent__last_name"] or ""
        username = item["assigned_agent__username"] or "Unknown"
        agent_name = f"{first_name} {last_name}".strip() or username
        agent_id = item["assigned_agent__id"]

        # Get commission from lookup, or estimate as 3% of revenue
        commission_total = commission_by_agent.get(agent_id, item["revenue"] * Decimal("0.03"))

        top_agents_list.append(
            {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "units": item["units"],
                "commission": commission_total,  # Changed from 'revenue' to 'commission'
            }
        )

    return {
        # Core metrics
        "units_sold": units_sold,
        "revenue": revenue,
        "cost_of_goods": cost_of_goods,
        "overhead_costs": overhead_costs,
        "total_costs": total_costs,
        "profit": profit,
        "profit_margin": profit_margin,
        # Stock metrics
        "stock_on_hand": stock_on_hand,
        "stock_cost_value": stock_cost_value,
        "stock_selling_value": stock_selling_value,
        "stock_potential_profit": stock_selling_value - stock_cost_value,
        # Payment mix
        "payment_mix_data": payment_mix_data,
        # Top performers
        "top_models": top_models_list,
        "top_agents": top_agents_list,
        # Period info
        "period_start": start_date,
        "period_end": end_date,
    }
