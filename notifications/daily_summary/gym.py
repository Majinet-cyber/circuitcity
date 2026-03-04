# notifications/daily_summary/gym.py
"""
Daily summary provider for Gym / Fitness businesses.

Metrics (NO COGS, NO top-product):
  - New Members Today
  - Active Members
  - Membership Revenue Today
  - Check-ins Today
  - Top Plan
  - Renewals Due (next 7 days)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.template.loader import render_to_string
from django.utils import timezone

from notifications.daily_summary.base import DailySummaryProvider

logger = logging.getLogger(__name__)


class GymDailySummaryProvider(DailySummaryProvider):
    vertical_label = "gym"

    def get_metrics(self, business: Any, report_date: date) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "new_members_today": 0,
            "active_members": 0,
            "membership_revenue_today": Decimal("0.00"),
            "checkins_today": 0,
            "top_plan": None,
            "renewals_due_7_days": 0,
            "currency": getattr(business, "currency", "MWK"),
        }

        try:
            self._populate_gym_metrics(business, report_date, metrics)
        except Exception:
            logger.exception("[GymProvider] Error fetching gym metrics for %s", business.name)

        return metrics

    def _populate_gym_metrics(
        self, business: Any, report_date: date, metrics: dict[str, Any]
    ) -> None:
        from django.db.models import Count, Sum
        import pytz

        from inventory.models_verticals import (
            GymCheckIn,
            GymMember,
            GymMemberStatus,
            GymPayment,
        )

        biz_tz_name = getattr(
            getattr(business, "daily_summary_settings", None), "timezone", "Africa/Blantyre"
        )
        try:
            biz_tz = pytz.timezone(biz_tz_name)
        except Exception:
            biz_tz = pytz.timezone("Africa/Blantyre")

        day_start = timezone.make_aware(
            timezone.datetime.combine(report_date, timezone.datetime.min.time()),
            biz_tz,
        )
        day_end = day_start + timedelta(days=1)

        members_qs = GymMember.objects.filter(business=business, is_archived=False)

        # Active members (membership not yet expired)
        active_qs = members_qs.filter(
            membership_end__gte=report_date, status=GymMemberStatus.ACTIVE
        )
        metrics["active_members"] = active_qs.count()

        # New members joined today
        metrics["new_members_today"] = members_qs.filter(
            joined_at__gte=day_start, joined_at__lt=day_end
        ).count()

        # Revenue today
        rev = GymPayment.objects.filter(
            member__business=business,
            paid_at__gte=day_start,
            paid_at__lt=day_end,
            is_active=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        metrics["membership_revenue_today"] = rev

        # Check-ins today
        metrics["checkins_today"] = GymCheckIn.objects.filter(
            business=business,
            timestamp__gte=day_start,
            timestamp__lt=day_end,
        ).count()

        # Top plan by active member count
        try:
            top = (
                active_qs.exclude(plan="")
                .values("plan")
                .annotate(cnt=Count("id"))
                .order_by("-cnt")
                .first()
            )
            if top and top.get("plan"):
                metrics["top_plan"] = top["plan"]
        except Exception:
            pass

        # Renewals due in next 7 days
        seven_days = report_date + timedelta(days=7)
        metrics["renewals_due_7_days"] = members_qs.filter(
            membership_end__gte=report_date,
            membership_end__lte=seven_days,
            status=GymMemberStatus.ACTIVE,
        ).count()

    def render_email(
        self,
        business: Any,
        metrics: dict[str, Any],
        report_date: date,
    ) -> tuple[str, str]:
        context = {
            "business": business,
            "report_date": report_date,
            **metrics,
        }
        html = render_to_string("emails/daily_summary/gym.html", context)
        text = render_to_string("emails/daily_summary/gym.txt", context)
        return html, text
