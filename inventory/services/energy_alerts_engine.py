# inventory/services/energy_alerts_engine.py
"""
Alert and recommendation engine for the Renewable Energy vertical.

Scans sites and assets for conditions that warrant alerts, then creates
EnergyAlert records. Designed to run periodically (management command,
celery task, or manual trigger from dashboard).

[AI_HOOK] Replace rules with ML anomaly-detection model output.
[IOT_HOOK] Add real-time telemetry trigger points.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


def run_alert_scan(business) -> dict:
    """
    Scan all sites/assets for a business and generate alerts.
    Returns summary: {"created": int, "categories": {...}}.
    """
    try:
        from inventory.models_energy import (
            EnergySite, EnergyAsset, EnergyAlert, EnergyReading,
            AlertType, AlertSeverity,
        )
    except ImportError:
        return {"created": 0, "error": "Energy models not available"}

    created = 0
    categories = {}
    today = timezone.now().date()

    def _create_alert(alert_type, severity, title, description, action, site=None, asset=None):
        nonlocal created
        existing = EnergyAlert.objects.filter(
            business=business, alert_type=alert_type,
            site=site, asset=asset, is_resolved=False,
        ).exists()
        if existing:
            return
        EnergyAlert.objects.create(
            business=business, site=site, asset=asset,
            alert_type=alert_type, severity=severity,
            title=title, description=description,
            suggested_action=action,
        )
        created += 1
        categories[alert_type] = categories.get(alert_type, 0) + 1

    # 1. Maintenance overdue
    for asset in EnergyAsset.objects.filter(
        business=business, status__in=["operational", "degraded"]
    ).select_related("site"):
        if asset.is_maintenance_overdue:
            due = asset.next_maintenance_date
            days_overdue = (today - due).days if due else 0
            severity = "critical" if days_overdue > 90 else ("high" if days_overdue > 30 else "medium")
            _create_alert(
                "maintenance_due", severity,
                f"Maintenance overdue: {asset.get_asset_type_display()} at {asset.site.name}",
                f"Last maintenance was {days_overdue} days overdue. "
                f"Asset health score: {asset.health_score}%.",
                "Schedule maintenance visit immediately.",
                site=asset.site, asset=asset,
            )

    # 2. Low asset health
    for asset in EnergyAsset.objects.filter(
        business=business, status__in=["operational", "degraded"],
        health_score__lt=50,
    ).select_related("site"):
        severity = "critical" if asset.health_score < 25 else "high"
        _create_alert(
            "asset_degraded", severity,
            f"Low health: {asset.get_asset_type_display()} at {asset.site.name} ({asset.health_score}%)",
            f"Asset health score has dropped to {asset.health_score}%. "
            f"Risk score: {asset.risk_score}%.",
            "Inspect asset and plan replacement if necessary.",
            site=asset.site, asset=asset,
        )

    # 3. Stale monitoring data
    threshold_date = today - timedelta(days=14)
    for site in EnergySite.objects.filter(business=business, status="active"):
        latest_reading = EnergyReading.objects.filter(
            site=site, business=business,
        ).order_by("-reading_date").first()
        if latest_reading is None or latest_reading.reading_date < threshold_date:
            days_missing = (today - latest_reading.reading_date).days if latest_reading else 999
            _create_alert(
                "data_missing", "medium",
                f"No recent readings for {site.name}",
                f"Last reading was {days_missing} days ago. "
                "Monitoring data may be stale.",
                "Enter manual readings or check IoT connectivity.",
                site=site,
            )

    # 4. Generation drops (compare last 7 days to previous 30-day average)
    seven_ago = today - timedelta(days=6)
    thirty_ago = today - timedelta(days=29)
    for site in EnergySite.objects.filter(business=business, status="active"):
        from django.db.models import Avg
        avg_30 = EnergyReading.objects.filter(
            site=site, reading_date__gte=thirty_ago, reading_date__lt=seven_ago,
        ).aggregate(avg=Avg("generation_kwh"))["avg"]
        avg_7 = EnergyReading.objects.filter(
            site=site, reading_date__gte=seven_ago,
        ).aggregate(avg=Avg("generation_kwh"))["avg"]

        if avg_30 and avg_7 and float(avg_30) > 0:
            drop_pct = (1 - float(avg_7) / float(avg_30)) * 100
            if drop_pct > 30:
                _create_alert(
                    "low_generation", "high",
                    f"Generation drop at {site.name} ({drop_pct:.0f}% decline)",
                    f"Average generation dropped from {float(avg_30):.1f} kWh/day to "
                    f"{float(avg_7):.1f} kWh/day over the past 7 days.",
                    "Inspect panels for shading, dust, or equipment faults.",
                    site=site,
                )

    # 5. Overload risk
    for site in EnergySite.objects.filter(business=business, status="active"):
        if site.installed_capacity_kw:
            from django.db.models import Max
            max_cons = EnergyReading.objects.filter(
                site=site, reading_date__gte=seven_ago,
            ).aggregate(mx=Max("consumption_kwh"))["mx"]
            if max_cons and float(max_cons) > float(site.installed_capacity_kw) * 24 * 0.85:
                _create_alert(
                    "overload_risk", "high",
                    f"Overload risk at {site.name}",
                    f"Recent daily consumption ({float(max_cons):.1f} kWh) approaches "
                    f"installed capacity ({float(site.installed_capacity_kw)} kW).",
                    "Review load management or consider system expansion.",
                    site=site,
                )

    # 6. Battery health (assets with type=battery and low health)
    for asset in EnergyAsset.objects.filter(
        business=business, asset_type="battery",
        status__in=["operational", "degraded"],
        health_score__lt=60,
    ).select_related("site"):
        _create_alert(
            "low_battery_health", "high" if asset.health_score < 40 else "medium",
            f"Battery health declining at {asset.site.name} ({asset.health_score}%)",
            f"Battery '{asset.brand} {asset.model_name}' health is at {asset.health_score}%. "
            f"Age: {asset.age_years:.1f} years." if asset.age_years else
            f"Battery health is at {asset.health_score}%.",
            "Plan battery testing or replacement.",
            site=asset.site, asset=asset,
        )

    logger.info(f"Alert scan for {business.name}: {created} new alerts created. Categories: {categories}")
    return {"created": created, "categories": categories}
