# inventory/analytics/adapters/gym.py
"""
Analytics adapter for gym vertical.
Gym uses GymPayment instead of sales.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet, Sum, Count, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.models_verticals import GymPayment, GymMember
from inventory.analytics.adapters.base import AnalyticsAdapter
from inventory.analytics.common import (
    apply_business_scope,
    apply_location_filter,
    apply_payment_method_filter,
    apply_search_filter,
)
from wallet.models import WalletTransaction, Ledger, TxnType


class GymAdapter(AnalyticsAdapter):
    """Analytics adapter for gym vertical."""

    def get_sales_queryset(self, business, location=None) -> QuerySet:
        """Get base sales queryset (GymPayment for gym)."""
        qs = GymPayment.objects.filter(member__business=business, is_active=True).select_related(
            "member", "paid_by", "trainer"
        )
        # GymPayment doesn't have location, so location filter is ignored
        return qs

    def get_stock_queryset(self, business, location=None) -> QuerySet:
        """Get base stock queryset (GymMember for gym)."""
        qs = GymMember.objects.filter(business=business, is_archived=False)
        return qs

    def get_costs_queryset(self, business, location=None) -> QuerySet:
        """Get costs queryset."""
        qs = WalletTransaction.objects.filter(
            business=business, ledger=Ledger.COMPANY, type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        return qs

    def get_search_fields(self) -> List[str]:
        """Return search fields for gym."""
        return ["member__name", "member__phone", "member__email", "notes"]

    def kpis(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate KPIs for gym."""
        payments_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        payments_qs = payments_qs.filter(paid_at__gte=start_dt, paid_at__lt=end_dt)

        payments_qs = apply_payment_method_filter(payments_qs, payment_method)
        if search_query:
            payments_qs = apply_search_filter(payments_qs, search_query, self.get_search_fields())

        revenue = payments_qs.aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"] or Decimal("0.00")
        total_sales = payments_qs.count()
        avg_order_value = revenue / total_sales if total_sales > 0 else Decimal("0.00")

        # Gym doesn't have cost of goods, so profit = revenue - costs
        costs_qs = self.get_costs_queryset(business, location)
        costs_qs = costs_qs.filter(
            Q(type=TxnType.COST_ONCE_OFF, effective_date__gte=start_date, effective_date__lte=end_date)
            | Q(type=TxnType.COST_RECURRING, effective_from__lte=end_date)
        )
        costs = abs(costs_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))

        profit = revenue - costs
        gross_margin = Decimal("100.00")  # Gym has no COGS, so margin is 100% (or N/A)

        # Member metrics
        members_qs = self.get_stock_queryset(business, location)
        today = timezone.now().date()
        total_members = members_qs.count()
        active_memberships = members_qs.filter(membership_end__gte=today, status="ACTIVE").count()

        # New members today
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        today_end = timezone.make_aware(
            timezone.datetime.combine(today + timedelta(days=1), timezone.datetime.min.time())
        )
        new_members_today = members_qs.filter(joined_at__gte=today_start, joined_at__lt=today_end).count()

        # New members this month
        month_start = timezone.make_aware(timezone.datetime.combine(today.replace(day=1), timezone.datetime.min.time()))
        new_members_this_month = members_qs.filter(joined_at__gte=month_start, joined_at__lt=today_end).count()

        # Payments today
        payments_today = payments_qs.filter(paid_at__gte=today_start, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        # Payments this month
        payments_this_month = payments_qs.filter(paid_at__gte=month_start, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        # Revenue today (from payments in date range that are today)
        revenue_today = payments_qs.filter(paid_at__gte=today_start, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        # Revenue this month
        revenue_this_month = payments_qs.filter(paid_at__gte=month_start, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        # Churn (members whose membership ended in period but haven't renewed)
        churned = 0
        ended_memberships = members_qs.filter(membership_end__gte=start_date, membership_end__lte=end_date)
        for member in ended_memberships:
            # Check if they renewed (last payment after membership_end)
            last_payment = member.payments.filter(paid_at__date__gte=member.membership_end).first()
            if not last_payment:
                churned += 1

        return {
            "revenue": revenue,
            "profit": profit,
            "total_sales": total_sales,
            "avg_order_value": avg_order_value,
            "gross_margin": gross_margin,
            "costs": costs,
            # Gym-specific metrics
            "total_members": total_members,
            "active_memberships": active_memberships,
            "new_members_today": new_members_today,
            "new_members_this_month": new_members_this_month,
            "payments_today": payments_today,
            "payments_this_month": payments_this_month,
            "revenue_today": revenue_today,
            "revenue_this_month": revenue_this_month,
            "churned_members": churned,
        }

    def charts(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate chart data for gym."""
        payments_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        payments_qs = payments_qs.filter(paid_at__gte=start_dt, paid_at__lt=end_dt)

        payments_qs = apply_payment_method_filter(payments_qs, payment_method)
        if search_query:
            payments_qs = apply_search_filter(payments_qs, search_query, self.get_search_fields())

        # Sales trend (payment trend)
        daily_payments = (
            payments_qs.annotate(day=TruncDate("paid_at"))
            .values("day")
            .annotate(revenue=Coalesce(Sum("amount"), Decimal("0.00")), count=Count("id"))
            .order_by("day")
        )

        sales_trend = [
            {
                "date": str(item["day"]),
                "date_short": item["day"].strftime("%m/%d") if item["day"] else "",
                "revenue": float(item["revenue"]),
                "profit": float(item["revenue"]),  # Gym has no COGS
                "count": item["count"],
            }
            for item in daily_payments
        ]

        profit_trend = sales_trend

        # Payment mix
        payment_mix = (
            payments_qs.values("payment_method")
            .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")), count=Count("id"))
            .order_by("-total")
        )

        total_amount = sum(float(pm["total"]) for pm in payment_mix)
        payment_mix_data = []
        for pm in payment_mix:
            amount = float(pm["total"])
            method = pm["payment_method"] or "cash"
            method_display = dict(GymPayment._meta.get_field("payment_method").choices).get(
                method, method.replace("_", " ").title()
            )
            payment_mix_data.append(
                {
                    "method": method,
                    "method_display": method_display,
                    "amount": amount,
                    "percentage": (amount / total_amount * 100) if total_amount > 0 else 0,
                }
            )

        # Top products (not applicable for gym, but return empty for consistency)
        top_products_data = []

        # Top trainers
        top_agents = (
            payments_qs.filter(trainer__isnull=False)
            .values("trainer__id", "trainer__name")
            .annotate(revenue=Coalesce(Sum("amount"), Decimal("0.00")), count=Count("id"))
            .order_by("-revenue")[:10]
        )

        top_agents_data = [
            {
                "name": item["trainer__name"] or "Unknown",
                "revenue": float(item["revenue"]),
                "units_sold": item["count"],  # Payment count
            }
            for item in top_agents
        ]

        # Stock overview (members overview)
        members_qs = self.get_stock_queryset(business, location)
        today = timezone.now().date()
        active_members = members_qs.filter(membership_end__gte=today, status="ACTIVE").count()

        stock_overview = {
            "stock_value": 0.0,  # Not applicable
            "stock_retail_value": 0.0,
            "low_stock_count": 0,
            "low_stock": [],
            "active_members": active_members,
        }

        return {
            "sales_trend": sales_trend,
            "profit_trend": profit_trend,
            "payment_mix": payment_mix_data,
            "top_products": top_products_data,
            "top_agents": top_agents_data,
            "stock_overview": stock_overview,
        }

    def vertical_sections(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
    ) -> Dict[str, Any]:
        """Vertical-specific sections for gym."""
        members_qs = self.get_stock_queryset(business, location)
        payments_qs = self.get_sales_queryset(business, location)

        today = timezone.now().date()
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )

        # New members in period
        new_members = members_qs.filter(joined_at__gte=start_dt, joined_at__lt=end_dt).count()

        # New payments in period
        new_payments = payments_qs.filter(paid_at__gte=start_dt, paid_at__lt=end_dt).count()

        # Active memberships
        active_memberships = members_qs.filter(membership_end__gte=today, status="ACTIVE").count()

        # Churn (members whose membership ended in period but haven't renewed)
        ended_memberships = members_qs.filter(membership_end__gte=start_date, membership_end__lte=end_date)

        churned = 0
        for member in ended_memberships:
            # Check if they renewed (last payment after membership_end)
            last_payment = member.payments.filter(paid_at__date__gte=member.membership_end).first()
            if not last_payment:
                churned += 1

        return {
            "new_members": new_members,
            "new_payments": new_payments,
            "active_memberships": active_memberships,
            "churned_members": churned,
        }
