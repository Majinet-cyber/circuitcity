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


class LedgerEntryData(TypedDict):
    """Data structure for a ledger entry (extracted from model)."""
    id: int
    date: date
    entry_type: str  # "expense" | "sale" | "other_income"
    enterprise_type: str
    category: str
    amount_mwk: Decimal
    quantity: Optional[Decimal]
    unit: str


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

