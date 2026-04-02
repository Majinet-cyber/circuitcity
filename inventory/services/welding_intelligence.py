# inventory/services/welding_intelligence.py
"""
Welding Workshop Intelligence Service — production analytics, client insights,
job profitability, and material usage intelligence.

Single source of truth: all metrics derived from canonical welding models.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def get_workshop_intelligence(business) -> dict:
    """
    Comprehensive workshop analytics: jobs, materials, revenue, profitability.
    """
    try:
        from inventory.models_welding import (
            WeldingCost, WeldingJob, WeldingMaterial,
            WeldingQuote, WeldingRevenue, WeldingInvoice,
        )
    except ImportError:
        return {}

    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    # --- Job metrics ---
    jobs = WeldingJob.objects.filter(business=business)
    active_jobs = jobs.filter(status__in=["pending", "in_progress"]).count()
    completed_30d = jobs.filter(
        status__in=["ready", "delivered"],
        completed_at__date__gte=thirty_days_ago,
    ).count()
    delayed_jobs = jobs.filter(status="pending", created_at__date__lt=seven_days_ago).count()

    # Average completion time
    completed_with_dates = jobs.filter(
        started_at__isnull=False, completed_at__isnull=False,
    )
    avg_days = None
    if completed_with_dates.exists():
        total_days = sum(
            (j.completed_at - j.started_at).days for j in completed_with_dates[:50]
        )
        avg_days = round(total_days / completed_with_dates.count(), 1)

    # --- Revenue & costs ---
    revenue_30d = WeldingRevenue.objects.filter(
        business=business, received_on__gte=thirty_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    costs_30d = WeldingCost.objects.filter(
        business=business, incurred_on__gte=thirty_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    profit_30d = revenue_30d - costs_30d

    # Revenue trend (daily)
    revenue_trend = (
        WeldingRevenue.objects.filter(business=business, received_on__gte=thirty_days_ago)
        .annotate(date=TruncDate("received_on"))
        .values("date")
        .annotate(total=Sum("amount"))
        .order_by("date")
    )

    # --- Quote metrics ---
    quotes = WeldingQuote.objects.filter(business=business)
    quotes_30d = quotes.filter(created_at__date__gte=thirty_days_ago).count()
    accepted_30d = quotes.filter(status="accepted", created_at__date__gte=thirty_days_ago).count()
    conversion_rate = round(accepted_30d / max(quotes_30d, 1) * 100, 1)

    # --- Material metrics ---
    materials = WeldingMaterial.objects.filter(business=business, is_active=True)
    total_materials = materials.count()
    materials_value = sum(
        (m.quantity_in_stock * m.price_mwk for m in materials), ZERO,
    )
    low_stock_materials = [
        {"name": m.name, "stock": float(m.quantity_in_stock), "threshold": float(m.low_stock_threshold or 0)}
        for m in materials if m.is_low_stock
    ]

    # --- Cost breakdown by category ---
    cost_by_category = (
        WeldingCost.objects.filter(business=business, incurred_on__gte=thirty_days_ago)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    return {
        "active_jobs": active_jobs,
        "completed_30d": completed_30d,
        "delayed_jobs": delayed_jobs,
        "avg_completion_days": avg_days,
        "revenue_30d": revenue_30d,
        "costs_30d": costs_30d,
        "profit_30d": profit_30d,
        "profit_margin": round(float(profit_30d / max(revenue_30d, Decimal("1"))) * 100, 1),
        "quotes_30d": quotes_30d,
        "accepted_30d": accepted_30d,
        "conversion_rate": conversion_rate,
        "total_materials": total_materials,
        "materials_value": materials_value,
        "low_stock_materials": low_stock_materials,
        "cost_by_category": list(cost_by_category),
        "revenue_trend": list(revenue_trend),
    }


def get_client_analytics(business) -> dict:
    """Client management analytics: top clients, repeat rates, revenue per client."""
    try:
        from inventory.models_welding import WeldingJob, WeldingQuote, WeldingRevenue
    except ImportError:
        return {}

    thirty_days_ago = timezone.now().date() - timedelta(days=30)

    # Top clients by job count
    top_clients_jobs = (
        WeldingJob.objects.filter(business=business)
        .values("customer_name", "customer_phone")
        .annotate(
            job_count=Count("id"),
            total_quoted=Sum("quoted_price"),
        )
        .order_by("-job_count")[:10]
    )

    # Top clients by quote value
    top_clients_value = (
        WeldingQuote.objects.filter(business=business, status="accepted")
        .values("customer_name")
        .annotate(
            quote_count=Count("id"),
            total_value=Sum("total"),
        )
        .order_by("-total_value")[:10]
    )

    # Repeat client rate
    all_clients = WeldingJob.objects.filter(business=business).values("customer_phone").distinct().count()
    repeat_clients = (
        WeldingJob.objects.filter(business=business)
        .values("customer_phone")
        .annotate(jobs=Count("id"))
        .filter(jobs__gt=1)
        .count()
    )
    repeat_rate = round(repeat_clients / max(all_clients, 1) * 100, 1)

    return {
        "top_clients_by_jobs": list(top_clients_jobs),
        "top_clients_by_value": list(top_clients_value),
        "total_unique_clients": all_clients,
        "repeat_clients": repeat_clients,
        "repeat_rate": repeat_rate,
    }


def get_production_insights(business) -> list[dict]:
    """Production intelligence insights for the welding workshop."""
    try:
        from inventory.models_welding import (
            WeldingCost, WeldingJob, WeldingMaterial, WeldingQuote, WeldingRevenue,
        )
    except ImportError:
        return []

    insights = []
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)

    # Delayed jobs warning
    delayed = WeldingJob.objects.filter(
        business=business, status="pending", created_at__date__lt=seven_days_ago,
    ).count()
    if delayed > 0:
        insights.append({
            "icon": "bi-clock-history",
            "text": f"{delayed} job(s) have been pending for over a week — review priorities.",
            "type": "warning",
        })

    # Material cost trend
    recent_costs = WeldingCost.objects.filter(
        business=business, category="consumables", incurred_on__gte=seven_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    older_costs = WeldingCost.objects.filter(
        business=business, category="consumables",
        incurred_on__gte=thirty_days_ago, incurred_on__lt=seven_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    if older_costs > 0 and recent_costs > older_costs * Decimal("1.2"):
        insights.append({
            "icon": "bi-graph-up",
            "text": "Material costs rising — consumables spending up this week vs. monthly average.",
            "type": "warning",
        })

    # Quote conversion
    quotes_30d = WeldingQuote.objects.filter(
        business=business, created_at__date__gte=thirty_days_ago,
    ).count()
    accepted = WeldingQuote.objects.filter(
        business=business, status="accepted", created_at__date__gte=thirty_days_ago,
    ).count()
    if quotes_30d > 5 and (accepted / quotes_30d) < 0.3:
        insights.append({
            "icon": "bi-percent",
            "text": f"Quote acceptance rate is low ({accepted}/{quotes_30d}). Review pricing strategy.",
            "type": "info",
        })

    # Profitability
    rev = WeldingRevenue.objects.filter(
        business=business, received_on__gte=thirty_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    cost = WeldingCost.objects.filter(
        business=business, incurred_on__gte=thirty_days_ago,
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    if rev > 0:
        margin = float((rev - cost) / rev * 100)
        if margin < 15:
            insights.append({
                "icon": "bi-exclamation-triangle",
                "text": f"Profit margin is only {margin:.0f}% this month — below healthy threshold.",
                "type": "danger",
            })
        elif margin > 40:
            insights.append({
                "icon": "bi-trophy",
                "text": f"Strong profit margin of {margin:.0f}% this month.",
                "type": "success",
            })

    # Low stock materials
    low_stock = WeldingMaterial.objects.filter(business=business, is_active=True)
    low_count = sum(1 for m in low_stock if m.is_low_stock)
    if low_count > 0:
        insights.append({
            "icon": "bi-box-seam",
            "text": f"{low_count} material(s) below restock threshold — order soon.",
            "type": "warning",
        })

    return insights[:8]
