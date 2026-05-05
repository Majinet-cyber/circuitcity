"""
Business Health Score — calculation service.

calculate_business_health_score(business, start_date=None, end_date=None)

Returns a structured dict with overall score, component scores, labels,
explanations, and actionable recommendations.

Design principles:
  - Never crash. Every component is wrapped in try/except.
  - Graceful when data is missing: returns "Not enough data" label, score=None.
  - Only averages available components (ignores None scores).
  - Returns an onboarding state when no meaningful data exists at all.
  - Business-scoped: never leaks data across tenants.

Weights (sum to 100 when all components available):
    profit_trend       25 %
    cash_flow          20 %
    stock_risk         20 %
    sales_consistency  15 %
    expense_control    10 %
    credit_exposure    10 %
    staff_efficiency    0 % (bonus, added only when timelogs data exists)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WEIGHTS = {
    "profit_trend": 25,
    "cash_flow": 20,
    "stock_risk": 20,
    "sales_consistency": 15,
    "expense_control": 10,
    "credit_exposure": 10,
}

STAFF_EFFICIENCY_BONUS_CAP = 5  # up to +5 points bonus

# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def _overall_label(score: int) -> tuple[str, str]:
    """Return (label, status_color) for an overall score."""
    if score >= 85:
        return "Excellent", "green"
    if score >= 70:
        return "Good", "green"
    if score >= 55:
        return "Fair", "amber"
    if score >= 40:
        return "At Risk", "orange"
    return "Critical", "red"


def _component_label(score: Optional[int], thresholds: tuple) -> str:
    """
    Map a 0–100 component score to a human label using caller-supplied
    thresholds = ((min_score, label), ...) in descending order.
    """
    if score is None:
        return "Not enough data"
    for min_score, label in thresholds:
        if score >= min_score:
            return label
    return "Poor"


def _null_component(explanation: str) -> dict:
    return {
        "score": None,
        "label": "Not enough data",
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Individual component scorers
# ---------------------------------------------------------------------------

def _score_profit_trend(business, start: date, end: date) -> dict:
    """
    Score based on whether gross profit margin is positive and trending.
    Uses InventoryItem sold records scoped to the business.
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Sum

        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
            selling_price__isnull=False,
            order_price__gt=0,
        )

        agg = qs.aggregate(
            revenue=Sum("selling_price"),
            cost=Sum("order_price"),
        )

        revenue = agg.get("revenue") or Decimal("0")
        cost = agg.get("cost") or Decimal("0")

        if revenue <= 0:
            return _null_component("No sales recorded in this period. Record your first sale to see profit trend.")

        margin_pct = float((revenue - cost) / revenue * 100)

        # Check if improving vs prior period
        days = (end - start).days or 1
        prior_start = start - timedelta(days=days)
        prior_end = start - timedelta(days=1)

        prior_agg = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=prior_start,
            sold_at__date__lte=prior_end,
            selling_price__isnull=False,
            order_price__gt=0,
        ).aggregate(
            revenue=Sum("selling_price"),
            cost=Sum("order_price"),
        )

        prior_rev = prior_agg.get("revenue") or Decimal("0")
        prior_cost = prior_agg.get("cost") or Decimal("0")
        prior_margin = float((prior_rev - prior_cost) / prior_rev * 100) if prior_rev > 0 else 0

        # Base score: margin quality
        if margin_pct >= 30:
            base = 90
        elif margin_pct >= 20:
            base = 75
        elif margin_pct >= 10:
            base = 60
        elif margin_pct > 0:
            base = 45
        else:
            base = 20

        # Trend bonus/penalty (±10)
        if prior_rev > 0:
            trend_delta = margin_pct - prior_margin
            trend_bonus = max(-10, min(10, int(trend_delta * 0.5)))
            score = min(100, max(0, base + trend_bonus))
        else:
            score = base

        thresholds = ((80, "Strong"), (65, "Good"), (50, "Improving"), (35, "Weak"), (0, "Poor"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"Gross margin is {margin_pct:.1f}% over this period. "
                + ("Trending better than prior period." if prior_rev > 0 and margin_pct > prior_margin
                   else "Flat or declining vs prior period." if prior_rev > 0
                   else "No prior period data available for comparison.")
            ),
        }
    except Exception as exc:
        logger.warning("profit_trend scorer error: %s", exc)
        return _null_component("Could not calculate profit trend.")


def _score_cash_flow(business, start: date, end: date) -> dict:
    """
    Estimate cash flow from sales revenue. A higher revenue-to-cost ratio
    with consistent daily inflows scores better.
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncDate

        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
            selling_price__isnull=False,
        )

        agg = qs.aggregate(revenue=Sum("selling_price"), count=Count("id"))
        revenue = agg.get("revenue") or Decimal("0")
        count = agg.get("count") or 0

        if count == 0:
            return _null_component(
                "No sales in this period. Cash flow cannot be assessed without recorded revenue."
            )

        days_active = (
            qs.annotate(day=TruncDate("sold_at"))
            .values("day")
            .distinct()
            .count()
        )

        total_days = max((end - start).days, 1)
        # Coverage: fraction of days with at least one sale
        coverage = days_active / total_days

        if coverage >= 0.8:
            score = 90
        elif coverage >= 0.6:
            score = 75
        elif coverage >= 0.4:
            score = 60
        elif coverage >= 0.2:
            score = 45
        else:
            score = 30

        thresholds = ((80, "Stable"), (65, "Consistent"), (50, "Moderate"), (30, "Irregular"), (0, "Unstable"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"Sales recorded on {days_active} of {total_days} days ({coverage:.0%} coverage). "
                f"Total revenue: {float(revenue):,.0f} MWK."
            ),
        }
    except Exception as exc:
        logger.warning("cash_flow scorer error: %s", exc)
        return _null_component("Could not calculate cash flow stability.")


def _score_stock_risk(business, *_) -> dict:
    """
    Score based on ratio of in-stock items to potential stockout risk.
    Low risk = good score.
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Count

        total_qs = InventoryItem.objects.filter(business=business, is_active=True)
        total = total_qs.count()

        if total == 0:
            return _null_component(
                "No active stock items found. Add inventory to see your stock risk score."
            )

        in_stock = total_qs.filter(status="IN_STOCK").count()
        stock_ratio = in_stock / total

        # Try to detect minimum-stock items if the field exists
        low_stock_count = 0
        try:
            from inventory.models import InventoryItem as II
            from django.db.models import F as _F
            if hasattr(II, "min_quantity"):
                low_stock_count = (
                    total_qs.filter(status="IN_STOCK", quantity__lt=_F("min_quantity")).count()
                )
        except Exception:
            pass

        if stock_ratio >= 0.7:
            base = 85
        elif stock_ratio >= 0.5:
            base = 70
        elif stock_ratio >= 0.3:
            base = 55
        elif stock_ratio >= 0.1:
            base = 40
        else:
            base = 20

        # Low-stock penalty
        if low_stock_count > 0:
            penalty = min(20, low_stock_count * 3)
            score = max(0, base - penalty)
        else:
            score = base

        thresholds = ((80, "Low Risk"), (65, "Healthy"), (50, "Watch"), (35, "At Risk"), (0, "Critical"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"{in_stock} of {total} active items are currently in stock "
                f"({stock_ratio:.0%} availability)."
                + (f" {low_stock_count} items are below minimum stock level." if low_stock_count else "")
            ),
        }
    except Exception as exc:
        logger.warning("stock_risk scorer error: %s", exc)
        return _null_component("Could not calculate stock risk.")


def _score_sales_consistency(business, start: date, end: date) -> dict:
    """
    Score based on how consistent daily sales volume is.
    Uses coefficient of variation (lower = more consistent = better).
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        import statistics

        daily_counts = list(
            InventoryItem.objects.filter(
                business=business,
                status="SOLD",
                sold_at__date__gte=start,
                sold_at__date__lte=end,
            )
            .annotate(day=TruncDate("sold_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .values_list("cnt", flat=True)
        )

        if len(daily_counts) < 3:
            return _null_component(
                "Need at least 3 days of sales data to measure consistency. Keep recording sales."
            )

        mean = statistics.mean(daily_counts)
        if mean == 0:
            return _null_component("Sales mean is zero; not enough data to score consistency.")

        stdev = statistics.stdev(daily_counts)
        cv = stdev / mean  # coefficient of variation

        if cv <= 0.2:
            score = 90
        elif cv <= 0.4:
            score = 75
        elif cv <= 0.6:
            score = 60
        elif cv <= 0.8:
            score = 45
        else:
            score = 30

        thresholds = ((80, "Very Consistent"), (65, "Consistent"), (50, "Improving"), (35, "Variable"), (0, "Erratic"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"Average {mean:.1f} sales/day with variation of ±{stdev:.1f}. "
                + ("Sales are very steady." if cv <= 0.3 else
                   "Some variation in daily sales." if cv <= 0.6 else
                   "High day-to-day variation — consider promotions to smooth sales.")
            ),
        }
    except Exception as exc:
        logger.warning("sales_consistency scorer error: %s", exc)
        return _null_component("Could not calculate sales consistency.")


def _score_expense_control(business, start: date, end: date) -> dict:
    """
    Compare operating expenses to revenue. Lower expense ratio = better score.
    Gracefully returns null if expense data is unavailable.
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Sum

        revenue_agg = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
            selling_price__isnull=False,
        ).aggregate(revenue=Sum("selling_price"))

        revenue = float(revenue_agg.get("revenue") or 0)

        if revenue <= 0:
            return _null_component("No revenue data to compare against expenses.")

        # Try to get expense data from cfo app
        total_expenses = 0.0
        try:
            from django.apps import apps
            if apps.is_installed("cfo"):
                Expense = apps.get_model("cfo", "Expense")
                # cfo.Expense uses branch FK — try to get branch for this business
                exp_agg = Expense.objects.filter(
                    date__gte=start,
                    date__lte=end,
                ).aggregate(total=Sum("amount"))
                total_expenses = float(exp_agg.get("total") or 0)
        except Exception:
            pass

        if total_expenses == 0:
            return _null_component(
                "No expense records found. Start recording expenses to see your expense control score."
            )

        expense_ratio = total_expenses / revenue

        if expense_ratio <= 0.15:
            score = 90
        elif expense_ratio <= 0.25:
            score = 75
        elif expense_ratio <= 0.40:
            score = 60
        elif expense_ratio <= 0.60:
            score = 45
        else:
            score = 20

        thresholds = ((80, "Excellent"), (65, "Controlled"), (50, "Watch"), (35, "High"), (0, "Critical"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"Expenses are {expense_ratio:.0%} of revenue "
                f"({total_expenses:,.0f} MWK vs {revenue:,.0f} MWK revenue)."
            ),
        }
    except Exception as exc:
        logger.warning("expense_control scorer error: %s", exc)
        return _null_component("Could not calculate expense control.")


def _score_credit_exposure(business, start: date, end: date) -> dict:
    """
    Score based on the ratio of credit (layby / unpaid) sales to total sales.
    High credit exposure = lower score.
    """
    try:
        from inventory.models import InventoryItem
        from django.db.models import Count, Sum

        total_sold = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
        ).count()

        if total_sold == 0:
            return _null_component("No sales recorded. Record sales to measure credit exposure.")

        # Try layby model
        layby_count = 0
        try:
            from django.apps import apps
            if apps.is_installed("layby"):
                LaybyOrder = apps.get_model("layby", "LaybyOrder")
                # LaybyOrder doesn't directly tie to business; filter by created_by membership
                from tenants.models import Membership
                business_user_ids = list(
                    Membership.objects.filter(business=business).values_list("user_id", flat=True)
                )
                layby_count = LaybyOrder.objects.filter(
                    created_by_id__in=business_user_ids,
                    created_at__date__gte=start,
                    created_at__date__lte=end,
                ).exclude(status="COMPLETED").count()
        except Exception:
            pass

        credit_ratio = layby_count / total_sold
        if credit_ratio <= 0.05:
            score = 90
        elif credit_ratio <= 0.15:
            score = 75
        elif credit_ratio <= 0.30:
            score = 60
        elif credit_ratio <= 0.50:
            score = 45
        else:
            score = 25

        thresholds = ((80, "Low Exposure"), (65, "Manageable"), (50, "Moderate"), (35, "High"), (0, "Critical"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"{layby_count} open credit/layby orders out of {total_sold} total sales "
                f"({credit_ratio:.0%} credit ratio)."
                if layby_count > 0
                else f"No open layby/credit orders detected out of {total_sold} sales. Good cash discipline."
            ),
        }
    except Exception as exc:
        logger.warning("credit_exposure scorer error: %s", exc)
        return _null_component("Could not calculate credit exposure.")


def _score_staff_efficiency(business, start: date, end: date) -> Optional[dict]:
    """
    Optional bonus component. Returns None if timelogs are unavailable.
    Uses TimeLog sessions (business-scoped) vs sales volume ratio.
    """
    try:
        from django.apps import apps
        if not apps.is_installed("timelogs"):
            return None

        from timelogs.models import TimeLog  # noqa: PLC0415
        from inventory.models import InventoryItem
        from django.db.models import Sum, ExpressionWrapper, F, DurationField

        # TimeLog has business FK directly — use it
        logs_qs = TimeLog.objects.filter(
            business=business,
            started_at__date__gte=start,
            started_at__date__lte=end,
            ended_at__isnull=False,
        )

        count = logs_qs.count()
        if count == 0:
            return None

        # Estimate hours from started_at/ended_at duration
        duration_agg = logs_qs.aggregate(
            total=Sum(
                ExpressionWrapper(F("ended_at") - F("started_at"), output_field=DurationField())
            )
        )
        total_duration = duration_agg.get("total")
        if total_duration is None:
            return None

        total_hours = total_duration.total_seconds() / 3600
        if total_hours < 1:
            return None

        total_sales = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
        ).count()

        sales_per_hour = total_sales / total_hours

        if sales_per_hour >= 2.0:
            score = 90
        elif sales_per_hour >= 1.0:
            score = 75
        elif sales_per_hour >= 0.5:
            score = 60
        elif sales_per_hour >= 0.2:
            score = 45
        else:
            score = 30

        thresholds = ((80, "High Efficiency"), (65, "Good"), (50, "Fair"), (35, "Low"), (0, "Poor"))
        return {
            "score": score,
            "label": _component_label(score, thresholds),
            "explanation": (
                f"{total_sales} sales over {total_hours:.0f} staff hours "
                f"= {sales_per_hour:.2f} sales/hour."
            ),
        }
    except Exception as exc:
        logger.debug("staff_efficiency scorer skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def calculate_business_health_score(
    business,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """
    Calculate a Business Health Score for *business* over the given date range.

    Args:
        business: A tenants.Business instance.
        start_date: Inclusive start date (default: 30 days ago).
        end_date: Inclusive end date (default: today).

    Returns:
        {
            "score": int | None,
            "label": str,
            "status_color": str,
            "components": { component_name: { score, label, explanation } },
            "recommendations": [ str ],
            "period": { "start": date, "end": date },
            "is_onboarding": bool,
        }
    """
    today = timezone.localdate()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = today - timedelta(days=30)

    # Run all component scorers
    components: dict = {}
    try:
        components["profit_trend"] = _score_profit_trend(business, start_date, end_date)
    except Exception as exc:
        logger.error("profit_trend failed: %s", exc)
        components["profit_trend"] = _null_component("Calculation error.")

    try:
        components["cash_flow"] = _score_cash_flow(business, start_date, end_date)
    except Exception as exc:
        logger.error("cash_flow failed: %s", exc)
        components["cash_flow"] = _null_component("Calculation error.")

    try:
        components["stock_risk"] = _score_stock_risk(business, start_date, end_date)
    except Exception as exc:
        logger.error("stock_risk failed: %s", exc)
        components["stock_risk"] = _null_component("Calculation error.")

    try:
        components["sales_consistency"] = _score_sales_consistency(business, start_date, end_date)
    except Exception as exc:
        logger.error("sales_consistency failed: %s", exc)
        components["sales_consistency"] = _null_component("Calculation error.")

    try:
        components["expense_control"] = _score_expense_control(business, start_date, end_date)
    except Exception as exc:
        logger.error("expense_control failed: %s", exc)
        components["expense_control"] = _null_component("Calculation error.")

    try:
        components["credit_exposure"] = _score_credit_exposure(business, start_date, end_date)
    except Exception as exc:
        logger.error("credit_exposure failed: %s", exc)
        components["credit_exposure"] = _null_component("Calculation error.")

    # Optional staff efficiency (bonus)
    staff = None
    try:
        staff = _score_staff_efficiency(business, start_date, end_date)
    except Exception as exc:
        logger.debug("staff_efficiency skipped: %s", exc)

    if staff is not None:
        components["staff_efficiency"] = staff
    else:
        components["staff_efficiency"] = _null_component(
            "No time-log data found. Enable staff time tracking to unlock this metric."
        )

    # ---------------------------------------------------------------------------
    # Compute weighted overall score from available (non-null) components
    # ---------------------------------------------------------------------------
    available_weight = 0
    weighted_sum = 0.0

    for key, weight in WEIGHTS.items():
        comp = components.get(key, {})
        score = comp.get("score")
        if score is not None:
            weighted_sum += score * weight
            available_weight += weight

    # Staff efficiency bonus (0–5 points)
    staff_bonus = 0
    if staff is not None and staff.get("score") is not None:
        staff_bonus = min(
            STAFF_EFFICIENCY_BONUS_CAP,
            round(staff["score"] / 100 * STAFF_EFFICIENCY_BONUS_CAP),
        )

    if available_weight == 0:
        # Truly new business — nothing to score yet
        return {
            "score": None,
            "label": "No data yet",
            "status_color": "gray",
            "components": components,
            "recommendations": [
                "Record your first sales to start tracking profit trend.",
                "Add your stock/inventory to see stock risk.",
                "Enable WhatsApp alerts to get daily summaries.",
            ],
            "period": {"start": start_date, "end": end_date},
            "is_onboarding": True,
        }

    # Normalise: re-scale so available weights sum to 100
    normalised_score = (weighted_sum / available_weight) + staff_bonus
    overall_score = min(100, max(0, round(normalised_score)))

    label, status_color = _overall_label(overall_score)

    # ---------------------------------------------------------------------------
    # Generate recommendations
    # ---------------------------------------------------------------------------
    recommendations: list[str] = []

    profit = components.get("profit_trend", {})
    if profit.get("score") is not None and profit["score"] < 60:
        recommendations.append(
            "Your profit margin is below target. Review your pricing or reduce cost of goods."
        )

    cash = components.get("cash_flow", {})
    if cash.get("score") is not None and cash["score"] < 60:
        recommendations.append(
            "Cash inflow is irregular. Try daily or multi-session selling to stabilise revenue."
        )

    stock = components.get("stock_risk", {})
    if stock.get("score") is not None and stock["score"] < 60:
        recommendations.append(
            "Restock fast-moving items before they fall below minimum levels to avoid losing sales."
        )

    consistency = components.get("sales_consistency", {})
    if consistency.get("score") is not None and consistency["score"] < 60:
        recommendations.append(
            "Sales are inconsistent. Consider promotions or WhatsApp campaigns on slow days."
        )

    expense = components.get("expense_control", {})
    if expense.get("score") is not None and expense["score"] < 60:
        recommendations.append(
            "Expenses are rising faster than sales. Identify which cost categories to cut."
        )

    credit = components.get("credit_exposure", {})
    if credit.get("score") is not None and credit["score"] < 60:
        recommendations.append(
            "Several customers have overdue balances. Follow up credit customers to improve cash flow."
        )

    if not recommendations:
        if overall_score >= 85:
            recommendations.append("Your business is in excellent health. Focus on growth and expansion.")
        elif overall_score >= 70:
            recommendations.append(
                "Good shape overall. Look for the weakest component above and target improvement."
            )
        else:
            recommendations.append(
                "Keep recording sales and expenses consistently to improve your score over time."
            )

    return {
        "score": overall_score,
        "label": label,
        "status_color": status_color,
        "components": components,
        "recommendations": recommendations,
        "period": {"start": start_date, "end": end_date},
        "is_onboarding": False,
    }
