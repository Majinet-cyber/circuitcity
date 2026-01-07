"""
Gym dashboard metrics service - single source of truth for financial KPIs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models_verticals import GymPayment, PaymentMethod


def get_gym_dashboard_metrics(business, start_date, end_date):
    """
    Calculate unified gym dashboard metrics for a given date range.

    This function provides a single source of truth for:
    - Payment count
    - Monthly revenue (sum of amounts)
    - Payment mix breakdown by method
    - All using the same base queryset with consistent filters

    Args:
        business: Business instance
        start_date: Start date (date object)
        end_date: End date (date object, inclusive)

    Returns:
        dict with keys:
            - payments_count: int
            - revenue: Decimal
            - payment_mix: list of dicts with 'method', 'count', 'amount'
    """
    # Build timezone-aware datetime range
    # Use localdate to avoid timezone conversion issues
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    # Ensure timezone-aware datetime boundaries
    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    # End date is inclusive, so use 23:59:59.999999
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

    # CRITICAL: Filter by is_active=True to exclude cancelled/refunded payments
    # This is the single source of truth queryset
    payments_qs = GymPayment.objects.filter(
        member__business=business,
        is_active=True,
        paid_at__gte=start_dt,
        paid_at__lte=end_dt,
    )

    # Payment count
    payments_count = payments_qs.count()

    # Revenue: Use Coalesce to ensure we get Decimal("0.00") instead of None
    # Only exclude payments with amount=None (null), but include amount=0 payments
    revenue_result = payments_qs.exclude(amount__isnull=True).aggregate(
        total=Coalesce(
            Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )
    revenue = revenue_result["total"]
    # Ensure revenue is a Decimal
    if revenue is None:
        revenue = Decimal("0.00")
    elif not isinstance(revenue, Decimal):
        revenue = Decimal(str(revenue))

    # Payment mix: Breakdown by payment method
    # Use the same queryset (excluding null amounts only)
    payment_mix_qs = payments_qs.exclude(amount__isnull=True)
    payment_mix_agg = (
        payment_mix_qs.values("payment_method")
        .annotate(
            count=Count("id"),
            total=Coalesce(
                Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=12, decimal_places=2)
            ),
        )
        .order_by("-total")
    )

    payment_mix = []
    for item in payment_mix_agg:
        method_code = item["payment_method"]
        method_display = dict(PaymentMethod.choices).get(method_code, method_code)
        amount = item["total"]
        if amount is None:
            amount = Decimal("0.00")
        elif not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        payment_mix.append(
            {
                "method": method_display,
                "count": item["count"],
                "amount": amount,
            }
        )

    return {
        "payments_count": payments_count,
        "revenue": revenue,
        "payment_mix": payment_mix,
    }


def get_this_month_metrics(business):
    """
    Get metrics for the current month (first day of month to today).

    Returns same structure as get_gym_dashboard_metrics.
    """
    today = timezone.localdate()
    month_start = today.replace(day=1)

    return get_gym_dashboard_metrics(business, month_start, today)
