# inventory/verticals/energy.py
"""
Renewable Energy vertical views.

Modules:
  - dashboard       : Overview KPIs, site health, alerts, forecasting summary
  - sites_list      : Site management (list + create)
  - site_detail     : Per-site detail
  - assets_list     : Asset registry (list + create)
  - maintenance_list/create : Maintenance scheduling and logs
  - alerts_list     : Alert centre
  - economics       : Costs, savings, ROI
  - reports         : Report hub
  - forecasting     : Demand forecasting (rules-based now, ML-ready)

Future AI/IoT integration points marked with # [AI_HOOK] / # [IOT_HOOK].
"""
from __future__ import annotations

import io
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.utils import require_business, get_active_business

log = logging.getLogger(__name__)


def _models():
    """Return dict of energy model classes, or empty dict if unavailable."""
    try:
        from inventory.models_energy import (
            EnergySite, EnergyAsset, AssetMaintenanceRecord,
            EnergyReading, SavingsRecord, EnergyAlert,
            SiteType, AssetType, AssetStatus, MaintenanceType,
            AlertSeverity, AlertType, SiteStatus,
            SystemSizingRun, SizingAppliance, SizingObjective,
            SystemArchitecture, ApplianceCategory, LoadPriority,
            DemandForecast, TechnicianVisit, LoadProfile,
        )
        return {
            "EnergySite": EnergySite,
            "EnergyAsset": EnergyAsset,
            "AssetMaintenanceRecord": AssetMaintenanceRecord,
            "EnergyReading": EnergyReading,
            "SavingsRecord": SavingsRecord,
            "EnergyAlert": EnergyAlert,
            "SiteType": SiteType,
            "AssetType": AssetType,
            "AssetStatus": AssetStatus,
            "MaintenanceType": MaintenanceType,
            "AlertSeverity": AlertSeverity,
            "AlertType": AlertType,
            "SiteStatus": SiteStatus,
            "SystemSizingRun": SystemSizingRun,
            "SizingAppliance": SizingAppliance,
            "SizingObjective": SizingObjective,
            "SystemArchitecture": SystemArchitecture,
            "ApplianceCategory": ApplianceCategory,
            "LoadPriority": LoadPriority,
            "DemandForecast": DemandForecast,
            "TechnicianVisit": TechnicianVisit,
            "LoadProfile": LoadProfile,
        }
    except ImportError:
        return {}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def dashboard(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    today = timezone.now().date()

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "stats": {},
        "recent_alerts": [],
        "sites_needing_attention": [],
        "high_risk_assets": [],
        "recent_readings": [],
        "forecast_summary": {},
        "intelligent_insights": [],
        "sizing_count": 0,
        "reading_dates_json": "[]",
        "gen_data_json": "[]",
        "cons_data_json": "[]",
    }

    if not m:
        return render(request, "energy/dashboard.html", ctx)

    from django.db.models import Count, Sum, Avg, Max
    import json

    EnergySite = m["EnergySite"]
    EnergyAsset = m["EnergyAsset"]
    EnergyReading = m["EnergyReading"]
    EnergyAlert = m["EnergyAlert"]
    SavingsRecord = m["SavingsRecord"]
    SystemSizingRun = m["SystemSizingRun"]

    sites_qs = EnergySite.objects.filter(business=biz)
    assets_qs = EnergyAsset.objects.filter(business=biz)
    alerts_qs = EnergyAlert.objects.filter(business=biz, is_resolved=False)

    total_sites = sites_qs.count()
    active_sites = sites_qs.filter(status="active").count()
    total_assets = assets_qs.count()
    operational_assets = assets_qs.filter(status="operational").count()
    degraded_assets = assets_qs.filter(status="degraded").count()
    faulty_assets = assets_qs.filter(status="faulty").count()
    critical_alerts = alerts_qs.filter(severity="critical").count()
    high_alerts = alerts_qs.filter(severity="high").count()

    # Installed capacity
    installed_capacity = sites_qs.filter(status="active").aggregate(
        total=Sum("installed_capacity_kw"))["total"] or Decimal("0")

    maintenance_overdue = sum(
        1 for asset in assets_qs.filter(status__in=["operational", "degraded"])
        if asset.is_maintenance_overdue
    )

    # Battery health average
    batteries = assets_qs.filter(asset_type="battery", status__in=["operational", "degraded"])
    avg_battery_health = batteries.aggregate(avg=Avg("health_score"))["avg"] or 0

    # Inverter health
    inverters = assets_qs.filter(asset_type="inverter", status__in=["operational", "degraded"])
    avg_inverter_health = inverters.aggregate(avg=Avg("health_score"))["avg"] or 0

    # Overall asset health
    avg_asset_health = assets_qs.filter(
        status__in=["operational", "degraded"]
    ).aggregate(avg=Avg("health_score"))["avg"] or 0

    month_start = today.replace(day=1)
    savings_this_month = (
        SavingsRecord.objects.filter(business=biz, month__gte=month_start)
        .aggregate(total=Sum("estimated_savings"))["total"] or Decimal("0")
    )
    cumulative_savings = (
        SavingsRecord.objects.filter(business=biz)
        .aggregate(total=Sum("estimated_savings"))["total"] or Decimal("0")
    )
    generation_this_month = (
        EnergyReading.objects.filter(business=biz, reading_date__gte=month_start)
        .aggregate(total=Sum("generation_kwh"))["total"] or Decimal("0")
    )
    consumption_this_month = (
        EnergyReading.objects.filter(business=biz, reading_date__gte=month_start)
        .aggregate(total=Sum("consumption_kwh"))["total"] or Decimal("0")
    )

    # Week data
    week_start = today - timedelta(days=6)
    gen_this_week = (
        EnergyReading.objects.filter(business=biz, reading_date__gte=week_start)
        .aggregate(total=Sum("generation_kwh"))["total"] or Decimal("0")
    )

    # Recent 30-day reading trend (for Chart.js)
    thirty_ago = today - timedelta(days=29)
    recent_readings = list(
        EnergyReading.objects.filter(business=biz, reading_date__gte=thirty_ago)
        .values("reading_date")
        .annotate(gen=Sum("generation_kwh"), cons=Sum("consumption_kwh"))
        .order_by("reading_date")[:30]
    )

    reading_dates = [r["reading_date"].strftime("%b %d") for r in recent_readings]
    gen_data = [float(r["gen"] or 0) for r in recent_readings]
    cons_data = [float(r["cons"] or 0) for r in recent_readings]

    # High-risk assets
    high_risk_assets = sorted(
        [a for a in assets_qs.filter(status__in=["operational", "degraded", "maintenance"]).select_related("site")
         if a.risk_score >= 40],
        key=lambda a: a.risk_score, reverse=True
    )[:6]

    # Sites with active alerts
    sites_needing_attention = (
        sites_qs.filter(alerts__is_resolved=False)
        .annotate(alert_count=Count("alerts"))
        .order_by("-alert_count")[:5]
    )

    recent_alerts = alerts_qs.select_related("site", "asset").order_by("-created_at")[:8]

    # Sizing count
    sizing_count = SystemSizingRun.objects.filter(business=biz).count()

    # Forecast
    forecast_summary = {
        "next_7_day_demand_kwh": None,
        "next_30_day_demand_kwh": None,
        "explanation": "Connect historical readings to enable demand forecasting.",
    }
    if generation_this_month > 0:
        daily_avg = generation_this_month / Decimal("30")
        forecast_summary["next_7_day_demand_kwh"] = round(float(daily_avg * 7), 1)
        forecast_summary["next_30_day_demand_kwh"] = round(float(daily_avg * 30), 1)
        forecast_summary["explanation"] = "Based on this month's generation average."

    # Intelligent insights
    insights = []
    overload_sites = []
    for site in sites_qs.filter(status="active"):
        if site.installed_capacity_kw:
            max_cons = EnergyReading.objects.filter(
                site=site, reading_date__gte=week_start
            ).aggregate(mx=Max("consumption_kwh"))["mx"]
            if max_cons and float(max_cons) > float(site.installed_capacity_kw) * 24 * 0.80:
                overload_sites.append(site.name)
    if overload_sites:
        insights.append({
            "type": "warning",
            "text": f"{len(overload_sites)} site{'s are' if len(overload_sites) > 1 else ' is'} at moderate overload risk in the next 7 days.",
        })
    if avg_battery_health > 0 and avg_battery_health < 60:
        insights.append({
            "type": "warning",
            "text": f"Average battery health is {avg_battery_health:.0f}% — plan replacements proactively.",
        })
    if maintenance_overdue > 0:
        insights.append({
            "type": "info",
            "text": f"{maintenance_overdue} asset{'s have' if maintenance_overdue > 1 else ' has'} overdue maintenance. Schedule visits soon.",
        })
    if generation_this_month > 0 and consumption_this_month > generation_this_month * Decimal("1.3"):
        insights.append({
            "type": "warning",
            "text": "Consumption exceeds generation by 30%+ this month. Grid/generator dependency is high.",
        })
    if sizing_count > 0:
        insights.append({
            "type": "success",
            "text": f"{sizing_count} system sizing proposal{'s' if sizing_count > 1 else ''} created.",
        })

    ctx["stats"] = {
        "total_sites": total_sites,
        "active_sites": active_sites,
        "total_assets": total_assets,
        "operational_assets": operational_assets,
        "degraded_assets": degraded_assets,
        "faulty_assets": faulty_assets,
        "critical_alerts": critical_alerts,
        "high_alerts": high_alerts,
        "maintenance_overdue": maintenance_overdue,
        "savings_this_month": savings_this_month,
        "cumulative_savings": cumulative_savings,
        "generation_this_month": generation_this_month,
        "consumption_this_month": consumption_this_month,
        "gen_this_week": gen_this_week,
        "installed_capacity": installed_capacity,
        "avg_battery_health": round(avg_battery_health),
        "avg_inverter_health": round(avg_inverter_health),
        "avg_asset_health": round(avg_asset_health),
    }
    ctx["recent_alerts"] = recent_alerts
    ctx["sites_needing_attention"] = sites_needing_attention
    ctx["high_risk_assets"] = high_risk_assets
    ctx["recent_readings"] = recent_readings
    ctx["forecast_summary"] = forecast_summary
    ctx["intelligent_insights"] = insights
    ctx["sizing_count"] = sizing_count
    ctx["reading_dates_json"] = json.dumps(reading_dates)
    ctx["gen_data_json"] = json.dumps(gen_data)
    ctx["cons_data_json"] = json.dumps(cons_data)

    return render(request, "energy/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Site Management
# ---------------------------------------------------------------------------

@login_required
@require_business
def sites_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    sites = []
    site_types = []
    if m:
        EnergySite = m["EnergySite"]
        sites = (
            EnergySite.objects.filter(business=biz)
            .prefetch_related("assets", "alerts")
            .order_by("status", "name")
        )
        site_types = m["SiteType"].choices

    return render(request, "energy/sites.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites": sites,
        "site_types": site_types,
    })


@login_required
@require_business
def site_create(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        messages.error(request, "Energy module not available.")
        return redirect("verticals:energy_dashboard")

    EnergySite = m["EnergySite"]
    SiteType = m["SiteType"]
    SiteStatus = m["SiteStatus"]

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Site name is required.")
            return redirect(request.path)

        try:
            capacity_str = request.POST.get("installed_capacity_kw", "").strip()
            capacity = Decimal(capacity_str) if capacity_str else None
        except InvalidOperation:
            capacity = None

        site = EnergySite.objects.create(
            business=biz,
            name=name,
            site_type=request.POST.get("site_type", SiteType.HOUSEHOLD),
            status=SiteStatus.ACTIVE,
            location=request.POST.get("location", "").strip(),
            customer_name=request.POST.get("customer_name", "").strip(),
            customer_phone=request.POST.get("customer_phone", "").strip(),
            customer_email=request.POST.get("customer_email", "").strip(),
            installed_capacity_kw=capacity,
            commissioning_date=request.POST.get("commissioning_date") or None,
            notes=request.POST.get("notes", "").strip(),
            energy_sources=[s for s in request.POST.getlist("energy_sources") if s],
        )
        messages.success(request, f"Site '{site.name}' created successfully.")
        return redirect("verticals:energy_site_detail", site_id=site.id)

    return render(request, "energy/site_form.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "site_types": SiteType.choices,
        "action": "Create",
    })


@login_required
@require_business
def site_detail(request: HttpRequest, site_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_dashboard")

    EnergySite = m["EnergySite"]
    EnergyAsset = m["EnergyAsset"]
    AssetType = m["AssetType"]
    SavingsRecord = m["SavingsRecord"]

    site = get_object_or_404(EnergySite, id=site_id, business=biz)
    assets = EnergyAsset.objects.filter(site=site).order_by("asset_type", "brand")
    recent_alerts = site.alerts.filter(is_resolved=False).order_by("-created_at")[:5]
    recent_readings = site.readings.order_by("-reading_date")[:10]

    from django.db.models import Sum
    total_savings = SavingsRecord.objects.filter(site=site).aggregate(
        total=Sum("estimated_savings"))["total"] or Decimal("0")
    installation_cost = site.installation_cost or Decimal("0")
    roi_pct = None
    if installation_cost > 0 and total_savings > 0:
        roi_pct = round(float(total_savings / installation_cost * 100), 1)

    payback_months = None
    if installation_cost > 0:
        last_rec = SavingsRecord.objects.filter(site=site).order_by("-month").first()
        if last_rec and last_rec.estimated_savings > 0:
            payback_months = round(float(installation_cost / last_rec.estimated_savings))

    return render(request, "energy/site_detail.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "site": site,
        "assets": assets,
        "recent_alerts": recent_alerts,
        "recent_readings": recent_readings,
        "total_savings": total_savings,
        "roi_pct": roi_pct,
        "payback_months": payback_months,
        "asset_types": AssetType.choices,
    })


# ---------------------------------------------------------------------------
# Asset Registry
# ---------------------------------------------------------------------------

@login_required
@require_business
def assets_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    assets = []
    asset_types = []
    asset_statuses = []
    sites = []

    if m:
        EnergyAsset = m["EnergyAsset"]
        EnergySite = m["EnergySite"]
        AssetType = m["AssetType"]
        AssetStatus = m["AssetStatus"]

        type_filter = request.GET.get("type", "")
        status_filter = request.GET.get("status", "")

        qs = EnergyAsset.objects.filter(business=biz).select_related("site")
        if type_filter:
            qs = qs.filter(asset_type=type_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

        assets = qs.order_by("site__name", "asset_type")
        asset_types = AssetType.choices
        asset_statuses = AssetStatus.choices
        sites = EnergySite.objects.filter(business=biz).values("id", "name")
    else:
        type_filter = ""
        status_filter = ""

    return render(request, "energy/assets.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "assets": assets,
        "asset_types": asset_types,
        "asset_statuses": asset_statuses,
        "sites": sites,
        "type_filter": request.GET.get("type", ""),
        "status_filter": request.GET.get("status", ""),
    })


@login_required
@require_business
def asset_create(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        messages.error(request, "Energy module not available.")
        return redirect("verticals:energy_assets")

    EnergySite = m["EnergySite"]
    EnergyAsset = m["EnergyAsset"]
    AssetType = m["AssetType"]
    AssetStatus = m["AssetStatus"]

    sites = EnergySite.objects.filter(business=biz)

    if request.method == "POST":
        site_id = request.POST.get("site")
        asset_type = request.POST.get("asset_type", "")

        if not site_id or not asset_type:
            messages.error(request, "Site and asset type are required.")
            return redirect(request.path)

        site = get_object_or_404(EnergySite, id=site_id, business=biz)

        try:
            cap_str = request.POST.get("capacity", "").strip()
            capacity = Decimal(cap_str) if cap_str else None
        except InvalidOperation:
            capacity = None

        try:
            cost_str = request.POST.get("asset_cost", "").strip()
            asset_cost = Decimal(cost_str) if cost_str else None
        except InvalidOperation:
            asset_cost = None

        asset = EnergyAsset.objects.create(
            site=site,
            business=biz,
            asset_type=asset_type,
            brand=request.POST.get("brand", "").strip(),
            model_name=request.POST.get("model_name", "").strip(),
            serial_number=request.POST.get("serial_number", "").strip(),
            capacity=capacity,
            capacity_unit=request.POST.get("capacity_unit", "kW").strip() or "kW",
            install_date=request.POST.get("install_date") or None,
            warranty_expiry=request.POST.get("warranty_expiry") or None,
            expected_lifespan_years=request.POST.get("expected_lifespan_years") or None,
            maintenance_interval_days=request.POST.get("maintenance_interval_days") or 180,
            asset_cost=asset_cost,
            notes=request.POST.get("notes", "").strip(),
        )
        messages.success(request, f"Asset added to {site.name}.")
        return redirect("verticals:energy_assets")

    prefill_type = request.GET.get("prefill_type", "")
    return render(request, "energy/asset_form.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites": sites,
        "asset_types": AssetType.choices,
        "action": "Add",
        "prefill_type": prefill_type,
    })


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

@login_required
@require_business
def maintenance_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    records = []
    overdue_assets = []
    if m:
        AssetMaintenanceRecord = m["AssetMaintenanceRecord"]
        EnergyAsset = m["EnergyAsset"]
        records = (
            AssetMaintenanceRecord.objects.filter(business=biz)
            .select_related("asset__site", "technician")
            .order_by("-performed_at")[:50]
        )
        overdue_assets = [
            a for a in EnergyAsset.objects.filter(
                business=biz, status__in=["operational", "degraded"]
            ).select_related("site")
            if a.is_maintenance_overdue
        ]

    return render(request, "energy/maintenance.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "records": records,
        "overdue_assets": overdue_assets,
    })


@login_required
@require_business
def maintenance_create(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_maintenance")

    EnergyAsset = m["EnergyAsset"]
    AssetMaintenanceRecord = m["AssetMaintenanceRecord"]
    MaintenanceType = m["MaintenanceType"]

    assets = EnergyAsset.objects.filter(business=biz).select_related("site")

    if request.method == "POST":
        asset_id = request.POST.get("asset")
        if not asset_id:
            messages.error(request, "Select an asset.")
            return redirect(request.path)

        asset = get_object_or_404(EnergyAsset, id=asset_id, business=biz)

        try:
            cost_str = request.POST.get("cost", "").strip()
            cost = Decimal(cost_str) if cost_str else None
        except InvalidOperation:
            cost = None

        health_str = request.POST.get("health_score_after", "").strip()
        try:
            health_after = int(health_str) if health_str else None
        except (ValueError, TypeError):
            health_after = None

        performed_at = request.POST.get("performed_at") or str(timezone.now().date())

        AssetMaintenanceRecord.objects.create(
            asset=asset,
            business=biz,
            technician=request.user,
            maintenance_type=request.POST.get("maintenance_type", MaintenanceType.ROUTINE),
            performed_at=performed_at,
            description=request.POST.get("description", "").strip(),
            parts_used=request.POST.get("parts_used", "").strip(),
            cost=cost,
            health_score_after=health_after,
            root_cause_notes=request.POST.get("root_cause_notes", "").strip(),
            follow_up_date=request.POST.get("follow_up_date") or None,
            resolved=request.POST.get("resolved") == "on",
        )

        if health_after is not None:
            asset.health_score = max(0, min(100, health_after))
            asset.save(update_fields=["health_score", "updated_at"])

        messages.success(request, f"Maintenance record logged for {asset}.")
        return redirect("verticals:energy_maintenance")

    return render(request, "energy/maintenance_form.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "assets": assets,
        "maintenance_types": MaintenanceType.choices,
        "action": "Log",
    })


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@login_required
@require_business
def alerts_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    alerts = []
    severity_choices = []
    if m:
        EnergyAlert = m["EnergyAlert"]
        AlertSeverity = m["AlertSeverity"]
        show_resolved = request.GET.get("resolved") == "1"
        qs = EnergyAlert.objects.filter(business=biz)
        if not show_resolved:
            qs = qs.filter(is_resolved=False)
        alerts = qs.select_related("site", "asset").order_by("-created_at")[:100]
        severity_choices = AlertSeverity.choices

    return render(request, "energy/alerts.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "alerts": alerts,
        "show_resolved": request.GET.get("resolved") == "1",
        "severity_choices": severity_choices,
    })


@login_required
@require_business
@require_POST
def alert_resolve(request: HttpRequest, alert_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_alerts")

    EnergyAlert = m["EnergyAlert"]
    alert = get_object_or_404(EnergyAlert, id=alert_id, business=biz)
    alert.resolve(user=request.user, notes=request.POST.get("notes", "").strip())
    messages.success(request, f"Alert resolved: {alert.title}")
    return redirect("verticals:energy_alerts")


# ---------------------------------------------------------------------------
# Economics & Savings
# ---------------------------------------------------------------------------

@login_required
@require_business
def economics(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    sites_data = []
    totals = {
        "installation_cost": Decimal("0"),
        "cumulative_savings": Decimal("0"),
        "monthly_savings": Decimal("0"),
        "roi_pct": None,
    }

    if m:
        from django.db.models import Sum
        EnergySite = m["EnergySite"]
        SavingsRecord = m["SavingsRecord"]
        today = timezone.now().date()
        month_start = today.replace(day=1)

        for site in EnergySite.objects.filter(business=biz).order_by("name"):
            site_savings = SavingsRecord.objects.filter(site=site).aggregate(
                total=Sum("estimated_savings"))["total"] or Decimal("0")
            month_savings = SavingsRecord.objects.filter(site=site, month__gte=month_start).aggregate(
                total=Sum("estimated_savings"))["total"] or Decimal("0")
            installation_cost = site.installation_cost or Decimal("0")
            roi_pct = None
            if installation_cost > 0 and site_savings > 0:
                roi_pct = round(float(site_savings / installation_cost * 100), 1)
            payback_months = None
            last_rec = SavingsRecord.objects.filter(site=site).order_by("-month").first()
            if installation_cost > 0 and last_rec and last_rec.estimated_savings > 0:
                payback_months = round(float(installation_cost / last_rec.estimated_savings))

            sites_data.append({
                "site": site,
                "cumulative_savings": site_savings,
                "monthly_savings": month_savings,
                "installation_cost": installation_cost,
                "roi_pct": roi_pct,
                "payback_months": payback_months,
            })
            totals["installation_cost"] += installation_cost
            totals["cumulative_savings"] += site_savings
            totals["monthly_savings"] += month_savings

        if totals["installation_cost"] > 0 and totals["cumulative_savings"] > 0:
            totals["roi_pct"] = round(
                float(totals["cumulative_savings"] / totals["installation_cost"] * 100), 1
            )

    return render(request, "energy/economics.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_data": sites_data,
        "totals": totals,
    })


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

@login_required
@require_business
def forecasting(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    forecasts = []
    if m:
        from django.db.models import Avg
        EnergySite = m["EnergySite"]
        EnergyReading = m["EnergyReading"]
        today = timezone.now().date()
        thirty_ago = today - timedelta(days=29)
        ninety_ago = today - timedelta(days=89)

        for site in EnergySite.objects.filter(business=biz, status="active").order_by("name"):
            avg_30 = EnergyReading.objects.filter(site=site, reading_date__gte=thirty_ago).aggregate(
                avg=Avg("generation_kwh"))["avg"] or 0
            avg_90 = EnergyReading.objects.filter(site=site, reading_date__gte=ninety_ago).aggregate(
                avg=Avg("generation_kwh"))["avg"] or 0
            avg_cons_30 = EnergyReading.objects.filter(site=site, reading_date__gte=thirty_ago).aggregate(
                avg=Avg("consumption_kwh"))["avg"] or 0

            # [AI_HOOK] Replace with ML forecasting engine
            next_7_gen = round(float(avg_30) * 7, 1) if avg_30 else None
            next_30_gen = round(float(avg_30) * 30, 1) if avg_30 else None
            next_7_cons = round(float(avg_cons_30) * 7, 1) if avg_cons_30 else None
            next_30_cons = round(float(avg_cons_30) * 30, 1) if avg_cons_30 else None

            trend = None
            if avg_30 and avg_90:
                if float(avg_30) > float(avg_90) * 1.05:
                    trend = "increasing"
                elif float(avg_30) < float(avg_90) * 0.95:
                    trend = "decreasing"
                else:
                    trend = "stable"

            forecasts.append({
                "site": site,
                "avg_daily_gen_30": round(float(avg_30), 2) if avg_30 else None,
                "avg_daily_cons_30": round(float(avg_cons_30), 2) if avg_cons_30 else None,
                "next_7_gen": next_7_gen,
                "next_30_gen": next_30_gen,
                "next_7_cons": next_7_cons,
                "next_30_cons": next_30_cons,
                "trend": trend,
            })

    return render(request, "energy/forecasting.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "forecasts": forecasts,
    })


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@login_required
@require_business
def reports(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    return render(request, "energy/reports.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
    })


# ---------------------------------------------------------------------------
# API: add energy reading
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def api_add_reading(request: HttpRequest) -> JsonResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return JsonResponse({"ok": False, "error": "Module unavailable"}, status=400)

    import json
    EnergyReading = m["EnergyReading"]
    EnergySite = m["EnergySite"]

    try:
        data = json.loads(request.body)
        site_id = data.get("site_id")
        reading_date = data.get("reading_date") or str(timezone.now().date())
        generation_kwh = data.get("generation_kwh")
        consumption_kwh = data.get("consumption_kwh")
        battery_soc_pct = data.get("battery_soc_pct")

        site = get_object_or_404(EnergySite, id=site_id, business=biz)

        reading, created = EnergyReading.objects.update_or_create(
            site=site,
            business=biz,
            reading_date=reading_date,
            defaults={
                "generation_kwh": Decimal(str(generation_kwh)) if generation_kwh is not None else None,
                "consumption_kwh": Decimal(str(consumption_kwh)) if consumption_kwh is not None else None,
                "battery_soc_pct": int(battery_soc_pct) if battery_soc_pct is not None else None,
                "notes": data.get("notes", ""),
            }
        )
        return JsonResponse({"ok": True, "created": created, "reading_id": reading.id})
    except Exception as e:
        log.exception(f"Error adding energy reading: {e}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# System Sizing — Flagship Module
# ---------------------------------------------------------------------------

@login_required
@require_business
def system_sizing_list(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    runs = []
    if m:
        SystemSizingRun = m["SystemSizingRun"]
        status_filter = request.GET.get("status", "")
        qs = SystemSizingRun.objects.filter(business=biz).select_related("site", "prepared_by")
        if status_filter:
            qs = qs.filter(status=status_filter)
        runs = qs.order_by("-updated_at")[:50]

    return render(request, "energy/system_sizing.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "runs": runs,
        "status_filter": request.GET.get("status", ""),
    })


@login_required
@require_business
def system_sizing_create(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        messages.error(request, "Energy module not available.")
        return redirect("verticals:energy_dashboard")

    SystemSizingRun = m["SystemSizingRun"]
    SizingAppliance = m["SizingAppliance"]
    SizingObjective = m["SizingObjective"]
    SystemArchitecture = m["SystemArchitecture"]
    ApplianceCategory = m["ApplianceCategory"]
    LoadPriority = m["LoadPriority"]
    EnergySite = m["EnergySite"]

    sites = EnergySite.objects.filter(business=biz).order_by("name")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "Title is required.")
            return redirect(request.path)

        site_id = request.POST.get("site")
        site = None
        if site_id:
            try:
                site = EnergySite.objects.get(id=site_id, business=biz)
            except EnergySite.DoesNotExist:
                pass

        try:
            run = SystemSizingRun.objects.create(
                business=biz,
                site=site,
                title=title,
                customer_name=request.POST.get("customer_name", "").strip(),
                customer_phone=request.POST.get("customer_phone", "").strip(),
                customer_email=request.POST.get("customer_email", "").strip(),
                customer_address=request.POST.get("customer_address", "").strip(),
                design_objective=request.POST.get("design_objective", SizingObjective.BALANCED),
                system_architecture=request.POST.get("system_architecture", SystemArchitecture.SOLAR_BATTERY),
                has_grid_access=request.POST.get("has_grid_access") == "on",
                grid_reliability_pct=int(request.POST.get("grid_reliability_pct", "80") or "80"),
                has_generator=request.POST.get("has_generator") == "on",
                peak_sun_hours=Decimal(request.POST.get("peak_sun_hours", "5.0") or "5.0"),
                panel_wattage=int(request.POST.get("panel_wattage", "550") or "550"),
                panel_efficiency_pct=int(request.POST.get("panel_efficiency_pct", "85") or "85"),
                battery_dod_pct=int(request.POST.get("battery_dod_pct", "80") or "80"),
                battery_voltage=int(request.POST.get("battery_voltage", "48") or "48"),
                autonomy_days=Decimal(request.POST.get("autonomy_days", "1.0") or "1.0"),
                diversity_factor=Decimal(request.POST.get("diversity_factor", "0.80") or "0.80"),
                simultaneity_factor=Decimal(request.POST.get("simultaneity_factor", "0.70") or "0.70"),
                future_growth_pct=int(request.POST.get("future_growth_pct", "20") or "20"),
                safety_margin_pct=int(request.POST.get("safety_margin_pct", "15") or "15"),
                notes=request.POST.get("notes", "").strip(),
                assumptions=request.POST.get("assumptions", "").strip(),
                prepared_by=request.user,
            )

            # Parse appliance rows
            names = request.POST.getlist("appliance_name")
            wattages = request.POST.getlist("appliance_wattage")
            quantities = request.POST.getlist("appliance_quantity")
            hours_list = request.POST.getlist("appliance_hours")
            categories = request.POST.getlist("appliance_category")
            priorities = request.POST.getlist("appliance_priority")
            periods = request.POST.getlist("appliance_period")
            criticals = request.POST.getlist("appliance_critical")

            for i, name in enumerate(names):
                name = name.strip()
                if not name:
                    continue
                try:
                    wattage = Decimal(wattages[i] if i < len(wattages) else "100")
                except (InvalidOperation, IndexError):
                    wattage = Decimal("100")
                try:
                    qty = int(quantities[i] if i < len(quantities) else "1")
                except (ValueError, IndexError):
                    qty = 1
                try:
                    hours = Decimal(hours_list[i] if i < len(hours_list) else "1")
                except (InvalidOperation, IndexError):
                    hours = Decimal("1")

                SizingAppliance.objects.create(
                    sizing_run=run,
                    name=name,
                    wattage=wattage,
                    quantity=qty,
                    hours_per_day=hours,
                    category=categories[i] if i < len(categories) else "custom",
                    priority=priorities[i] if i < len(priorities) else "medium",
                    usage_period=periods[i] if i < len(periods) else "both",
                    is_critical=str(i) in criticals,
                )

            # Run sizing engine
            from inventory.services.energy_sizing import compute_sizing
            result = compute_sizing(run)

            if result.get("ok"):
                messages.success(request, f"System sizing '{run.title}' computed successfully.")
            else:
                messages.warning(request, f"Sizing created but needs appliance data: {result.get('error', '')}")

            return redirect("verticals:energy_sizing_detail", run_id=run.id)

        except Exception as e:
            log.exception(f"Error creating sizing run: {e}")
            messages.error(request, f"Error: {e}")
            return redirect(request.path)

    return render(request, "energy/system_sizing_form.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites": sites,
        "objectives": SizingObjective.choices,
        "architectures": SystemArchitecture.choices,
        "appliance_categories": ApplianceCategory.choices,
        "priorities": LoadPriority.choices,
        "action": "Create",
    })


@login_required
@require_business
def system_sizing_detail(request: HttpRequest, run_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_dashboard")

    SystemSizingRun = m["SystemSizingRun"]
    from django.shortcuts import get_object_or_404
    run = get_object_or_404(SystemSizingRun, id=run_id, business=biz)
    appliances = list(run.appliances.all())

    return render(request, "energy/system_sizing_detail.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "run": run,
        "appliances": appliances,
    })


@login_required
@require_business
def system_sizing_pdf(request: HttpRequest, run_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        messages.error(request, "Energy module not available.")
        return redirect("verticals:energy_dashboard")

    SystemSizingRun = m["SystemSizingRun"]
    run = get_object_or_404(SystemSizingRun, id=run_id, business=biz)

    from inventory.services.energy_pdf import generate_sizing_pdf
    pdf_bytes = generate_sizing_pdf(run, business=biz)

    if pdf_bytes:
        from django.http import FileResponse
        response = FileResponse(
            io.BytesIO(pdf_bytes),
            content_type="application/pdf",
            as_attachment=True,
            filename=f"sizing-proposal-{run.id}-v{run.version}.pdf",
        )
        return response

    messages.error(request, "Could not generate PDF. Please ensure ReportLab is installed.")
    return redirect("verticals:energy_sizing_detail", run_id=run.id)


@login_required
@require_business
def system_sizing_clone(request: HttpRequest, run_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_dashboard")

    SystemSizingRun = m["SystemSizingRun"]
    run = get_object_or_404(SystemSizingRun, id=run_id, business=biz)
    new_run = run.clone()

    from inventory.services.energy_sizing import compute_sizing
    compute_sizing(new_run)

    messages.success(request, f"Sizing run cloned as '{new_run.title}' v{new_run.version}.")
    return redirect("verticals:energy_sizing_detail", run_id=new_run.id)


@login_required
@require_business
def system_sizing_recalculate(request: HttpRequest, run_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_dashboard")

    SystemSizingRun = m["SystemSizingRun"]
    run = get_object_or_404(SystemSizingRun, id=run_id, business=biz)

    from inventory.services.energy_sizing import compute_sizing
    result = compute_sizing(run)

    if result.get("ok"):
        messages.success(request, "Sizing recalculated successfully.")
    else:
        messages.warning(request, f"Recalculation issue: {result.get('error', '')}")

    return redirect("verticals:energy_sizing_detail", run_id=run.id)


# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

@login_required
@require_business
def monitoring(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    sites_data = []
    if m:
        from django.db.models import Sum, Avg, Count
        EnergySite = m["EnergySite"]
        EnergyAsset = m["EnergyAsset"]
        EnergyReading = m["EnergyReading"]
        today = timezone.now().date()
        seven_ago = today - timedelta(days=6)

        for site in EnergySite.objects.filter(business=biz, status="active").order_by("name"):
            assets = EnergyAsset.objects.filter(site=site)
            asset_count = assets.count()
            avg_health = assets.aggregate(avg=Avg("health_score"))["avg"] or 0
            recent_gen = EnergyReading.objects.filter(
                site=site, reading_date__gte=seven_ago
            ).aggregate(total=Sum("generation_kwh"))["total"] or Decimal("0")
            recent_cons = EnergyReading.objects.filter(
                site=site, reading_date__gte=seven_ago
            ).aggregate(total=Sum("consumption_kwh"))["total"] or Decimal("0")
            active_alerts = site.alerts.filter(is_resolved=False).count()
            latest_reading = EnergyReading.objects.filter(site=site).order_by("-reading_date").first()

            sites_data.append({
                "site": site,
                "asset_count": asset_count,
                "avg_health": round(avg_health),
                "gen_7d": recent_gen,
                "cons_7d": recent_cons,
                "active_alerts": active_alerts,
                "latest_reading": latest_reading,
                "capacity_kw": site.installed_capacity_kw or 0,
            })

    return render(request, "energy/monitoring.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_data": sites_data,
    })


# ---------------------------------------------------------------------------
# Load Management
# ---------------------------------------------------------------------------

@login_required
@require_business
def load_management(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    sites_load = []
    if m:
        from django.db.models import Avg, Max, Sum
        EnergySite = m["EnergySite"]
        EnergyReading = m["EnergyReading"]
        today = timezone.now().date()
        thirty_ago = today - timedelta(days=29)

        for site in EnergySite.objects.filter(business=biz, status="active").order_by("name"):
            readings = EnergyReading.objects.filter(site=site, reading_date__gte=thirty_ago)
            if not readings.exists():
                continue

            avg_cons = readings.aggregate(avg=Avg("consumption_kwh"))["avg"] or 0
            max_cons = readings.aggregate(mx=Max("consumption_kwh"))["mx"] or 0
            avg_gen = readings.aggregate(avg=Avg("generation_kwh"))["avg"] or 0

            capacity = float(site.installed_capacity_kw or 0)
            utilization = 0
            if capacity > 0:
                daily_capacity_kwh = capacity * 24
                utilization = min(round(float(avg_cons) / daily_capacity_kwh * 100, 1), 100) if daily_capacity_kwh > 0 else 0

            overload_risk = False
            if capacity > 0 and float(max_cons) > capacity * 24 * 0.85:
                overload_risk = True

            recommendations = []
            if overload_risk:
                recommendations.append("Peak consumption is approaching installed capacity. Consider load shedding or expansion.")
            if float(avg_gen) > 0 and float(avg_cons) > float(avg_gen) * 1.2:
                recommendations.append("Consumption exceeds generation — grid/generator dependency is high.")
            if utilization < 30 and capacity > 0:
                recommendations.append("System utilization is low. Verify readings or consider load optimization.")

            sites_load.append({
                "site": site,
                "avg_daily_cons": round(float(avg_cons), 1),
                "max_daily_cons": round(float(max_cons), 1),
                "avg_daily_gen": round(float(avg_gen), 1),
                "utilization_pct": utilization,
                "overload_risk": overload_risk,
                "recommendations": recommendations,
            })

    return render(request, "energy/load_management.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_load": sites_load,
    })


# ---------------------------------------------------------------------------
# Technician Operations
# ---------------------------------------------------------------------------

@login_required
@require_business
def technicians(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()

    visits = []
    upcoming = []
    overdue = []
    if m:
        TechnicianVisit = m["TechnicianVisit"]
        today = timezone.now().date()

        all_visits = TechnicianVisit.objects.filter(business=biz).select_related(
            "site", "technician", "related_alert"
        ).order_by("-scheduled_date")

        visits = all_visits[:50]
        upcoming = all_visits.filter(
            status="scheduled", scheduled_date__gte=today, scheduled_date__lte=today + timedelta(days=14)
        )[:10]
        overdue = all_visits.filter(
            status="scheduled", scheduled_date__lt=today
        )[:10]

    return render(request, "energy/technicians.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "visits": visits,
        "upcoming": upcoming,
        "overdue": overdue,
    })


@login_required
@require_business
def technician_visit_create(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_technicians")

    TechnicianVisit = m["TechnicianVisit"]
    EnergySite = m["EnergySite"]
    sites = EnergySite.objects.filter(business=biz).order_by("name")

    if request.method == "POST":
        site_id = request.POST.get("site")
        if not site_id:
            messages.error(request, "Site is required.")
            return redirect(request.path)

        site = get_object_or_404(EnergySite, id=site_id, business=biz)
        TechnicianVisit.objects.create(
            business=biz,
            site=site,
            technician=request.user,
            visit_type=request.POST.get("visit_type", "maintenance"),
            scheduled_date=request.POST.get("scheduled_date") or str(timezone.now().date()),
            description=request.POST.get("description", "").strip(),
        )
        messages.success(request, "Visit scheduled.")
        return redirect("verticals:energy_technicians")

    return render(request, "energy/technician_visit_form.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites": sites,
    })


# ---------------------------------------------------------------------------
# Report PDF Downloads
# ---------------------------------------------------------------------------

@login_required
@require_business
def site_report_pdf(request: HttpRequest, site_id: int) -> HttpResponse:
    biz = get_active_business(request)
    m = _models()
    if not m:
        messages.error(request, "Energy module not available.")
        return redirect("verticals:energy_reports")

    EnergySite = m["EnergySite"]
    site = get_object_or_404(EnergySite, id=site_id, business=biz)

    readings = list(site.readings.order_by("-reading_date")[:30])
    savings = list(site.savings_records.order_by("-month")[:12])
    alerts = list(site.alerts.filter(is_resolved=False).order_by("-created_at")[:20])

    from inventory.services.energy_pdf import generate_site_report_pdf
    pdf_bytes = generate_site_report_pdf(site, business=biz, readings=readings, savings=savings, alerts=alerts)

    if pdf_bytes:
        import io as _io
        from django.http import FileResponse
        return FileResponse(
            _io.BytesIO(pdf_bytes),
            content_type="application/pdf",
            as_attachment=True,
            filename=f"site-report-{site.id}.pdf",
        )

    messages.error(request, "Could not generate PDF.")
    return redirect("verticals:energy_site_detail", site_id=site.id)


# ---------------------------------------------------------------------------
# Alert Scan Trigger
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def trigger_alert_scan(request: HttpRequest) -> HttpResponse:
    biz = get_active_business(request)
    from inventory.services.energy_alerts_engine import run_alert_scan
    result = run_alert_scan(biz)
    created = result.get("created", 0)
    if created > 0:
        messages.success(request, f"Alert scan complete: {created} new alerts generated.")
    else:
        messages.info(request, "Alert scan complete. No new issues detected.")
    return redirect("verticals:energy_alerts")


# ---------------------------------------------------------------------------
# Phase 2: Scenario Comparison
# ---------------------------------------------------------------------------

@login_required
@require_business
def scenario_compare(request: HttpRequest, run_id: int) -> HttpResponse:
    """Create and display scenario comparison from a base sizing run."""
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_sizing_list")

    SSR = m["SystemSizingRun"]
    base = get_object_or_404(SSR, id=run_id, business=biz)

    if request.method == "POST":
        from inventory.services.energy_sizing import create_scenario_group
        scenarios = create_scenario_group(base)
        group_id = base.scenario_group
        messages.success(request, f"Created {len(scenarios)} scenarios for comparison.")
        return redirect("verticals:energy_scenario_view", group_id=group_id)

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "run": base,
    }
    return render(request, "energy/scenario_confirm.html", ctx)


@login_required
@require_business
def scenario_view(request: HttpRequest, group_id: str) -> HttpResponse:
    """Side-by-side scenario comparison view."""
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_sizing_list")

    from inventory.services.energy_sizing import get_scenario_comparison
    scenarios = get_scenario_comparison(group_id)
    scenarios = [s for s in scenarios if s.business == biz]

    if not scenarios:
        messages.error(request, "Scenario group not found.")
        return redirect("verticals:energy_sizing_list")

    recommended = next((s for s in scenarios if s.is_recommended_scenario), None)

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "scenarios": scenarios,
        "group_id": group_id,
        "recommended": recommended,
    }
    return render(request, "energy/scenario_compare.html", ctx)


# ---------------------------------------------------------------------------
# Phase 2: Proposal Lifecycle
# ---------------------------------------------------------------------------

@login_required
@require_business
@require_POST
def proposal_update_status(request: HttpRequest, run_id: int) -> HttpResponse:
    """Update proposal status (send, approve, convert to project)."""
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_sizing_list")

    SSR = m["SystemSizingRun"]
    EnergySite = m["EnergySite"]
    run = get_object_or_404(SSR, id=run_id, business=biz)
    action = request.POST.get("action", "")
    today = timezone.now().date()

    if action == "send_proposal":
        run.proposal_status = "proposal_sent"
        run.proposal_sent_date = today
        run.proposal_valid_until = today + timedelta(days=30)
        run.save(update_fields=["proposal_status", "proposal_sent_date", "proposal_valid_until"])
        messages.success(request, "Proposal marked as sent to customer.")

    elif action == "approve":
        run.proposal_status = "approved"
        run.approval_date = today
        run.save(update_fields=["proposal_status", "approval_date"])
        messages.success(request, "Proposal approved!")

    elif action == "convert_to_project":
        site = EnergySite.objects.create(
            business=biz,
            name=run.customer_name or run.title,
            site_type="commercial",
            status="installing",
            customer_name=run.customer_name,
            customer_phone=run.customer_phone,
            customer_email=run.customer_email,
            location=run.customer_address,
            installed_capacity_kw=run.recommended_array_kw,
            installation_cost=run.estimated_capex,
            notes=f"Created from sizing proposal: {run.title} v{run.version}",
        )
        run.proposal_status = "project"
        run.linked_project_site = site
        run.save(update_fields=["proposal_status", "linked_project_site"])
        messages.success(request, f"Project created! Site '{site.name}' is now active.")

    elif action == "reject":
        run.proposal_status = "rejected"
        run.save(update_fields=["proposal_status"])
        messages.info(request, "Proposal marked as rejected.")

    elif action == "complete":
        run.proposal_status = "completed"
        run.save(update_fields=["proposal_status"])
        if run.linked_project_site:
            run.linked_project_site.status = "active"
            run.linked_project_site.commissioning_date = today
            run.linked_project_site.save(update_fields=["status", "commissioning_date"])
        messages.success(request, "Project completed and site is now live!")

    return redirect("verticals:energy_sizing_detail", run_id=run.id)


# ---------------------------------------------------------------------------
# Phase 2: Portfolio Command Center
# ---------------------------------------------------------------------------

@login_required
@require_business
def portfolio(request: HttpRequest) -> HttpResponse:
    """Executive portfolio view across all sites."""
    biz = get_active_business(request)
    m = _models()
    if not m:
        return render(request, "energy/portfolio.html", {"business": biz, "BUSINESS_VERTICAL": "energy"})

    EnergySite = m["EnergySite"]
    EnergyAsset = m["EnergyAsset"]
    EnergyReading = m["EnergyReading"]
    SavingsRecord = m["SavingsRecord"]

    from django.db.models import Avg, Count, Sum
    thirty_days_ago = timezone.now().date() - timedelta(days=30)

    sites = EnergySite.objects.filter(business=biz, status="active")
    site_data = []
    for site in sites[:50]:
        readings = EnergyReading.objects.filter(site=site, reading_date__gte=thirty_days_ago)
        gen = readings.aggregate(t=Sum("generation_kwh"))["t"] or Decimal("0")
        cons = readings.aggregate(t=Sum("consumption_kwh"))["t"] or Decimal("0")
        savings = SavingsRecord.objects.filter(
            site=site, month__gte=thirty_days_ago,
        ).aggregate(t=Sum("estimated_savings"))["t"] or Decimal("0")
        asset_count = site.assets.filter(status__in=["operational", "degraded"]).count()
        avg_health = site.assets.filter(
            status__in=["operational", "degraded"],
        ).aggregate(a=Avg("health_score"))["a"] or 0

        site_data.append({
            "site": site,
            "generation_30d": gen,
            "consumption_30d": cons,
            "savings_30d": savings,
            "asset_count": asset_count,
            "avg_health": round(float(avg_health)),
            "capacity_kw": site.installed_capacity_kw or 0,
        })

    site_data.sort(key=lambda x: x["savings_30d"], reverse=True)

    portfolio_totals = {
        "total_sites": sites.count(),
        "total_capacity": sites.aggregate(t=Sum("installed_capacity_kw"))["t"] or 0,
        "total_generation": sum(s["generation_30d"] for s in site_data),
        "total_consumption": sum(s["consumption_30d"] for s in site_data),
        "total_savings": sum(s["savings_30d"] for s in site_data),
    }

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "site_data": site_data,
        "totals": portfolio_totals,
        "best_sites": site_data[:5],
        "worst_sites": sorted(site_data, key=lambda x: x["avg_health"])[:5],
    }
    return render(request, "energy/portfolio.html", ctx)


# ---------------------------------------------------------------------------
# Phase 2: Energy Copilot Intelligence Panel
# ---------------------------------------------------------------------------

@login_required
@require_business
def copilot(request: HttpRequest) -> HttpResponse:
    """Energy Copilot — rule-based intelligence panel."""
    biz = get_active_business(request)
    from inventory.services.energy_copilot import generate_copilot_insights
    insights = generate_copilot_insights(biz)

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "insights": insights,
    }
    return render(request, "energy/copilot.html", ctx)


# ---------------------------------------------------------------------------
# Phase 2: Data Ingestion (CSV upload)
# ---------------------------------------------------------------------------

@login_required
@require_business
def data_upload(request: HttpRequest) -> HttpResponse:
    """Upload CSV data for energy readings."""
    biz = get_active_business(request)
    m = _models()
    if not m:
        return redirect("verticals:energy_dashboard")

    EnergySite = m["EnergySite"]
    EnergyReading = m["EnergyReading"]

    if request.method == "POST" and request.FILES.get("csv_file"):
        import csv
        from inventory.models_energy import EnergyDataUpload

        csv_file = request.FILES["csv_file"]
        site_id = request.POST.get("site_id")
        site = get_object_or_404(EnergySite, id=site_id, business=biz) if site_id else None

        upload = EnergyDataUpload.objects.create(
            business=biz, site=site,
            upload_type="csv",
            filename=csv_file.name,
            uploaded_by=request.user,
        )

        rows_total = 0
        rows_imported = 0
        rows_skipped = 0
        errors = []

        try:
            decoded = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded)
            for row in reader:
                rows_total += 1
                try:
                    from datetime import date as _date
                    reading_date = _date.fromisoformat(row.get("date", "").strip())
                    gen = Decimal(row.get("generation_kwh", "0").strip() or "0")
                    cons = Decimal(row.get("consumption_kwh", "0").strip() or "0")
                    soc = row.get("battery_soc_pct", "").strip()

                    reading, created = EnergyReading.objects.update_or_create(
                        site=site, reading_date=reading_date,
                        defaults={
                            "business": biz,
                            "generation_kwh": gen,
                            "consumption_kwh": cons,
                            "battery_soc_pct": int(soc) if soc else None,
                            "source": "manual",
                        },
                    )
                    rows_imported += 1
                except Exception as e:
                    rows_skipped += 1
                    errors.append(f"Row {rows_total}: {str(e)[:100]}")
        except Exception as e:
            errors.append(f"CSV parse error: {str(e)[:200]}")

        # Data quality scoring
        quality = 100
        if rows_total > 0:
            success_rate = rows_imported / rows_total * 100
            quality = max(int(success_rate), 0)
        if rows_skipped > rows_total * 0.2:
            quality = min(quality, 60)

        upload.rows_total = rows_total
        upload.rows_imported = rows_imported
        upload.rows_skipped = rows_skipped
        upload.errors = errors[:20]
        upload.data_quality_score = quality
        upload.save()

        messages.success(
            request,
            f"Imported {rows_imported}/{rows_total} readings. "
            f"Data quality: {quality}%."
        )
        return redirect("verticals:energy_monitoring")

    sites = EnergySite.objects.filter(business=biz).order_by("name")
    uploads = []
    try:
        from inventory.models_energy import EnergyDataUpload
        uploads = EnergyDataUpload.objects.filter(business=biz).order_by("-created_at")[:10]
    except Exception:
        pass

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites": sites,
        "uploads": uploads,
    }
    return render(request, "energy/data_upload.html", ctx)
