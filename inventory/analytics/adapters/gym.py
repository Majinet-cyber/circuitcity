# inventory/analytics/adapters/gym.py
"""
Analytics adapter for gym vertical.
Gym uses GymPayment instead of sales.
Provides gym-specific KPIs: active members, attendance, check-ins, etc.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, DecimalField, Q, QuerySet, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.analytics.adapters.base import AnalyticsAdapter
from inventory.analytics.common import (
    apply_business_scope,
    apply_location_filter,
    apply_payment_method_filter,
    apply_search_filter,
)
from inventory.models_verticals import GymCheckIn, GymMember, GymMemberStatus, GymPayment
from wallet.models import Ledger, TxnType, WalletTransaction


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
        """
        Calculate KPIs for gym.

        Returns gym-specific KPIs:
        - Active Members
        - Expiring Soon (<=7 days)
        - Check-ins Today
        - Attendance Rate (last 7 days)
        - Missed 2+ Days
        - Membership Revenue (this month)
        - Payments Collected (this week)
        - Next Payments Due (next 7 days)
        """
        today = timezone.now().date()
        today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        today_end = timezone.make_aware(
            timezone.datetime.combine(today + timedelta(days=1), timezone.datetime.min.time())
        )

        # Date ranges
        week_start = today - timedelta(days=7)
        week_start_dt = timezone.make_aware(timezone.datetime.combine(week_start, timezone.datetime.min.time()))
        month_start = today.replace(day=1)
        month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))
        seven_days_from_now = today + timedelta(days=7)
        two_days_ago = today - timedelta(days=2)

        # Base querysets
        members_qs = self.get_stock_queryset(business, location)
        payments_qs = self.get_sales_queryset(business, location)

        # Apply date filter for payments in the requested range
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )
        payments_in_range = payments_qs.filter(paid_at__gte=start_dt, paid_at__lt=end_dt)

        if payment_method:
            payments_in_range = apply_payment_method_filter(payments_in_range, payment_method)
        if search_query:
            payments_in_range = apply_search_filter(payments_in_range, search_query, self.get_search_fields())

        # Revenue and payments in requested range
        # CRITICAL FIX: Calculate directly from membership_amount + trainer_fee
        # This ensures revenue is ALWAYS correct even if amount field has legacy 0/NULL values
        from django.db.models import ExpressionWrapper, F
        
        revenue = payments_in_range.aggregate(
            total=Coalesce(
                Sum(
                    ExpressionWrapper(
                        Coalesce(F("membership_amount"), Decimal("0.00")) +
                        Coalesce(F("trainer_fee"), Decimal("0.00")),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
                Decimal("0.00"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )["total"] or Decimal("0.00")
        total_sales = payments_in_range.count()
        avg_order_value = revenue / total_sales if total_sales > 0 else Decimal("0.00")

        # Costs
        costs_qs = self.get_costs_queryset(business, location)
        costs_qs = costs_qs.filter(
            Q(type=TxnType.COST_ONCE_OFF, effective_date__gte=start_date, effective_date__lte=end_date)
            | Q(type=TxnType.COST_RECURRING, effective_from__lte=end_date)
        )
        costs = abs(costs_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"))

        profit = revenue - costs
        gross_margin = Decimal("100.00")  # Gym has no COGS

        # ===== GYM-SPECIFIC KPIs =====

        # 1. Active Members (have valid membership today)
        active_members = members_qs.filter(
            membership_end__gte=today, status=GymMemberStatus.ACTIVE, is_active=True
        ).count()

        # 2. Expiring Soon (membership ends within 7 days)
        expiring_soon = members_qs.filter(
            membership_end__gte=today, membership_end__lte=seven_days_from_now, status=GymMemberStatus.ACTIVE
        ).count()

        # 3. Check-ins Today
        checkins_today = GymCheckIn.objects.filter(
            business=business, timestamp__gte=today_start, timestamp__lt=today_end
        ).count()

        # 4. Attendance Rate (last 7 days): total check-ins / (active_members * 7)
        checkins_last_7_days = GymCheckIn.objects.filter(
            business=business, timestamp__gte=week_start_dt, timestamp__lt=today_end
        ).count()

        if active_members > 0:
            attendance_rate = (checkins_last_7_days / (active_members * 7)) * 100
        else:
            attendance_rate = 0

        # 5. Missed 2+ Days (active members who haven't checked in for 2+ days)
        # Get active members with last check-in <= today-2 OR never checked in AND membership age >= 2 days
        missed_2_days = 0
        active_member_objs = members_qs.filter(membership_end__gte=today, status=GymMemberStatus.ACTIVE, is_active=True)

        for member in active_member_objs:
            membership_age_days = (today - member.membership_start).days if member.membership_start else 0
            if membership_age_days < 2:
                continue  # Skip members with new memberships

            # Get member's last check-in
            last_checkin = GymCheckIn.objects.filter(business=business, member=member).order_by("-timestamp").first()

            if not last_checkin:
                # Never checked in and membership age >= 2
                missed_2_days += 1
            elif last_checkin.timestamp.date() <= two_days_ago:
                # Last check-in was 2+ days ago
                missed_2_days += 1

        # 6. Membership Revenue (this month)
        membership_revenue_this_month = payments_qs.filter(
            paid_at__gte=month_start_dt, paid_at__lt=today_end
        ).aggregate(total=Coalesce(Sum("membership_amount"), Decimal("0.00")))["total"] or Decimal("0.00")

        # 7. Payments Collected (this week)
        payments_this_week = payments_qs.filter(paid_at__gte=week_start_dt, paid_at__lt=today_end).count()

        payments_collected_this_week = payments_qs.filter(paid_at__gte=week_start_dt, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        # 8. Next Payments Due (next 7 days)
        # Members whose membership ends within the next 7 days
        next_payments_due = members_qs.filter(
            membership_end__gte=today, membership_end__lte=seven_days_from_now, status=GymMemberStatus.ACTIVE
        ).count()

        # Additional useful metrics
        total_members = members_qs.count()
        new_members_this_month = members_qs.filter(joined_at__gte=month_start_dt, joined_at__lt=today_end).count()

        # Revenue this month (total)
        revenue_this_month = payments_qs.filter(paid_at__gte=month_start_dt, paid_at__lt=today_end).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"))
        )["total"] or Decimal("0.00")

        return {
            # Standard KPIs (for compatibility)
            "revenue": revenue,
            "profit": profit,
            "total_sales": total_sales,
            "avg_order_value": avg_order_value,
            "gross_margin": gross_margin,
            "costs": costs,
            # Gym-specific KPIs (primary)
            "active_members": active_members,
            "expiring_soon": expiring_soon,
            "checkins_today": checkins_today,
            "attendance_rate": round(attendance_rate, 1),
            "missed_2_days": missed_2_days,
            "membership_revenue_this_month": membership_revenue_this_month,
            "payments_this_week": payments_this_week,
            "payments_collected_this_week": payments_collected_this_week,
            "next_payments_due": next_payments_due,
            # Additional metrics
            "total_members": total_members,
            "new_members_this_month": new_members_this_month,
            "revenue_this_month": revenue_this_month,
            "checkins_last_7_days": checkins_last_7_days,
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
        """
        Generate chart data for gym.

        Charts:
        - Attendance Trend (daily check-ins over time)
        - Plan Mix (distribution of membership types if applicable)
        - Payment Mix (cash/bank/mobile)
        - Top Trainers (by check-ins, NOT revenue)
        """
        today = timezone.now().date()
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(
            timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time())
        )

        payments_qs = self.get_sales_queryset(business, location)
        payments_qs = payments_qs.filter(paid_at__gte=start_dt, paid_at__lt=end_dt)

        if payment_method:
            payments_qs = apply_payment_method_filter(payments_qs, payment_method)
        if search_query:
            payments_qs = apply_search_filter(payments_qs, search_query, self.get_search_fields())

        # ===== ATTENDANCE TREND (daily check-ins) =====
        checkins_qs = GymCheckIn.objects.filter(business=business, timestamp__gte=start_dt, timestamp__lt=end_dt)

        daily_checkins = (
            checkins_qs.annotate(day=TruncDate("timestamp")).values("day").annotate(count=Count("id")).order_by("day")
        )

        attendance_trend = [
            {
                "date": str(item["day"]),
                "date_short": item["day"].strftime("%m/%d") if item["day"] else "",
                "checkins": item["count"],
            }
            for item in daily_checkins
        ]

        # ===== SALES TREND (payment trend for backward compatibility) =====
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

        # ===== PAYMENT MIX =====
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

        # ===== TOP TRAINERS (by check-ins, NOT revenue) =====
        # Get trainers with check-in counts in the date range
        from inventory.models_verticals import GymTrainer

        trainers = GymTrainer.objects.filter(business=business, is_active=True)
        trainer_stats = []

        for trainer in trainers:
            # Count check-ins for members assigned to this trainer
            checkins_count = checkins_qs.filter(member__trainer=trainer).count()

            # Revenue from payments with this trainer
            trainer_revenue = payments_qs.filter(trainer=trainer).aggregate(
                total=Coalesce(Sum("amount"), Decimal("0.00"))
            )["total"] or Decimal("0.00")

            if checkins_count > 0:
                trainer_stats.append(
                    {
                        "name": trainer.name,
                        "checkins": checkins_count,
                        "revenue": float(trainer_revenue),
                        "units_sold": checkins_count,  # For compatibility (use check-ins)
                    }
                )

        # Sort by check-ins (descending) and take top 10
        trainer_stats.sort(key=lambda x: x["checkins"], reverse=True)
        top_trainers_data = trainer_stats[:10]

        # ===== PLAN MIX (membership types distribution) =====
        # For now, we'll show a simple breakdown based on has_trainer
        members_qs = self.get_stock_queryset(business, location)
        active_members_qs = members_qs.filter(membership_end__gte=today, status=GymMemberStatus.ACTIVE)

        with_trainer = active_members_qs.filter(has_trainer=True).count()
        without_trainer = active_members_qs.filter(has_trainer=False).count()
        total_active = with_trainer + without_trainer

        plan_mix_data = []
        if total_active > 0:
            if with_trainer > 0:
                plan_mix_data.append(
                    {
                        "plan_type": "With Trainer",
                        "count": with_trainer,
                        "percentage": (with_trainer / total_active) * 100,
                    }
                )
            if without_trainer > 0:
                plan_mix_data.append(
                    {
                        "plan_type": "Standard Membership",
                        "count": without_trainer,
                        "percentage": (without_trainer / total_active) * 100,
                    }
                )

        # ===== EMPTY DATA FOR NON-APPLICABLE SECTIONS =====
        # Top products doesn't make sense for gym
        top_products_data = []

        # Stock overview - repurpose for gym member overview
        expired_memberships = members_qs.filter(
            membership_end__lt=today, status__in=[GymMemberStatus.BEHIND_SCHEDULE, GymMemberStatus.EXPIRED]
        ).count()

        stock_overview = {
            "stock_value": 0.0,  # Not applicable
            "stock_retail_value": 0.0,  # Not applicable
            "low_stock_count": expired_memberships,  # Repurpose as expired memberships
            "low_stock": [],
            "active_members": total_active,
            "expired_memberships": expired_memberships,
        }

        return {
            "sales_trend": sales_trend,
            "profit_trend": profit_trend,
            "attendance_trend": attendance_trend,  # NEW: gym-specific
            "payment_mix": payment_mix_data,
            "plan_mix": plan_mix_data,  # NEW: gym-specific
            "top_products": top_products_data,  # Empty for gym
            "top_agents": top_trainers_data,  # Trainers ranked by check-ins
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
