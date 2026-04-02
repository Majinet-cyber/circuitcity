# inventory/services/business_os.py
"""
Cross-Vertical Business OS Intelligence Layer.

Provides unified analytics across all business verticals (energy, welding,
groceries, etc.) for the executive Business OS dashboard.

Follows single source of truth: aggregates from canonical vertical models
without duplicating calculation logic.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Max, Min, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def get_business_os_metrics(business) -> dict:
    """
    Compute cross-vertical metrics for the Business OS dashboard.
    Gracefully handles missing verticals/models.
    """
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)
    bk = getattr(business, "business_kind", "")

    metrics = {
        "business": business,
        "business_kind": bk,
        "verticals_active": [],
        "total_revenue_30d": ZERO,
        "total_orders_30d": 0,
        "inventory_value": ZERO,
        "low_stock_alerts": 0,
        "employee_activity": 0,
        "alerts_active": 0,
        "insights": [],
        "vertical_metrics": {},
    }

    # --- Energy vertical metrics ---
    energy_data = _get_energy_metrics(business, thirty_days_ago)
    if energy_data:
        metrics["verticals_active"].append("energy")
        metrics["vertical_metrics"]["energy"] = energy_data
        metrics["alerts_active"] += energy_data.get("active_alerts", 0)
        metrics["total_revenue_30d"] += energy_data.get("savings_30d", ZERO)
        metrics["employee_activity"] += energy_data.get("technician_visits_30d", 0)

    # --- Welding vertical metrics ---
    welding_data = _get_welding_metrics(business, thirty_days_ago)
    if welding_data:
        metrics["verticals_active"].append("welding")
        metrics["vertical_metrics"]["welding"] = welding_data
        metrics["total_revenue_30d"] += welding_data.get("revenue_30d", ZERO)
        metrics["total_orders_30d"] += welding_data.get("jobs_30d", 0)
        metrics["inventory_value"] += welding_data.get("materials_value", ZERO)
        metrics["low_stock_alerts"] += welding_data.get("low_stock_count", 0)

    # --- Groceries vertical metrics ---
    groceries_data = _get_groceries_metrics(business, thirty_days_ago)
    if groceries_data:
        metrics["verticals_active"].append("groceries")
        metrics["vertical_metrics"]["groceries"] = groceries_data
        metrics["total_revenue_30d"] += groceries_data.get("revenue_30d", ZERO)
        metrics["total_orders_30d"] += groceries_data.get("sales_30d", 0)
        metrics["inventory_value"] += groceries_data.get("stock_value", ZERO)
        metrics["low_stock_alerts"] += groceries_data.get("low_stock_count", 0)

    # --- Cross-vertical insights ---
    metrics["insights"] = _generate_os_insights(metrics)

    return metrics


def _get_energy_metrics(business, since_date) -> dict | None:
    """Fetch energy vertical KPIs. Returns None if vertical not available."""
    try:
        from inventory.models_energy import (
            EnergyAlert, EnergyAsset, EnergyReading, EnergySite,
            SavingsRecord, SystemSizingRun, TechnicianVisit,
        )
    except ImportError:
        return None

    sites = EnergySite.objects.filter(business=business)
    if not sites.exists():
        return None

    active_sites = sites.filter(status="active").count()
    total_assets = EnergyAsset.objects.filter(business=business).count()
    active_alerts = EnergyAlert.objects.filter(business=business, is_resolved=False).count()

    capacity = sites.filter(status="active").aggregate(
        total=Sum("installed_capacity_kw"),
    )["total"] or ZERO

    savings = SavingsRecord.objects.filter(
        business=business, month__gte=since_date,
    ).aggregate(total=Sum("estimated_savings"))["total"] or ZERO

    readings = EnergyReading.objects.filter(
        business=business, reading_date__gte=since_date,
    )
    gen_30d = readings.aggregate(total=Sum("generation_kwh"))["total"] or ZERO
    cons_30d = readings.aggregate(total=Sum("consumption_kwh"))["total"] or ZERO

    visits = TechnicianVisit.objects.filter(
        business=business, scheduled_date__gte=since_date,
    ).count()

    proposals = SystemSizingRun.objects.filter(
        business=business, proposal_status__in=["proposal_sent", "approved"],
    ).count()

    avg_health = EnergyAsset.objects.filter(
        business=business, status__in=["operational", "degraded"],
    ).aggregate(avg=Avg("health_score"))["avg"] or 0

    return {
        "active_sites": active_sites,
        "total_assets": total_assets,
        "installed_capacity_kw": capacity,
        "active_alerts": active_alerts,
        "savings_30d": savings,
        "generation_30d_kwh": gen_30d,
        "consumption_30d_kwh": cons_30d,
        "technician_visits_30d": visits,
        "active_proposals": proposals,
        "avg_asset_health": round(float(avg_health)),
    }


def _get_welding_metrics(business, since_date) -> dict | None:
    """Fetch welding vertical KPIs."""
    try:
        from inventory.models_welding import (
            WeldingCost, WeldingJob, WeldingMaterial,
            WeldingQuote, WeldingRevenue,
        )
    except ImportError:
        return None

    jobs = WeldingJob.objects.filter(business=business)
    if not jobs.exists() and not WeldingMaterial.objects.filter(business=business).exists():
        return None

    jobs_30d = jobs.filter(created_at__date__gte=since_date).count()
    active_jobs = jobs.filter(status__in=["pending", "in_progress"]).count()
    completed_30d = jobs.filter(
        status__in=["ready", "delivered"], completed_at__date__gte=since_date,
    ).count()
    delayed_jobs = jobs.filter(status="pending").count()

    revenue = WeldingRevenue.objects.filter(
        business=business, received_on__gte=since_date,
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    costs = WeldingCost.objects.filter(
        business=business, incurred_on__gte=since_date,
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    materials = WeldingMaterial.objects.filter(business=business, is_active=True)
    materials_value = sum(
        (m.quantity_in_stock * m.price_mwk for m in materials), ZERO,
    )
    low_stock = sum(1 for m in materials if m.is_low_stock)

    quotes_30d = WeldingQuote.objects.filter(
        business=business, created_at__date__gte=since_date,
    ).count()
    accepted_quotes = WeldingQuote.objects.filter(
        business=business, status="accepted", created_at__date__gte=since_date,
    ).count()

    return {
        "jobs_30d": jobs_30d,
        "active_jobs": active_jobs,
        "completed_30d": completed_30d,
        "delayed_jobs": delayed_jobs,
        "revenue_30d": revenue,
        "costs_30d": costs,
        "profit_30d": revenue - costs,
        "materials_value": materials_value,
        "low_stock_count": low_stock,
        "quotes_30d": quotes_30d,
        "accepted_quotes": accepted_quotes,
    }


def _get_groceries_metrics(business, since_date) -> dict | None:
    """Fetch groceries vertical KPIs."""
    try:
        from inventory.models import MerchProduct
        from inventory.models_verticals import GrocerySale
    except ImportError:
        return None

    products = MerchProduct.objects.filter(business=business, kind="grocery", is_active=True)
    if not products.exists():
        return None

    total_products = products.count()
    stock_value = sum(
        ((p.quantity_in_stock or 0) * (p.cost_price or ZERO) for p in products), ZERO,
    )
    low_stock = products.filter(quantity_in_stock__lt=10, quantity_in_stock__gt=0).count()
    out_of_stock = products.filter(quantity_in_stock=0).count()

    sales = GrocerySale.objects.filter(business=business, sold_at__date__gte=since_date)
    sales_count = sales.count()
    revenue = sales.aggregate(total=Sum("total_price"))["total"] or ZERO
    costs = sales.aggregate(total=Sum("total_cost"))["total"] or ZERO

    return {
        "total_products": total_products,
        "stock_value": stock_value,
        "low_stock_count": low_stock,
        "out_of_stock": out_of_stock,
        "sales_30d": sales_count,
        "revenue_30d": revenue,
        "costs_30d": costs,
        "profit_30d": revenue - costs,
    }


def _generate_os_insights(metrics) -> list[dict]:
    """Generate cross-vertical executive insights."""
    insights = []
    vm = metrics.get("vertical_metrics", {})

    # Cross-vertical revenue comparison
    revenues = {}
    for vname, vdata in vm.items():
        rev = vdata.get("revenue_30d") or vdata.get("savings_30d") or ZERO
        if rev > 0:
            revenues[vname] = rev

    if len(revenues) > 1:
        best = max(revenues, key=revenues.get)
        insights.append({
            "icon": "bi-graph-up-arrow",
            "text": f"{best.title()} vertical showing strongest revenue contribution this month.",
            "type": "success",
        })

    # Low stock cross-vertical
    total_low = metrics.get("low_stock_alerts", 0)
    if total_low > 0:
        insights.append({
            "icon": "bi-exclamation-triangle",
            "text": f"{total_low} low-stock alert(s) across your business.",
            "type": "warning",
        })

    # Alert summary
    alerts = metrics.get("alerts_active", 0)
    if alerts > 0:
        insights.append({
            "icon": "bi-bell",
            "text": f"{alerts} active alert(s) requiring attention.",
            "type": "danger" if alerts > 5 else "warning",
        })

    # Welding-specific
    weld = vm.get("welding", {})
    if weld.get("delayed_jobs", 0) > 0:
        insights.append({
            "icon": "bi-clock-history",
            "text": f"{weld['delayed_jobs']} welding job(s) pending — review workshop capacity.",
            "type": "warning",
        })
    if weld.get("profit_30d") and weld["profit_30d"] < 0:
        insights.append({
            "icon": "bi-exclamation-circle",
            "text": "Welding workshop costs exceeding revenue this period.",
            "type": "danger",
        })

    # Groceries-specific
    groc = vm.get("groceries", {})
    if groc.get("out_of_stock", 0) > 5:
        insights.append({
            "icon": "bi-box-seam",
            "text": f"{groc['out_of_stock']} grocery products are out of stock — restock urgently.",
            "type": "danger",
        })

    # Energy-specific
    enrg = vm.get("energy", {})
    if enrg.get("active_proposals", 0) > 0:
        insights.append({
            "icon": "bi-lightning-charge",
            "text": f"{enrg['active_proposals']} energy proposal(s) in pipeline — potential new projects.",
            "type": "info",
        })

    return insights[:10]
