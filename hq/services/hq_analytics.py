# hq/services/hq_analytics.py
"""
HQ Analytics Service Layer
Provides filter-driven analytics data for HQ Command Center charts.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from collections import defaultdict

from django.db.models import Sum, Count, Q, F, Value, DecimalField, Case, When, IntegerField, Avg
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone

from tenants.models import Business, Membership
from sales.models import Sale, PaymentMethod
from inventory.models import InventoryItem, Location
from billing.models import Subscription, Invoice


def get_hq_analytics_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    vertical: Optional[str] = None,
    payment_mode: Optional[str] = None,
    location_id: Optional[int] = None,
    sale_type: Optional[str] = None,  # 'credit' or 'cash' - if system supports
) -> Dict[str, Any]:
    """
    Main entry point for HQ analytics data.
    Returns a comprehensive dict with KPIs, chart series, and breakdowns.

    All filters are optional. If not provided, aggregates across all data.
    """
    # Default date range: last 30 days
    if not end_date:
        end_date = timezone.now().date()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Build base querysets
    sales_qs = _build_sales_queryset(
        start_date=start_date,
        end_date=end_date,
        business_id=business_id,
        agent_id=agent_id,
        vertical=vertical,
        payment_mode=payment_mode,
        location_id=location_id,
        sale_type=sale_type,
    )

    # Aggregate KPIs
    kpis = _get_kpis(sales_qs, start_date, end_date, business_id, vertical)

    # Chart series (daily trends)
    series = _get_chart_series(sales_qs, start_date, end_date)

    # Breakdowns (for pie/bar charts)
    breakdowns = _get_breakdowns(sales_qs, business_id, vertical)

    # Top lists
    top_lists = _get_top_lists(sales_qs, business_id, vertical)

    return {
        "kpis": kpis,
        "series": series,
        "breakdowns": breakdowns,
        "top_lists": top_lists,
    }


def _build_sales_queryset(
    start_date: date,
    end_date: date,
    business_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    vertical: Optional[str] = None,
    payment_mode: Optional[str] = None,
    location_id: Optional[int] = None,
    sale_type: Optional[str] = None,
):
    """Build filtered sales queryset."""
    # Start with all sales in date range
    qs = Sale.objects.filter(
        sold_at__gte=start_date,
        sold_at__lte=end_date,
    ).select_related("item", "agent", "location", "item__business")

    # Filter by business (via item.business)
    if business_id:
        qs = qs.filter(item__business_id=business_id)

    # Filter by vertical (via item.business.vertical/business_kind)
    if vertical:
        # Try different field names for vertical
        qs = qs.filter(Q(item__business__business_kind__iexact=vertical) | Q(item__business__vertical__iexact=vertical))

    # Filter by agent
    if agent_id:
        qs = qs.filter(agent_id=agent_id)

    # Filter by location
    if location_id:
        qs = qs.filter(location_id=location_id)

    # Filter by payment mode
    if payment_mode:
        qs = qs.filter(payment_method=payment_mode)

    # Filter by sale type (credit vs cash sale)
    # This is a placeholder - adjust based on your actual model structure
    # For now, we'll use payment_method as a proxy
    if sale_type == "credit":
        # If you have a credit field, use it; otherwise skip
        pass
    elif sale_type == "cash":
        qs = qs.filter(payment_method=PaymentMethod.CASH)

    return qs


def _get_kpis(
    sales_qs,
    start_date: date,
    end_date: date,
    business_id: Optional[int],
    vertical: Optional[str],
) -> Dict[str, Any]:
    """Calculate KPIs from sales queryset."""
    zero_dec = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))

    # Revenue
    revenue = sales_qs.aggregate(total=Coalesce(Sum("price"), zero_dec))["total"] or Decimal("0.00")

    # Sales count
    sales_count = sales_qs.count()

    # Profit (revenue - cost of goods)
    # Use cost_price field (the canonical cost field on InventoryItem)
    zero_cost = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    profit_annotation = F("price") - Coalesce(F("item__cost_price"), zero_cost)
    profit_data = sales_qs.annotate(profit=profit_annotation).aggregate(total_profit=Coalesce(Sum("profit"), zero_dec))
    profit = profit_data["total_profit"] or Decimal("0.00")

    # Cost of goods
    cost_data = sales_qs.aggregate(
        total_cost=Coalesce(Sum(Coalesce(F("item__cost_price"), zero_cost)), zero_dec)
    )
    cost_of_goods = cost_data["total_cost"] or Decimal("0.00")

    # Additional KPIs based on filters
    active_businesses = Business.objects.all()
    if business_id:
        active_businesses = active_businesses.filter(pk=business_id)
    if vertical:
        active_businesses = active_businesses.filter(Q(business_kind__iexact=vertical) | Q(vertical__iexact=vertical))
    total_businesses = active_businesses.count()

    active_agents = Membership.objects.filter(role="AGENT")
    if business_id:
        active_agents = active_agents.filter(business_id=business_id)
    total_agents = active_agents.count()

    # Stock value (if inventory verticals)
    stock_value = Decimal("0.00")
    retail_value = Decimal("0.00")
    expected_margin = Decimal("0.00")

    if not vertical or vertical.lower() != "gym":
        # Calculate stock value for inventory-based verticals
        inv_qs = InventoryItem.objects.filter(status__in=["AVAILABLE", "IN_STOCK"])
        if business_id:
            inv_qs = inv_qs.filter(business_id=business_id)
        if vertical:
            # Filter by business vertical
            inv_qs = inv_qs.filter(Q(business__business_kind__iexact=vertical) | Q(business__vertical__iexact=vertical))

        # Stock value (cost basis, using cost_price field)
        stock_value_data = inv_qs.aggregate(
            total=Coalesce(Sum(Coalesce(F("cost_price"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)))), zero_dec)
        )
        stock_value = stock_value_data["total"] or Decimal("0.00")

        # Retail value
        retail_value_data = inv_qs.aggregate(total=Coalesce(Sum("price"), zero_dec))
        retail_value = retail_value_data["total"] or Decimal("0.00")

        # Expected margin
        expected_margin = retail_value - stock_value

    return {
        "revenue": float(revenue),
        "sales_count": sales_count,
        "profit": float(profit),
        "cost_of_goods": float(cost_of_goods),
        "total_businesses": total_businesses,
        "total_agents": total_agents,
        "stock_value": float(stock_value),
        "retail_value": float(retail_value),
        "expected_margin": float(expected_margin),
    }


def _get_chart_series(
    sales_qs,
    start_date: date,
    end_date: date,
) -> Dict[str, List[Dict[str, Any]]]:
    """Get daily trend series for line charts."""
    from django.db import connection

    # SQLite-safe daily aggregation
    if connection.vendor == "sqlite":
        # Fetch raw data and group in Python
        sales_raw = sales_qs.values("sold_at", "price", "id").order_by("sold_at")
        from collections import defaultdict

        daily_data = defaultdict(lambda: {"revenue": Decimal("0.00"), "count": 0})

        for sale in sales_raw:
            if sale["sold_at"]:
                day = sale["sold_at"].date() if hasattr(sale["sold_at"], "date") else sale["sold_at"]
                daily_data[day]["revenue"] += Decimal(str(sale["price"] or 0))
                daily_data[day]["count"] += 1

        daily_revenue = [
            {"day": day, "revenue": data["revenue"], "count": data["count"]} for day, data in sorted(daily_data.items())
        ]
    else:
        # PostgreSQL/MySQL: use DB-level aggregation
        daily_revenue = (
            sales_qs.annotate(day=TruncDate("sold_at"))
            .values("day")
            .annotate(
                revenue=Coalesce(Sum("price"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))),
                count=Count("id"),
            )
            .order_by("day")
        )

    revenue_trend = []
    sales_count_trend = []
    profit_trend = []

    # Build profit map (using cost_price field)
    profit_map = {}
    zero_cost = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
    if connection.vendor == "sqlite":
        # Calculate profit in Python for SQLite
        sales_for_profit = sales_qs.select_related("item").values(
            "sold_at", "price", "item__cost_price"
        )
        daily_profit_data = defaultdict(Decimal)

        for sale in sales_for_profit:
            if sale["sold_at"]:
                day = sale["sold_at"].date() if hasattr(sale["sold_at"], "date") else sale["sold_at"]
                price = Decimal(str(sale["price"] or 0))
                cost = Decimal(str(sale["item__cost_price"] or 0))
                daily_profit_data[day] += price - cost

        profit_map = {day: float(profit) for day, profit in daily_profit_data.items()}
    else:
        # PostgreSQL/MySQL: use DB-level aggregation
        profit_annotation = F("price") - Coalesce(F("item__cost_price"), zero_cost)

        daily_profit = (
            sales_qs.annotate(day=TruncDate("sold_at"), profit=profit_annotation)
            .values("day")
            .annotate(
                total_profit=Coalesce(
                    Sum("profit"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
                )
            )
            .order_by("day")
        )

        profit_map = {item["day"]: float(item["total_profit"]) for item in daily_profit if item["day"]}

    # Fill in all days in range (including days with no sales)
    current = start_date
    while current <= end_date:
        day_str = current.isoformat()
        day_short = current.strftime("%m/%d")

        # Find matching day data
        day_data = next((d for d in daily_revenue if d["day"] == current), None)

        revenue_trend.append(
            {
                "date": day_str,
                "date_short": day_short,
                "revenue": float(day_data["revenue"]) if day_data else 0.0,
            }
        )

        sales_count_trend.append(
            {
                "date": day_str,
                "date_short": day_short,
                "count": day_data["count"] if day_data else 0,
            }
        )

        profit_trend.append(
            {
                "date": day_str,
                "date_short": day_short,
                "profit": profit_map.get(current, 0.0),
            }
        )

        current += timedelta(days=1)

    return {
        "revenue_trend": revenue_trend,
        "sales_count_trend": sales_count_trend,
        "profit_trend": profit_trend,
    }


def _get_breakdowns(
    sales_qs,
    business_id: Optional[int],
    vertical: Optional[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Get breakdowns for pie/bar charts."""
    zero_dec = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))

    # Cash mix (payment method breakdown)
    payment_mix = (
        sales_qs.values("payment_method")
        .annotate(total=Coalesce(Sum("price"), zero_dec), count=Count("id"))
        .order_by("-total")
    )

    total_amount = sum(float(pm["total"] or 0) for pm in payment_mix)
    cash_mix = []
    for pm in payment_mix:
        amount = float(pm["total"] or 0)
        method = pm["payment_method"] or "UNKNOWN"
        # Get display name from PaymentMethod choices
        method_display = dict(PaymentMethod.choices).get(method, method)
        cash_mix.append(
            {
                "method": method,
                "method_display": method_display,
                "amount": amount,
                "count": pm["count"],
                "percentage": (amount / total_amount * 100) if total_amount > 0 else 0,
            }
        )

    # Vertical mix (revenue by vertical)
    vertical_mix = []
    if not business_id:  # Only show if not filtering by business
        # Aggregate by business vertical
        vertical_agg = (
            sales_qs.values("item__business__business_kind", "item__business__vertical")
            .annotate(revenue=Coalesce(Sum("price"), zero_dec), count=Count("id"))
            .order_by("-revenue")
        )

        total_vertical_revenue = sum(float(v["revenue"] or 0) for v in vertical_agg)
        for v in vertical_agg:
            vert = v["item__business__business_kind"] or v["item__business__vertical"] or "Unknown"
            amount = float(v["revenue"] or 0)
            vertical_mix.append(
                {
                    "vertical": vert,
                    "revenue": amount,
                    "count": v["count"],
                    "percentage": (amount / total_vertical_revenue * 100) if total_vertical_revenue > 0 else 0,
                }
            )

    return {
        "cash_mix": cash_mix,
        "vertical_mix": vertical_mix,
    }


def _get_top_lists(
    sales_qs,
    business_id: Optional[int],
    vertical: Optional[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Get top lists for bar charts."""
    zero_dec = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))

    # Top businesses by revenue
    top_businesses = []
    if not business_id:  # Only show if not filtering by business
        business_agg = (
            sales_qs.values("item__business_id", "item__business__name")
            .annotate(revenue=Coalesce(Sum("price"), zero_dec), count=Count("id"))
            .order_by("-revenue")[:10]
        )

        for b in business_agg:
            top_businesses.append(
                {
                    "business_id": b["item__business_id"],
                    "name": b["item__business__name"] or f"Business #{b['item__business_id']}",
                    "revenue": float(b["revenue"] or 0),
                    "sales_count": b["count"],
                }
            )

    # Top agents by revenue
    agent_agg = (
        sales_qs.values("agent_id", "agent__username", "agent__first_name", "agent__last_name")
        .annotate(revenue=Coalesce(Sum("price"), zero_dec), count=Count("id"))
        .order_by("-revenue")[:10]
    )

    top_agents = []
    for a in agent_agg:
        name = f"{a['agent__first_name'] or ''} {a['agent__last_name'] or ''}".strip()
        if not name:
            name = a["agent__username"] or f"Agent #{a['agent_id']}"
        top_agents.append(
            {
                "agent_id": a["agent_id"],
                "name": name,
                "revenue": float(a["revenue"] or 0),
                "sales_count": a["count"],
            }
        )

    return {
        "top_businesses": top_businesses,
        "top_agents": top_agents,
    }
