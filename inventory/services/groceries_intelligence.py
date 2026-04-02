# inventory/services/groceries_intelligence.py
"""
Groceries Intelligence Service — inventory analytics, sales insights,
smart restocking, and expiry management for the grocery vertical.

Follows the single source of truth principle: all metrics computed from
canonical MerchProduct and GrocerySale models.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Max, Sum, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def get_inventory_intelligence(business) -> dict:
    """
    Comprehensive inventory analytics for groceries dashboard.
    Returns stock health, turnover, and categorized product analysis.
    """
    try:
        from inventory.models import MerchProduct
        from inventory.models_verticals import GrocerySale
    except ImportError:
        return {}

    products = MerchProduct.objects.filter(business=business, kind="grocery", is_active=True)
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)

    total_products = products.count()
    in_stock = products.filter(quantity_in_stock__gt=0).count()
    out_of_stock = products.filter(quantity_in_stock=0).count()
    low_stock = products.filter(quantity_in_stock__gt=0, quantity_in_stock__lt=10).count()

    stock_value = sum(
        ((p.quantity_in_stock or 0) * (p.cost_price or ZERO) for p in products), ZERO,
    )

    # Turnover analysis: units sold / avg stock
    sales_30d = GrocerySale.objects.filter(business=business, sold_at__date__gte=thirty_days_ago)
    total_sold = sales_30d.aggregate(total=Sum("quantity"))["total"] or 0
    total_stock = sum((p.quantity_in_stock or 0 for p in products), 0)
    turnover_rate = round(total_sold / max(total_stock, 1) * 30, 1)

    # Fast-moving items (top 10 by quantity sold)
    fast_movers = (
        sales_30d.values("product__name", "product__id")
        .annotate(total_sold=Sum("quantity"), revenue=Sum("total_price"))
        .order_by("-total_sold")[:10]
    )

    # Slow-moving items (in stock but no sales in 30 days)
    sold_product_ids = set(sales_30d.values_list("product_id", flat=True))
    slow_movers = [
        {"name": p.name, "stock": p.quantity_in_stock, "cost_price": p.cost_price}
        for p in products.filter(quantity_in_stock__gt=5).exclude(id__in=sold_product_ids)[:10]
    ]

    # Category performance
    category_perf = (
        sales_30d.values("product__category")
        .annotate(
            total_revenue=Sum("total_price"),
            total_units=Sum("quantity"),
            avg_profit=Avg(F("total_price") - F("total_cost")),
        )
        .order_by("-total_revenue")
    )

    return {
        "total_products": total_products,
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "low_stock": low_stock,
        "stock_value": stock_value,
        "turnover_rate": turnover_rate,
        "total_sold_30d": total_sold,
        "fast_movers": list(fast_movers),
        "slow_movers": slow_movers,
        "category_performance": list(category_perf),
    }


def get_sales_analytics(business, days=30) -> dict:
    """Daily sales trends, peak hours, and product performance."""
    try:
        from inventory.models_verticals import GrocerySale
    except ImportError:
        return {}

    today = timezone.now().date()
    since = today - timedelta(days=days)

    sales = GrocerySale.objects.filter(business=business, sold_at__date__gte=since)

    # Daily sales trend
    daily_trend = (
        sales.annotate(date=TruncDate("sold_at"))
        .values("date")
        .annotate(
            revenue=Sum("total_price"),
            units=Sum("quantity"),
            profit=Sum(F("total_price") - F("total_cost")),
            transactions=Count("id"),
        )
        .order_by("date")
    )

    # Totals
    totals = sales.aggregate(
        total_revenue=Sum("total_price"),
        total_cost=Sum("total_cost"),
        total_units=Sum("quantity"),
        total_transactions=Count("id"),
    )
    revenue = totals["total_revenue"] or ZERO
    cost = totals["total_cost"] or ZERO

    # Payment method breakdown
    payment_mix = (
        sales.values("payment_method")
        .annotate(count=Count("id"), total=Sum("total_price"))
        .order_by("-total")
    )

    # Sale mode breakdown (retail vs wholesale)
    mode_mix = (
        sales.values("sale_mode")
        .annotate(count=Count("id"), total=Sum("total_price"))
        .order_by("-total")
    )

    # Top products by revenue
    top_products = (
        sales.values("product__name")
        .annotate(revenue=Sum("total_price"), units=Sum("quantity"))
        .order_by("-revenue")[:10]
    )

    # Average basket size
    avg_basket = round(float(revenue / max(totals["total_transactions"] or 1, 1)), 2)

    return {
        "daily_trend": list(daily_trend),
        "total_revenue": revenue,
        "total_cost": cost,
        "total_profit": revenue - cost,
        "total_units": totals["total_units"] or 0,
        "total_transactions": totals["total_transactions"] or 0,
        "avg_basket_value": avg_basket,
        "payment_mix": list(payment_mix),
        "mode_mix": list(mode_mix),
        "top_products": list(top_products),
    }


def get_restock_recommendations(business) -> list[dict]:
    """
    Smart restocking recommendations based on sales velocity and current stock.
    """
    try:
        from inventory.models import MerchProduct
        from inventory.models_verticals import GrocerySale
    except ImportError:
        return []

    products = MerchProduct.objects.filter(business=business, kind="grocery", is_active=True)
    today = timezone.now().date()
    fourteen_days_ago = today - timedelta(days=14)

    recommendations = []

    for product in products[:100]:
        recent_sales = GrocerySale.objects.filter(
            business=business, product=product, sold_at__date__gte=fourteen_days_ago,
        )
        total_sold = recent_sales.aggregate(total=Sum("quantity"))["total"] or 0
        daily_rate = total_sold / 14.0

        if daily_rate <= 0:
            continue

        current_stock = product.quantity_in_stock or 0
        days_of_stock = current_stock / daily_rate if daily_rate > 0 else 999

        if days_of_stock < 7:
            reorder_qty = max(int(daily_rate * 14) - current_stock, 1)
            urgency = "critical" if days_of_stock < 3 else "soon"
            recommendations.append({
                "product_id": product.id,
                "product_name": product.name,
                "current_stock": current_stock,
                "daily_rate": round(daily_rate, 1),
                "days_of_stock": round(days_of_stock, 1),
                "recommended_order": reorder_qty,
                "estimated_cost": float(reorder_qty * (product.cost_price or ZERO)),
                "urgency": urgency,
            })

    recommendations.sort(key=lambda x: x["days_of_stock"])
    return recommendations[:20]


def get_expiry_alerts(business) -> list[dict]:
    """
    Products approaching expiry or at spoilage risk.
    Uses track_expiry flag on MerchProduct.
    """
    try:
        from inventory.models import MerchProduct
    except ImportError:
        return []

    products = MerchProduct.objects.filter(
        business=business, kind="grocery", is_active=True, track_expiry=True,
    )

    alerts = []
    for p in products[:50]:
        if p.quantity_in_stock and p.quantity_in_stock > 0:
            alerts.append({
                "product_name": p.name,
                "stock": p.quantity_in_stock,
                "cost_at_risk": float((p.quantity_in_stock or 0) * (p.cost_price or ZERO)),
                "category": p.category or "uncategorized",
            })

    return alerts
