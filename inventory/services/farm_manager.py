# inventory/services/farm_manager.py
"""
Single Source of Truth (SSOT) for Farm Manager computations.

All profit/estimation calculations are pure functions that take data as input
and return deterministic results. These functions are unit-testable and
do not access the database directly.

Usage:
    from inventory.services.farm_manager import (
        compute_monthly_profit,
        compute_enterprise_profit,
        compute_crop_projection,
        compute_livestock_snapshot,
        compute_alerts,
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, TypedDict

from django.utils import timezone


# ==============================================================================
# TYPE DEFINITIONS
# ==============================================================================


class LedgerEntryData(TypedDict, total=False):
    """Data structure for a ledger entry (extracted from model).

    `total=False` so optional linkage fields can be absent.
    """
    id: int
    date: date
    entry_type: str   # "expense" | "sale" | "other_income"
    enterprise_type: str
    category: str
    amount_mwk: Decimal
    quantity: Optional[Decimal]
    unit: str
    livestock_batch_id: Optional[int]   # FK to FarmLivestockBatch
    crop_season_id: Optional[int]       # FK to FarmCropSeason


class LivestockEventData(TypedDict):
    """Data structure for a livestock event."""
    id: int
    batch_id: int
    event_type: str  # birth, death, purchase, sale, transfer_in, transfer_out, slaughter
    date: date
    count: int
    unit_price_mwk: Optional[Decimal]


class LivestockBatchData(TypedDict):
    """Data structure for a livestock batch."""
    id: int
    animal_type: str
    name: str
    count_current: int
    valuation_enabled: bool
    avg_weight_kg: Optional[Decimal]
    price_per_kg_mwk: Optional[Decimal]
    price_per_animal_mwk: Optional[Decimal]


class CropSeasonData(TypedDict):
    """Data structure for a crop season."""
    id: int
    crop_type: str
    name: str
    start_date: date
    end_date: Optional[date]
    area_value: Decimal
    area_unit: str
    projected_yield: Optional[Decimal]
    yield_unit: str
    projected_price_per_unit_mwk: Optional[Decimal]
    actual_yield: Optional[Decimal]
    actual_price_per_unit_mwk: Optional[Decimal]
    status: str


@dataclass
class MonthlyProfitResult:
    """Result of monthly profit computation."""
    year: int
    month: int
    total_income: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    sales_count: int
    expense_count: int
    top_expense_categories: List[Dict[str, Any]]
    income_by_enterprise: Dict[str, Decimal]
    expense_by_enterprise: Dict[str, Decimal]


@dataclass
class EnterpriseProfitResult:
    """Result of enterprise-specific profit computation."""
    enterprise_type: str
    total_income: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    entry_count: int


@dataclass
class CropProjectionResult:
    """Result of crop season projection computation."""
    season_id: int
    season_name: str
    projected_income: Optional[Decimal]
    actual_income: Optional[Decimal]
    income_variance: Optional[Decimal]
    income_variance_pct: Optional[Decimal]
    projected_costs: Decimal
    actual_costs: Decimal
    cost_variance: Decimal
    cost_variance_pct: Optional[Decimal]
    projected_profit: Optional[Decimal]
    actual_profit: Decimal


@dataclass
class LivestockSnapshotResult:
    """Result of livestock snapshot computation."""
    batch_id: int
    batch_name: str
    animal_type: str
    count_current: int
    births_total: int
    deaths_total: int
    purchases_total: int
    sales_total: int
    mortality_rate: Optional[Decimal]
    estimated_value: Optional[Decimal]


@dataclass
class AlertItem:
    """An alert/notification for the farmer."""
    alert_type: str  # expenses_rising, no_sales, high_mortality, low_profit
    severity: str  # info, warning, critical
    title: str
    message: str
    data: Dict[str, Any]


# ==============================================================================
# CORE COMPUTATION FUNCTIONS (PURE, DETERMINISTIC)
# ==============================================================================


def compute_monthly_profit(
    ledger_entries: List[LedgerEntryData],
    year: int,
    month: int,
) -> MonthlyProfitResult:
    """
    Compute monthly profit summary from ledger entries.
    
    Args:
        ledger_entries: List of ledger entry data dicts
        year: Year to filter
        month: Month to filter (1-12)
    
    Returns:
        MonthlyProfitResult with income, expenses, net profit, and breakdowns
    
    Pure function: deterministic output for same inputs.
    """
    # Filter entries for the specified month
    month_entries = [
        e for e in ledger_entries
        if e["date"].year == year and e["date"].month == month
    ]
    
    # Separate income and expenses
    income_entries = [e for e in month_entries if e["entry_type"] in ("sale", "other_income")]
    expense_entries = [e for e in month_entries if e["entry_type"] == "expense"]
    
    # Sum totals
    total_income = sum((e["amount_mwk"] for e in income_entries), Decimal("0"))
    total_expenses = sum((e["amount_mwk"] for e in expense_entries), Decimal("0"))
    net_profit = total_income - total_expenses
    
    # Group expenses by category
    expense_by_category: Dict[str, Decimal] = {}
    for e in expense_entries:
        cat = e["category"]
        expense_by_category[cat] = expense_by_category.get(cat, Decimal("0")) + e["amount_mwk"]
    
    # Sort to get top expense categories
    sorted_categories = sorted(
        expense_by_category.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    top_expense_categories = [
        {"category": cat, "amount": amt, "percentage": (amt / total_expenses * 100) if total_expenses > 0 else Decimal("0")}
        for cat, amt in sorted_categories[:5]
    ]
    
    # Group by enterprise type
    income_by_enterprise: Dict[str, Decimal] = {}
    expense_by_enterprise: Dict[str, Decimal] = {}
    
    for e in income_entries:
        ent = e["enterprise_type"]
        income_by_enterprise[ent] = income_by_enterprise.get(ent, Decimal("0")) + e["amount_mwk"]
    
    for e in expense_entries:
        ent = e["enterprise_type"]
        expense_by_enterprise[ent] = expense_by_enterprise.get(ent, Decimal("0")) + e["amount_mwk"]
    
    return MonthlyProfitResult(
        year=year,
        month=month,
        total_income=total_income,
        total_expenses=total_expenses,
        net_profit=net_profit,
        sales_count=len(income_entries),
        expense_count=len(expense_entries),
        top_expense_categories=top_expense_categories,
        income_by_enterprise=income_by_enterprise,
        expense_by_enterprise=expense_by_enterprise,
    )


def compute_enterprise_profit(
    ledger_entries: List[LedgerEntryData],
    enterprise_type: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> EnterpriseProfitResult:
    """
    Compute profit for a specific enterprise type.
    
    Args:
        ledger_entries: List of ledger entry data dicts
        enterprise_type: Enterprise to filter by (e.g., "pigs", "maize")
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        EnterpriseProfitResult with totals for that enterprise
    """
    # Filter by enterprise
    filtered = [e for e in ledger_entries if e["enterprise_type"] == enterprise_type]
    
    # Filter by date range if provided
    if start_date:
        filtered = [e for e in filtered if e["date"] >= start_date]
    if end_date:
        filtered = [e for e in filtered if e["date"] <= end_date]
    
    income_entries = [e for e in filtered if e["entry_type"] in ("sale", "other_income")]
    expense_entries = [e for e in filtered if e["entry_type"] == "expense"]
    
    total_income = sum((e["amount_mwk"] for e in income_entries), Decimal("0"))
    total_expenses = sum((e["amount_mwk"] for e in expense_entries), Decimal("0"))
    
    return EnterpriseProfitResult(
        enterprise_type=enterprise_type,
        total_income=total_income,
        total_expenses=total_expenses,
        net_profit=total_income - total_expenses,
        entry_count=len(filtered),
    )


def compute_crop_projection(
    season: CropSeasonData,
    ledger_entries: List[LedgerEntryData],
) -> CropProjectionResult:
    """
    Compute projected vs actual for a crop season.
    
    Args:
        season: Crop season data
        ledger_entries: All ledger entries (will filter by season date range)
    
    Returns:
        CropProjectionResult with variance analysis
    """
    # Calculate projected income
    projected_income: Optional[Decimal] = None
    if season["projected_yield"] and season["projected_price_per_unit_mwk"]:
        projected_income = season["projected_yield"] * season["projected_price_per_unit_mwk"]
    
    # Calculate actual income
    actual_income: Optional[Decimal] = None
    if season["actual_yield"] and season["actual_price_per_unit_mwk"]:
        actual_income = season["actual_yield"] * season["actual_price_per_unit_mwk"]
    
    # Income variance
    income_variance: Optional[Decimal] = None
    income_variance_pct: Optional[Decimal] = None
    if projected_income is not None and actual_income is not None:
        income_variance = actual_income - projected_income
        if projected_income > 0:
            income_variance_pct = (income_variance / projected_income) * 100
    
    # Filter ledger entries for this season's date range
    season_entries = [
        e for e in ledger_entries
        if e["date"] >= season["start_date"]
        and (season["end_date"] is None or e["date"] <= season["end_date"])
        and e["enterprise_type"] == season["crop_type"]
    ]
    
    # Calculate actual costs from ledger
    actual_costs = sum(
        (e["amount_mwk"] for e in season_entries if e["entry_type"] == "expense"),
        Decimal("0"),
    )
    
    # Projected costs: we use actual costs as baseline if no projection specified
    # (In real system, could store projected costs per season)
    projected_costs = actual_costs  # Placeholder
    
    cost_variance = actual_costs - projected_costs
    cost_variance_pct: Optional[Decimal] = None
    if projected_costs > 0:
        cost_variance_pct = (cost_variance / projected_costs) * 100
    
    # Calculate profits
    projected_profit: Optional[Decimal] = None
    if projected_income is not None:
        projected_profit = projected_income - projected_costs
    
    actual_income_for_profit = actual_income if actual_income is not None else Decimal("0")
    actual_profit = actual_income_for_profit - actual_costs
    
    return CropProjectionResult(
        season_id=season["id"],
        season_name=season["name"],
        projected_income=projected_income,
        actual_income=actual_income,
        income_variance=income_variance,
        income_variance_pct=income_variance_pct,
        projected_costs=projected_costs,
        actual_costs=actual_costs,
        cost_variance=cost_variance,
        cost_variance_pct=cost_variance_pct,
        projected_profit=projected_profit,
        actual_profit=actual_profit,
    )


def compute_livestock_snapshot(
    batch: LivestockBatchData,
    events: List[LivestockEventData],
    as_of_date: Optional[date] = None,
) -> LivestockSnapshotResult:
    """
    Compute a snapshot of livestock batch status from events.
    
    Args:
        batch: Batch data
        events: All events for this batch
        as_of_date: Optional date to compute snapshot as of (defaults to today)
    
    Returns:
        LivestockSnapshotResult with counts, rates, and valuation
    """
    if as_of_date is None:
        as_of_date = timezone.now().date()
    
    # Filter events for this batch up to as_of_date
    batch_events = [
        e for e in events
        if e["batch_id"] == batch["id"] and e["date"] <= as_of_date
    ]
    
    # Count by event type
    births_total = sum(e["count"] for e in batch_events if e["event_type"] == "birth")
    deaths_total = sum(e["count"] for e in batch_events if e["event_type"] in ("death", "slaughter"))
    purchases_total = sum(e["count"] for e in batch_events if e["event_type"] == "purchase")
    sales_total = sum(e["count"] for e in batch_events if e["event_type"] == "sale")
    transfers_in = sum(e["count"] for e in batch_events if e["event_type"] == "transfer_in")
    transfers_out = sum(e["count"] for e in batch_events if e["event_type"] == "transfer_out")
    
    # Calculate current count from events (could verify against batch.count_current)
    count_current = births_total + purchases_total + transfers_in - deaths_total - sales_total - transfers_out
    count_current = max(0, count_current)  # Can't go negative
    
    # Mortality rate: deaths / (births + purchases + transfers_in)
    total_in = births_total + purchases_total + transfers_in
    mortality_rate: Optional[Decimal] = None
    if total_in > 0:
        mortality_rate = Decimal(deaths_total) / Decimal(total_in) * 100
    
    # Estimated value
    estimated_value: Optional[Decimal] = None
    if batch["valuation_enabled"] and count_current > 0:
        if batch["price_per_animal_mwk"]:
            estimated_value = Decimal(count_current) * batch["price_per_animal_mwk"]
        elif batch["price_per_kg_mwk"] and batch["avg_weight_kg"]:
            estimated_value = Decimal(count_current) * batch["avg_weight_kg"] * batch["price_per_kg_mwk"]
    
    return LivestockSnapshotResult(
        batch_id=batch["id"],
        batch_name=batch["name"],
        animal_type=batch["animal_type"],
        count_current=count_current,
        births_total=births_total,
        deaths_total=deaths_total,
        purchases_total=purchases_total,
        sales_total=sales_total,
        mortality_rate=mortality_rate,
        estimated_value=estimated_value,
    )


def compute_alerts(
    current_month_profit: MonthlyProfitResult,
    previous_month_profit: Optional[MonthlyProfitResult],
    livestock_snapshots: List[LivestockSnapshotResult],
    days_since_last_sale: Optional[int],
    config: Optional[Dict[str, Any]] = None,
) -> List[AlertItem]:
    """
    Compute farm alerts based on current data.
    
    Args:
        current_month_profit: This month's profit data
        previous_month_profit: Last month's profit data (for comparison)
        livestock_snapshots: Current livestock status
        days_since_last_sale: Number of days since the last sale
        config: Optional alert configuration thresholds
    
    Returns:
        List of AlertItem objects
    
    Pure function: deterministic alerts based on input data.
    """
    config = config or {}
    alerts: List[AlertItem] = []
    
    # Threshold defaults
    expense_increase_threshold = Decimal(config.get("expense_increase_threshold", 20))  # 20% increase
    no_sale_days_threshold = config.get("no_sale_days_threshold", 14)  # 14 days
    mortality_threshold = Decimal(config.get("mortality_threshold", 10))  # 10% mortality
    
    # Alert 1: Expenses rising vs last month
    if previous_month_profit is not None and previous_month_profit.total_expenses > 0:
        expense_increase = (
            (current_month_profit.total_expenses - previous_month_profit.total_expenses)
            / previous_month_profit.total_expenses * 100
        )
        if expense_increase > expense_increase_threshold:
            alerts.append(AlertItem(
                alert_type="expenses_rising",
                severity="warning",
                title="Expenses Rising",
                message=f"Expenses increased by {expense_increase:.1f}% compared to last month.",
                data={
                    "current_expenses": current_month_profit.total_expenses,
                    "previous_expenses": previous_month_profit.total_expenses,
                    "increase_pct": expense_increase,
                },
            ))
    
    # Alert 2: No sales recorded recently
    if days_since_last_sale is not None and days_since_last_sale > no_sale_days_threshold:
        alerts.append(AlertItem(
            alert_type="no_sales",
            severity="info",
            title="No Recent Sales",
            message=f"No sales recorded in the last {days_since_last_sale} days.",
            data={"days_since_last_sale": days_since_last_sale},
        ))
    
    # Alert 3: High mortality in livestock
    for snapshot in livestock_snapshots:
        if snapshot.mortality_rate is not None and snapshot.mortality_rate > mortality_threshold:
            alerts.append(AlertItem(
                alert_type="high_mortality",
                severity="critical",
                title=f"High Mortality: {snapshot.batch_name}",
                message=f"Mortality rate of {snapshot.mortality_rate:.1f}% in {snapshot.batch_name}.",
                data={
                    "batch_id": snapshot.batch_id,
                    "batch_name": snapshot.batch_name,
                    "mortality_rate": snapshot.mortality_rate,
                    "deaths_total": snapshot.deaths_total,
                },
            ))
    
    # Alert 4: Low/negative profit
    if current_month_profit.net_profit < 0:
        alerts.append(AlertItem(
            alert_type="negative_profit",
            severity="critical",
            title="Negative Profit This Month",
            message=f"You are running at a loss of MWK {abs(current_month_profit.net_profit):,.2f} this month.",
            data={
                "net_profit": current_month_profit.net_profit,
                "income": current_month_profit.total_income,
                "expenses": current_month_profit.total_expenses,
            },
        ))
    elif current_month_profit.total_income > 0:
        margin = current_month_profit.net_profit / current_month_profit.total_income * 100
        if margin < 10:  # Less than 10% margin
            alerts.append(AlertItem(
                alert_type="low_profit",
                severity="warning",
                title="Low Profit Margin",
                message=f"Your profit margin is only {margin:.1f}%. Consider reducing costs.",
                data={
                    "margin_pct": margin,
                    "net_profit": current_month_profit.net_profit,
                    "income": current_month_profit.total_income,
                },
            ))
    
    return alerts


# ==============================================================================
# HELPER FUNCTIONS FOR MODEL CONVERSION
# ==============================================================================


def ledger_entry_to_data(entry) -> LedgerEntryData:
    """Convert a FarmLedgerEntry model instance to LedgerEntryData dict."""
    return LedgerEntryData(
        id=entry.id,
        date=entry.date,
        entry_type=entry.entry_type,
        enterprise_type=entry.enterprise_type,
        category=entry.category,
        amount_mwk=entry.amount_mwk,
        quantity=entry.quantity,
        unit=entry.unit,
        livestock_batch_id=getattr(entry, "livestock_batch_id", None),
        crop_season_id=getattr(entry, "crop_season_id", None),
    )


def livestock_batch_to_data(batch) -> LivestockBatchData:
    """Convert a FarmLivestockBatch model instance to LivestockBatchData dict."""
    return LivestockBatchData(
        id=batch.id,
        animal_type=batch.animal_type,
        name=batch.name,
        count_current=batch.count_current,
        valuation_enabled=batch.valuation_enabled,
        avg_weight_kg=batch.avg_weight_kg,
        price_per_kg_mwk=batch.price_per_kg_mwk,
        price_per_animal_mwk=batch.price_per_animal_mwk,
    )


def livestock_event_to_data(event) -> LivestockEventData:
    """Convert a FarmLivestockEvent model instance to LivestockEventData dict."""
    return LivestockEventData(
        id=event.id,
        batch_id=event.batch_id,
        event_type=event.event_type,
        date=event.date,
        count=event.count,
        unit_price_mwk=event.unit_price_mwk,
    )


def crop_season_to_data(season) -> CropSeasonData:
    """Convert a FarmCropSeason model instance to CropSeasonData dict."""
    return CropSeasonData(
        id=season.id,
        crop_type=season.crop_type,
        name=season.name,
        start_date=season.start_date,
        end_date=season.end_date,
        area_value=season.area_value,
        area_unit=season.area_unit,
        projected_yield=season.projected_yield,
        yield_unit=season.yield_unit,
        projected_price_per_unit_mwk=season.projected_price_per_unit_mwk,
        actual_yield=season.actual_yield,
        actual_price_per_unit_mwk=season.actual_price_per_unit_mwk,
        status=season.status,
    )


# ==============================================================================
# DASHBOARD SNAPSHOT (SSOT AGGREGATION)
# ==============================================================================


@dataclass
class DashboardSnapshot:
    """Complete dashboard data snapshot from SSOT."""
    # KPIs
    net_profit_mwk: Decimal
    total_income_mwk: Decimal
    total_expenses_mwk: Decimal
    sales_count: int
    expense_count: int
    
    # Comparison to previous month
    profit_change_pct: Optional[Decimal]
    income_change_pct: Optional[Decimal]
    expense_change_pct: Optional[Decimal]
    profit_trend: str  # "up", "down", "flat"
    
    # Top cost driver
    top_cost_driver_name: str
    top_cost_driver_amount: Decimal
    top_cost_driver_pct: Decimal
    
    # Trends (last 6 months)
    profit_trend_data: List[Dict[str, Any]]  # [{month, year, net_profit, income, expenses}]
    
    # Expense breakdown by category
    expense_breakdown: List[Dict[str, Any]]  # [{category, amount, percentage}]
    
    # Alerts
    alerts: List[AlertItem]
    critical_alerts_count: int
    warning_alerts_count: int
    
    # Livestock summary
    total_livestock_count: int
    total_livestock_value: Optional[Decimal]
    livestock_births_this_month: int
    livestock_deaths_this_month: int
    mortality_rate_pct: Optional[Decimal]
    
    # Crops summary
    active_seasons_count: int
    total_crop_area: Decimal
    projected_crop_income: Optional[Decimal]
    
    # Metadata
    as_of_date: date
    month_name: str
    year: int


def compute_profit_trend(
    ledger_entries: List[LedgerEntryData],
    end_year: int,
    end_month: int,
    num_months: int = 6,
) -> List[Dict[str, Any]]:
    """
    Compute profit trend for the last N months.
    
    Args:
        ledger_entries: All ledger entries
        end_year: Year of the most recent month
        end_month: Month of the most recent month (1-12)
        num_months: Number of months to include
    
    Returns:
        List of dicts with month, year, net_profit, income, expenses
    """
    import calendar
    
    trend_data = []
    
    for i in range(num_months - 1, -1, -1):
        # Calculate month/year for this position
        month = end_month - i
        year = end_year
        
        while month <= 0:
            month += 12
            year -= 1
        
        month_profit = compute_monthly_profit(ledger_entries, year, month)
        
        trend_data.append({
            "month": month,
            "month_name": calendar.month_abbr[month],
            "year": year,
            "label": f"{calendar.month_abbr[month]} {str(year)[-2:]}",
            "net_profit": float(month_profit.net_profit),
            "income": float(month_profit.total_income),
            "expenses": float(month_profit.total_expenses),
        })
    
    return trend_data


def get_farm_dashboard_snapshot(
    ledger_entries: List[LedgerEntryData],
    livestock_snapshots: List[LivestockSnapshotResult],
    active_seasons_count: int,
    total_crop_area: Decimal,
    projected_crop_income: Optional[Decimal],
    today: date,
    days_since_last_sale: Optional[int] = None,
) -> DashboardSnapshot:
    """
    Compute complete dashboard snapshot from raw data.
    
    This is the main SSOT function for the Farm Dashboard.
    All dashboard values are computed here - the template only formats and renders.
    
    Args:
        ledger_entries: All ledger entries for the business
        livestock_snapshots: Computed livestock snapshots for all batches
        active_seasons_count: Number of active crop seasons
        total_crop_area: Total area under cultivation
        projected_crop_income: Projected income from crops
        today: Current date
        days_since_last_sale: Days since last sale was recorded
    
    Returns:
        DashboardSnapshot with all dashboard data
    """
    import calendar
    
    current_month = today.month
    current_year = today.year
    
    # Current month profit
    current_profit = compute_monthly_profit(ledger_entries, current_year, current_month)
    
    # Previous month for comparison
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    previous_profit = compute_monthly_profit(ledger_entries, prev_year, prev_month)
    
    # Calculate change percentages
    profit_change_pct: Optional[Decimal] = None
    income_change_pct: Optional[Decimal] = None
    expense_change_pct: Optional[Decimal] = None
    
    if previous_profit.net_profit != 0:
        profit_change_pct = (
            (current_profit.net_profit - previous_profit.net_profit) 
            / abs(previous_profit.net_profit) * 100
        )
    elif current_profit.net_profit != 0:
        profit_change_pct = Decimal("100") if current_profit.net_profit > 0 else Decimal("-100")
    
    if previous_profit.total_income > 0:
        income_change_pct = (
            (current_profit.total_income - previous_profit.total_income)
            / previous_profit.total_income * 100
        )
    
    if previous_profit.total_expenses > 0:
        expense_change_pct = (
            (current_profit.total_expenses - previous_profit.total_expenses)
            / previous_profit.total_expenses * 100
        )
    
    # Determine profit trend
    profit_trend = "flat"
    if profit_change_pct is not None:
        if profit_change_pct > 5:
            profit_trend = "up"
        elif profit_change_pct < -5:
            profit_trend = "down"
    
    # Top cost driver
    top_cost_driver_name = "None"
    top_cost_driver_amount = Decimal("0")
    top_cost_driver_pct = Decimal("0")
    
    if current_profit.top_expense_categories:
        top_cat = current_profit.top_expense_categories[0]
        top_cost_driver_name = top_cat["category"]
        top_cost_driver_amount = top_cat["amount"]
        top_cost_driver_pct = top_cat["percentage"]
    
    # Compute profit trend data for last 6 months
    profit_trend_data = compute_profit_trend(
        ledger_entries, current_year, current_month, num_months=6
    )
    
    # Expense breakdown (use top 5 categories)
    expense_breakdown = [
        {
            "category": cat["category"],
            "label": cat["category"].replace("_", " ").title(),
            "amount": float(cat["amount"]),
            "percentage": float(cat["percentage"]),
        }
        for cat in current_profit.top_expense_categories[:5]
    ]
    
    # Compute alerts
    alerts = compute_alerts(
        current_month_profit=current_profit,
        previous_month_profit=previous_profit,
        livestock_snapshots=livestock_snapshots,
        days_since_last_sale=days_since_last_sale,
    )
    
    critical_alerts_count = len([a for a in alerts if a.severity == "critical"])
    warning_alerts_count = len([a for a in alerts if a.severity == "warning"])
    
    # Livestock summary
    total_livestock_count = sum(s.count_current for s in livestock_snapshots)
    total_livestock_value = Decimal("0")
    total_births = 0
    total_deaths = 0
    total_animals_tracked = 0
    
    for s in livestock_snapshots:
        if s.estimated_value:
            total_livestock_value += s.estimated_value
        total_births += s.births_total
        total_deaths += s.deaths_total
        total_animals_tracked += s.births_total + s.purchases_total
    
    total_livestock_value = total_livestock_value if total_livestock_value > 0 else None
    
    # Compute overall mortality rate
    mortality_rate_pct: Optional[Decimal] = None
    if total_animals_tracked > 0:
        mortality_rate_pct = Decimal(total_deaths) / Decimal(total_animals_tracked) * 100
    
    return DashboardSnapshot(
        # KPIs
        net_profit_mwk=current_profit.net_profit,
        total_income_mwk=current_profit.total_income,
        total_expenses_mwk=current_profit.total_expenses,
        sales_count=current_profit.sales_count,
        expense_count=current_profit.expense_count,
        
        # Comparison
        profit_change_pct=profit_change_pct,
        income_change_pct=income_change_pct,
        expense_change_pct=expense_change_pct,
        profit_trend=profit_trend,
        
        # Top cost driver
        top_cost_driver_name=top_cost_driver_name,
        top_cost_driver_amount=top_cost_driver_amount,
        top_cost_driver_pct=top_cost_driver_pct,
        
        # Trends
        profit_trend_data=profit_trend_data,
        
        # Expense breakdown
        expense_breakdown=expense_breakdown,
        
        # Alerts
        alerts=alerts,
        critical_alerts_count=critical_alerts_count,
        warning_alerts_count=warning_alerts_count,
        
        # Livestock summary
        total_livestock_count=total_livestock_count,
        total_livestock_value=total_livestock_value,
        livestock_births_this_month=total_births,
        livestock_deaths_this_month=total_deaths,
        mortality_rate_pct=mortality_rate_pct,
        
        # Crops summary
        active_seasons_count=active_seasons_count,
        total_crop_area=total_crop_area,
        projected_crop_income=projected_crop_income,
        
        # Metadata
        as_of_date=today,
        month_name=calendar.month_name[current_month],
        year=current_year,
    )


# ==============================================================================
# MORTALITY RISK LEVEL
# ==============================================================================


def compute_mortality_risk_level(mortality_rate: Optional[Decimal]) -> str:
    """
    Convert a mortality rate percentage into a risk level string.

    Returns one of: 'critical' | 'high_risk' | 'watch' | 'good' | 'unknown'
    """
    if mortality_rate is None:
        return "unknown"
    if mortality_rate >= Decimal("20"):
        return "critical"
    if mortality_rate >= Decimal("10"):
        return "high_risk"
    if mortality_rate >= Decimal("5"):
        return "watch"
    return "good"


# ==============================================================================
# LIVESTOCK INTELLIGENCE (EXTENDED SNAPSHOT)
# ==============================================================================


@dataclass
class LivestockIntelligenceResult:
    """Rich intelligence result for a single livestock batch."""
    batch_id: int
    batch_name: str
    animal_type: str
    count_current: int
    births_total: int
    deaths_total: int
    purchases_total: int
    sales_total: int

    # Rates
    mortality_rate: Optional[Decimal]
    survival_rate: Optional[Decimal]
    mortality_risk_level: str   # critical | high_risk | watch | good | unknown

    # Financial
    feed_cost_mwk: Decimal
    medicine_cost_mwk: Decimal
    labour_cost_mwk: Decimal
    other_cost_mwk: Decimal
    total_cost_mwk: Decimal
    revenue_mwk: Decimal
    net_profit_mwk: Decimal

    # Per-animal
    profit_per_animal_mwk: Optional[Decimal]
    cost_per_surviving_animal_mwk: Optional[Decimal]
    break_even_price_mwk: Optional[Decimal]

    # Scores
    batch_health_score: int     # 0–100
    days_in_cycle: int

    # Estimated value
    estimated_value: Optional[Decimal]

    # Marketplace
    has_asking_price: bool
    has_stock: bool

    # Recommendations
    recommendations: List[str]


def compute_livestock_intelligence(
    batch: LivestockBatchData,
    events: List[LivestockEventData],
    ledger_entries: List[LedgerEntryData],
    batch_created_date: date,
    today: Optional[date] = None,
) -> LivestockIntelligenceResult:
    """
    Compute full intelligence for a livestock batch from events and ledger data.

    Args:
        batch: Batch data dict
        events: All events for this batch
        ledger_entries: Ledger entries linked to this batch (pre-filtered)
        batch_created_date: Date the batch was created
        today: Current date (defaults to today)

    Returns:
        LivestockIntelligenceResult with all intelligence fields
    """
    if today is None:
        today = timezone.now().date()

    # --- Counts from events ---
    batch_events = [e for e in events if e["batch_id"] == batch["id"] and e["date"] <= today]
    births_total = sum(e["count"] for e in batch_events if e["event_type"] == "birth")
    deaths_total = sum(e["count"] for e in batch_events if e["event_type"] in ("death", "slaughter"))
    purchases_total = sum(e["count"] for e in batch_events if e["event_type"] == "purchase")
    sales_total = sum(e["count"] for e in batch_events if e["event_type"] == "sale")
    transfers_in = sum(e["count"] for e in batch_events if e["event_type"] == "transfer_in")
    transfers_out = sum(e["count"] for e in batch_events if e["event_type"] == "transfer_out")

    count_current = max(0, births_total + purchases_total + transfers_in - deaths_total - sales_total - transfers_out)

    total_in = births_total + purchases_total + transfers_in
    mortality_rate: Optional[Decimal] = None
    survival_rate: Optional[Decimal] = None
    if total_in > 0:
        mortality_rate = Decimal(deaths_total) / Decimal(total_in) * 100
        survival_rate = Decimal("100") - mortality_rate

    risk_level = compute_mortality_risk_level(mortality_rate)

    # --- Financial from ledger ---
    feed_cost = Decimal("0")
    medicine_cost = Decimal("0")
    labour_cost = Decimal("0")
    other_cost = Decimal("0")
    revenue = Decimal("0")

    for entry in ledger_entries:
        if entry["entry_type"] == "expense":
            cat = entry["category"]
            if cat == "feed":
                feed_cost += entry["amount_mwk"]
            elif cat == "vet":
                medicine_cost += entry["amount_mwk"]
            elif cat == "labour":
                labour_cost += entry["amount_mwk"]
            else:
                other_cost += entry["amount_mwk"]
        elif entry["entry_type"] in ("sale", "other_income"):
            revenue += entry["amount_mwk"]

    # Also count sale event revenue
    for e in batch_events:
        if e["event_type"] == "sale" and e.get("unit_price_mwk"):
            revenue += Decimal(e["count"]) * e["unit_price_mwk"]

    total_cost = feed_cost + medicine_cost + labour_cost + other_cost
    net_profit = revenue - total_cost

    # Per-animal
    profit_per_animal: Optional[Decimal] = None
    if count_current > 0 and total_cost > 0:
        profit_per_animal = net_profit / Decimal(count_current)

    cost_per_surviving: Optional[Decimal] = None
    if count_current > 0:
        cost_per_surviving = total_cost / Decimal(count_current)

    break_even: Optional[Decimal] = None
    if count_current > 0 and total_cost > 0:
        break_even = total_cost / Decimal(count_current)

    # --- Estimated value ---
    estimated_value: Optional[Decimal] = None
    if batch["valuation_enabled"] and count_current > 0:
        if batch["price_per_animal_mwk"]:
            estimated_value = Decimal(count_current) * batch["price_per_animal_mwk"]
        elif batch["price_per_kg_mwk"] and batch["avg_weight_kg"]:
            estimated_value = Decimal(count_current) * batch["avg_weight_kg"] * batch["price_per_kg_mwk"]

    # --- Days in cycle ---
    days_in_cycle = max(0, (today - batch_created_date).days)

    # --- Batch health score (0–100) ---
    health_score = 100
    if risk_level == "critical":
        health_score -= 40
    elif risk_level == "high_risk":
        health_score -= 25
    elif risk_level == "watch":
        health_score -= 10
    if net_profit < Decimal("0"):
        health_score -= 20
    if not batch.get("price_per_animal_mwk") and not batch.get("price_per_kg_mwk"):
        health_score -= 10
    if total_cost == Decimal("0"):
        health_score -= 10
    health_score = max(0, min(100, health_score))

    # --- Recommendations ---
    recs: List[str] = []
    if risk_level in ("critical", "high_risk"):
        recs.append(f"Mortality is {risk_level.replace('_', ' ')} — review disease and death events immediately.")
    if not batch.get("price_per_animal_mwk") and not batch.get("expected_sale_price_mwk"):
        recs.append("Add an expected sale price to unlock profit simulation.")
    if net_profit < Decimal("0") and revenue > Decimal("0"):
        recs.append("Batch is running at a loss — review costs and pricing.")
    if feed_cost > Decimal("0") and count_current > 0:
        feed_per = feed_cost / Decimal(count_current)
        if feed_per > Decimal("5000"):
            recs.append("Feed cost per animal is high — review feed type and waste.")
    if count_current > 0 and not batch.get("price_per_animal_mwk"):
        recs.append("Set a target sale price so profit can be estimated.")

    return LivestockIntelligenceResult(
        batch_id=batch["id"],
        batch_name=batch["name"],
        animal_type=batch["animal_type"],
        count_current=count_current,
        births_total=births_total,
        deaths_total=deaths_total,
        purchases_total=purchases_total,
        sales_total=sales_total,
        mortality_rate=mortality_rate,
        survival_rate=survival_rate,
        mortality_risk_level=risk_level,
        feed_cost_mwk=feed_cost,
        medicine_cost_mwk=medicine_cost,
        labour_cost_mwk=labour_cost,
        other_cost_mwk=other_cost,
        total_cost_mwk=total_cost,
        revenue_mwk=revenue,
        net_profit_mwk=net_profit,
        profit_per_animal_mwk=profit_per_animal,
        cost_per_surviving_animal_mwk=cost_per_surviving,
        break_even_price_mwk=break_even,
        batch_health_score=health_score,
        days_in_cycle=days_in_cycle,
        estimated_value=estimated_value,
        has_asking_price=bool(batch.get("price_per_animal_mwk") or batch.get("expected_sale_price_mwk")),
        has_stock=(count_current > 0),
        recommendations=recs,
    )


# ==============================================================================
# LIVESTOCK SIMULATION
# ==============================================================================


@dataclass
class LivestockSimulationResult:
    """Projected profit scenarios for a livestock batch."""
    batch_id: int
    batch_name: str
    count_to_sell: int
    sale_price_per_head: Decimal
    total_cost: Decimal

    # Scenarios
    best_case_revenue: Decimal
    best_case_profit: Decimal
    expected_case_revenue: Decimal
    expected_case_profit: Decimal
    worst_case_revenue: Decimal
    worst_case_profit: Decimal

    # Key metrics
    roi_pct: Optional[Decimal]
    break_even_price: Optional[Decimal]

    # Human-readable summary
    summary: str


def compute_livestock_simulation(
    batch: LivestockBatchData,
    current_costs: Decimal,
    expected_sale_price: Optional[Decimal],
    expected_count_to_sell: Optional[int] = None,
    expected_mortality_pct: Decimal = Decimal("5"),
) -> LivestockSimulationResult:
    """
    Compute best/expected/worst case profit scenarios for a livestock batch.

    Args:
        batch: Batch data dict
        current_costs: Total costs incurred so far (MWK)
        expected_sale_price: Expected sale price per head (MWK). Uses batch price if None.
        expected_count_to_sell: Animals expected to sell. Defaults to current count.
        expected_mortality_pct: Expected mortality % for scenario calculations.

    Returns:
        LivestockSimulationResult with three scenarios
    """
    count = expected_count_to_sell or batch["count_current"] or 0
    price = expected_sale_price or batch.get("price_per_animal_mwk") or Decimal("0")

    # Expected case: sell expected_count at expected_price
    expected_revenue = Decimal(count) * price
    expected_profit = expected_revenue - current_costs

    # Best case: +10% price, no extra mortality
    best_price = price * Decimal("1.10")
    best_revenue = Decimal(count) * best_price
    best_profit = best_revenue - current_costs

    # Worst case: mortality eats into sellable count, -10% price
    extra_deaths = int(count * (expected_mortality_pct / Decimal("100")))
    worst_count = max(0, count - extra_deaths)
    worst_price = price * Decimal("0.90")
    worst_revenue = Decimal(worst_count) * worst_price
    worst_profit = worst_revenue - current_costs

    # ROI
    roi_pct: Optional[Decimal] = None
    if current_costs > Decimal("0"):
        roi_pct = (expected_profit / current_costs) * Decimal("100")

    # Break-even
    break_even: Optional[Decimal] = None
    if count > 0 and current_costs > Decimal("0"):
        break_even = current_costs / Decimal(count)

    # Summary text
    if price > Decimal("0") and count > 0:
        summary = (
            f"If you sell {count} animals at MWK {price:,.0f} each, "
            f"projected profit is MWK {expected_profit:,.0f}."
        )
        if break_even:
            summary += f" Break-even is MWK {break_even:,.0f} per animal."
    else:
        summary = "Set a sale price and animal count to run this simulation."

    return LivestockSimulationResult(
        batch_id=batch["id"],
        batch_name=batch["name"],
        count_to_sell=count,
        sale_price_per_head=price,
        total_cost=current_costs,
        best_case_revenue=best_revenue,
        best_case_profit=best_profit,
        expected_case_revenue=expected_revenue,
        expected_case_profit=expected_profit,
        worst_case_revenue=worst_revenue,
        worst_case_profit=worst_profit,
        roi_pct=roi_pct,
        break_even_price=break_even,
        summary=summary,
    )


# ==============================================================================
# CROP INTELLIGENCE
# ==============================================================================


@dataclass
class CropIntelligenceResult:
    """Rich intelligence result for a single crop season."""
    season_id: int
    season_name: str
    crop_type: str
    area_value: Decimal
    area_unit: str
    status: str

    # Costs
    input_cost_mwk: Decimal
    input_cost_per_acre: Optional[Decimal]

    # Projections
    projected_income_mwk: Optional[Decimal]
    projected_profit_mwk: Optional[Decimal]
    yield_per_acre: Optional[Decimal]
    break_even_price: Optional[Decimal]

    # Actual
    actual_income_mwk: Optional[Decimal]
    actual_profit_mwk: Optional[Decimal]

    # Intelligence
    harvest_readiness: str   # ready | near | growing | planning | harvested | unknown
    risk_level: str          # good | watch | risky | unknown
    days_to_harvest: Optional[int]
    recommendations: List[str]


def compute_crop_intelligence(
    season: CropSeasonData,
    ledger_entries: List[LedgerEntryData],
    today: date,
) -> CropIntelligenceResult:
    """
    Compute rich intelligence for a crop season.

    Args:
        season: Crop season data dict
        ledger_entries: Ledger entries linked to this season (pre-filtered by season)
        today: Current date

    Returns:
        CropIntelligenceResult with harvest readiness, risk level, and recommendations
    """
    # Input costs from ledger
    input_cost = sum(
        (e["amount_mwk"] for e in ledger_entries if e["entry_type"] == "expense"),
        Decimal("0"),
    )

    # Per-acre cost
    input_cost_per_acre: Optional[Decimal] = None
    if season["area_value"] and season["area_value"] > 0:
        input_cost_per_acre = input_cost / season["area_value"]

    # Projected income and profit
    projected_income: Optional[Decimal] = None
    projected_profit: Optional[Decimal] = None
    if season["projected_yield"] and season["projected_price_per_unit_mwk"]:
        projected_income = season["projected_yield"] * season["projected_price_per_unit_mwk"]
        projected_profit = projected_income - input_cost

    # Yield per acre
    yield_per_acre: Optional[Decimal] = None
    if season["projected_yield"] and season["area_value"] and season["area_value"] > 0:
        yield_per_acre = season["projected_yield"] / season["area_value"]

    # Break-even price per yield unit
    break_even: Optional[Decimal] = None
    if season["projected_yield"] and season["projected_yield"] > 0 and input_cost > 0:
        break_even = input_cost / season["projected_yield"]

    # Actual income and profit
    actual_income: Optional[Decimal] = None
    actual_profit: Optional[Decimal] = None
    if season["actual_yield"] and season["actual_price_per_unit_mwk"]:
        actual_income = season["actual_yield"] * season["actual_price_per_unit_mwk"]
        actual_profit = actual_income - input_cost

    # Harvest readiness
    harvest_readiness = "unknown"
    days_to_harvest: Optional[int] = None
    status = season["status"]

    if status == "harvested" or status == "closed":
        harvest_readiness = "harvested"
    elif season["end_date"]:
        days_remaining = (season["end_date"] - today).days
        days_to_harvest = days_remaining
        if days_remaining <= 0:
            harvest_readiness = "ready"
        elif days_remaining <= 14:
            harvest_readiness = "ready"
        elif days_remaining <= 30:
            harvest_readiness = "near"
        elif status == "active":
            harvest_readiness = "growing"
        else:
            harvest_readiness = "planning"
    elif status == "active":
        harvest_readiness = "growing"
    elif status == "planning":
        harvest_readiness = "planning"

    # Risk level
    risk_level = "unknown"
    if projected_income and input_cost > Decimal("0"):
        if projected_income > input_cost * Decimal("1.5"):
            risk_level = "good"
        elif projected_income > input_cost:
            risk_level = "watch"
        else:
            risk_level = "risky"
    elif input_cost > Decimal("0") and not projected_income:
        risk_level = "watch"

    # Recommendations
    recs: List[str] = []
    if not season["projected_yield"]:
        recs.append(f"Add expected yield for {season['name']} to unlock profit forecast.")
    if not season["projected_price_per_unit_mwk"]:
        recs.append(f"Add expected sale price for {season['name']} to see projected income.")
    if harvest_readiness == "ready":
        recs.append(f"{season['name']} is ready to harvest — prepare labour and storage.")
    elif harvest_readiness == "near":
        recs.append(f"{season['name']} harvest is approaching — plan logistics now.")
    if risk_level == "risky":
        recs.append(f"Input costs for {season['name']} exceed projected income — review costs.")
    if status == "harvested" and not season["actual_yield"]:
        recs.append(f"Record actual yield for {season['name']} after harvest.")

    return CropIntelligenceResult(
        season_id=season["id"],
        season_name=season["name"],
        crop_type=season["crop_type"],
        area_value=season["area_value"],
        area_unit=season["area_unit"],
        status=status,
        input_cost_mwk=input_cost,
        input_cost_per_acre=input_cost_per_acre,
        projected_income_mwk=projected_income,
        projected_profit_mwk=projected_profit,
        yield_per_acre=yield_per_acre,
        break_even_price=break_even,
        actual_income_mwk=actual_income,
        actual_profit_mwk=actual_profit,
        harvest_readiness=harvest_readiness,
        risk_level=risk_level,
        days_to_harvest=days_to_harvest,
        recommendations=recs,
    )


# ==============================================================================
# EGG / POULTRY SUMMARY
# ==============================================================================


@dataclass
class EggProductionSummary:
    """Summary of egg production for a poultry batch."""
    batch_id: int
    batch_name: str
    total_eggs_collected: int
    eggs_today: int
    eggs_this_week: int
    eggs_this_month: int
    spoiled_eggs: int
    eggs_sold: int
    eggs_in_stock: int
    revenue_mwk: Decimal
    feed_cost_mwk: Decimal
    feed_cost_per_egg: Optional[Decimal]
    productivity_rate: Optional[Decimal]   # eggs per bird per day (last 7 days)
    spoilage_rate: Optional[Decimal]
    trend: str    # up | down | stable


def compute_egg_summary(
    batch_id: int,
    batch_name: str,
    initial_birds: int,
    current_birds: int,
    total_eggs: int,
    total_feed_kg: Decimal,
    total_cost: Decimal,
    total_sales: Decimal,
    daily_records: List[Dict[str, Any]],
    today: date,
) -> EggProductionSummary:
    """
    Compute egg production intelligence from poultry batch daily records.

    Args:
        batch_id: Batch primary key
        batch_name: Batch display name
        initial_birds: Birds at batch start
        current_birds: Current birds alive
        total_eggs: Running total from batch model
        total_feed_kg: Running total feed kg
        total_cost: Running total cost from cashbook
        total_sales: Running total sales from cashbook
        daily_records: List of dicts with keys: date, eggs_collected, deaths, feed_kg
        today: Current date

    Returns:
        EggProductionSummary
    """
    # Filter records by period
    this_week_start = today - timedelta(days=7)
    this_month_start = today.replace(day=1)

    eggs_today = 0
    eggs_this_week = 0
    eggs_this_month = 0
    spoiled_eggs = 0   # from records with spoilage field if present
    eggs_sold = 0

    for r in daily_records:
        rec_date = r.get("date")
        if not rec_date:
            continue
        if isinstance(rec_date, str):
            from datetime import datetime
            rec_date = datetime.strptime(rec_date, "%Y-%m-%d").date()

        eggs = r.get("eggs_collected", 0) or 0
        spoiled = r.get("eggs_spoiled", 0) or 0
        sold = r.get("eggs_sold", 0) or 0

        if rec_date == today:
            eggs_today += eggs
        if rec_date >= this_week_start:
            eggs_this_week += eggs
        if rec_date >= this_month_start:
            eggs_this_month += eggs

        spoiled_eggs += spoiled
        eggs_sold += sold

    eggs_in_stock = max(0, total_eggs - eggs_sold - spoiled_eggs)

    # Feed cost per egg
    feed_cost_per_egg: Optional[Decimal] = None
    if total_eggs > 0 and total_cost > Decimal("0"):
        feed_cost_per_egg = total_cost / Decimal(total_eggs)

    # Productivity rate: eggs per bird per day over last 7 days
    productivity_rate: Optional[Decimal] = None
    week_records = [
        r for r in daily_records
        if r.get("date") and (
            (r["date"] if isinstance(r["date"], date) else date.fromisoformat(r["date"][:10]))
            >= this_week_start
        )
    ]
    if week_records and current_birds > 0:
        week_eggs = sum(r.get("eggs_collected", 0) or 0 for r in week_records)
        productivity_rate = Decimal(week_eggs) / Decimal(current_birds) / Decimal(len(week_records))

    # Spoilage rate
    spoilage_rate: Optional[Decimal] = None
    if total_eggs > 0 and spoiled_eggs > 0:
        spoilage_rate = Decimal(spoiled_eggs) / Decimal(total_eggs) * 100

    # Trend: compare this week to previous week
    prev_week_start = this_week_start - timedelta(days=7)
    prev_week_records = [
        r for r in daily_records
        if r.get("date") and (
            prev_week_start <=
            (r["date"] if isinstance(r["date"], date) else date.fromisoformat(r["date"][:10]))
            < this_week_start
        )
    ]
    prev_week_eggs = sum(r.get("eggs_collected", 0) or 0 for r in prev_week_records)
    trend = "stable"
    if prev_week_eggs > 0:
        if eggs_this_week > prev_week_eggs * Decimal("1.05"):
            trend = "up"
        elif eggs_this_week < prev_week_eggs * Decimal("0.95"):
            trend = "down"

    return EggProductionSummary(
        batch_id=batch_id,
        batch_name=batch_name,
        total_eggs_collected=total_eggs,
        eggs_today=eggs_today,
        eggs_this_week=eggs_this_week,
        eggs_this_month=eggs_this_month,
        spoiled_eggs=spoiled_eggs,
        eggs_sold=eggs_sold,
        eggs_in_stock=eggs_in_stock,
        revenue_mwk=total_sales,
        feed_cost_mwk=total_cost,
        feed_cost_per_egg=feed_cost_per_egg,
        productivity_rate=productivity_rate,
        spoilage_rate=spoilage_rate,
        trend=trend,
    )


# ==============================================================================
# FARM SCORE
# ==============================================================================


FARM_RANKS: List[tuple] = [
    (95, "Model Farm"),
    (85, "Elite Farm"),
    (70, "Smart Farm"),
    (50, "Growing Farm"),
    (30, "Seedling Farm"),
    (0,  "Struggling Farm"),
]

FARM_ACHIEVEMENTS_DEFS: Dict[str, str] = {
    "books_balanced":      "Books Balanced",
    "profitable_farm":     "Profitable Farm",
    "low_mortality":       "Low Mortality",
    "marketplace_ready":   "Marketplace Ready",
    "feed_master":         "Feed Master",
    "clean_records":       "Clean Records",
    "harvest_ready":       "Harvest Ready",
    "sales_active":        "Sales Active",
    "cost_controlled":     "Cost Controlled",
}


@dataclass
class FarmScoreResult:
    """Gamified farm score result."""
    score: int                           # 0–100
    rank: str                            # "Struggling Farm" etc.
    xp_points: int                       # score * 10 for display
    badges: List[str]                    # earned achievement labels
    weaknesses: List[str]                # areas dragging the score
    next_action: str                     # single best action to improve score
    score_components: Dict[str, int]     # component_name → contribution


def compute_farm_score(
    net_profit: Decimal,
    total_income: Decimal,
    total_expenses: Decimal,
    livestock_risk_levels: List[str],
    active_crop_seasons_count: int,
    missing_yield_count: int,
    missing_sale_price_count: int,
    marketplace_listings_count: int,
    days_since_last_sale: Optional[int],
    days_since_last_expense: Optional[int],
    has_recent_livestock_event: bool,
) -> FarmScoreResult:
    """
    Compute a gamified farm score from 0–100 based on farm health signals.

    All inputs are scalars — no ORM calls inside this function.
    """
    components: Dict[str, int] = {}
    weaknesses: List[str] = []
    badges: List[str] = []

    # 1. Profitability (20 pts)
    if net_profit > Decimal("0"):
        components["profitability"] = 20
        badges.append(FARM_ACHIEVEMENTS_DEFS["profitable_farm"])
    elif net_profit == Decimal("0") and total_income == Decimal("0"):
        components["profitability"] = 5   # no data yet, not penalised
    else:
        components["profitability"] = 0
        weaknesses.append("Farm is not profitable this period")

    # 2. Books activity — sales and expenses in last 30 days (15 pts)
    recent_sale = days_since_last_sale is not None and days_since_last_sale <= 30
    recent_expense = days_since_last_expense is not None and days_since_last_expense <= 30
    if recent_sale and recent_expense:
        components["records_activity"] = 15
        badges.append(FARM_ACHIEVEMENTS_DEFS["clean_records"])
    elif recent_sale or recent_expense:
        components["records_activity"] = 8
    else:
        components["records_activity"] = 0
        weaknesses.append("No sales or expenses recorded recently")

    # 3. Sales activity (10 pts)
    if days_since_last_sale is not None and days_since_last_sale <= 14:
        components["sales_active"] = 10
        badges.append(FARM_ACHIEVEMENTS_DEFS["sales_active"])
    elif days_since_last_sale is not None and days_since_last_sale <= 30:
        components["sales_active"] = 5
    else:
        components["sales_active"] = 0
        weaknesses.append("No recent sales activity")

    # 4. Livestock mortality (15 pts)
    if not livestock_risk_levels:
        components["livestock_health"] = 10   # no livestock, not penalised
    else:
        critical_count = livestock_risk_levels.count("critical")
        high_count = livestock_risk_levels.count("high_risk")
        if critical_count == 0 and high_count == 0:
            components["livestock_health"] = 15
            badges.append(FARM_ACHIEVEMENTS_DEFS["low_mortality"])
        elif critical_count > 0:
            components["livestock_health"] = 0
            weaknesses.append(f"{critical_count} batch(es) have critical mortality")
        else:
            components["livestock_health"] = 5
            weaknesses.append(f"{high_count} batch(es) have high mortality risk")

    # 5. Crop yield data completeness (10 pts)
    if active_crop_seasons_count == 0:
        components["crop_data"] = 7   # no crops, not penalised
    elif missing_yield_count == 0:
        components["crop_data"] = 10
    else:
        components["crop_data"] = max(0, 10 - (missing_yield_count * 3))
        weaknesses.append(f"{missing_yield_count} crop season(s) missing expected yield")

    # 6. Livestock has asking price (10 pts)
    if missing_sale_price_count == 0 and (livestock_risk_levels or active_crop_seasons_count > 0):
        components["pricing_data"] = 10
        badges.append(FARM_ACHIEVEMENTS_DEFS["cost_controlled"])
    elif missing_sale_price_count > 0:
        components["pricing_data"] = max(0, 10 - (missing_sale_price_count * 3))
        weaknesses.append(f"{missing_sale_price_count} batch(es) missing expected sale price")
    else:
        components["pricing_data"] = 7

    # 7. Marketplace presence (10 pts)
    if marketplace_listings_count > 0:
        components["marketplace"] = 10
        badges.append(FARM_ACHIEVEMENTS_DEFS["marketplace_ready"])
    else:
        components["marketplace"] = 0
        weaknesses.append("No marketplace listings published")

    # 8. Expense control (10 pts)
    if total_income > Decimal("0"):
        expense_ratio = total_expenses / total_income
        if expense_ratio <= Decimal("0.6"):
            components["expense_control"] = 10
        elif expense_ratio <= Decimal("0.8"):
            components["expense_control"] = 6
        else:
            components["expense_control"] = 2
            weaknesses.append("Expenses are high relative to income")
    else:
        components["expense_control"] = 5

    # 9. Harvest readiness bonus (not in main score, just badge)
    # (Crops with harvest_readiness="ready" earn badge, visible in template context)

    score = sum(components.values())
    score = max(0, min(100, score))

    # Rank
    rank = "Struggling Farm"
    for threshold, label in FARM_RANKS:
        if score >= threshold:
            rank = label
            break

    # XP
    xp = score * 10

    # Next action (pick the most impactful weakness)
    next_action = "Keep recording your farm activity to improve your score."
    if "critical" in livestock_risk_levels:
        next_action = "Urgently review critical mortality batches."
    elif not recent_sale and not recent_expense:
        next_action = "Record a sale or expense to show your farm is active."
    elif missing_sale_price_count > 0:
        next_action = "Add expected sale prices to your livestock batches."
    elif missing_yield_count > 0:
        next_action = "Add expected yield to your crop seasons."
    elif marketplace_listings_count == 0:
        next_action = "Publish a livestock batch or crop to the marketplace."
    elif net_profit < Decimal("0"):
        next_action = "Review your highest expense category to improve profit."

    return FarmScoreResult(
        score=score,
        rank=rank,
        xp_points=xp,
        badges=badges,
        weaknesses=weaknesses,
        next_action=next_action,
        score_components=components,
    )


# ==============================================================================
# MARKETPLACE READINESS
# ==============================================================================


@dataclass
class MarketplaceReadinessResult:
    """Marketplace readiness check for a batch or crop."""
    is_ready: bool
    has_stock: bool
    has_asking_price: bool
    has_image: bool
    has_description: bool
    is_already_published: bool
    missing_items: List[str]
    readiness_score: int    # 0–100


def compute_livestock_marketplace_readiness(
    count_current: int,
    price_per_animal_mwk: Optional[Decimal],
    expected_sale_price_mwk: Optional[Decimal],
    has_primary_image: bool,
    notes: str,
    is_already_published: bool,
) -> MarketplaceReadinessResult:
    """Compute marketplace readiness for a livestock batch."""
    has_stock = count_current > 0
    has_asking_price = bool(price_per_animal_mwk or expected_sale_price_mwk)
    has_image = has_primary_image
    has_description = bool(notes and len(notes.strip()) > 10)

    missing: List[str] = []
    if not has_stock:
        missing.append("No animals in stock")
    if not has_asking_price:
        missing.append("No asking price set")
    if not has_image:
        missing.append("No photo uploaded")
    if not has_description:
        missing.append("No description or notes")
    if is_already_published:
        missing.append("Already published")

    score_pts = 0
    if has_stock:
        score_pts += 40
    if has_asking_price:
        score_pts += 30
    if has_image:
        score_pts += 20
    if has_description:
        score_pts += 10

    is_ready = has_stock and has_asking_price and not is_already_published

    return MarketplaceReadinessResult(
        is_ready=is_ready,
        has_stock=has_stock,
        has_asking_price=has_asking_price,
        has_image=has_image,
        has_description=has_description,
        is_already_published=is_already_published,
        missing_items=missing,
        readiness_score=score_pts,
    )


def compute_crop_marketplace_readiness(
    quantity_available: Decimal,
    list_price_per_unit_mwk: Optional[Decimal],
    has_primary_image: bool,
    description: str,
    is_already_published: bool,
) -> MarketplaceReadinessResult:
    """Compute marketplace readiness for a crop stock line."""
    has_stock = quantity_available > Decimal("0")
    has_asking_price = bool(list_price_per_unit_mwk)
    has_image = has_primary_image
    has_description = bool(description and len(description.strip()) > 10)

    missing: List[str] = []
    if not has_stock:
        missing.append("No stock available")
    if not has_asking_price:
        missing.append("No asking price set")
    if not has_image:
        missing.append("No photo uploaded")
    if not has_description:
        missing.append("No description")
    if is_already_published:
        missing.append("Already published")

    score_pts = 0
    if has_stock:
        score_pts += 40
    if has_asking_price:
        score_pts += 30
    if has_image:
        score_pts += 20
    if has_description:
        score_pts += 10

    is_ready = has_stock and has_asking_price and not is_already_published

    return MarketplaceReadinessResult(
        is_ready=is_ready,
        has_stock=has_stock,
        has_asking_price=has_asking_price,
        has_image=has_image,
        has_description=has_description,
        is_already_published=is_already_published,
        missing_items=missing,
        readiness_score=score_pts,
    )


# ==============================================================================
# RECOMMENDATION GENERATOR
# ==============================================================================


def generate_farm_recommendations(
    net_profit: Decimal,
    livestock_intelligences: List[LivestockIntelligenceResult],
    crop_intelligences: List[CropIntelligenceResult],
    has_marketplace_listings: bool,
    has_poultry: bool,
    days_since_egg_record: Optional[int],
    days_since_last_sale: Optional[int],
    limit: int = 5,
) -> List[str]:
    """
    Generate a short list of plain-English farm recommendations.

    Returns up to `limit` action strings, highest priority first.
    All inputs are scalars — no ORM calls inside this function.
    """
    recs: List[Dict[str, Any]] = []

    # Priority 1: critical mortality
    for intel in livestock_intelligences:
        if intel.mortality_risk_level == "critical":
            recs.append({
                "priority": 1,
                "text": (
                    f"Mortality is critical in '{intel.batch_name}' "
                    f"({intel.mortality_rate:.1f}% — {intel.deaths_total} deaths). "
                    "Review death events and disease records immediately."
                ),
            })

    # Priority 2: negative profit
    if net_profit < Decimal("0"):
        recs.append({
            "priority": 2,
            "text": f"Farm is running at a loss of MWK {abs(net_profit):,.0f}. Review your top expense categories.",
        })

    # Priority 3: ready to harvest
    for ci in crop_intelligences:
        if ci.harvest_readiness == "ready":
            recs.append({
                "priority": 3,
                "text": f"'{ci.season_name}' is ready to harvest. Prepare labour and storage now.",
            })

    # Priority 4: high mortality (watch/high_risk)
    for intel in livestock_intelligences:
        if intel.mortality_risk_level == "high_risk":
            recs.append({
                "priority": 4,
                "text": (
                    f"Mortality is high in '{intel.batch_name}' "
                    f"({intel.mortality_rate:.1f}%). Review disease events and feeding records."
                ),
            })

    # Priority 5: missing sale price on livestock
    no_price = [i for i in livestock_intelligences if not i.has_asking_price and i.has_stock]
    if no_price:
        names = ", ".join(i.batch_name for i in no_price[:2])
        recs.append({
            "priority": 5,
            "text": f"Add an expected sale price to: {names}. This unlocks profit simulation.",
        })

    # Priority 6: missing crop yield
    no_yield = [c for c in crop_intelligences if not c.projected_income_mwk and c.status in ("active", "planning")]
    if no_yield:
        names = no_yield[0].season_name
        recs.append({
            "priority": 6,
            "text": f"Add expected yield for '{names}' to unlock crop profit forecast.",
        })

    # Priority 7: egg collection overdue
    if has_poultry and days_since_egg_record is not None and days_since_egg_record >= 1:
        recs.append({
            "priority": 7,
            "text": "Record today's egg collection to keep production tracking accurate.",
        })

    # Priority 8: no marketplace listings
    if not has_marketplace_listings:
        recs.append({
            "priority": 8,
            "text": "You have no marketplace listings. Publish ready livestock or crop stock to attract buyers.",
        })

    # Priority 9: no recent sales
    if days_since_last_sale is not None and days_since_last_sale > 30:
        recs.append({
            "priority": 9,
            "text": f"No sales recorded in {days_since_last_sale} days. Record any recent sales to keep books current.",
        })

    # Priority 10: near harvest
    for ci in crop_intelligences:
        if ci.harvest_readiness == "near":
            recs.append({
                "priority": 10,
                "text": f"'{ci.season_name}' harvest is approaching ({ci.days_to_harvest} days). Plan transport and buyers.",
            })

    recs.sort(key=lambda x: x["priority"])
    return [r["text"] for r in recs[:limit]]


# ==============================================================================
# CATEGORIZED ALERTS
# ==============================================================================


@dataclass
class CategorizedAlerts:
    """Farm alerts split into critical, warnings, and opportunities."""
    critical: List[AlertItem]
    warnings: List[AlertItem]
    opportunities: List[AlertItem]
    total_count: int


def compute_categorized_alerts(
    net_profit: Decimal,
    total_income: Decimal,
    total_expenses: Decimal,
    livestock_intelligences: List[LivestockIntelligenceResult],
    crop_intelligences: List[CropIntelligenceResult],
    days_since_last_sale: Optional[int],
    marketplace_listings_count: int,
) -> CategorizedAlerts:
    """
    Generate categorized farm alerts: critical, warnings, and opportunities.

    All inputs are scalars — no ORM calls.
    """
    critical: List[AlertItem] = []
    warnings: List[AlertItem] = []
    opportunities: List[AlertItem] = []

    # --- CRITICAL ---

    # Negative profit
    if net_profit < Decimal("0"):
        critical.append(AlertItem(
            alert_type="negative_profit",
            severity="critical",
            title="Farm Running at a Loss",
            message=f"Net loss of MWK {abs(net_profit):,.0f} this period. Review expenses immediately.",
            data={"net_profit": float(net_profit)},
        ))

    # Critical mortality batches
    for intel in livestock_intelligences:
        if intel.mortality_risk_level == "critical":
            critical.append(AlertItem(
                alert_type="high_mortality",
                severity="critical",
                title=f"Critical Mortality: {intel.batch_name}",
                message=(
                    f"Mortality rate is {intel.mortality_rate:.1f}%. "
                    "Review deaths, disease events, and feed records."
                ),
                data={"batch_id": intel.batch_id, "mortality_rate": float(intel.mortality_rate or 0)},
            ))

    # Expenses > 90% of income
    if total_income > Decimal("0") and total_expenses > total_income * Decimal("0.9"):
        critical.append(AlertItem(
            alert_type="high_expenses",
            severity="critical",
            title="Expenses Consuming Almost All Income",
            message=(
                f"Expenses are {(total_expenses / total_income * 100):.0f}% of income. "
                "Profit margin is dangerously thin."
            ),
            data={"expense_ratio": float(total_expenses / total_income)},
        ))

    # --- WARNINGS ---

    # High mortality batches
    for intel in livestock_intelligences:
        if intel.mortality_risk_level == "high_risk":
            warnings.append(AlertItem(
                alert_type="high_mortality_warning",
                severity="warning",
                title=f"High Mortality Risk: {intel.batch_name}",
                message=(
                    f"Mortality rate is {intel.mortality_rate:.1f}%. "
                    "Monitor closely and consult a vet."
                ),
                data={"batch_id": intel.batch_id, "mortality_rate": float(intel.mortality_rate or 0)},
            ))

    # Missing sale price on active livestock
    for intel in livestock_intelligences:
        if intel.has_stock and not intel.has_asking_price:
            warnings.append(AlertItem(
                alert_type="missing_sale_price",
                severity="warning",
                title=f"No Sale Price: {intel.batch_name}",
                message="Add an expected sale price to enable profit simulation and marketplace readiness.",
                data={"batch_id": intel.batch_id},
            ))

    # Missing crop yield projections
    for ci in crop_intelligences:
        if not ci.projected_income_mwk and ci.status in ("active", "planning"):
            warnings.append(AlertItem(
                alert_type="missing_crop_yield",
                severity="warning",
                title=f"Missing Yield Data: {ci.season_name}",
                message="Add expected yield and price to unlock profit forecast for this season.",
                data={"season_id": ci.season_id},
            ))

    # No recent sales
    if days_since_last_sale is not None and days_since_last_sale > 14:
        warnings.append(AlertItem(
            alert_type="no_recent_sales",
            severity="warning",
            title="No Recent Sales",
            message=f"No sales recorded in the last {days_since_last_sale} days. Record any sales to keep books current.",
            data={"days_since_last_sale": days_since_last_sale},
        ))

    # No marketplace listings
    if marketplace_listings_count == 0:
        warnings.append(AlertItem(
            alert_type="no_marketplace",
            severity="warning",
            title="No Marketplace Listings",
            message="Publish livestock or crop stock to the marketplace to attract buyers.",
            data={},
        ))

    # --- OPPORTUNITIES ---

    # Harvest ready
    for ci in crop_intelligences:
        if ci.harvest_readiness == "ready":
            opportunities.append(AlertItem(
                alert_type="harvest_ready",
                severity="info",
                title=f"Ready to Harvest: {ci.season_name}",
                message="Harvest time has arrived. Prepare labour, transport, and storage.",
                data={"season_id": ci.season_id},
            ))

    # Livestock ready to sell
    for intel in livestock_intelligences:
        if intel.has_stock and intel.has_asking_price and intel.mortality_risk_level in ("good", "watch"):
            opportunities.append(AlertItem(
                alert_type="livestock_ready",
                severity="info",
                title=f"Ready to Sell: {intel.batch_name}",
                message=(
                    f"{intel.count_current} animals available at asking price. "
                    "Consider publishing to marketplace."
                ),
                data={"batch_id": intel.batch_id},
            ))

    # Profitable batch
    for intel in livestock_intelligences:
        if intel.net_profit_mwk > Decimal("0"):
            opportunities.append(AlertItem(
                alert_type="profitable_batch",
                severity="info",
                title=f"Profitable Batch: {intel.batch_name}",
                message=f"Estimated net profit of MWK {intel.net_profit_mwk:,.0f}. Keep managing well.",
                data={"batch_id": intel.batch_id, "profit": float(intel.net_profit_mwk)},
            ))

    # Harvest near
    for ci in crop_intelligences:
        if ci.harvest_readiness == "near":
            opportunities.append(AlertItem(
                alert_type="harvest_near",
                severity="info",
                title=f"Harvest Approaching: {ci.season_name}",
                message=f"About {ci.days_to_harvest} days to harvest. Line up buyers and logistics.",
                data={"season_id": ci.season_id, "days_to_harvest": ci.days_to_harvest},
            ))

    total = len(critical) + len(warnings) + len(opportunities)
    return CategorizedAlerts(
        critical=critical,
        warnings=warnings,
        opportunities=opportunities,
        total_count=total,
    )

