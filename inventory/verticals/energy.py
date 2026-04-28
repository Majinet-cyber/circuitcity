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

    # ── Demo/placeholder detection ──────────────────────────────────────────
    # A workspace is "new" (empty) if it has no sites AND no assets AND no readings.
    # In that state we inject clearly-labeled sample estimates so the dashboard
    # doesn't look dead. Real data always overrides placeholder values.
    is_new_workspace = (total_sites == 0 and total_assets == 0)
    _DEMO = {
        "active_sites": 1,
        "total_assets": 4,
        "installed_capacity": Decimal("5.2"),
        "generation_this_month": Decimal("620"),
        "consumption_this_month": Decimal("480"),
        "avg_battery_health": 96,
        "avg_asset_health": 94,
        "savings_this_month": Decimal("185000"),
        "label": "sample estimate",
    }

    ctx["stats"] = {
        "total_sites": total_sites,
        "active_sites": active_sites if not is_new_workspace else _DEMO["active_sites"],
        "total_assets": total_assets if not is_new_workspace else _DEMO["total_assets"],
        "operational_assets": operational_assets,
        "degraded_assets": degraded_assets,
        "faulty_assets": faulty_assets,
        "critical_alerts": critical_alerts,
        "high_alerts": high_alerts,
        "maintenance_overdue": maintenance_overdue,
        "savings_this_month": savings_this_month if not is_new_workspace else _DEMO["savings_this_month"],
        "cumulative_savings": cumulative_savings,
        "generation_this_month": generation_this_month if not is_new_workspace else _DEMO["generation_this_month"],
        "consumption_this_month": consumption_this_month if not is_new_workspace else _DEMO["consumption_this_month"],
        "gen_this_week": gen_this_week,
        "installed_capacity": installed_capacity if not is_new_workspace else _DEMO["installed_capacity"],
        "avg_battery_health": round(avg_battery_health) if not is_new_workspace else _DEMO["avg_battery_health"],
        "avg_inverter_health": round(avg_inverter_health) if not is_new_workspace else _DEMO["avg_asset_health"],
        "avg_asset_health": round(avg_asset_health) if not is_new_workspace else _DEMO["avg_asset_health"],
    }
    ctx["is_new_workspace"] = is_new_workspace
    ctx["demo_label"] = _DEMO["label"] if is_new_workspace else ""
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

    # Demo site preview cards for new workspaces
    if is_new_workspace:
        ctx["demo_site_preview"] = [
            {"label": "Site Name", "value": "Solar Demo Site", "note": "Sample preview"},
            {"label": "Installed Capacity", "value": "5.2 kW", "highlight": True},
            {"label": "Monthly Generation", "value": "620 kWh", "highlight": True},
            {"label": "Monthly Consumption", "value": "480 kWh"},
            {"label": "Battery Health", "value": "96%", "highlight": True},
            {"label": "Asset Health", "value": "94%"},
            {"label": "Est. Savings/Month", "value": "MWK 185,000", "highlight": True, "note": "vs grid tariff"},
            {"label": "Blackout Risk", "value": "Medium", "note": "Needs sizing review"},
        ]
    else:
        ctx["demo_site_preview"] = []

    # Decision recommendations (real data)
    decision_recs = []
    if is_new_workspace:
        decision_recs = [
            {"type": "info", "text": "Your next best action is to add real appliances and run system sizing to get accurate recommendations."},
            {"type": "info", "text": "Start with 'Add Site' to register your first installation location."},
        ]
    else:
        if avg_battery_health > 0 and avg_battery_health < 60:
            decision_recs.append({"type": "risk", "text": f"Battery health at {avg_battery_health:.0f}% — plan replacement before the next rainy season to avoid prolonged blackouts."})
        if maintenance_overdue > 0:
            decision_recs.append({"type": "warning", "text": f"{maintenance_overdue} asset(s) have overdue maintenance. Battery checks should happen monthly."})
        if critical_alerts > 0:
            decision_recs.append({"type": "risk", "text": f"Critical alerts should be handled before adding more loads. {critical_alerts} critical alert(s) require action."})
        if generation_this_month > 0 and consumption_this_month > generation_this_month:
            ratio = float(consumption_this_month / generation_this_month)
            decision_recs.append({"type": "warning", "text": f"Consumption is {ratio:.1f}× generation this month. Shift non-critical loads to solar hours (10:00–15:00)."})
        if sizing_count == 0 and total_sites > 0:
            decision_recs.append({"type": "info", "text": "No system sizing runs yet. Run sizing using your actual appliances to get payback and ROI projections."})
        if not decision_recs:
            decision_recs.append({"type": "info", "text": "System looks healthy. Review forecasting data and plan for peak season demand."})
    ctx["decision_recommendations"] = decision_recs

    # Financial opportunity panel
    financial_opp = []
    if is_new_workspace:
        financial_opp = [
            {"label": "Sample Investment", "value": "MWK 3,500,000", "color": "#4f46e5", "note": "Estimate — run sizing for your actual quote"},
            {"label": "Monthly Savings", "value": "MWK 185,000", "color": "#059669", "note": "vs grid tariff at MWK 185/kWh"},
            {"label": "Annual Savings", "value": "MWK 2,220,000", "color": "#059669"},
            {"label": "Payback Period", "value": "~18.9 months", "color": "#0891b2", "note": "Battery cost dominates payback"},
            {"label": "Key Decision", "value": "Battery cost drives payback", "color": "#d97706", "note": "Reduce night loads or shift usage to solar hours"},
        ]
    elif savings_this_month > 0:
        financial_opp = [
            {"label": "This Month Savings", "value": f"MWK {int(savings_this_month):,}", "color": "#059669"},
            {"label": "Cumulative Savings", "value": f"MWK {int(cumulative_savings):,}", "color": "#059669"},
        ]
        if generation_this_month > 0:
            monthly_mwk = float(generation_this_month) * 185
            financial_opp.append({"label": "Grid Offset Value", "value": f"MWK {int(monthly_mwk):,}", "color": "#4f46e5", "note": "at MWK 185/kWh"})
    ctx["financial_opportunity"] = financial_opp if (is_new_workspace or savings_this_month > 0) else []

    # ── Demo alerts and risks for new workspaces ────────────────────────────
    if is_new_workspace:
        ctx["demo_alerts"] = [
            {
                "severity": "medium",
                "icon": "🟡",
                "title": "Evening load may drain battery by midnight",
                "description": "Based on a 5.2 kW system with 200Ah battery: high evening loads (TV, pumping, lighting) after 20:00 risk depleting battery before 00:00.",
                "action": "Shift heavy loads (ironing, pumping, washing) to 10:00–15:00 solar hours.",
                "type_label": "Load Risk",
                "demo": True,
            },
            {
                "severity": "low",
                "icon": "🟢",
                "title": "Clean panels monthly to protect generation",
                "description": "Dust and dirt on panels can reduce generation by up to 15%. Schedule a monthly panel cleaning to maintain optimal output.",
                "action": "Schedule technician visit: panel inspection + cleaning.",
                "type_label": "Maintenance",
                "demo": True,
            },
            {
                "severity": "low",
                "icon": "🟢",
                "title": "Adding one more battery improves night autonomy",
                "description": "Current sample system has a medium blackout risk after 22:00. Adding one 200Ah battery extends night autonomy by approximately 4 hours.",
                "action": "Review battery sizing — run system sizing with real load data.",
                "type_label": "Capacity",
                "demo": True,
            },
            {
                "severity": "low",
                "icon": "🟢",
                "title": "ROI improves if you shift high-consumption loads",
                "description": "Moving ironing, water pumping, or washing to 10:00–15:00 (peak solar hours) reduces battery draw and shortens payback period by 2–3 months.",
                "action": "Configure load scheduling — talk to your installer.",
                "type_label": "Optimization",
                "demo": True,
            },
        ]
        ctx["demo_risks"] = [
            {
                "name": "Inverter (Demo)",
                "asset_type": "inverter",
                "icon": "⚡",
                "risk_score": 82,
                "risk_color": "#ef4444",
                "note": "Inverter load reaches 82% during evening peak",
                "demo": True,
            },
            {
                "name": "Battery Bank (Demo)",
                "asset_type": "battery",
                "icon": "🔋",
                "risk_score": 55,
                "risk_color": "#f97316",
                "note": "Battery may drop below 30% after 22:00",
                "demo": True,
            },
        ]
        ctx["demo_forecast"] = {
            "next_7_day_demand_kwh": "113.7",
            "next_30_day_demand_kwh": "480",
            "explanation": "Sample estimate: based on 5.2 kW system generating 620 kWh/month.",
            "demo": True,
        }
    else:
        ctx["demo_alerts"] = []
        ctx["demo_risks"] = []
        ctx["demo_forecast"] = None

    # Commerce KPIs (energy retail)
    try:
        from inventory.models_energy import EnergyProduct, EnergyItemSale, EnergyStockIn
        from django.db.models import Sum, Count

        products_qs = EnergyProduct.objects.filter(business=biz, is_active=True)
        total_products = products_qs.count()
        low_stock_products = sum(1 for p in products_qs if p.is_low_stock)
        from django.db import models as _djmodels
        inventory_value = products_qs.aggregate(
            val=Sum(_djmodels.ExpressionWrapper(
                _djmodels.F("cost_price") * _djmodels.F("quantity_in_stock"),
                output_field=_djmodels.DecimalField(max_digits=16, decimal_places=2)
            ))
        )["val"] or Decimal("0")

        sales_this_month = EnergyItemSale.objects.filter(
            business=biz, sold_at__date__gte=month_start, is_reversed=False
        ).aggregate(
            revenue=Sum("total_amount"),
            profit=Sum("profit"),
            count=Count("id"),
        )
        recent_energy_sales = (
            EnergyItemSale.objects
            .filter(business=biz, is_reversed=False)
            .select_related("product", "sold_by")
            .order_by("-sold_at")[:8]
        )

        ctx["commerce"] = {
            "total_products": total_products,
            "low_stock_products": low_stock_products,
            "inventory_value": inventory_value,
            "revenue_this_month": sales_this_month["revenue"] or Decimal("0"),
            "profit_this_month": sales_this_month["profit"] or Decimal("0"),
            "sales_this_month": sales_this_month["count"] or 0,
        }
        ctx["recent_energy_sales"] = recent_energy_sales
    except Exception as _ce:
        log.debug(f"Energy commerce KPIs unavailable: {_ce}")
        ctx["commerce"] = {}
        ctx["recent_energy_sales"] = []

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
    is_demo_alerts = False
    demo_alerts = []

    if m:
        EnergyAlert = m["EnergyAlert"]
        AlertSeverity = m["AlertSeverity"]
        EnergySite = m["EnergySite"]
        EnergyAsset = m["EnergyAsset"]
        show_resolved = request.GET.get("resolved") == "1"
        qs = EnergyAlert.objects.filter(business=biz)
        if not show_resolved:
            qs = qs.filter(is_resolved=False)
        alerts = qs.select_related("site", "asset").order_by("-created_at")[:100]
        severity_choices = AlertSeverity.choices

        # Show demo alerts if no real sites/assets exist
        has_sites = EnergySite.objects.filter(business=biz).exists()
        has_assets = EnergyAsset.objects.filter(business=biz).exists()
        if not has_sites and not has_assets and not alerts:
            is_demo_alerts = True
            demo_alerts = [
                {
                    "severity": "medium", "icon": "🟡",
                    "title": "Evening load may drain battery by midnight",
                    "description": "Based on a 5.2 kW system with 200Ah battery: high evening loads (TV, pumping, lighting) after 20:00 risk depleting battery before 00:00.",
                    "action": "Shift heavy loads (ironing, pumping, washing) to 10:00–15:00 solar hours.",
                    "type_label": "Load Risk",
                },
                {
                    "severity": "low", "icon": "🟢",
                    "title": "Current sample system has medium blackout risk after 22:00",
                    "description": "Without a second battery, nights with high TV + appliance loads risk partial blackout. This is a sizing gap, not a fault.",
                    "action": "Run system sizing with real appliances to get an accurate battery recommendation.",
                    "type_label": "Sizing",
                },
                {
                    "severity": "low", "icon": "🟢",
                    "title": "Clean panels monthly to protect generation",
                    "description": "Dust and debris can reduce solar output by 10–15%. A monthly cleaning routine protects your investment.",
                    "action": "Schedule technician visit: panel inspection + cleaning.",
                    "type_label": "Maintenance",
                },
                {
                    "severity": "low", "icon": "🟢",
                    "title": "Move ironing, pumping, or washing to solar hours",
                    "description": "Running high-wattage appliances between 10:00–15:00 uses direct solar power, saving battery charge for night use.",
                    "action": "Configure load scheduling for high-demand appliances.",
                    "type_label": "Optimization",
                },
                {
                    "severity": "low", "icon": "🟢",
                    "title": "Adding one battery improves night autonomy by ~4 hours",
                    "description": "Sample ROI calculation: one 200Ah battery at MWK 650,000 extends night autonomy and reduces blackout risk significantly.",
                    "action": "Review battery sizing — run system sizing with your real load data.",
                    "type_label": "ROI",
                },
            ]

    return render(request, "energy/alerts.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "alerts": alerts,
        "show_resolved": request.GET.get("resolved") == "1",
        "severity_choices": severity_choices,
        "is_demo_alerts": is_demo_alerts,
        "demo_alerts": demo_alerts,
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

    is_demo_economics = (len(sites_data) == 0 and totals["cumulative_savings"] == Decimal("0"))
    economics_recs = []
    if is_demo_economics:
        economics_recs = [
            {"type": "info", "text": "Run system sizing using your real appliances to get accurate payback and ROI projections."},
            {"type": "info", "text": "Payback improves if grid tariff or diesel costs rise. Track monthly savings to confirm system performance."},
        ]
    else:
        if totals["cumulative_savings"] > 0 and totals["installation_cost"] > 0:
            ratio = float(totals["cumulative_savings"] / totals["installation_cost"])
            if ratio < 0.3:
                economics_recs.append({"type": "info", "text": f"Savings so far represent {ratio*100:.0f}% of investment. System is on track — keep logging monthly savings records."})
        economics_recs.append({"type": "info", "text": "Payback improves if grid tariff or diesel costs rise. Ensure monthly savings records are logged for all sites."})

    demo_econ_cards = [
        {"label": "Total Investment", "value": "MWK 3,500,000", "color": "#4f46e5", "note": "5.2 kW system estimate"},
        {"label": "Monthly Savings", "value": "MWK 185,000", "color": "#059669", "note": "vs grid at MWK 185/kWh"},
        {"label": "Annual Savings", "value": "MWK 2,220,000", "color": "#059669"},
        {"label": "Payback Period", "value": "~18.9 months", "color": "#0891b2", "note": "After installation"},
        {"label": "25-Year ROI", "value": "~1,490%", "color": "#6366f1", "note": "With 5% tariff escalation"},
        {"label": "Monthly Reserve", "value": "MWK 5,833", "color": "#f59e0b", "note": "2% maintenance reserve/year"},
        {"label": "Battery Replacement", "value": "Year 10", "color": "#dc2626", "note": "Set aside MWK 50,000/month"},
        {"label": "Grid vs Solar", "value": "37× cheaper", "color": "#059669", "note": "After payback vs diesel"},
    ] if is_demo_economics else []

    return render(request, "energy/economics.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_data": sites_data,
        "totals": totals,
        "is_demo_economics": is_demo_economics,
        "economics_recs": economics_recs,
        "demo_econ_cards": demo_econ_cards,
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

        def _dec(val, default="0"):
            try:
                return Decimal(val) if val and str(val).strip() else None
            except InvalidOperation:
                return None

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
                energy_tariff_per_kwh=_dec(request.POST.get("energy_tariff_per_kwh", "")),
                diesel_cost_per_litre=_dec(request.POST.get("diesel_cost_per_litre", "")),
                installation_cost_pct=_dec(request.POST.get("installation_cost_pct", "")),
                annual_maintenance_pct=_dec(request.POST.get("annual_maintenance_pct", "")),
                tariff_escalation_pct=Decimal(request.POST.get("tariff_escalation_pct", "5.0") or "5.0"),
                discount_rate_pct=Decimal(request.POST.get("discount_rate_pct", "10.0") or "10.0"),
                # Editable component cost assumptions
                cost_per_panel_wp=_dec(request.POST.get("cost_per_panel_wp", "")),
                cost_per_battery_kwh=_dec(request.POST.get("cost_per_battery_kwh", "")),
                cost_per_inverter_kw=_dec(request.POST.get("cost_per_inverter_kw", "")),
                cost_per_cc_amp=_dec(request.POST.get("cost_per_cc_amp", "")),
                cost_wiring_lump=_dec(request.POST.get("cost_wiring_lump", "")),
                cost_breakers_lump=_dec(request.POST.get("cost_breakers_lump", "")),
                cost_mounting_lump=_dec(request.POST.get("cost_mounting_lump", "")),
                notes=request.POST.get("notes", "").strip(),
                assumptions=request.POST.get("assumptions", "").strip(),
                prepared_by=request.user,
            )

            # Parse appliance rows
            names = request.POST.getlist("appliance_name")
            wattages = request.POST.getlist("appliance_wattage")
            surges = request.POST.getlist("appliance_surge")
            quantities = request.POST.getlist("appliance_quantity")
            hours_list = request.POST.getlist("appliance_hours")
            categories = request.POST.getlist("appliance_category")
            priorities = request.POST.getlist("appliance_priority")
            periods = request.POST.getlist("appliance_period")
            criticals = set(request.POST.getlist("appliance_critical"))

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
                surge_w = None
                try:
                    sv = surges[i] if i < len(surges) else ""
                    surge_w = Decimal(sv) if sv and sv.strip() else None
                except (InvalidOperation, IndexError):
                    surge_w = None

                SizingAppliance.objects.create(
                    sizing_run=run,
                    name=name,
                    wattage=wattage,
                    surge_wattage=surge_w,
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

    is_demo_monitoring = (len(sites_data) == 0)
    monitoring_recs = []
    if not is_demo_monitoring:
        # Real-data recommendations
        for sd in sites_data:
            if sd["avg_health"] < 60:
                monitoring_recs.append({"type": "warning", "text": f"{sd['site'].name}: Battery reaches low state by 22:00; reduce evening loads."})
            if sd["active_alerts"] > 0:
                monitoring_recs.append({"type": "risk", "text": f"{sd['site'].name}: {sd['active_alerts']} alert(s) require attention before adding more loads."})
        if not monitoring_recs:
            monitoring_recs.append({"type": "info", "text": "All monitored sites are within normal operating parameters."})

    demo_monitoring_sites = [
        {"name": "Solar Demo Site", "type": "Residential", "assets": 4, "gen_7d": 43.4, "cons_7d": 33.6, "capacity": 5.2, "health": 94, "alert": None},
        {"name": "Backup Office System", "type": "Commercial", "assets": 2, "gen_7d": 18.2, "cons_7d": 21.0, "capacity": 2.5, "health": 78, "alert": "Battery health below 80% — schedule inspection"},
    ] if is_demo_monitoring else []

    return render(request, "energy/monitoring.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_data": sites_data,
        "is_demo_monitoring": is_demo_monitoring,
        "demo_monitoring_sites": demo_monitoring_sites,
        "monitoring_recs": monitoring_recs,
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

    is_demo_load = (len(sites_load) == 0)
    load_recs = []
    if not is_demo_load:
        for sl in sites_load:
            if sl["overload_risk"]:
                load_recs.append({"type": "risk", "text": f"{sl['site'].name}: Running iron + fridge + TV together may exceed inverter comfort zone. Stagger appliances."})
            if float(sl["avg_daily_cons"]) > float(sl["avg_daily_gen"]) * 1.2:
                load_recs.append({"type": "warning", "text": f"{sl['site'].name}: Evening loads are responsible for most blackout risk. Move washing/ironing to 10:00–15:00."})
        if not load_recs:
            load_recs.append({"type": "info", "text": "Shift non-critical loads to 10:00–15:00 to maximise solar usage and reduce battery drain."})

    return render(request, "energy/load_management.html", {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "sites_load": sites_load,
        "is_demo_load": is_demo_load,
        "load_recs": load_recs,
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


# ---------------------------------------------------------------------------
# Energy Commerce — Product Catalog, Stock-In, Sales
# ---------------------------------------------------------------------------

def _commerce_models():
    """Lazy-load energy commerce models; returns None tuple on import error."""
    try:
        from inventory.models_energy import EnergyProduct, EnergyStockIn, EnergyItemSale, EnergyProductCategory
        return EnergyProduct, EnergyStockIn, EnergyItemSale, EnergyProductCategory
    except Exception:
        return None, None, None, None


@login_required
@require_business
def energy_catalog(request: HttpRequest) -> HttpResponse:
    """Product catalog: list active products with stock levels."""
    biz = get_active_business(request)
    EnergyProduct, _, _, EnergyProductCategory = _commerce_models()
    if EnergyProduct is None:
        messages.error(request, "Energy commerce module unavailable.")
        return redirect("verticals:energy_dashboard")

    products = EnergyProduct.objects.filter(business=biz, is_active=True).order_by("category", "name")
    low_stock = [p for p in products if p.is_low_stock]

    category_choices = EnergyProductCategory.choices

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "products": products,
        "low_stock_count": len(low_stock),
        "total_value": sum(p.inventory_value for p in products),
        "category_choices": category_choices,
    }
    return render(request, "energy/product_list.html", ctx)


@login_required
@require_business
def energy_stock_in(request: HttpRequest) -> HttpResponse:
    """Stock-in view: record received energy goods."""
    from django.db import transaction as db_tx
    biz = get_active_business(request)
    EnergyProduct, EnergyStockIn, _, EnergyProductCategory = _commerce_models()
    if EnergyProduct is None:
        messages.error(request, "Energy commerce module unavailable.")
        return redirect("verticals:energy_dashboard")

    if request.method == "POST":
        product_id = request.POST.get("product_id", "").strip()
        new_product_name = request.POST.get("new_product_name", "").strip()
        category = request.POST.get("category", "other").strip()
        quantity_str = request.POST.get("quantity", "").strip()
        cost_price_str = request.POST.get("cost_price", "0").strip()
        selling_price_str = request.POST.get("selling_price", "0").strip()
        supplier = request.POST.get("supplier", "").strip()
        notes = request.POST.get("notes", "").strip()
        received_date_str = request.POST.get("received_date", "").strip()

        # Validate required fields
        errors = []
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                errors.append("Quantity must be at least 1.")
        except (ValueError, TypeError):
            errors.append("Enter a valid quantity.")

        try:
            cost_price = Decimal(cost_price_str)
        except (InvalidOperation, ValueError):
            cost_price = Decimal("0.00")

        try:
            selling_price = Decimal(selling_price_str)
        except (InvalidOperation, ValueError):
            selling_price = Decimal("0.00")

        from datetime import date as _date
        try:
            received_date = _date.fromisoformat(received_date_str) if received_date_str else _date.today()
        except ValueError:
            received_date = _date.today()

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                with db_tx.atomic():
                    if product_id:
                        product = EnergyProduct.objects.get(id=product_id, business=biz)
                    elif new_product_name:
                        product, _ = EnergyProduct.objects.get_or_create(
                            business=biz,
                            name=new_product_name,
                            category=category,
                            defaults={
                                "selling_price": selling_price,
                                "unit": request.POST.get("unit", "unit").strip() or "unit",
                            },
                        )
                    else:
                        messages.error(request, "Select an existing product or enter a new product name.")
                        return redirect(request.path)

                    # Update product prices and stock
                    product.cost_price = cost_price
                    if selling_price > 0:
                        product.selling_price = selling_price
                    product.quantity_in_stock += quantity
                    product.save()

                    EnergyStockIn.objects.create(
                        business=biz,
                        product=product,
                        quantity=quantity,
                        cost_price=cost_price,
                        supplier=supplier,
                        notes=notes,
                        received_date=received_date,
                        recorded_by=request.user,
                    )

                messages.success(request, f"✅ Stock-in recorded: {product.name} ×{quantity}")
                return redirect("verticals:energy_catalog")
            except EnergyProduct.DoesNotExist:
                messages.error(request, "Selected product not found.")
            except Exception as exc:
                log.error(f"Energy stock-in error: {exc}", exc_info=True)
                messages.error(request, f"Stock-in failed: {exc}")

    products = EnergyProduct.objects.filter(business=biz, is_active=True).order_by("category", "name")
    category_choices = EnergyProductCategory.choices

    # Wizard presets: product family → subtype → prefilled values
    import json as _json
    wizard_presets = _json.dumps({
        "solar_panel": {
            "subtypes": [
                {"label": "100W Mono Panel", "name": "100W Mono Solar Panel", "cost": 185000, "price": 240000, "unit": "unit", "notes": "100W monocrystalline panel. Suitable for small lighting kits."},
                {"label": "200W Mono Panel", "name": "200W Mono Solar Panel", "cost": 320000, "price": 420000, "unit": "unit", "notes": "200W monocrystalline panel. Ideal for home starter systems."},
                {"label": "350W Mono Panel", "name": "350W Mono Solar Panel", "cost": 480000, "price": 620000, "unit": "unit", "notes": "350W monocrystalline. Good for medium home or office systems."},
                {"label": "450W Mono Panel", "name": "450W Mono Solar Panel", "cost": 580000, "price": 750000, "unit": "unit", "notes": "450W monocrystalline. High output for large systems."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "battery": {
            "subtypes": [
                {"label": "100Ah 12V AGM", "name": "100Ah 12V AGM Battery", "cost": 320000, "price": 420000, "unit": "unit", "notes": "AGM sealed battery. Good for moderate cycle life. 12V 100Ah ≈ 1.2kWh."},
                {"label": "200Ah 12V AGM", "name": "200Ah 12V AGM Battery", "cost": 580000, "price": 750000, "unit": "unit", "notes": "AGM sealed battery. 12V 200Ah ≈ 2.4kWh usable at 50% DoD."},
                {"label": "100Ah Lithium (LiFePO4)", "name": "100Ah 12V Lithium LiFePO4 Battery", "cost": 780000, "price": 1000000, "unit": "unit", "notes": "Lithium iron phosphate. 80% DoD, 2000+ cycles. Best long-term ROI."},
                {"label": "200Ah Lithium (LiFePO4)", "name": "200Ah 12V Lithium LiFePO4 Battery", "cost": 1450000, "price": 1900000, "unit": "unit", "notes": "200Ah lithium ≈ 4.8kWh usable. Excellent for night autonomy."},
                {"label": "Gel Battery 100Ah", "name": "100Ah 12V Gel Battery", "cost": 350000, "price": 450000, "unit": "unit", "notes": "Gel battery. Maintenance-free. Better than AGM in high temperatures."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "inverter": {
            "subtypes": [
                {"label": "1kW Pure Sine Inverter", "name": "1kW Pure Sine Inverter", "cost": 280000, "price": 370000, "unit": "unit", "notes": "1000W pure sine wave. Suitable for lighting + small appliances."},
                {"label": "3kW Hybrid Inverter", "name": "3kW Hybrid Solar Inverter", "cost": 750000, "price": 980000, "unit": "unit", "notes": "3kW hybrid inverter with built-in MPPT charge controller."},
                {"label": "5kW Hybrid Inverter", "name": "5kW Hybrid Solar Inverter", "cost": 1200000, "price": 1550000, "unit": "unit", "notes": "5kW hybrid with MPPT. Suitable for large homes and small offices."},
                {"label": "5kW Off-Grid Inverter", "name": "5kW Off-Grid Inverter", "cost": 950000, "price": 1250000, "unit": "unit", "notes": "5kW off-grid inverter. No grid tie. Use for rural/off-grid sites."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "charge_controller": {
            "subtypes": [
                {"label": "20A MPPT Controller", "name": "20A MPPT Charge Controller", "cost": 95000, "price": 130000, "unit": "unit", "notes": "20A MPPT. For small systems up to 260W at 12V."},
                {"label": "40A MPPT Controller", "name": "40A MPPT Charge Controller", "cost": 175000, "price": 230000, "unit": "unit", "notes": "40A MPPT. For medium systems up to 520W at 12V."},
                {"label": "60A MPPT Controller", "name": "60A MPPT Charge Controller", "cost": 290000, "price": 380000, "unit": "unit", "notes": "60A MPPT. For larger systems."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "pico_system": {
            "subtypes": [
                {"label": "Phone Charging Kit", "name": "Pico Solar Phone Charging Kit", "cost": 25000, "price": 38000, "unit": "unit", "notes": "Small panel + USB output for phone charging. Suitable for rural areas."},
                {"label": "Lighting Kit (3 lights)", "name": "Pico Solar Lighting Kit (3 Lights)", "cost": 55000, "price": 80000, "unit": "unit", "notes": "3-LED lighting kit + small solar panel. Includes phone charging port."},
                {"label": "TV + Lighting Kit", "name": "Pico Solar TV + Lighting Kit", "cost": 185000, "price": 250000, "unit": "unit", "notes": "Supports small LED TV + 4 lights + phone charging. ~80W panel."},
                {"label": "Shop Starter Kit", "name": "Pico Solar Shop Starter Kit", "cost": 320000, "price": 430000, "unit": "unit", "notes": "For small shops: 100W panel + 50Ah battery + inverter + 4 lights + USB."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "solar_kit": {
            "subtypes": [
                {"label": "Home Starter Kit (1kW)", "name": "1kW Home Solar Starter Kit", "cost": 1200000, "price": 1600000, "unit": "set", "notes": "Complete kit: 2×200W panels + 100Ah AGM + 1kW inverter + cabling."},
                {"label": "Home System (2kW)", "name": "2kW Home Solar System Kit", "cost": 2200000, "price": 2900000, "unit": "set", "notes": "4×200W panels + 200Ah AGM + 2kW inverter + cabling + MC4 connectors."},
                {"label": "Business System (5kW)", "name": "5kW Business Solar System Kit", "cost": 4800000, "price": 6300000, "unit": "set", "notes": "5kW complete kit for small offices or shops. Includes all components."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "set", "notes": ""},
            ]
        },
        "cable_protection": {
            "subtypes": [
                {"label": "4mm² DC Solar Cable (per metre)", "name": "4mm² DC Solar Cable", "cost": 1800, "price": 2500, "unit": "metre", "notes": "4mm² copper solar cable (red or black). For panel-to-controller runs."},
                {"label": "6mm² DC Cable (per metre)", "name": "6mm² DC Solar Cable", "cost": 2500, "price": 3500, "unit": "metre", "notes": "6mm² for high-current runs. Use for battery-to-inverter connections."},
                {"label": "MC4 Connector Pair", "name": "MC4 Solar Connector Pair", "cost": 1500, "price": 2500, "unit": "pair", "notes": "Waterproof MC4 connectors. For panel-to-panel or panel-to-cable joints."},
                {"label": "Circuit Breaker 63A DC", "name": "63A DC Circuit Breaker", "cost": 18000, "price": 28000, "unit": "unit", "notes": "DC-rated breaker for battery-to-inverter protection."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "appliance": {
            "subtypes": [
                {"label": "LED Bulb 9W", "name": "LED Bulb 9W", "cost": 3500, "price": 5500, "unit": "unit", "notes": "9W LED, E27. Suitable for solar-powered lighting."},
                {"label": "LED Bulb 15W", "name": "LED Bulb 15W", "cost": 5500, "price": 8000, "unit": "unit", "notes": "15W LED, E27. Bright enough for shop or living room."},
                {"label": "DC Fan 12V", "name": "12V DC Ceiling Fan", "cost": 65000, "price": 95000, "unit": "unit", "notes": "12V DC fan. Draws only 25W. Ideal for solar-powered rooms."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
        "mounting": {
            "subtypes": [
                {"label": "Roof Mount Rail (per set)", "name": "Solar Panel Roof Mount Rail Set", "cost": 45000, "price": 68000, "unit": "set", "notes": "Aluminium roof mounting rails for 2 panels. Includes L-brackets."},
                {"label": "Ground Mount Frame (2 panels)", "name": "Solar Ground Mount Frame (2 Panels)", "cost": 85000, "price": 120000, "unit": "set", "notes": "Adjustable angle ground mount for 2 panels. Galvanized steel."},
                {"label": "Custom/Other", "name": "", "cost": 0, "price": 0, "unit": "unit", "notes": ""},
            ]
        },
    })

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "products": products,
        "category_choices": category_choices,
        "today": timezone.now().date().isoformat(),
        "wizard_presets": wizard_presets,
    }
    return render(request, "energy/stock_in.html", ctx)


@login_required
@require_business
def energy_sell(request: HttpRequest) -> HttpResponse:
    """Sell view: record a sale of an energy product."""
    from django.db import transaction as db_tx
    biz = get_active_business(request)
    EnergyProduct, _, EnergyItemSale, _ = _commerce_models()
    if EnergyProduct is None:
        messages.error(request, "Energy commerce module unavailable.")
        return redirect("verticals:energy_dashboard")

    if request.method == "POST":
        product_id = request.POST.get("product_id", "").strip()
        quantity_str = request.POST.get("quantity", "1").strip()
        unit_price_str = request.POST.get("unit_price", "0").strip()
        payment_method = request.POST.get("payment_method", "CASH").strip()
        customer_name = request.POST.get("customer_name", "").strip()
        notes = request.POST.get("notes", "").strip()

        errors = []
        try:
            qty = int(quantity_str)
            if qty <= 0:
                errors.append("Quantity must be at least 1.")
        except (ValueError, TypeError):
            errors.append("Enter a valid quantity.")
            qty = 1

        try:
            unit_price = Decimal(unit_price_str)
        except (InvalidOperation, ValueError):
            errors.append("Enter a valid unit price.")
            unit_price = Decimal("0.00")

        if not product_id:
            errors.append("Please select a product.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                product = EnergyProduct.objects.get(id=product_id, business=biz, is_active=True)

                if product.quantity_in_stock < qty:
                    messages.error(
                        request,
                        f"Insufficient stock. Requested {qty}, available {product.quantity_in_stock}."
                    )
                else:
                    with db_tx.atomic():
                        sale = EnergyItemSale.objects.create(
                            business=biz,
                            product=product,
                            quantity=qty,
                            unit_price=unit_price,
                            unit_cost=product.cost_price,
                            payment_method=payment_method,
                            customer_name=customer_name,
                            notes=notes,
                            sold_by=request.user,
                        )
                        product.quantity_in_stock -= qty
                        product.save(update_fields=["quantity_in_stock", "updated_at"])

                        # Email managers after commit
                        _sale_id = sale.id
                        _biz_id = biz.id
                        db_tx.on_commit(
                            lambda: _email_managers_on_energy_sale(_sale_id, _biz_id)
                        )

                    messages.success(
                        request,
                        f"✅ Sale recorded: {product.name} ×{qty} — {biz.currency if hasattr(biz, 'currency') else 'MWK'} {sale.total_amount:,.2f}"
                    )
                    return redirect("verticals:energy_sell")
            except EnergyProduct.DoesNotExist:
                messages.error(request, "Selected product not found.")
            except Exception as exc:
                log.error(f"Energy sell error: {exc}", exc_info=True)
                messages.error(request, f"Sale failed: {exc}")

    # GET: show form
    products = (
        EnergyProduct.objects.filter(business=biz, is_active=True, quantity_in_stock__gt=0)
        .order_by("category", "name")
    )

    # Group products by category for the sell wizard
    import json as _json
    products_by_category: dict = {}
    for p in products:
        cat = p.get_category_display() if hasattr(p, "get_category_display") else p.category
        cat_key = p.category
        if cat_key not in products_by_category:
            products_by_category[cat_key] = {"label": cat, "products": []}
        products_by_category[cat_key]["products"].append({
            "id": p.id,
            "name": p.name,
            "price": float(p.selling_price),
            "cost": float(p.cost_price),
            "stock": p.quantity_in_stock,
            "unit": p.unit,
        })

    sell_categories = [
        {"key": "solar_panel", "label": "Solar Panel", "icon": "☀️", "desc": "Monocrystalline panels"},
        {"key": "battery", "label": "Battery", "icon": "🔋", "desc": "AGM, Gel, Lithium"},
        {"key": "inverter", "label": "Inverter", "icon": "⚡", "desc": "Off-grid & hybrid"},
        {"key": "charge_controller", "label": "Charge Controller", "icon": "🔌", "desc": "MPPT controllers"},
        {"key": "pico_system", "label": "Pico Kit", "icon": "🔆", "desc": "Starter solar kits"},
        {"key": "solar_kit", "label": "Full System Package", "icon": "🏡", "desc": "Complete system bundles"},
        {"key": "cable_protection", "label": "Cable & Protection", "icon": "🔧", "desc": "Cables, connectors, breakers"},
        {"key": "appliance", "label": "Appliance / Load", "icon": "💡", "desc": "LED bulbs, fans, DC appliances"},
        {"key": "mounting", "label": "Mounting Structure", "icon": "🏗️", "desc": "Roof & ground mounts"},
    ]

    ctx = {
        "business": biz,
        "BUSINESS_VERTICAL": "energy",
        "products": products,
        "payment_choices": EnergyItemSale.PAYMENT_CHOICES if EnergyItemSale else [],
        "products_by_category_json": _json.dumps(products_by_category),
        "sell_categories": sell_categories,
    }
    return render(request, "energy/sell.html", ctx)


def _email_managers_on_energy_sale(sale_id: int, business_id: int) -> None:
    """Email all managers after a committed energy sale — never raises."""
    from django.core.mail import send_mail
    from django.conf import settings as dj_settings
    from tenants.models import Business, Membership
    from inventory.models_energy import EnergyItemSale as _Sale

    try:
        sale = _Sale.objects.select_related("business", "product", "sold_by").get(pk=sale_id)
        biz = Business.objects.get(pk=business_id)
        managers = Membership.objects.filter(
            business=biz, role__in=["manager", "owner"], status="active"
        ).select_related("user")
        recipients = [m.user.email for m in managers if m.user.email]
        if not recipients:
            return

        currency = getattr(biz, "currency", "MWK")
        cashier = (
            sale.sold_by.get_full_name() or sale.sold_by.username
        ) if sale.sold_by else "System"
        subject = f"New Energy Sale — {biz.name} — {currency} {sale.total_amount:,.2f}"
        body = (
            f"A new energy product sale was recorded at {biz.name}.\n\n"
            f"Product       : {sale.product.name}\n"
            f"Category      : {sale.product.get_category_display()}\n"
            f"Quantity      : {sale.quantity} {sale.product.unit}\n"
            f"Unit Price    : {currency} {sale.unit_price:,.2f}\n"
            f"Total         : {currency} {sale.total_amount:,.2f}\n"
            f"Profit        : {currency} {sale.profit:,.2f}\n"
            f"Payment       : {sale.payment_method}\n"
            f"Cashier       : {cashier}\n"
            f"Date/Time     : {sale.sold_at.strftime('%Y-%m-%d %H:%M')}\n"
        )
        if sale.customer_name:
            body += f"Customer      : {sale.customer_name}\n"

        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "noreply@emajinet.com"),
            recipient_list=recipients,
            fail_silently=True,
        )
    except Exception as exc:
        log.error(f"_email_managers_on_energy_sale failed for sale #{sale_id}: {exc}", exc_info=True)


@login_required
@require_business
def energy_seed_catalog(request: HttpRequest) -> HttpResponse:
    """
    Idempotent seed endpoint: creates the standard energy product catalog
    for the active business. Only creates items that don't already exist.
    """
    from django.db import transaction as db_tx
    biz = get_active_business(request)
    EnergyProduct, _, _, EnergyProductCategory = _commerce_models()
    if EnergyProduct is None:
        messages.error(request, "Energy commerce module unavailable.")
        return redirect("verticals:energy_dashboard")

    CATALOG = [
        # Solar Panels
        {"name": "50W Mono Solar Panel",        "category": "solar_panel",       "unit": "unit"},
        {"name": "100W Mono Solar Panel",       "category": "solar_panel",       "unit": "unit"},
        {"name": "200W Mono Solar Panel",       "category": "solar_panel",       "unit": "unit"},
        {"name": "300W Mono Solar Panel",       "category": "solar_panel",       "unit": "unit"},
        {"name": "400W Mono Solar Panel",       "category": "solar_panel",       "unit": "unit"},
        {"name": "550W Mono Solar Panel",       "category": "solar_panel",       "unit": "unit"},
        # Batteries
        {"name": "100Ah 12V AGM Battery",       "category": "battery",           "unit": "unit"},
        {"name": "200Ah 12V AGM Battery",       "category": "battery",           "unit": "unit"},
        {"name": "100Ah Lithium (LiFePO4)",     "category": "battery",           "unit": "unit"},
        {"name": "200Ah Lithium (LiFePO4)",     "category": "battery",           "unit": "unit"},
        {"name": "5kWh Lithium Battery Pack",   "category": "battery",           "unit": "unit"},
        # Inverters
        {"name": "300W Pure Sine Inverter",     "category": "inverter",          "unit": "unit"},
        {"name": "500W Pure Sine Inverter",     "category": "inverter",          "unit": "unit"},
        {"name": "1000W Pure Sine Inverter",    "category": "inverter",          "unit": "unit"},
        {"name": "2000W Pure Sine Inverter",    "category": "inverter",          "unit": "unit"},
        {"name": "3000W Pure Sine Inverter",    "category": "inverter",          "unit": "unit"},
        {"name": "5000W Hybrid Inverter",       "category": "inverter",          "unit": "unit"},
        # Charge Controllers
        {"name": "10A MPPT Charge Controller",  "category": "charge_controller", "unit": "unit"},
        {"name": "20A MPPT Charge Controller",  "category": "charge_controller", "unit": "unit"},
        {"name": "30A MPPT Charge Controller",  "category": "charge_controller", "unit": "unit"},
        {"name": "40A MPPT Charge Controller",  "category": "charge_controller", "unit": "unit"},
        {"name": "60A MPPT Charge Controller",  "category": "charge_controller", "unit": "unit"},
        # Solar Lights
        {"name": "5W Solar Bulb",               "category": "solar_light",       "unit": "unit"},
        {"name": "10W Solar Bulb",              "category": "solar_light",       "unit": "unit"},
        {"name": "30W Solar Street Light",      "category": "solar_light",       "unit": "unit"},
        {"name": "50W Solar Street Light",      "category": "solar_light",       "unit": "unit"},
        {"name": "Solar Garden Light",          "category": "solar_light",       "unit": "unit"},
        # Cables & Wiring
        {"name": "Solar Cable 4mm² (metre)",    "category": "cable_wire",        "unit": "metre"},
        {"name": "Solar Cable 6mm² (metre)",    "category": "cable_wire",        "unit": "metre"},
        {"name": "Battery Cable 16mm² (metre)", "category": "cable_wire",        "unit": "metre"},
        {"name": "Battery Cable 25mm² (metre)", "category": "cable_wire",        "unit": "metre"},
        # Breakers & Protection
        {"name": "10A DC Circuit Breaker",      "category": "breaker",           "unit": "unit"},
        {"name": "20A DC Circuit Breaker",      "category": "breaker",           "unit": "unit"},
        {"name": "40A DC Circuit Breaker",      "category": "breaker",           "unit": "unit"},
        {"name": "60A DC Fuse Holder",          "category": "breaker",           "unit": "unit"},
        {"name": "100A Battery Fuse",           "category": "breaker",           "unit": "unit"},
        # Mounting
        {"name": "Roof Mount Brackets (pair)",  "category": "mounting",          "unit": "pair"},
        {"name": "Ground Mount Frame (1 panel)","category": "mounting",          "unit": "unit"},
        {"name": "Mounting Rail (metre)",       "category": "mounting",          "unit": "metre"},
        {"name": "Mid Clamp",                   "category": "mounting",          "unit": "unit"},
        {"name": "End Clamp",                   "category": "mounting",          "unit": "unit"},
        # Connectors
        {"name": "MC4 Connector Pair",          "category": "connector",         "unit": "pair"},
        {"name": "MC4 Branch Connector (Y)",    "category": "connector",         "unit": "unit"},
        {"name": "MC4 Cable Crimping Tool",     "category": "connector",         "unit": "unit"},
        # Gas Equipment
        {"name": "2-Burner Gas Cooker",         "category": "gas_cooker",        "unit": "unit"},
        {"name": "3-Burner Gas Cooker",         "category": "gas_cooker",        "unit": "unit"},
        {"name": "Single Burner Gas Cooker",    "category": "gas_cooker",        "unit": "unit"},
        {"name": "6kg Gas Cylinder (filled)",   "category": "gas_cylinder",      "unit": "unit"},
        {"name": "14kg Gas Cylinder (filled)",  "category": "gas_cylinder",      "unit": "unit"},
        {"name": "45kg Gas Cylinder (filled)",  "category": "gas_cylinder",      "unit": "unit"},
        {"name": "Standard Gas Regulator",      "category": "gas_regulator",     "unit": "unit"},
        {"name": "High-Pressure Gas Regulator", "category": "gas_regulator",     "unit": "unit"},
        # Energy Meters
        {"name": "Single-Phase Energy Meter",   "category": "energy_meter",      "unit": "unit"},
        {"name": "Three-Phase Energy Meter",    "category": "energy_meter",      "unit": "unit"},
        {"name": "Prepaid Smart Meter",         "category": "energy_meter",      "unit": "unit"},
        # Pumps
        {"name": "Solar Water Pump 12V",        "category": "pump",              "unit": "unit"},
        {"name": "Solar Water Pump 24V",        "category": "pump",              "unit": "unit"},
        {"name": "Submersible Solar Pump",      "category": "pump",              "unit": "unit"},
        # Backup Kits
        {"name": "100W Solar Home Kit",         "category": "backup_kit",        "unit": "kit"},
        {"name": "200W Solar Home Kit",         "category": "backup_kit",        "unit": "kit"},
        {"name": "500W Off-Grid Starter Kit",   "category": "backup_kit",        "unit": "kit"},
        {"name": "1kW Mini Off-Grid System",    "category": "backup_kit",        "unit": "kit"},
    ]

    created_count = 0
    with db_tx.atomic():
        for item in CATALOG:
            _, created = EnergyProduct.objects.get_or_create(
                business=biz,
                name=item["name"],
                category=item["category"],
                defaults={
                    "unit": item.get("unit", "unit"),
                    "is_seeded": True,
                    "is_active": True,
                },
            )
            if created:
                created_count += 1

    if created_count:
        messages.success(request, f"✅ Seeded {created_count} energy products into your catalog.")
    else:
        messages.info(request, "Catalog already up to date — no new products added.")

    return redirect("verticals:energy_catalog")
