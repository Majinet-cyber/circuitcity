# inventory/services/farm_intelligence.py
"""
Farm Intelligence Service — Extended analytics layer.

Provides NEW functionality on top of farm_manager.py (SSOT):
- Batch-level livestock intelligence with ROI, break-even, risk badges
- Livestock simulation (best/expected/worst case projections)
- Crop season intelligence (harvest readiness, profitability)
- Egg/poultry production summary
- Marketplace readiness checks
- Housing planner (basis for future 3D integration)
- Farm Business Health Score (farm-specific)
- Categorised alerts: critical / warning / opportunity
- "What should I do next?" recommendations (typed FarmRecommendation)

NOTE: compute_farm_score, compute_livestock_intelligence, compute_egg_summary,
generate_farm_recommendations already exist in farm_manager.py with their own
signatures. This module provides COMPLEMENTARY functions with different
signatures and output structures.

All functions are pure (no direct DB access) for easy unit-testing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


# ==============================================================================
# CONSTANTS
# ==============================================================================

MORTALITY_CRITICAL = Decimal("20")   # >=20% → critical
MORTALITY_HIGH     = Decimal("10")   # >=10% → high risk
MORTALITY_WATCH    = Decimal("5")    # >=5%  → watch
# <5% → good

FARM_RANK_LEVELS = [
    (95, "Model Farm",       "🏆"),
    (85, "Elite Farm",       "🌟"),
    (70, "Smart Farm",       "🧠"),
    (50, "Growing Farm",     "🌱"),
    (30, "Seedling Farm",    "🌾"),
    (0,  "Struggling Farm",  "⚠️"),
]

ACHIEVEMENTS = {
    "books_balanced":     ("Books Balanced",     "bi-journal-check",   "success"),
    "profitable":         ("Profitable Farm",     "bi-graph-up-arrow",  "success"),
    "low_mortality":      ("Low Mortality",       "bi-heart-pulse",     "success"),
    "marketplace_ready":  ("Marketplace Ready",   "bi-shop",            "info"),
    "feed_master":        ("Feed Master",         "bi-basket",          "info"),
    "clean_records":      ("Clean Records",       "bi-clipboard-check", "info"),
    "harvest_ready":      ("Harvest Ready",       "bi-scissors",        "warning"),
    "sales_active":       ("Sales Active",        "bi-lightning",       "success"),
    "cost_controlled":    ("Cost Controlled",     "bi-piggy-bank",      "success"),
}


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================


@dataclass
class FarmScoreResult:
    """Gamified farm score with rank, badges, XP, and improvement path."""
    score: int                           # 0–100
    rank: str                            # "Model Farm" etc.
    rank_emoji: str
    xp: int                              # score × 100
    earned_badges: List[str]             # keys from ACHIEVEMENTS
    missing_badges: List[str]
    weaknesses: List[str]                # human-readable weak points
    next_action: str                     # single most important next step
    score_components: Dict[str, int]     # breakdown of score points


@dataclass
class FarmAlert:
    """A single farm alert with category, action, and link."""
    severity: str      # "critical" | "warning" | "opportunity"
    title: str
    message: str
    action: str        # short recommended action text
    link: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnhancedAlertsResult:
    """Categorised farm alerts."""
    critical: List[FarmAlert]
    warnings: List[FarmAlert]
    opportunities: List[FarmAlert]

    @property
    def all_alerts(self) -> List[FarmAlert]:
        return self.critical + self.warnings + self.opportunities

    @property
    def has_critical(self) -> bool:
        return bool(self.critical)

    @property
    def total_count(self) -> int:
        return len(self.critical) + len(self.warnings) + len(self.opportunities)


@dataclass
class LivestockBatchIntelligence:
    """Per-batch intelligence scores and calculations."""
    batch_id: int
    batch_name: str
    animal_type: str

    # Counts
    count_current: int
    births: int
    deaths: int
    purchases: int
    sales: int

    # Rates
    mortality_rate: Optional[Decimal]
    survival_rate: Optional[Decimal]
    mortality_risk: str            # "good" | "watch" | "high_risk" | "critical"

    # Financials
    total_cost_mwk: Decimal
    total_revenue_mwk: Decimal
    net_profit_mwk: Decimal
    feed_cost_mwk: Decimal
    expected_revenue_mwk: Optional[Decimal]

    # Per-animal
    cost_per_animal_mwk: Optional[Decimal]
    revenue_per_animal_mwk: Optional[Decimal]
    profit_per_animal_mwk: Optional[Decimal]
    break_even_price_mwk: Optional[Decimal]
    roi_pct: Optional[Decimal]

    # Scores
    health_score: int              # 0-100
    profit_score: int              # 0-100
    overall_score: int             # 0-100

    # Badges & risk
    earned_badges: List[str]
    risk_badge: str                # "Good" | "Watch" | "High Risk" | "Critical"
    risk_color: str                # CSS class "success" | "warning" | "danger" | "secondary"

    # Recommendations
    recommendation: str


@dataclass
class CropSeasonIntelligence:
    """Per-season crop intelligence."""
    season_id: int
    season_name: str
    crop_type: str
    status: str

    area_value: Decimal
    area_unit: str

    # Yield
    projected_yield: Optional[Decimal]
    actual_yield: Optional[Decimal]
    yield_unit: str
    yield_per_area: Optional[Decimal]

    # Financials
    projected_income: Optional[Decimal]
    actual_income: Optional[Decimal]
    actual_costs: Decimal
    projected_profit: Optional[Decimal]
    actual_profit: Decimal
    break_even_price: Optional[Decimal]
    input_cost_per_area: Optional[Decimal]

    # Intelligence
    harvest_readiness: str         # "not_due" | "approaching" | "ready" | "overdue" | "harvested"
    profitability_flag: str        # "profitable" | "break_even" | "loss" | "unknown"
    risk_level: str                # "low" | "medium" | "high" | "unknown"
    recommendation: str
    days_to_harvest: Optional[int]


@dataclass
class EggProductionSummary:
    """Egg/poultry production summary (from PoultryDailyRecord data)."""
    batch_count: int
    total_birds: int

    # Production
    eggs_today: int
    eggs_this_week: int
    eggs_this_month: int
    eggs_in_stock: int
    eggs_sold: int
    spoiled_eggs: int

    # Revenue & cost
    revenue_this_month: Decimal
    feed_cost_this_month: Decimal
    cost_per_egg: Optional[Decimal]

    # Rates
    productivity_rate: Optional[Decimal]   # eggs / birds / day
    spoilage_rate: Optional[Decimal]

    # Trend
    trend: str                             # "up" | "down" | "flat" | "unknown"


@dataclass
class FarmRecommendation:
    """A single actionable farm recommendation."""
    priority: int                  # 1 = highest
    icon: str                      # Bootstrap icon name
    text: str
    category: str                  # "livestock" | "crops" | "finance" | "marketplace" | "records"
    link: Optional[str] = None


# ==============================================================================
# FARM SCORE CALCULATION
# ==============================================================================


def compute_farm_score(
    *,
    net_profit_mwk: Decimal,
    total_income_mwk: Decimal,
    total_expenses_mwk: Decimal,
    livestock_snapshots: List[Any],           # LivestockSnapshotResult-like
    active_seasons_count: int,
    ledger_entries_count: int,
    recent_activity_days: Optional[int],      # days since last entry
    marketplace_live_count: int,
    active_batches_count: int,
    crops_with_projected_yield: int,
    batches_with_sale_price: int,
    days_since_last_sale: Optional[int],
    feed_cost_mwk: Decimal,
) -> FarmScoreResult:
    """
    Compute the Farm Score (0-100) with rank, badges, XP.

    Score components (total 100):
    - Profitability (25 pts): positive profit = full; break-even = 12; loss = 0
    - Books activity (15 pts): recent ledger entries
    - Livestock health (20 pts): low mortality, active batches
    - Crop forecast quality (15 pts): seasons with yield data
    - Marketplace readiness (10 pts): live listings
    - Records completeness (10 pts): sale price set, yield data set
    - Sales activity (5 pts): recent sales
    """
    components: Dict[str, int] = {}
    badges: List[str] = []
    weaknesses: List[str] = []

    # 1. Profitability (25 pts)
    profit_pts = 0
    if total_income_mwk > 0:
        if net_profit_mwk > 0:
            margin = net_profit_mwk / total_income_mwk * 100
            profit_pts = min(25, int(margin / 2) + 10)
            if profit_pts >= 20:
                badges.append("profitable")
            if profit_pts >= 15:
                badges.append("cost_controlled")
        elif net_profit_mwk == 0:
            profit_pts = 10
        else:
            weaknesses.append("Farm is running at a loss this period")
    elif ledger_entries_count == 0:
        profit_pts = 5   # no data yet, partial credit
    components["profitability"] = profit_pts

    # 2. Books activity (15 pts)
    activity_pts = 0
    if ledger_entries_count >= 20:
        activity_pts = 15
        badges.append("books_balanced")
    elif ledger_entries_count >= 10:
        activity_pts = 10
    elif ledger_entries_count >= 3:
        activity_pts = 6
    elif ledger_entries_count > 0:
        activity_pts = 3
    else:
        weaknesses.append("No ledger entries recorded yet")
    if recent_activity_days is not None and recent_activity_days > 30:
        activity_pts = max(0, activity_pts - 5)
        weaknesses.append(f"No activity in {recent_activity_days} days")
    components["books_activity"] = activity_pts

    # 3. Livestock health (20 pts)
    livestock_pts = 0
    if active_batches_count > 0:
        mortality_rates = [
            s.mortality_rate for s in livestock_snapshots
            if hasattr(s, "mortality_rate") and s.mortality_rate is not None
        ]
        if mortality_rates:
            avg_mortality = sum(mortality_rates) / len(mortality_rates)
            if avg_mortality < MORTALITY_WATCH:
                livestock_pts = 20
                badges.append("low_mortality")
            elif avg_mortality < MORTALITY_HIGH:
                livestock_pts = 14
            elif avg_mortality < MORTALITY_CRITICAL:
                livestock_pts = 7
                weaknesses.append("High mortality rate detected in livestock")
            else:
                livestock_pts = 2
                weaknesses.append("Critical mortality rate in one or more batches")
        else:
            livestock_pts = 10   # batches exist but no events yet
    else:
        livestock_pts = 5    # no livestock, neutral
    components["livestock_health"] = livestock_pts

    # 4. Crop forecast quality (15 pts)
    crop_pts = 0
    if active_seasons_count > 0:
        if crops_with_projected_yield >= active_seasons_count:
            crop_pts = 15
        elif crops_with_projected_yield > 0:
            crop_pts = 8
        else:
            crop_pts = 3
            weaknesses.append("Add expected yield to crop seasons for better forecasts")
    else:
        crop_pts = 5    # no crops, neutral
    components["crop_forecast"] = crop_pts

    # 5. Marketplace readiness (10 pts)
    mp_pts = 0
    if marketplace_live_count >= 3:
        mp_pts = 10
        badges.append("marketplace_ready")
    elif marketplace_live_count >= 1:
        mp_pts = 6
    elif active_batches_count > 0 or active_seasons_count > 0:
        mp_pts = 2
        weaknesses.append("No marketplace listings published")
    components["marketplace"] = mp_pts

    # 6. Records completeness (10 pts)
    records_pts = 0
    if active_batches_count > 0:
        price_coverage = batches_with_sale_price / active_batches_count
        records_pts += int(price_coverage * 7)
        if price_coverage >= 1:
            badges.append("clean_records")
        elif price_coverage == 0:
            weaknesses.append("Set expected sale price on livestock batches")
    else:
        records_pts = 5
    if active_seasons_count > 0 and crops_with_projected_yield > 0:
        records_pts += 3
    components["records"] = min(10, records_pts)

    # 7. Sales activity (5 pts)
    sales_pts = 0
    if days_since_last_sale is None:
        sales_pts = 2   # no sales ever
    elif days_since_last_sale <= 7:
        sales_pts = 5
        badges.append("sales_active")
    elif days_since_last_sale <= 14:
        sales_pts = 4
    elif days_since_last_sale <= 30:
        sales_pts = 3
    else:
        sales_pts = 1
        weaknesses.append(f"No sales in {days_since_last_sale} days")
    components["sales_activity"] = sales_pts

    score = sum(components.values())
    score = max(0, min(100, score))

    # Determine rank
    rank, rank_emoji = "Struggling Farm", "⚠️"
    for threshold, r, emoji in FARM_RANK_LEVELS:
        if score >= threshold:
            rank, rank_emoji = r, emoji
            break

    # Determine next action
    if weaknesses:
        next_action = weaknesses[0]
    elif score < 50:
        next_action = "Record more farm activities to improve your score"
    elif score < 70:
        next_action = "Publish stock to marketplace to unlock Marketplace badge"
    elif score < 85:
        next_action = "Keep mortality low and sales active to reach Elite Farm"
    else:
        next_action = "Your farm is performing well — keep records up to date"

    # Missing badges
    all_badge_keys = set(ACHIEVEMENTS.keys())
    earned_set = set(badges)
    missing_badges = list(all_badge_keys - earned_set)

    return FarmScoreResult(
        score=score,
        rank=rank,
        rank_emoji=rank_emoji,
        xp=score * 100,
        earned_badges=badges,
        missing_badges=missing_badges,
        weaknesses=weaknesses,
        next_action=next_action,
        score_components=components,
    )


# ==============================================================================
# ENHANCED ALERTS
# ==============================================================================


def compute_enhanced_alerts(
    *,
    net_profit_mwk: Decimal,
    total_income_mwk: Decimal,
    total_expenses_mwk: Decimal,
    livestock_snapshots: List[Any],
    active_seasons: List[Any],           # FarmCropSeason-like objects
    today: date,
    days_since_last_sale: Optional[int],
    feed_cost_mwk: Decimal,
    marketplace_live_count: int,
    active_batches_count: int,
    batches_with_sale_price: int,
    crops_with_projected_yield: int,
    ledger_entries_count: int,
) -> EnhancedAlertsResult:
    """
    Generate categorised farm alerts: critical / warning / opportunity.
    """
    critical: List[FarmAlert] = []
    warnings: List[FarmAlert] = []
    opportunities: List[FarmAlert] = []

    # ---- CRITICAL ----

    # Negative profit
    if total_income_mwk > 0 and net_profit_mwk < 0:
        critical.append(FarmAlert(
            severity="critical",
            title="Farm Running at a Loss",
            message=f"Net profit is MWK {net_profit_mwk:,.0f}. Expenses exceed income.",
            action="Review expenses and find the biggest cost driver.",
            link="/verticals/farm/expenses/",
        ))

    # High livestock mortality
    for snap in livestock_snapshots:
        if not hasattr(snap, "mortality_rate") or snap.mortality_rate is None:
            continue
        if snap.mortality_rate >= MORTALITY_CRITICAL:
            critical.append(FarmAlert(
                severity="critical",
                title=f"Critical Mortality: {snap.batch_name}",
                message=(
                    f"Mortality rate is {snap.mortality_rate:.1f}%. "
                    f"{snap.deaths_total} deaths recorded."
                ),
                action="Review deaths, disease events and feed records immediately.",
                link="/verticals/farm/livestock/",
                data={"batch_id": snap.batch_id, "mortality_rate": float(snap.mortality_rate)},
            ))

    # Very high expenses (expenses > 90% of income)
    if total_income_mwk > 0:
        expense_ratio = total_expenses_mwk / total_income_mwk
        if expense_ratio > Decimal("0.90"):
            critical.append(FarmAlert(
                severity="critical",
                title="Expenses Very High",
                message=(
                    f"Expenses are {expense_ratio * 100:.0f}% of income. "
                    "Profit margin is critically thin."
                ),
                action="Review each expense category and cut where possible.",
                link="/verticals/farm/expenses/",
            ))

    # ---- WARNINGS ----

    # High mortality (not critical)
    for snap in livestock_snapshots:
        if not hasattr(snap, "mortality_rate") or snap.mortality_rate is None:
            continue
        if MORTALITY_HIGH <= snap.mortality_rate < MORTALITY_CRITICAL:
            warnings.append(FarmAlert(
                severity="warning",
                title=f"High Mortality: {snap.batch_name}",
                message=f"Mortality rate is {snap.mortality_rate:.1f}%. Check batch health.",
                action="Record health events and review vet expenses.",
                link="/verticals/farm/livestock/",
                data={"batch_id": snap.batch_id},
            ))

    # No sales recently
    if days_since_last_sale is not None and days_since_last_sale > 14:
        warnings.append(FarmAlert(
            severity="warning",
            title="No Recent Sales",
            message=f"No sales recorded in {days_since_last_sale} days.",
            action="Record any sales that happened, or push stock to marketplace.",
            link="/verticals/farm/sales/",
        ))

    # Crop seasons without yield data
    if active_seasons and crops_with_projected_yield < len(active_seasons):
        missing = len(active_seasons) - crops_with_projected_yield
        warnings.append(FarmAlert(
            severity="warning",
            title="Missing Crop Yield Data",
            message=f"{missing} crop season(s) have no expected yield set.",
            action="Add expected yield to unlock profit forecasts.",
            link="/verticals/farm/crops/",
        ))

    # Batches without sale price
    if active_batches_count > 0 and batches_with_sale_price < active_batches_count:
        missing = active_batches_count - batches_with_sale_price
        warnings.append(FarmAlert(
            severity="warning",
            title="Missing Sale Price",
            message=f"{missing} batch(es) have no expected sale price.",
            action="Set a sale price to unlock profit simulation.",
            link="/verticals/farm/livestock/",
        ))

    # Feed cost is very high relative to income
    if total_income_mwk > 0 and feed_cost_mwk > 0:
        feed_ratio = feed_cost_mwk / total_income_mwk
        if feed_ratio > Decimal("0.40"):
            warnings.append(FarmAlert(
                severity="warning",
                title="Feed Cost Pressure",
                message=f"Feed costs are {feed_ratio * 100:.0f}% of income. Review feed efficiency.",
                action="Compare feed cost per animal across batches.",
                link="/verticals/farm/expenses/",
            ))

    # No records at all
    if ledger_entries_count == 0:
        warnings.append(FarmAlert(
            severity="warning",
            title="No Financial Records",
            message="You have no income or expense records yet.",
            action="Start by recording your first expense or sale.",
            link="/verticals/farm/expenses/",
        ))

    # Crops approaching harvest
    for season in active_seasons:
        if not hasattr(season, "end_date") or season.end_date is None:
            continue
        if not hasattr(season, "status") or season.status in ("harvested", "closed"):
            continue
        days_left = (season.end_date - today).days
        if 0 <= days_left <= 14:
            warnings.append(FarmAlert(
                severity="warning",
                title=f"Harvest Approaching: {season.name}",
                message=f"Harvest date is in {days_left} days.",
                action="Prepare storage and plan for sale.",
                link="/verticals/farm/crops/",
                data={"season_id": season.id, "days_left": days_left},
            ))
        elif days_left < 0:
            warnings.append(FarmAlert(
                severity="warning",
                title=f"Harvest Overdue: {season.name}",
                message=f"Expected harvest date passed {abs(days_left)} days ago.",
                action="Record actual harvest or update end date.",
                link="/verticals/farm/crops/",
            ))

    # ---- OPPORTUNITIES ----

    # Batches ready to sell (count > 0 and sale price set)
    for snap in livestock_snapshots:
        batch_id = getattr(snap, "batch_id", None)
        if snap.count_current > 0:
            opportunities.append(FarmAlert(
                severity="opportunity",
                title=f"Stock Ready: {snap.batch_name}",
                message=f"{snap.count_current} animals available.",
                action="Consider publishing to marketplace or recording a sale.",
                link=f"/verticals/farm/livestock/{batch_id}/" if batch_id else "/verticals/farm/livestock/",
                data={"batch_id": batch_id},
            ))

    # No marketplace listings but stock exists
    if marketplace_live_count == 0 and active_batches_count > 0:
        opportunities.append(FarmAlert(
            severity="opportunity",
            title="Publish to Marketplace",
            message="You have livestock stock but no marketplace listings.",
            action="Publish a listing to reach buyers.",
            link="/verticals/farm/livestock/",
        ))

    # Good profit
    if total_income_mwk > 0:
        margin = net_profit_mwk / total_income_mwk * 100
        if margin >= 30:
            opportunities.append(FarmAlert(
                severity="opportunity",
                title="Strong Profit Margin",
                message=f"Profit margin is {margin:.1f}%. Farm is performing well.",
                action="Consider expanding your best-performing enterprise.",
                link="/verticals/farm/dashboard/",
            ))

    # Limit opportunities to avoid clutter (max 5)
    opportunities = opportunities[:5]

    return EnhancedAlertsResult(
        critical=critical,
        warnings=warnings,
        opportunities=opportunities,
    )


# ==============================================================================
# LIVESTOCK BATCH INTELLIGENCE
# ==============================================================================


def compute_livestock_batch_intelligence(
    *,
    batch_id: int,
    batch_name: str,
    animal_type: str,
    count_current: int,
    births: int,
    deaths: int,
    purchases: int,
    sales: int,
    total_cost_mwk: Decimal,
    total_revenue_mwk: Decimal,
    feed_cost_mwk: Decimal,
    expected_sale_price_mwk: Optional[Decimal],
    cost_basis_per_head_mwk: Optional[Decimal],
) -> LivestockBatchIntelligence:
    """
    Compute intelligence for a single livestock batch.
    Returns mortality risk, ROI, break-even price, scores and recommendations.
    """
    # Mortality
    total_in = births + purchases
    mortality_rate: Optional[Decimal] = None
    survival_rate: Optional[Decimal] = None
    if total_in > 0:
        mortality_rate = Decimal(deaths) / Decimal(total_in) * 100
        survival_rate = Decimal("100") - mortality_rate

    # Mortality risk level
    if mortality_rate is None:
        mortality_risk = "unknown"
    elif mortality_rate >= MORTALITY_CRITICAL:
        mortality_risk = "critical"
    elif mortality_rate >= MORTALITY_HIGH:
        mortality_risk = "high_risk"
    elif mortality_rate >= MORTALITY_WATCH:
        mortality_risk = "watch"
    else:
        mortality_risk = "good"

    # Per-animal calculations
    sold_and_current = (sales + count_current) or None
    cost_per_animal: Optional[Decimal] = None
    revenue_per_animal: Optional[Decimal] = None
    profit_per_animal: Optional[Decimal] = None
    break_even_price: Optional[Decimal] = None
    expected_revenue: Optional[Decimal] = None

    if total_in > 0 and total_cost_mwk > 0:
        cost_per_animal = total_cost_mwk / Decimal(total_in)

    if sales > 0 and total_revenue_mwk > 0:
        revenue_per_animal = total_revenue_mwk / Decimal(sales)

    if cost_per_animal is not None and revenue_per_animal is not None:
        profit_per_animal = revenue_per_animal - cost_per_animal

    if total_cost_mwk > 0 and count_current > 0:
        break_even_price = total_cost_mwk / Decimal(count_current)

    if expected_sale_price_mwk is not None and count_current > 0:
        expected_revenue = expected_sale_price_mwk * Decimal(count_current)

    # Net profit
    net_profit_mwk = total_revenue_mwk - total_cost_mwk

    # ROI
    roi_pct: Optional[Decimal] = None
    if total_cost_mwk > 0:
        roi_pct = (net_profit_mwk / total_cost_mwk) * 100

    # Health score (0-100): based on mortality
    if mortality_rate is None:
        health_score = 50
    elif mortality_rate < MORTALITY_WATCH:
        health_score = 90
    elif mortality_rate < MORTALITY_HIGH:
        health_score = 65
    elif mortality_rate < MORTALITY_CRITICAL:
        health_score = 35
    else:
        health_score = 10

    # Profit score (0-100)
    if total_cost_mwk == 0:
        profit_score = 50
    elif roi_pct is not None:
        if roi_pct >= 50:
            profit_score = 95
        elif roi_pct >= 20:
            profit_score = 75
        elif roi_pct >= 0:
            profit_score = 55
        else:
            profit_score = 20
    else:
        profit_score = 40

    overall_score = int((health_score * 0.5) + (profit_score * 0.5))

    # Badges
    earned_badges: List[str] = []
    if mortality_risk == "good":
        earned_badges.append("Low Mortality")
    if net_profit_mwk > 0:
        earned_badges.append("Profitable Batch")
    if total_cost_mwk > 0 and total_revenue_mwk > 0:
        earned_badges.append("Fully Tracked")
    if expected_sale_price_mwk is not None:
        earned_badges.append("Marketplace Ready")
    if feed_cost_mwk > 0:
        earned_badges.append("Feed Tracked")

    # Risk badge
    risk_map = {
        "good":      ("Good",      "success"),
        "watch":     ("Watch",     "warning"),
        "high_risk": ("High Risk", "danger"),
        "critical":  ("Critical",  "danger"),
        "unknown":   ("Unknown",   "secondary"),
    }
    risk_badge, risk_color = risk_map.get(mortality_risk, ("Unknown", "secondary"))

    # Recommendation
    if mortality_risk == "critical":
        recommendation = "Mortality is critical. Review deaths and disease events immediately."
    elif mortality_risk == "high_risk":
        recommendation = "Mortality is high. Improve hygiene, feed quality, and vet checks."
    elif net_profit_mwk < 0 and total_cost_mwk > 0:
        recommendation = "Batch is running at a loss. Review costs and expected sale price."
    elif expected_sale_price_mwk is None:
        recommendation = "Set an expected sale price to unlock profit simulation."
    elif break_even_price is not None and expected_sale_price_mwk < break_even_price:
        recommendation = f"Sale price (MWK {expected_sale_price_mwk:,.0f}) is below break-even (MWK {break_even_price:,.0f})."
    elif count_current > 0:
        recommendation = "Batch looks healthy. Consider publishing to marketplace."
    else:
        recommendation = "Batch is closed or empty. Record final sale and close batch."

    return LivestockBatchIntelligence(
        batch_id=batch_id,
        batch_name=batch_name,
        animal_type=animal_type,
        count_current=count_current,
        births=births,
        deaths=deaths,
        purchases=purchases,
        sales=sales,
        mortality_rate=mortality_rate,
        survival_rate=survival_rate,
        mortality_risk=mortality_risk,
        total_cost_mwk=total_cost_mwk,
        total_revenue_mwk=total_revenue_mwk,
        net_profit_mwk=net_profit_mwk,
        feed_cost_mwk=feed_cost_mwk,
        expected_revenue_mwk=expected_revenue,
        cost_per_animal_mwk=cost_per_animal,
        revenue_per_animal_mwk=revenue_per_animal,
        profit_per_animal_mwk=profit_per_animal,
        break_even_price_mwk=break_even_price,
        roi_pct=roi_pct,
        health_score=health_score,
        profit_score=profit_score,
        overall_score=overall_score,
        earned_badges=earned_badges,
        risk_badge=risk_badge,
        risk_color=risk_color,
        recommendation=recommendation,
    )


# ==============================================================================
# LIVESTOCK SIMULATION
# ==============================================================================


@dataclass
class LivestockSimulationResult:
    """Projection scenarios for a livestock batch."""
    current_count: int
    expected_sale_price: Decimal
    total_cost: Decimal

    # Scenarios
    best_revenue: Decimal
    best_profit: Decimal
    best_roi: Decimal

    expected_revenue: Decimal
    expected_profit: Decimal
    expected_roi: Decimal

    worst_revenue: Decimal
    worst_profit: Decimal
    worst_roi: Decimal

    break_even_price: Optional[Decimal]

    # Narrative
    summary: str


def simulate_livestock_batch(
    *,
    count_current: int,
    expected_sale_price_mwk: Decimal,
    total_cost_mwk: Decimal,
    mortality_pct_best: Decimal = Decimal("2"),
    mortality_pct_expected: Decimal = Decimal("5"),
    mortality_pct_worst: Decimal = Decimal("15"),
    price_uplift_best: Decimal = Decimal("1.10"),
    price_expected: Decimal = Decimal("1.00"),
    price_drop_worst: Decimal = Decimal("0.85"),
) -> LivestockSimulationResult:
    """
    Run best/expected/worst case simulation for a livestock batch.
    """
    def _calc(count: int, mortality_pct: Decimal, price_mult: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
        surviving = max(0, int(count * (1 - mortality_pct / 100)))
        price = expected_sale_price_mwk * price_mult
        revenue = Decimal(surviving) * price
        profit = revenue - total_cost_mwk
        roi = (profit / total_cost_mwk * 100) if total_cost_mwk > 0 else Decimal("0")
        return revenue, profit, roi

    best_rev, best_profit, best_roi = _calc(count_current, mortality_pct_best, price_uplift_best)
    exp_rev, exp_profit, exp_roi = _calc(count_current, mortality_pct_expected, price_expected)
    worst_rev, worst_profit, worst_roi = _calc(count_current, mortality_pct_worst, price_drop_worst)

    break_even: Optional[Decimal] = None
    if count_current > 0 and total_cost_mwk > 0:
        break_even = total_cost_mwk / Decimal(count_current)

    # Narrative
    if exp_profit > 0:
        summary = (
            f"If you sell {count_current} animals at MWK {expected_sale_price_mwk:,.0f} each, "
            f"expected profit is MWK {exp_profit:,.0f} (ROI {exp_roi:.0f}%)."
        )
    else:
        summary = (
            f"At MWK {expected_sale_price_mwk:,.0f} per animal, "
            f"this batch projects a loss of MWK {abs(exp_profit):,.0f}. "
            f"Break-even price is MWK {break_even:,.0f}." if break_even else
            "Add cost data for a full profit simulation."
        )

    return LivestockSimulationResult(
        current_count=count_current,
        expected_sale_price=expected_sale_price_mwk,
        total_cost=total_cost_mwk,
        best_revenue=best_rev,
        best_profit=best_profit,
        best_roi=best_roi,
        expected_revenue=exp_rev,
        expected_profit=exp_profit,
        expected_roi=exp_roi,
        worst_revenue=worst_rev,
        worst_profit=worst_profit,
        worst_roi=worst_roi,
        break_even_price=break_even,
        summary=summary,
    )


# ==============================================================================
# CROP SEASON INTELLIGENCE
# ==============================================================================


def compute_crop_season_intelligence(
    *,
    season_id: int,
    season_name: str,
    crop_type: str,
    status: str,
    area_value: Decimal,
    area_unit: str,
    projected_yield: Optional[Decimal],
    actual_yield: Optional[Decimal],
    yield_unit: str,
    projected_price_per_unit: Optional[Decimal],
    actual_price_per_unit: Optional[Decimal],
    actual_costs: Decimal,
    start_date: date,
    end_date: Optional[date],
    today: date,
) -> CropSeasonIntelligence:
    """
    Compute intelligence for a single crop season.
    """
    # Projected and actual income
    projected_income: Optional[Decimal] = None
    if projected_yield and projected_price_per_unit:
        projected_income = projected_yield * projected_price_per_unit

    actual_income: Optional[Decimal] = None
    if actual_yield and actual_price_per_unit:
        actual_income = actual_yield * actual_price_per_unit

    # Profits
    projected_profit: Optional[Decimal] = None
    if projected_income is not None:
        projected_profit = projected_income - actual_costs

    actual_income_val = actual_income if actual_income is not None else Decimal("0")
    actual_profit = actual_income_val - actual_costs

    # Yield per area
    yield_per_area: Optional[Decimal] = None
    if projected_yield and area_value > 0:
        yield_per_area = projected_yield / area_value
    elif actual_yield and area_value > 0:
        yield_per_area = actual_yield / area_value

    # Input cost per area
    input_cost_per_area: Optional[Decimal] = None
    if actual_costs > 0 and area_value > 0:
        input_cost_per_area = actual_costs / area_value

    # Break-even price
    break_even_price: Optional[Decimal] = None
    if actual_costs > 0 and (projected_yield or actual_yield):
        yield_for_be = actual_yield or projected_yield
        if yield_for_be and yield_for_be > 0:
            break_even_price = actual_costs / yield_for_be

    # Harvest readiness
    days_to_harvest: Optional[int] = None
    harvest_readiness = "not_due"
    if status in ("harvested", "closed"):
        harvest_readiness = "harvested"
    elif end_date is not None:
        days_left = (end_date - today).days
        days_to_harvest = days_left
        if days_left < 0:
            harvest_readiness = "overdue"
        elif days_left <= 14:
            harvest_readiness = "ready"
        elif days_left <= 30:
            harvest_readiness = "approaching"

    # Profitability flag
    if projected_income is not None and actual_costs > 0:
        if projected_profit is not None and projected_profit > 0:
            profitability_flag = "profitable"
        elif projected_profit is not None and projected_profit == 0:
            profitability_flag = "break_even"
        else:
            profitability_flag = "loss"
    elif actual_income is not None and actual_costs > 0:
        if actual_profit > 0:
            profitability_flag = "profitable"
        elif actual_profit == 0:
            profitability_flag = "break_even"
        else:
            profitability_flag = "loss"
    else:
        profitability_flag = "unknown"

    # Risk level
    if profitability_flag == "loss":
        risk_level = "high"
    elif profitability_flag == "break_even":
        risk_level = "medium"
    elif profitability_flag == "unknown":
        risk_level = "unknown"
    else:
        risk_level = "low"

    # Recommendation
    if harvest_readiness == "overdue":
        recommendation = "Harvest is overdue. Update end date or record actual harvest."
    elif harvest_readiness == "ready":
        recommendation = "Harvest is near. Prepare storage and plan sales."
    elif projected_yield is None:
        recommendation = "Add expected yield to unlock profit forecast."
    elif profitability_flag == "loss":
        recommendation = "Projected loss detected. Review input costs."
    elif profitability_flag == "profitable":
        recommendation = "Good forecast. Consider publishing harvested stock to marketplace."
    else:
        recommendation = "Set expected yield and price for accurate profit forecast."

    return CropSeasonIntelligence(
        season_id=season_id,
        season_name=season_name,
        crop_type=crop_type,
        status=status,
        area_value=area_value,
        area_unit=area_unit,
        projected_yield=projected_yield,
        actual_yield=actual_yield,
        yield_unit=yield_unit,
        yield_per_area=yield_per_area,
        projected_income=projected_income,
        actual_income=actual_income,
        actual_costs=actual_costs,
        projected_profit=projected_profit,
        actual_profit=actual_profit,
        break_even_price=break_even_price,
        input_cost_per_area=input_cost_per_area,
        harvest_readiness=harvest_readiness,
        profitability_flag=profitability_flag,
        risk_level=risk_level,
        recommendation=recommendation,
        days_to_harvest=days_to_harvest,
    )


# ==============================================================================
# EGG / POULTRY SUMMARY
# ==============================================================================


def compute_egg_summary(
    *,
    daily_records: List[Any],   # PoultryDailyRecord-like dicts
    today: date,
    layer_batches_count: int,
    total_layer_birds: int,
    eggs_sold_count: int = 0,
    eggs_revenue_mwk: Decimal = Decimal("0"),
    feed_cost_mwk: Decimal = Decimal("0"),
) -> EggProductionSummary:
    """
    Compute egg/poultry production summary from daily records.

    daily_records should be list of dicts with keys:
    date, eggs_collected, deaths, feed_kg
    """
    if not daily_records:
        return EggProductionSummary(
            batch_count=layer_batches_count,
            total_birds=total_layer_birds,
            eggs_today=0,
            eggs_this_week=0,
            eggs_this_month=0,
            eggs_in_stock=0,
            eggs_sold=eggs_sold_count,
            spoiled_eggs=0,
            revenue_this_month=eggs_revenue_mwk,
            feed_cost_this_month=feed_cost_mwk,
            cost_per_egg=None,
            productivity_rate=None,
            spoilage_rate=None,
            trend="unknown",
        )

    week_start = today - timedelta(days=7)
    month_start = today.replace(day=1)

    eggs_today = 0
    eggs_this_week = 0
    eggs_this_month = 0
    spoiled_eggs = 0

    for rec in daily_records:
        rec_date = rec.get("date") if isinstance(rec, dict) else getattr(rec, "date", None)
        eggs = rec.get("eggs_collected", 0) if isinstance(rec, dict) else getattr(rec, "eggs_collected", 0)
        spoiled = rec.get("spoiled_eggs", 0) if isinstance(rec, dict) else getattr(rec, "spoiled_eggs", 0)

        if rec_date is None:
            continue
        if rec_date == today:
            eggs_today += eggs
        if rec_date >= week_start:
            eggs_this_week += eggs
        if rec_date >= month_start:
            eggs_this_month += eggs
            spoiled_eggs += spoiled

    eggs_in_stock = max(0, eggs_this_month - eggs_sold_count - spoiled_eggs)

    # Cost per egg
    cost_per_egg: Optional[Decimal] = None
    if feed_cost_mwk > 0 and eggs_this_month > 0:
        cost_per_egg = feed_cost_mwk / Decimal(eggs_this_month)

    # Productivity rate (eggs per bird per day in last 7 days)
    productivity_rate: Optional[Decimal] = None
    if total_layer_birds > 0 and eggs_this_week > 0:
        productivity_rate = Decimal(eggs_this_week) / Decimal(total_layer_birds) / Decimal("7")

    # Spoilage rate
    spoilage_rate: Optional[Decimal] = None
    total_collected = eggs_this_month + spoiled_eggs
    if total_collected > 0 and spoiled_eggs > 0:
        spoilage_rate = Decimal(spoiled_eggs) / Decimal(total_collected) * 100

    # Trend (compare first vs second half of month records)
    mid_date = month_start + timedelta(days=15)
    first_half = sum(
        (rec.get("eggs_collected", 0) if isinstance(rec, dict) else getattr(rec, "eggs_collected", 0))
        for rec in daily_records
        if (rec.get("date") if isinstance(rec, dict) else getattr(rec, "date", None)) is not None
        and month_start <= (rec.get("date") if isinstance(rec, dict) else getattr(rec, "date")) < mid_date
    )
    second_half = sum(
        (rec.get("eggs_collected", 0) if isinstance(rec, dict) else getattr(rec, "eggs_collected", 0))
        for rec in daily_records
        if (rec.get("date") if isinstance(rec, dict) else getattr(rec, "date", None)) is not None
        and (rec.get("date") if isinstance(rec, dict) else getattr(rec, "date")) >= mid_date
    )
    if first_half == 0:
        trend = "unknown"
    elif second_half > first_half * Decimal("1.1"):
        trend = "up"
    elif second_half < first_half * Decimal("0.9"):
        trend = "down"
    else:
        trend = "flat"

    return EggProductionSummary(
        batch_count=layer_batches_count,
        total_birds=total_layer_birds,
        eggs_today=eggs_today,
        eggs_this_week=eggs_this_week,
        eggs_this_month=eggs_this_month,
        eggs_in_stock=eggs_in_stock,
        eggs_sold=eggs_sold_count,
        spoiled_eggs=spoiled_eggs,
        revenue_this_month=eggs_revenue_mwk,
        feed_cost_this_month=feed_cost_mwk,
        cost_per_egg=cost_per_egg,
        productivity_rate=productivity_rate,
        spoilage_rate=spoilage_rate,
        trend=trend,
    )


# ==============================================================================
# RECOMMENDATIONS ("What Should I Do Next?")
# ==============================================================================


def generate_farm_recommendations(
    *,
    net_profit_mwk: Decimal,
    total_income_mwk: Decimal,
    livestock_snapshots: List[Any],
    active_seasons: List[Any],
    active_batches_count: int,
    batches_with_sale_price: int,
    crops_with_projected_yield: int,
    marketplace_live_count: int,
    days_since_last_sale: Optional[int],
    feed_cost_mwk: Decimal,
    ledger_entries_count: int,
    has_layer_batches: bool,
    today: date,
) -> List[FarmRecommendation]:
    """
    Generate a short list of practical next actions for the farmer.
    Returns at most 5 recommendations, ordered by priority.
    """
    recs: List[FarmRecommendation] = []

    # Priority 1: Critical mortality
    for snap in livestock_snapshots:
        if not hasattr(snap, "mortality_rate") or snap.mortality_rate is None:
            continue
        if snap.mortality_rate >= MORTALITY_HIGH:
            recs.append(FarmRecommendation(
                priority=1,
                icon="bi-exclamation-triangle-fill",
                text=f"Mortality is {snap.mortality_rate:.1f}% in {snap.batch_name} — review deaths, disease events, and feed.",
                category="livestock",
                link="/verticals/farm/livestock/",
            ))

    # Priority 2: No financial records
    if ledger_entries_count == 0:
        recs.append(FarmRecommendation(
            priority=2,
            icon="bi-journal-plus",
            text="Start by recording your first expense or sale to begin tracking profit.",
            category="finance",
            link="/verticals/farm/expenses/",
        ))

    # Priority 3: Missing sale price on batches
    if active_batches_count > 0 and batches_with_sale_price < active_batches_count:
        missing = active_batches_count - batches_with_sale_price
        recs.append(FarmRecommendation(
            priority=3,
            icon="bi-tag",
            text=f"Add expected sale price to {missing} livestock batch(es) to unlock profit simulation.",
            category="livestock",
            link="/verticals/farm/livestock/",
        ))

    # Priority 4: Missing crop yield
    if active_seasons and crops_with_projected_yield < len(active_seasons):
        recs.append(FarmRecommendation(
            priority=4,
            icon="bi-flower1",
            text="Add expected yield to crop seasons for profit forecasting.",
            category="crops",
            link="/verticals/farm/crops/",
        ))

    # Priority 5: Harvest approaching
    for season in active_seasons:
        if not hasattr(season, "end_date") or season.end_date is None:
            continue
        if getattr(season, "status", "") in ("harvested", "closed"):
            continue
        days_left = (season.end_date - today).days
        if 0 <= days_left <= 21:
            recs.append(FarmRecommendation(
                priority=5,
                icon="bi-scissors",
                text=f"Harvest for {season.name} is in {days_left} days — prepare storage.",
                category="crops",
                link=f"/verticals/farm/crops/{season.id}/",
            ))

    # Priority 6: Publish to marketplace
    if active_batches_count > 0 and marketplace_live_count == 0:
        recs.append(FarmRecommendation(
            priority=6,
            icon="bi-shop",
            text="No marketplace listings. Publish livestock to reach buyers.",
            category="marketplace",
            link="/verticals/farm/livestock/",
        ))

    # Priority 7: Record egg collection
    if has_layer_batches:
        recs.append(FarmRecommendation(
            priority=7,
            icon="bi-egg",
            text="Record today's egg collection for your layer batches.",
            category="livestock",
            link="/verticals/farm/egg-tracking/",
        ))

    # Priority 8: No recent sales
    if days_since_last_sale is not None and days_since_last_sale > 14:
        recs.append(FarmRecommendation(
            priority=8,
            icon="bi-cash-coin",
            text=f"No sales in {days_since_last_sale} days. Record any sales that happened.",
            category="finance",
            link="/verticals/farm/sales/",
        ))

    # Priority 9: Feed cost pressure
    if total_income_mwk > 0 and feed_cost_mwk > total_income_mwk * Decimal("0.35"):
        recs.append(FarmRecommendation(
            priority=9,
            icon="bi-piggy-bank",
            text="Feed costs are high relative to income. Review batch profitability.",
            category="finance",
            link="/verticals/farm/expenses/",
        ))

    # Sort by priority and return top 5
    recs.sort(key=lambda r: r.priority)
    return recs[:5]


# ==============================================================================
# HOUSING PLANNER
# ==============================================================================


@dataclass
class HousingPlannerResult:
    """Structured livestock housing plan (basis for future 3D integration)."""
    animal_type: str
    animal_count: int
    housing_type: str
    floor_space_m2: Decimal
    feed_storage_kg: Decimal
    ventilation_recommendation: str
    biosecurity_checklist: List[str]
    hygiene_checklist: List[str]
    layout_notes: str
    estimated_cost_range_mwk: Optional[str]
    three_d_ready: bool    # placeholder for future Three.js integration


def compute_housing_plan(
    *,
    animal_type: str,
    animal_count: int,
    housing_type: str = "standard",
    available_land_m2: Optional[Decimal] = None,
) -> HousingPlannerResult:
    """
    Generate a housing plan recommendation for a livestock batch.
    """
    # Floor space requirements per animal (m²)
    SPACE_PER_ANIMAL = {
        "chickens": Decimal("0.08"),
        "pigs":     Decimal("1.50"),
        "cattle":   Decimal("5.00"),
        "goats":    Decimal("1.50"),
        "ducks":    Decimal("0.20"),
        "rabbits":  Decimal("0.40"),
        "sheep":    Decimal("1.50"),
        "fish":     Decimal("1.00"),  # pond m² per fish
    }
    space_per = SPACE_PER_ANIMAL.get(animal_type, Decimal("2.00"))
    floor_space = space_per * Decimal(animal_count) * Decimal("1.2")  # +20% buffer

    # Feed storage recommendation (7 days of feed)
    FEED_KG_PER_DAY_PER_ANIMAL = {
        "chickens": Decimal("0.12"),
        "pigs":     Decimal("2.00"),
        "cattle":   Decimal("8.00"),
        "goats":    Decimal("1.50"),
        "ducks":    Decimal("0.15"),
        "rabbits":  Decimal("0.15"),
        "sheep":    Decimal("1.50"),
    }
    feed_per_day = FEED_KG_PER_DAY_PER_ANIMAL.get(animal_type, Decimal("1.00"))
    feed_storage = feed_per_day * Decimal(animal_count) * Decimal("7")

    # Ventilation
    if animal_type in ("chickens", "ducks"):
        ventilation = "Ensure cross-ventilation with side openings. Avoid ammonia buildup. 1 fan per 500 birds recommended."
    elif animal_type == "pigs":
        ventilation = "Ensure good airflow, especially in hot season. Slatted floors or drainage help reduce gas buildup."
    else:
        ventilation = "Ensure adequate airflow. Open-sided structures preferred in warm climates."

    # Biosecurity checklist
    biosecurity = [
        "Fence perimeter to restrict wildlife entry",
        "Foot dip at entry point",
        "Quarantine new animals for 14 days",
        "Restrict visitor access",
        "Keep feed storage sealed and pest-free",
        "Regular disinfection of housing",
    ]

    # Hygiene checklist
    hygiene = [
        "Daily removal of manure and wet bedding",
        "Weekly full clean of housing",
        "Fresh water available at all times",
        "Dry, clean bedding material",
        "No standing water near housing",
        "Proper drainage away from housing",
    ]

    # Cost estimate
    cost_estimates = {
        "chickens": "MWK 150,000 – 500,000 (basic open structure)",
        "pigs":     "MWK 800,000 – 2,500,000 (concrete pen)",
        "cattle":   "MWK 1,500,000 – 5,000,000 (open shed)",
        "goats":    "MWK 300,000 – 1,000,000 (basic shed)",
    }
    cost_range = cost_estimates.get(animal_type)

    layout_notes = (
        f"Planned for {animal_count} {animal_type}. "
        f"Minimum floor space: {floor_space:.1f} m². "
        f"Store {feed_storage:.0f} kg feed for 7 days."
    )

    return HousingPlannerResult(
        animal_type=animal_type,
        animal_count=animal_count,
        housing_type=housing_type,
        floor_space_m2=floor_space,
        feed_storage_kg=feed_storage,
        ventilation_recommendation=ventilation,
        biosecurity_checklist=biosecurity,
        hygiene_checklist=hygiene,
        layout_notes=layout_notes,
        estimated_cost_range_mwk=cost_range,
        three_d_ready=False,
    )


# ==============================================================================
# MARKETPLACE READINESS
# ==============================================================================


@dataclass
class MarketplaceReadinessResult:
    """Marketplace readiness check for a batch or crop."""
    is_ready: bool
    score: int      # 0-100
    checks: Dict[str, bool]
    missing: List[str]
    suggestion: str


def check_livestock_marketplace_readiness(
    *,
    count_current: int,
    expected_sale_price_mwk: Optional[Decimal],
    has_primary_image: bool,
    has_description: bool,
    is_already_live: bool,
) -> MarketplaceReadinessResult:
    """Check if a livestock batch is ready for marketplace."""
    checks = {
        "has_stock":       count_current > 0,
        "has_price":       expected_sale_price_mwk is not None,
        "has_image":       has_primary_image,
        "has_description": has_description,
        "not_live":        not is_already_live,
    }
    weights = {"has_stock": 30, "has_price": 30, "has_image": 20, "has_description": 10, "not_live": 10}
    score = sum(weights[k] for k, v in checks.items() if v)

    missing: List[str] = []
    if not checks["has_stock"]:
        missing.append("No animals in batch")
    if not checks["has_price"]:
        missing.append("No expected sale price")
    if not checks["has_image"]:
        missing.append("No primary photo")
    if not checks["has_description"]:
        missing.append("No notes/description")

    is_ready = checks["has_stock"] and checks["has_price"]

    if is_already_live:
        suggestion = "Already published. Update to refresh listing."
    elif is_ready:
        suggestion = "Ready to publish. Add a photo for better results."
    elif not checks["has_stock"]:
        suggestion = "Add animals to the batch before publishing."
    else:
        suggestion = "Set an expected sale price to publish."

    return MarketplaceReadinessResult(
        is_ready=is_ready,
        score=score,
        checks=checks,
        missing=missing,
        suggestion=suggestion,
    )


# ==============================================================================
# FARM BUSINESS HEALTH SCORE (farm-specific)
# ==============================================================================


@dataclass
class FarmBusinessHealthResult:
    """Farm-specific Business Health Score."""
    score: int          # 0-100
    status: str         # "Critical" | "Needs Attention" | "Stable" | "Strong" | "Excellent"
    status_color: str   # "danger" | "warning" | "info" | "success" | "success"
    headline: str
    badges: List[str]
    weaknesses: List[str]
    recommended_action: str
    score_components: Dict[str, int]


def compute_farm_business_health(
    *,
    net_profit_mwk: Decimal,
    total_income_mwk: Decimal,
    total_expenses_mwk: Decimal,
    expected_income_mwk: Optional[Decimal],
    livestock_value_mwk: Optional[Decimal],
    assets_value_mwk: Decimal,
    mortality_rate_pct: Optional[Decimal],
    marketplace_live_count: int,
    active_batches_count: int,
    active_seasons_count: int,
    ledger_entries_count: int,
    days_since_last_activity: Optional[int],
    crops_with_projected_yield: int,
) -> FarmBusinessHealthResult:
    """
    Farm-specific business health score with copy tailored for farmers.
    """
    components: Dict[str, int] = {}
    badges: List[str] = []
    weaknesses: List[str] = []

    # Profitability (30 pts)
    prof_pts = 0
    if total_income_mwk > 0:
        margin = net_profit_mwk / total_income_mwk * 100
        if margin >= 30:
            prof_pts = 30
            badges.append("Profit Strong")
        elif margin >= 15:
            prof_pts = 22
        elif margin >= 0:
            prof_pts = 13
        else:
            prof_pts = 0
            weaknesses.append("Negative profit this period")
    components["profitability"] = prof_pts

    # Books & records (20 pts)
    books_pts = 0
    if ledger_entries_count >= 20:
        books_pts = 20
        badges.append("Books Balanced")
    elif ledger_entries_count >= 10:
        books_pts = 13
    elif ledger_entries_count >= 3:
        books_pts = 7
    else:
        weaknesses.append("Very few financial records")
    components["books"] = books_pts

    # Livestock health (20 pts)
    ls_pts = 0
    if active_batches_count > 0:
        if mortality_rate_pct is not None:
            if mortality_rate_pct < MORTALITY_WATCH:
                ls_pts = 20
                badges.append("Livestock Stable")
            elif mortality_rate_pct < MORTALITY_HIGH:
                ls_pts = 12
            else:
                ls_pts = 4
                weaknesses.append("High livestock mortality")
        else:
            ls_pts = 10
    else:
        ls_pts = 10  # no livestock = neutral
    components["livestock"] = ls_pts

    # Crop health (15 pts)
    crop_pts = 0
    if active_seasons_count > 0:
        if crops_with_projected_yield >= active_seasons_count:
            crop_pts = 15
            badges.append("Crops Healthy")
        elif crops_with_projected_yield > 0:
            crop_pts = 8
        else:
            crop_pts = 3
            weaknesses.append("Crop seasons missing yield data")
    else:
        crop_pts = 8  # no crops = neutral
    components["crops"] = crop_pts

    # Marketplace (10 pts)
    mp_pts = 0
    if marketplace_live_count >= 2:
        mp_pts = 10
        badges.append("Marketplace Ready")
    elif marketplace_live_count == 1:
        mp_pts = 6
    elif active_batches_count > 0:
        mp_pts = 2
    components["marketplace"] = mp_pts

    # Activity recency (5 pts)
    act_pts = 5
    if days_since_last_activity is not None and days_since_last_activity > 30:
        act_pts = 1
        weaknesses.append(f"No activity in {days_since_last_activity} days")
    components["activity"] = act_pts

    total = sum(components.values())
    total = max(0, min(100, total))

    # Status
    if total >= 85:
        status, status_color = "Excellent", "success"
    elif total >= 70:
        status, status_color = "Strong", "success"
    elif total >= 50:
        status, status_color = "Stable", "info"
    elif total >= 30:
        status, status_color = "Needs Attention", "warning"
    else:
        status, status_color = "Critical", "danger"

    # Headline copy
    headlines = {
        "Excellent": "Your farm is balanced and ready to scale.",
        "Strong":    "Stock is healthy and the books look good.",
        "Stable":    "Your farm is breathing well. Keep records current.",
        "Needs Attention": "Some areas need attention — check the alerts below.",
        "Critical":  "Your farm needs immediate action. Start with the critical alerts.",
    }
    headline = headlines.get(status, "Review your farm data for insights.")

    # Recommended action
    if weaknesses:
        recommended_action = weaknesses[0]
    elif status in ("Strong", "Excellent"):
        recommended_action = "Expand your best enterprise and publish to marketplace."
    else:
        recommended_action = "Add more records to improve your health score."

    return FarmBusinessHealthResult(
        score=total,
        status=status,
        status_color=status_color,
        headline=headline,
        badges=badges,
        weaknesses=weaknesses,
        recommended_action=recommended_action,
        score_components=components,
    )
