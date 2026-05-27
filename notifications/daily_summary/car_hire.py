# notifications/daily_summary/car_hire.py
"""
Daily summary provider for Car Hire businesses.

Metrics:
  - Rentals Today        (trips started today)
  - Revenue Today        (from CarHireRevenue records)
  - Utilisation Rate     (vehicles on trip / total active vehicles)
  - Top Vehicle          (most trips)
  - Overdue Returns      (trips past expected_return that are still ACTIVE)
  - Maintenance Alerts   (vehicles with overdue / due-today maintenance)
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


class CarHireDailySummaryProvider(DailySummaryProvider):
    vertical_label = "car_hire"

    def get_metrics(self, business: Any, report_date: date) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "rentals_today": 0,
            "revenue_today": Decimal("0.00"),
            "utilisation_rate": Decimal("0.00"),
            "top_vehicle": None,
            "overdue_returns": 0,
            "maintenance_alerts": 0,
            "currency": getattr(business, "currency", "MWK"),
        }

        try:
            self._populate_car_hire_metrics(business, report_date, metrics)
        except Exception:
            logger.exception(
                "[CarHireProvider] Error fetching car hire metrics for %s", business.name
            )

        return metrics

    def _populate_car_hire_metrics(
        self, business: Any, report_date: date, metrics: dict[str, Any]
    ) -> None:
        from django.db.models import Count, Sum
        import pytz

        from inventory.models_car_hire import (
            MaintenanceRecord,
            Trip,
            TripStatus,
            Vehicle,
            VehicleStatus,
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

        # ---- Rentals today (trips that started today) ----
        trips_today = Trip.objects.filter(
            business=business,
            start_time__gte=day_start,
            start_time__lt=day_end,
        ).exclude(status=TripStatus.CANCELLED)
        metrics["rentals_today"] = trips_today.count()

        # ---- Revenue today ----
        try:
            from inventory.models_car_hire import CarHireRevenue

            rev = CarHireRevenue.objects.filter(
                business=business,
                date=report_date,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        except Exception:
            # Fallback: sum from completed trip amounts
            rev = trips_today.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        metrics["revenue_today"] = rev

        # ---- Utilisation rate ----
        total_vehicles = Vehicle.objects.filter(business=business, is_active=True).count()
        if total_vehicles > 0:
            on_trip = Vehicle.objects.filter(
                business=business,
                is_active=True,
                status=VehicleStatus.ON_TRIP,
            ).count()
            metrics["utilisation_rate"] = round(
                Decimal(on_trip) / Decimal(total_vehicles) * 100, 1
            )

        # ---- Top vehicle (most trips today) ----
        top = (
            trips_today.values("vehicle__name")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
            .first()
        )
        if top and top.get("vehicle__name"):
            metrics["top_vehicle"] = top["vehicle__name"]

        # ---- Overdue returns ----
        now_aware = timezone.now()
        metrics["overdue_returns"] = Trip.objects.filter(
            business=business,
            status=TripStatus.ACTIVE,
            expected_return__lt=now_aware,
        ).count()

        # ---- Maintenance alerts (due today or overdue) ----
        try:
            metrics["maintenance_alerts"] = MaintenanceRecord.objects.filter(
                vehicle__business=business,
                is_completed=False,
                scheduled_date__lte=report_date,
            ).count()
        except Exception:
            pass

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
        html = render_to_string("emails/daily_summary/car_hire.html", context)
        text = render_to_string("emails/daily_summary/car_hire.txt", context)
        return html, text
