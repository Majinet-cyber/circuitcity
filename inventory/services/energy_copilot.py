# inventory/services/energy_copilot.py
"""
Energy Copilot — rule-based intelligence panel for the flagship energy vertical.

Generates actionable insights by scanning sites, assets, readings, and alerts.
No heavy AI — pure business-rule intelligence that works without sensors.

[AI_HOOK] Replace with ML-driven insight generation when models are available.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def generate_copilot_insights(business) -> list[dict]:
    """
    Scan business energy data and generate structured insights.
    Returns a list of insight dicts suitable for display or CopilotInsight creation.
    """
    try:
        from inventory.models_energy import (
            EnergyAlert, EnergyAsset, EnergyReading, EnergySite,
            SavingsRecord, SystemSizingRun,
        )
    except ImportError:
        return []

    insights = []
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    sites = EnergySite.objects.filter(business=business, status="active")
    assets = EnergyAsset.objects.filter(business=business)

    # 1. Battery degradation detection
    degraded_batteries = assets.filter(
        asset_type="battery", health_score__lt=70, status__in=["operational", "degraded"],
    )
    for batt in degraded_batteries[:3]:
        insights.append({
            "category": "maintenance",
            "severity": "high" if batt.health_score < 50 else "medium",
            "title": f"Battery degradation at {batt.site.name}",
            "explanation": (
                f"{batt.brand} {batt.model_name} battery health is at {batt.health_score}%. "
                f"Replacement planning may be needed within the next 6-12 months."
            ),
            "action": "Schedule a battery capacity test and review replacement budget.",
        })

    # 2. Evening load spike detection
    for site in sites[:20]:
        readings = EnergyReading.objects.filter(
            site=site, reading_date__gte=thirty_days_ago,
        ).order_by("reading_date")
        if readings.count() < 7:
            continue

        recent = readings.filter(reading_date__gte=seven_days_ago)
        older = readings.filter(reading_date__lt=seven_days_ago, reading_date__gte=thirty_days_ago)

        recent_avg = recent.aggregate(a=Avg("consumption_kwh"))["a"]
        older_avg = older.aggregate(a=Avg("consumption_kwh"))["a"]

        if recent_avg and older_avg and older_avg > 0:
            change_pct = ((recent_avg - older_avg) / older_avg * 100)
            if change_pct > 15:
                insights.append({
                    "category": "capacity",
                    "severity": "medium",
                    "title": f"Consumption increasing at {site.name}",
                    "explanation": (
                        f"Average daily consumption has increased {change_pct:.0f}% in the last 7 days "
                        f"compared to the previous 3 weeks ({float(older_avg):.1f} → {float(recent_avg):.1f} kWh)."
                    ),
                    "action": "Review load additions and consider system capacity expansion.",
                })

    # 3. Underperforming sites (generation vs capacity)
    for site in sites.filter(installed_capacity_kw__gt=0)[:20]:
        month_readings = EnergyReading.objects.filter(
            site=site, reading_date__gte=thirty_days_ago,
        )
        avg_gen = month_readings.aggregate(a=Avg("generation_kwh"))["a"]
        if avg_gen and site.installed_capacity_kw:
            expected_daily = float(site.installed_capacity_kw) * 5.0 * 0.85
            if avg_gen < expected_daily * 0.6:
                insights.append({
                    "category": "performance",
                    "severity": "high",
                    "title": f"{site.name} generating below expectations",
                    "explanation": (
                        f"Average daily generation ({float(avg_gen):.1f} kWh) is significantly below "
                        f"expected output ({expected_daily:.1f} kWh). Panel cleaning, shading, "
                        f"or inverter issues may be the cause."
                    ),
                    "action": "Schedule site inspection and panel cleaning.",
                })

    # 4. Stale data warnings
    for site in sites[:20]:
        latest = EnergyReading.objects.filter(site=site).aggregate(m=Max("reading_date"))["m"]
        if latest and latest < seven_days_ago:
            days_stale = (today - latest).days
            insights.append({
                "category": "risk",
                "severity": "low",
                "title": f"No recent data from {site.name}",
                "explanation": f"Last reading was {days_stale} days ago. Monitoring continuity is at risk.",
                "action": "Log new readings or check monitoring equipment.",
            })

    # 5. Overdue maintenance
    overdue_count = sum(1 for a in assets.filter(status__in=["operational", "degraded"]) if a.is_maintenance_overdue)
    if overdue_count > 0:
        insights.append({
            "category": "maintenance",
            "severity": "high" if overdue_count > 5 else "medium",
            "title": f"{overdue_count} asset(s) have overdue maintenance",
            "explanation": "Delayed maintenance increases failure risk and reduces asset lifespan.",
            "action": "Review maintenance schedule and dispatch technicians.",
        })

    # 6. Savings opportunity
    total_savings = SavingsRecord.objects.filter(
        business=business, month__gte=thirty_days_ago,
    ).aggregate(s=Sum("estimated_savings"))["s"] or 0
    if total_savings > 0:
        insights.append({
            "category": "cost",
            "severity": "low",
            "title": f"MWK {float(total_savings):,.0f} saved this month",
            "explanation": "Portfolio is generating measurable cost savings versus grid/fuel baseline.",
            "action": "Review per-site savings to identify top performers.",
        })

    # 7. Sizing proposals awaiting action
    pending = SystemSizingRun.objects.filter(
        business=business, proposal_status__in=["proposal_sent", "proposal_draft"],
    ).count()
    if pending > 0:
        insights.append({
            "category": "opportunity",
            "severity": "low",
            "title": f"{pending} proposal(s) awaiting customer response",
            "explanation": "Active proposals represent potential new projects and revenue.",
            "action": "Follow up with customers on pending proposals.",
        })

    return insights[:15]
