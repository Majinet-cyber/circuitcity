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
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
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


def _business_kind(business) -> str:
    return (getattr(business, "business_kind", None) or getattr(business, "kind", None) or "").lower()


def _exclusive_end(end: date) -> date:
    return end + timedelta(days=1)


def _clothing_metrics(business, start: date, end: date) -> dict:
    """
    Reuse the clothing dashboard's own metric helpers so Business Health matches
    the vertical dashboard numbers for revenue, profit, costs, and stock value.
    """
    from inventory.verticals import base as vertical_base

    sales = vertical_base.clothing_sales_metrics(
        business,
        start_date=start,
        end_date=_exclusive_end(end),
    )
    inventory = vertical_base.clothing_inventory_metrics(business)
    days = sum(1 for row in sales.get("sales_trend", []) if row.get("count", 0) > 0)

    return {
        "revenue": sales.get("revenue") or Decimal("0"),
        "cost": sales.get("cost_of_goods") or Decimal("0"),
        "overhead_costs": sales.get("overhead_costs") or Decimal("0"),
        "profit": sales.get("profit") or Decimal("0"),
        "count": sales.get("total_sales") or 0,
        "days": days,
        "stock_value": inventory.get("inventory_value") or Decimal("0"),
        "retail_value": inventory.get("retail_value") or Decimal("0"),
        "expected_margin": inventory.get("expected_margin") or Decimal("0"),
        "sales_trend": sales.get("sales_trend") or [],
    }


def _sales_totals(business, start: date, end: date) -> dict:
    """
    Return business-scoped sales totals from the canonical Sale table when
    available, falling back to sold InventoryItem rows.
    """
    if _business_kind(business) == "clothing":
        try:
            metrics = _clothing_metrics(business, start, end)
            return {
                "revenue": metrics["revenue"],
                "cost": metrics["cost"] + metrics["overhead_costs"],
                "count": metrics["count"],
                "days": metrics["days"],
            }
        except Exception as exc:
            logger.warning("clothing health sales metrics failed: %s", exc)

    try:
        from sales.models import Sale

        sales = Sale.objects.filter(
            location__business=business,
            sold_at__gte=start,
            sold_at__lte=end,
            is_rolled_back=False,
        ).select_related("item")
        if sales.exists():
            rows = list(sales)
            revenue = sum((row.price or Decimal("0")) for row in rows)
            cost = sum((getattr(row.item, "order_price", None) or Decimal("0")) for row in rows)
            days = len({row.sold_at for row in rows if row.sold_at})
            return {"revenue": revenue, "cost": cost, "count": len(rows), "days": days}
    except Exception:
        pass

    try:
        from inventory.models import InventoryItem
        from django.db.models import Count, Sum
        from django.db.models.functions import TruncDate

        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
            selling_price__isnull=False,
        )
        agg = qs.aggregate(revenue=Sum("selling_price"), cost=Sum("order_price"), count=Count("id"))
        days = qs.annotate(day=TruncDate("sold_at")).values("day").distinct().count()
        return {
            "revenue": agg.get("revenue") or Decimal("0"),
            "cost": agg.get("cost") or Decimal("0"),
            "count": agg.get("count") or 0,
            "days": days,
        }
    except Exception:
        return {"revenue": Decimal("0"), "cost": Decimal("0"), "count": 0, "days": 0}


def _monthly_recurring_costs(business) -> Decimal:
    try:
        from inventory.models import RecurringCost

        total = Decimal("0")
        for cost in RecurringCost.objects.filter(business=business, is_active=True):
            amount = cost.amount or Decimal("0")
            if cost.frequency == "weekly":
                total += amount * Decimal("4.33")
            elif cost.frequency == "quarterly":
                total += amount / Decimal("3")
            elif cost.frequency == "annually":
                total += amount / Decimal("12")
            else:
                total += amount
        return total
    except Exception:
        return Decimal("0")


def _business_has_older_data(business, start: date) -> bool:
    """True when useful business data exists before the current scoring window."""
    if _business_kind(business) == "clothing":
        try:
            from inventory.models import MerchProduct
            from inventory.models_clothing_barcode import ClothingBarcodeUnit
            from inventory.models_verticals import ClothingSale

            return (
                ClothingSale.objects.filter(business=business).exists()
                or MerchProduct.objects.filter(
                    business=business,
                    kind="clothing",
                    is_active=True,
                    is_archived=False,
                    quantity_in_stock__gt=0,
                ).exists()
                or ClothingBarcodeUnit.objects.filter(
                    business=business,
                    is_active=True,
                    status="IN_STOCK",
                ).exists()
            )
        except Exception:
            pass

    try:
        from sales.models import Sale

        if Sale.objects.filter(
            location__business=business,
            sold_at__lt=start,
            is_rolled_back=False,
        ).exists():
            return True
    except Exception:
        pass

    try:
        from inventory.models import InventoryItem, RecurringCost

        if InventoryItem.objects.filter(business=business, is_active=True).exists():
            return True
        if InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__lt=start,
            selling_price__isnull=False,
        ).exists():
            return True
        if RecurringCost.objects.filter(business=business, is_active=True).exists():
            return True
    except Exception:
        pass

    return False


def _cfo_expense_total(business, start: date, end: date) -> Decimal:
    """
    Include CFO expenses only when they can be scoped to the active business.
    Some installations store branch as free text, so avoid global aggregation.
    """
    try:
        from django.apps import apps

        if not apps.is_installed("cfo"):
            return Decimal("0")

        Expense = apps.get_model("cfo", "Expense")
        qs = Expense.objects.filter(date__gte=start, date__lte=end)
        branch_field = Expense._meta.get_field("branch")

        if getattr(branch_field, "remote_field", None) and branch_field.remote_field:
            related_model = branch_field.remote_field.model
            related_fields = {field.name for field in related_model._meta.get_fields()}
            if "business" in related_fields:
                qs = qs.filter(branch__business=business)
            else:
                return Decimal("0")
        else:
            branch_values = [str(business.pk), getattr(business, "slug", ""), getattr(business, "name", "")]
            branch_values = [value for value in branch_values if value]
            if not branch_values:
                return Decimal("0")
            qs = qs.filter(branch__in=branch_values)

        from django.db.models import Sum

        return qs.aggregate(total=Sum("amount")).get("total") or Decimal("0")
    except Exception:
        return Decimal("0")


def _summary_cards(business, start: date, end: date) -> list[dict]:
    """Small business-scoped facts for the health page header cards."""
    if _business_kind(business) == "clothing":
        metrics = _clothing_metrics(business, start, end)
        revenue = metrics["revenue"]
        gross_profit = metrics["profit"]
        recurring = metrics["cost"] + metrics["overhead_costs"]
        cost_label = "Costs"
        cost_detail = "Cost of goods plus overheads"
        stock_value = metrics["stock_value"]
        sales_count = metrics["count"]
        stock_count = 0
        try:
            from inventory.models import MerchProduct
            from inventory.models_clothing_barcode import ClothingBarcodeUnit
            common_units = (
                MerchProduct.objects.filter(
                    business=business,
                    kind="clothing",
                    is_active=True,
                    is_archived=False,
                    quantity_in_stock__gt=0,
                ).aggregate(total=Sum("quantity_in_stock")).get("total") or 0
            )
            tracked_units = ClothingBarcodeUnit.objects.filter(
                business=business,
                is_active=True,
                status="IN_STOCK",
            ).count()
            stock_count = int(common_units or 0) + tracked_units
        except Exception:
            pass
        revenue_delta = None
    else:
        sales = _sales_totals(business, start, end)
        sales_count = sales["count"]
        prior_days = max((end - start).days, 1)
        prior_start = start - timedelta(days=prior_days)
        prior_end = start - timedelta(days=1)
        prior_sales = _sales_totals(business, prior_start, prior_end)

        revenue = sales["revenue"]
        gross_profit = revenue - sales["cost"]
        prior_revenue = prior_sales["revenue"]
        revenue_delta = None
        if prior_revenue > 0:
            revenue_delta = float((revenue - prior_revenue) / prior_revenue * 100)

        stock_count = 0
        stock_value = Decimal("0")
        try:
            from inventory.models import InventoryItem
            stock = InventoryItem.objects.filter(business=business, is_active=True, status="IN_STOCK")
            stock_count = stock.count()
            stock_value = sum((item.order_price or Decimal("0")) for item in stock.only("order_price"))
        except Exception:
            pass

        recurring = _monthly_recurring_costs(business)
        cost_label = "Recurring Costs"
        cost_detail = "Estimated monthly obligations"

    return [
        {
            "label": "Revenue",
            "value": f"MWK {revenue:,.0f}",
            "detail": (
                f"{revenue_delta:+.0f}% vs prior period"
                if revenue_delta is not None
                else f"{sales_count} sales in period"
            ),
            "icon": "bi-cash-stack",
        },
        {
            "label": "Profit",
            "value": f"MWK {gross_profit:,.0f}",
            "detail": "Revenue less cost of goods and overheads",
            "icon": "bi-graph-up-arrow",
        },
        {
            "label": "Stock On Hand",
            "value": f"{stock_count:,} units",
            "detail": f"MWK {stock_value:,.0f} at cost",
            "icon": "bi-box-seam",
        },
        {
            "label": cost_label,
            "value": f"MWK {recurring:,.0f}",
            "detail": cost_detail,
            "icon": "bi-calendar2-week",
        },
    ]


# ---------------------------------------------------------------------------
# Individual component scorers
# ---------------------------------------------------------------------------

def _score_profit_trend(business, start: date, end: date) -> dict:
    """
    Score based on whether gross profit margin is positive and trending.
    Uses InventoryItem sold records scoped to the business.
    """
    try:
        totals = _sales_totals(business, start, end)
        revenue = totals["revenue"]
        cost = totals["cost"]

        if revenue <= 0:
            return _null_component("No sales recorded in this period. Record your first sale to see profit trend.")

        margin_pct = float((revenue - cost) / revenue * 100)

        # Check if improving vs prior period
        days = (end - start).days or 1
        prior_start = start - timedelta(days=days)
        prior_end = start - timedelta(days=1)

        prior_totals = _sales_totals(business, prior_start, prior_end)
        prior_rev = prior_totals["revenue"]
        prior_cost = prior_totals["cost"]
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
        totals = _sales_totals(business, start, end)
        revenue = totals["revenue"]
        count = totals["count"]

        if count == 0:
            return _null_component(
                "No sales in this period. Cash flow cannot be assessed without recorded revenue."
            )

        days_active = totals["days"]

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
    if _business_kind(business) == "clothing":
        try:
            metrics = _clothing_metrics(business, timezone.localdate().replace(day=1), timezone.localdate())
            from inventory.models import MerchProduct
            from inventory.models_clothing_barcode import ClothingBarcodeUnit

            common_units = (
                MerchProduct.objects.filter(
                    business=business,
                    kind="clothing",
                    is_active=True,
                    is_archived=False,
                    quantity_in_stock__gt=0,
                ).aggregate(total=Sum("quantity_in_stock")).get("total") or 0
            )
            tracked_units = ClothingBarcodeUnit.objects.filter(
                business=business,
                is_active=True,
                status="IN_STOCK",
            ).count()
            units = int(common_units or 0) + tracked_units
            stock_value = metrics["stock_value"]

            if units == 0 and stock_value <= 0:
                return _null_component("No active clothing stock found. Add inventory to see stock health.")

            low_stock_count = MerchProduct.objects.filter(
                business=business,
                kind="clothing",
                is_active=True,
                is_archived=False,
                quantity_in_stock__gt=0,
                quantity_in_stock__lte=5,
            ).count()

            score = 88
            if low_stock_count:
                score = max(45, score - min(35, low_stock_count * 4))
            if metrics["revenue"] > 0 and stock_value > 0:
                stock_cover = float(stock_value / metrics["revenue"])
                if stock_cover < 0.5:
                    score = min(score, 58)
                elif stock_cover > 8:
                    score = min(score, 68)

            thresholds = ((80, "Healthy"), (65, "Good"), (50, "Watch"), (35, "At Risk"), (0, "Critical"))
            return {
                "score": score,
                "label": _component_label(score, thresholds),
                "explanation": (
                    f"Current clothing stock value is {float(stock_value):,.0f} MWK across {units:,} units. "
                    + (f"{low_stock_count} product lines are low on stock." if low_stock_count else "No low-stock pressure detected.")
                ),
            }
        except Exception as exc:
            logger.warning("clothing stock scorer error: %s", exc)

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
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        import statistics

        if _business_kind(business) == "clothing":
            from inventory.models_verticals import ClothingSale
            daily_counts = list(
                ClothingSale.objects.filter(
                    business=business,
                    sold_at__gte=timezone.make_aware(datetime.combine(start, datetime.min.time())),
                    sold_at__lt=timezone.make_aware(datetime.combine(_exclusive_end(end), datetime.min.time())),
                )
                .annotate(day=TruncDate("sold_at"))
                .values("day")
                .annotate(cnt=Count("id"))
                .values_list("cnt", flat=True)
            )
        else:
            try:
                from sales.models import Sale
                sale_qs = Sale.objects.filter(
                    location__business=business,
                    sold_at__gte=start,
                    sold_at__lte=end,
                    is_rolled_back=False,
                )
                if sale_qs.exists():
                    daily_counts = list(
                        sale_qs.values("sold_at").annotate(cnt=Count("id")).values_list("cnt", flat=True)
                    )
                else:
                    raise ValueError("no Sale rows")
            except Exception:
                from inventory.models import InventoryItem
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
        if _business_kind(business) == "clothing":
            metrics = _clothing_metrics(business, start, end)
            revenue = float(metrics["revenue"] or 0)
            total_expenses = float(metrics["overhead_costs"] or 0)
            if revenue <= 0 and total_expenses <= 0:
                return _null_component("No clothing revenue or cost data found for this period.")
            if revenue <= 0:
                return {
                    "score": 40,
                    "label": "Unbenchmarked",
                    "explanation": f"Costs are about {total_expenses:,.0f} MWK, but no revenue was found.",
                }
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
                score = 25

            thresholds = ((80, "Lean"), (65, "Controlled"), (50, "Moderate"), (35, "High"), (0, "Excessive"))
            return {
                "score": score,
                "label": _component_label(score, thresholds),
                "explanation": (
                    f"Dashboard overhead costs are {total_expenses:,.0f} MWK against "
                    f"{revenue:,.0f} MWK revenue ({expense_ratio:.0%})."
                ),
            }

        revenue = float(_sales_totals(business, start, end)["revenue"] or 0)
        recurring_monthly = float(_monthly_recurring_costs(business) or 0)

        if revenue <= 0 and recurring_monthly <= 0:
            return _null_component("No revenue or recurring-cost data to compare against expenses.")

        total_expenses = float(_cfo_expense_total(business, start, end))

        period_months = max((end - start).days + 1, 1) / 30
        total_expenses += recurring_monthly * period_months

        if total_expenses == 0:
            return _null_component(
                "No expense records found. Start recording expenses to see your expense control score."
            )

        if revenue <= 0:
            return {
                "score": 40,
                "label": "Unbenchmarked",
                "explanation": f"Recurring costs are about {total_expenses:,.0f} MWK for this period, but no revenue was found.",
            }

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
        total_sold = _sales_totals(business, start, end)["count"]

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
    _allow_extended_period: bool = True,
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
        start_date = today.replace(day=1)

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
        if _allow_extended_period and _business_has_older_data(business, start_date):
            business_created = getattr(business, "created_at", None)
            created_date = business_created.date() if business_created else today - timedelta(days=365)
            wide_start = min(today - timedelta(days=365), created_date)
            if wide_start < start_date:
                result = calculate_business_health_score(
                    business,
                    start_date=wide_start,
                    end_date=end_date,
                    _allow_extended_period=False,
                )
                result["used_extended_period"] = True
                return result

        # Truly new business: nothing useful exists to score yet.
        name = getattr(business, "name", "Your business")
        return {
            "score": None,
            "label": "No data yet",
            "status_color": "gray",
            "grade": "N/A",
            "risk_level": "Unknown",
            "components": components,
            "recommendations": [
                "Record your first sales to start tracking profit trend.",
                "Add your stock/inventory to see stock risk.",
                "Enable WhatsApp alerts to get daily summaries.",
            ],
            "top_problems": [],
            "top_actions": [
                "Record your first sales to start tracking profit trend.",
                "Add your stock/inventory to see stock risk.",
            ],
            "weekly_mission": f"This week's mission: record your first sale and add your stock — unlock {name}'s real score.",
            "encouraging_summary": f"{name} is just getting started. Record your first sale and add inventory to unlock your Business Health Score.",
            "period": {"start": start_date, "end": end_date},
            "is_onboarding": True,
            "used_extended_period": False,
            "summary_cards": _summary_cards(business, start_date, end_date),
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
            "Profit is below target — review your pricing and identify your highest-cost items. "
            "Every margin point counts."
        )

    cash = components.get("cash_flow", {})
    if cash.get("score") is not None and cash["score"] < 60:
        recommendations.append(
            "Cash inflow is irregular. Try selling daily in shorter sessions to smooth your revenue stream."
        )

    stock = components.get("stock_risk", {})
    if stock.get("score") is not None and stock["score"] < 60:
        recommendations.append(
            "Restock fast-moving items now — before a stockout costs you a sale you can't recover."
        )

    consistency = components.get("sales_consistency", {})
    if consistency.get("score") is not None and consistency["score"] < 60:
        recommendations.append(
            "Sales are patchy. A WhatsApp promotion on your quietest day could shift the pattern fast."
        )

    expense = components.get("expense_control", {})
    if expense.get("score") is not None and expense["score"] < 60:
        recommendations.append(
            "Expenses are climbing faster than sales. Pin down the biggest cost category and challenge it."
        )

    credit = components.get("credit_exposure", {})
    if credit.get("score") is not None and credit["score"] < 60:
        recommendations.append(
            "Customers owe you money. Follow up today — even a partial collection improves your cash position."
        )

    if not recommendations:
        if overall_score >= 85:
            recommendations.append(
                "Your business is in excellent health. The engine is running — now focus on scaling."
            )
        elif overall_score >= 70:
            recommendations.append(
                "You're in good shape. Find your weakest component above and make it your next target."
            )
        else:
            recommendations.append(
                "Consistency is your superpower right now — record every sale and expense daily to climb the score."
            )

    # Vertical-aware extras
    kind = _business_kind(business)
    vertical_components = _vertical_extra_components(business, kind, start_date, end_date)
    if vertical_components:
        components.update(vertical_components)

    grade = _grade_from_score(overall_score)
    risk_level = _risk_level(overall_score)
    top_problems = _extract_top_problems(components)
    top_actions = recommendations[:3]
    weekly_mission = _weekly_mission(kind, components, overall_score, business)
    encouraging_summary = _encouraging_summary(kind, overall_score, label, business)

    return {
        "score": overall_score,
        "label": label,
        "grade": grade,
        "risk_level": risk_level,
        "status_color": status_color,
        "components": components,
        "recommendations": recommendations,
        "top_problems": top_problems,
        "top_actions": top_actions,
        "weekly_mission": weekly_mission,
        "encouraging_summary": encouraging_summary,
        "period": {"start": start_date, "end": end_date},
        "is_onboarding": False,
        "used_extended_period": not _allow_extended_period,
        "summary_cards": _summary_cards(business, start_date, end_date),
    }


# ---------------------------------------------------------------------------
# Vertical-aware extra helpers  (Phase 8)
# ---------------------------------------------------------------------------

def _grade_from_score(score: Optional[int]) -> str:
    if score is None:
        return "N/A"
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _risk_level(score: Optional[int]) -> str:
    if score is None:
        return "Unknown"
    if score >= 70:
        return "Low"
    if score >= 50:
        return "Medium"
    if score >= 35:
        return "High"
    return "Critical"


def _extract_top_problems(components: dict) -> list[str]:
    """Return up to 3 component names / descriptions with the lowest scores."""
    scored = [
        (key, c.get("score", 100), c.get("explanation", ""))
        for key, c in components.items()
        if c.get("score") is not None
    ]
    scored.sort(key=lambda x: x[1])
    problems = []
    for key, score, explanation in scored[:3]:
        if score < 70:
            label = key.replace("_", " ").title()
            problems.append(f"{label} ({score}/100): {explanation[:100]}")
    return problems


def _weekly_mission(kind: str, components: dict, score: int, business) -> str:
    """Generate a short, actionable weekly mission based on business kind and score."""
    if kind == "mixed_retail":
        stock = components.get("stock_risk", {}).get("score")
        if stock is not None and stock < 60:
            return "This week's mission: restock your 3 lowest-stock items before they run out."
        credit = components.get("credit_exposure", {}).get("score")
        if credit is not None and credit < 60:
            return "This week's mission: follow up with at least 2 credit customers and collect partial payments."
        if score < 70:
            return "This week's mission: record every sale and expense — accuracy unlocks your real score."
        return "This week's mission: list your top 5 products by margin and push sales for the highest two."

    if kind == "mobile_money":
        if score < 60:
            return "This week's mission: close every day with a reconciliation — even a partial one counts."
        return "This week's mission: compare commission earnings to last week and identify your busiest transaction type."

    if kind == "consultancy":
        credit = components.get("credit_exposure", {}).get("score")
        if credit is not None and credit < 60:
            return "This week's mission: send payment reminders to all overdue invoice clients."
        if score < 70:
            return "This week's mission: invoice any unbilled project work from the past 30 days."
        return "This week's mission: reach out to your best client and explore a retainer arrangement."

    if kind == "farm":
        mortality = components.get("farm_mortality", {}).get("score")
        if mortality is not None and mortality < 50:
            return "This week's mission: investigate high mortality — check feed, water, and disease signs."
        feed = components.get("farm_feed_pressure", {}).get("score")
        if feed is not None and feed < 60:
            return "This week's mission: record all feed expenses and check remaining feed stock."
        if score < 70:
            return "This week's mission: update your livestock counts and record any missing expense entries."
        return "This week's mission: publish your best livestock batch to the marketplace."

    if kind == "clothing":
        stock = components.get("stock_risk", {}).get("score")
        if stock is not None and stock < 50:
            return "This week's mission: restock your 3 lowest-stock categories before a sale opportunity is lost."
        margin = components.get("clothing_margin_health", {}).get("score")
        if margin is not None and margin < 60:
            return "This week's mission: review your selling prices — some items may be priced below margin."
        if score < 70:
            return "This week's mission: record at least 5 sales and check your inventory accuracy."
        return "This week's mission: identify your top 3 selling categories and double down on them."

    # Generic
    if score >= 80:
        return "This week's mission: identify one growth opportunity and make your first move."
    if score < 50:
        return "This week's mission: record at least one sale per day and log your top expense category."
    return "This week's mission: review your slowest-moving products and consider a small promotion."


def _encouraging_summary(kind: str, score: int, label: str, business) -> str:
    name = getattr(business, "name", "Your business")
    if kind == "mixed_retail":
        if score >= 80:
            return f"{name} is running strong. Stock is moving, margins are healthy, and cash is flowing."
        if score >= 60:
            return f"{name} has a solid foundation. A few quick wins on stock and credit will push you higher."
        return f"{name} has room to grow. Focus on restocking fast-moving items and following up credit sales."

    if kind == "mobile_money":
        if score >= 80:
            return f"{name} is a model agent. Float is balanced, reconciliation is tight, and commission is growing."
        if score >= 60:
            return f"{name} is doing well. Tighten your daily close and keep an eye on float health."
        return f"{name} needs stronger daily habits. A consistent daily close will dramatically improve your score."

    if kind == "consultancy":
        if score >= 80:
            return f"{name} is in excellent shape. Clients are paying, projects are moving, and revenue is consistent."
        if score >= 60:
            return f"{name} is solid. Clear overdue invoices and your score will jump quickly."
        return f"{name} needs attention on unpaid invoices. Invoice all completed work and follow up regularly."

    if kind == "farm":
        if score >= 85:
            return f"{name} is thriving. The livestock is healthy, books are clean, and profit is flowing. Keep this momentum."
        if score >= 70:
            return f"{name} is breathing well. Keep mortality low and record every expense to maintain momentum."
        if score >= 50:
            return f"{name} has healthy stock, but profit needs attention. Watch your feed costs and record every sale."
        return f"Act now — high mortality is damaging {name}'s score before costs mount and losses compound."

    if kind == "clothing":
        if score >= 85:
            return f"{name} is your best season yet. Stock is healthy, sales are flowing, and margins are strong."
        if score >= 70:
            return f"{name} is doing well. Push harder on your best categories to keep the momentum."
        if score >= 50:
            return f"{name} has strong cash, but expenses are rising. Check your margins and restock your fast movers."
        return f"{name} needs attention on stock and margin. Record all sales and review pricing on slow-moving items."

    # Generic
    if score >= 80:
        return f"{name} scored {score}/100 — excellent. Keep your momentum going."
    if score >= 60:
        return f"{name} scored {score}/100 — good shape. Target your weakest area this week."
    return f"{name} scored {score}/100 — room to improve. Consistent recording is your first step."


def _vertical_extra_components(business, kind: str, start: date, end: date) -> dict:
    """Add vertical-specific health components to the standard components dict."""
    extra: dict = {}
    try:
        if kind == "mixed_retail":
            extra.update(_mixed_retail_health_components(business, start, end))
        elif kind == "mobile_money":
            extra.update(_mobile_money_health_components(business, start, end))
        elif kind == "consultancy":
            extra.update(_consultancy_health_components(business, start, end))
        elif kind == "farm":
            extra.update(_farm_health_components(business, start, end))
        elif kind == "clothing":
            extra.update(_clothing_health_components(business, start, end))
    except Exception as exc:
        logger.warning("vertical extra components failed (%s): %s", kind, exc)
    return extra


def _mixed_retail_health_components(business, start: date, end: date) -> dict:
    """Health components specific to Mixed Retail."""
    components: dict = {}
    try:
        from inventory.models_mixed_retail import RetailProduct, RetailSale, RetailExpense
        from django.db.models import F, ExpressionWrapper, DecimalField as Dec

        products_qs = RetailProduct.objects.filter(business=business, is_active=True)
        total = products_qs.count()

        # Stock movement: ratio of products with recent sales vs total
        if total > 0:
            sold_product_ids = set(
                RetailSale.objects.filter(
                    business=business, is_rolled_back=False,
                    sold_at__date__gte=start, sold_at__date__lte=end,
                ).values_list("product_id", flat=True)
            )
            movement_pct = len(sold_product_ids) / total * 100
            if movement_pct >= 50:
                mv_score = 90
            elif movement_pct >= 30:
                mv_score = 70
            elif movement_pct >= 15:
                mv_score = 50
            elif movement_pct > 0:
                mv_score = 35
            else:
                mv_score = 10
            components["stock_movement"] = {
                "score": mv_score,
                "label": _component_label(mv_score, ((80, "Active"), (60, "Good"), (40, "Slow"), (0, "Dead Stock Risk"))),
                "explanation": f"{len(sold_product_ids)}/{total} products sold in this period ({movement_pct:.0f}%).",
            }

            # Dead stock: products with zero sales in past 30 days
            dead_count = total - len(sold_product_ids)
            dead_pct = dead_count / total * 100
            if dead_pct <= 10:
                ds_score = 90
            elif dead_pct <= 25:
                ds_score = 70
            elif dead_pct <= 50:
                ds_score = 50
            else:
                ds_score = 20
            components["dead_stock"] = {
                "score": ds_score,
                "label": _component_label(ds_score, ((80, "Healthy"), (60, "Manageable"), (40, "Concerning"), (0, "Critical"))),
                "explanation": f"{dead_count} products ({dead_pct:.0f}%) had no sales this period.",
            }

        # Category concentration risk
        from django.db.models import Sum as DSum
        from inventory.models_mixed_retail import RetailSale
        _DEC2 = DecimalField(max_digits=16, decimal_places=2)
        dept_breakdown = (
            RetailSale.objects.filter(
                business=business, is_rolled_back=False,
                sold_at__date__gte=start, sold_at__date__lte=end,
            )
            .values("product__department__name")
            .annotate(total=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC2))
            .order_by("-total")
        )
        if dept_breakdown:
            totals = [float(d["total"]) for d in dept_breakdown]
            grand_total = sum(totals)
            if grand_total > 0 and len(totals) > 1:
                top_pct = totals[0] / grand_total * 100
                if top_pct <= 50:
                    cc_score = 90
                elif top_pct <= 70:
                    cc_score = 65
                elif top_pct <= 85:
                    cc_score = 45
                else:
                    cc_score = 25
                dept_name = list(dept_breakdown)[0].get("product__department__name") or "one department"
                components["category_concentration"] = {
                    "score": cc_score,
                    "label": _component_label(cc_score, ((80, "Diversified"), (55, "Moderate"), (0, "Concentrated"))),
                    "explanation": f"{top_pct:.0f}% of sales from {dept_name}. Diversification reduces risk.",
                }
    except Exception as exc:
        logger.debug("mixed retail health components failed: %s", exc)
    return components


def _mobile_money_health_components(business, start: date, end: date) -> dict:
    """Health components specific to Mobile Money Agent."""
    components: dict = {}
    try:
        from inventory.models_mobilemoney import (
            MobileMoneyReconciliation,
            MobileMoneyTransaction,
            MobileMoneyTxType,
        )
        _DEC2 = DecimalField(max_digits=14, decimal_places=2)

        # Reconciliation discipline: days reconciled vs days in period
        days_in_period = (end - start).days + 1
        reconciled_days = MobileMoneyReconciliation.objects.filter(
            business=business,
            recon_date__gte=start,
            recon_date__lte=end,
        ).values("recon_date").distinct().count()

        if days_in_period > 0:
            recon_pct = reconciled_days / days_in_period * 100
            if recon_pct >= 80:
                rc_score = 95
            elif recon_pct >= 60:
                rc_score = 75
            elif recon_pct >= 40:
                rc_score = 55
            elif recon_pct > 0:
                rc_score = 35
            else:
                rc_score = 0
            components["reconciliation_discipline"] = {
                "score": rc_score,
                "label": _component_label(rc_score, ((80, "Excellent"), (60, "Good"), (40, "Fair"), (0, "Poor"))),
                "explanation": f"Reconciled {reconciled_days}/{days_in_period} days ({recon_pct:.0f}%).",
            }

        # Float health: positive float balance
        tx_qs = MobileMoneyTransaction.objects.filter(
            business=business,
            tx_date__gte=start,
            tx_date__lte=end,
        )
        float_balance = Decimal(str(
            tx_qs.aggregate(
                total=Coalesce(Sum("float_movement"), Value(0), output_field=_DEC2)
            )["total"] or 0
        ))
        if float_balance > 10000:
            fh_score = 90
        elif float_balance > 0:
            fh_score = 65
        elif float_balance == 0 and tx_qs.count() == 0:
            fh_score = None
        else:
            fh_score = 30

        if fh_score is not None:
            components["float_health"] = {
                "score": fh_score,
                "label": _component_label(fh_score, ((80, "Strong"), (60, "Fair"), (0, "Low/Negative"))),
                "explanation": f"Current float position: MWK {float_balance:,.0f}.",
            }

        # Provider concentration risk
        provider_breakdown = (
            tx_qs.values("network")
            .annotate(cnt=Sum("amount"))
            .order_by("-cnt")
        )
        if provider_breakdown:
            cnts = [float(d["cnt"] or 0) for d in provider_breakdown]
            grand = sum(cnts)
            if grand > 0 and len(cnts) > 1:
                top_pct = cnts[0] / grand * 100
                pc_score = 90 if top_pct <= 60 else (65 if top_pct <= 80 else 40)
                components["provider_concentration"] = {
                    "score": pc_score,
                    "label": _component_label(pc_score, ((80, "Diversified"), (55, "Moderate"), (0, "Single Provider"))),
                    "explanation": f"{top_pct:.0f}% of volume from one provider. Multi-provider reduces risk.",
                }

    except Exception as exc:
        logger.debug("mobile money health components failed: %s", exc)
    return components


def _consultancy_health_components(business, start: date, end: date) -> dict:
    """Health components specific to Consultancy & Services."""
    components: dict = {}
    try:
        from inventory.models_consultancy import (
            ConsultancyClient,
            ConsultancyInvoice,
            ConsultancyProject,
            ConsultancyPayment,
        )
        from django.utils import timezone as tz
        today = tz.localdate()
        _DEC2 = DecimalField(max_digits=14, decimal_places=2)

        invoices_qs = ConsultancyInvoice.objects.filter(business=business, is_void=False)

        # Unpaid invoice ratio
        all_invoices = invoices_qs.count()
        if all_invoices > 0:
            overdue_count = invoices_qs.filter(
                status__in=["overdue", "sent", "partial"],
                due_date__lt=today,
            ).count() + invoices_qs.filter(status="overdue").count()
            overdue_count = min(overdue_count, all_invoices)
            overdue_pct = overdue_count / all_invoices * 100
            if overdue_pct == 0:
                ui_score = 100
            elif overdue_pct <= 10:
                ui_score = 80
            elif overdue_pct <= 25:
                ui_score = 60
            elif overdue_pct <= 50:
                ui_score = 40
            else:
                ui_score = 20
            components["invoice_health"] = {
                "score": ui_score,
                "label": _component_label(ui_score, ((90, "Excellent"), (70, "Good"), (50, "Fair"), (0, "Poor"))),
                "explanation": f"{overdue_count}/{all_invoices} invoices overdue or unpaid ({overdue_pct:.0f}%).",
            }

        # Client concentration risk
        client_revenue = (
            invoices_qs.filter(
                issued_at__date__gte=start,
                issued_at__date__lte=end,
            )
            .values("client_id", "client__name")
            .annotate(total=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC2))
            .order_by("-total")
        )
        if client_revenue:
            revenues = [float(c["total"]) for c in client_revenue]
            grand_total = sum(revenues)
            if grand_total > 0 and len(revenues) > 1:
                top_pct = revenues[0] / grand_total * 100
                cc_score = 90 if top_pct <= 40 else (65 if top_pct <= 60 else 40 if top_pct <= 80 else 20)
                top_client = list(client_revenue)[0].get("client__name", "one client")
                components["client_concentration"] = {
                    "score": cc_score,
                    "label": _component_label(cc_score, ((80, "Well-spread"), (55, "Moderate"), (0, "Concentrated"))),
                    "explanation": f"{top_pct:.0f}% of revenue from {top_client}. Reducing dependency reduces risk.",
                }

        # Delivery performance: delivered vs total active/closed projects
        projects_qs = ConsultancyProject.objects.filter(
            business=business,
            is_active=True,
        )
        active_count = projects_qs.count()
        if active_count > 0:
            overdue_projects = sum(1 for p in projects_qs if p.is_overdue)
            overdue_proj_pct = overdue_projects / active_count * 100
            if overdue_proj_pct == 0:
                dp_score = 95
            elif overdue_proj_pct <= 10:
                dp_score = 75
            elif overdue_proj_pct <= 25:
                dp_score = 55
            else:
                dp_score = 30
            components["delivery_health"] = {
                "score": dp_score,
                "label": _component_label(dp_score, ((80, "On Track"), (60, "Mostly On Time"), (0, "Delays Detected"))),
                "explanation": f"{overdue_projects}/{active_count} projects overdue ({overdue_proj_pct:.0f}%).",
            }

    except Exception as exc:
        logger.debug("consultancy health components failed: %s", exc)
    return components


# ---------------------------------------------------------------------------
# Farm Health Components  (Phase 9 — Farm vertical)
# ---------------------------------------------------------------------------

def _farm_health_components(business, start: date, end: date) -> dict:
    """Health components specific to the Farm vertical."""
    components: dict = {}
    try:
        from inventory.models_farm import (
            FarmLivestockBatch,
            FarmLivestockEvent,
            FarmLedgerEntry,
            FarmEntryType,
            FarmExpenseCategory,
        )
        from django.utils import timezone as tz
        today = tz.localdate()
        _DEC2 = DecimalField(max_digits=14, decimal_places=2)

        # ── Mortality risk ────────────────────────────────────────────
        batches = FarmLivestockBatch.objects.filter(business=business, is_active=True)
        total_current = sum(int(b.count_current or 0) for b in batches)
        total_deaths = 0
        for b in batches:
            total_deaths += (
                FarmLivestockEvent.objects.filter(
                    batch=b, event_type="death"
                ).aggregate(n=Sum("count"))["n"] or 0
            )

        # Estimate starting count as current + deaths (deaths reduce from starting)
        total_starting = total_current + total_deaths
        if total_starting > 0:
            mortality_pct = total_deaths / total_starting * 100
            if mortality_pct < 2:
                mort_score = 95
            elif mortality_pct < 5:
                mort_score = 80
            elif mortality_pct < 10:
                mort_score = 60
            elif mortality_pct < 20:
                mort_score = 35
            else:
                mort_score = 10
            components["farm_mortality"] = {
                "score": mort_score,
                "label": _component_label(
                    mort_score,
                    ((85, "Excellent"), (70, "Good"), (50, "Watch"), (30, "High Risk"), (0, "Critical")),
                ),
                "explanation": (
                    f"Overall mortality rate: {mortality_pct:.1f}% ({total_deaths} deaths from "
                    f"{total_starting} starting animals). "
                    + ("Mortality is low — well managed." if mort_score >= 80
                       else "Mortality is elevated. Investigate disease, feed, or housing issues.")
                ),
            }

        # ── Feed cost pressure ────────────────────────────────────────
        feed_cost = (
            FarmLedgerEntry.objects.filter(
                business=business,
                entry_type=FarmEntryType.EXPENSE,
                category=FarmExpenseCategory.FEED,
                date__gte=start,
                date__lte=end,
            ).aggregate(total=Coalesce(Sum("amount_mwk"), Value(0), output_field=_DEC2))["total"]
        ) or Decimal("0")

        total_expenses = (
            FarmLedgerEntry.objects.filter(
                business=business,
                entry_type=FarmEntryType.EXPENSE,
                date__gte=start,
                date__lte=end,
            ).aggregate(total=Coalesce(Sum("amount_mwk"), Value(0), output_field=_DEC2))["total"]
        ) or Decimal("0")

        if total_expenses > 0:
            feed_pct = float(feed_cost / total_expenses * 100)
            if feed_pct <= 40:
                fp_score = 85
            elif feed_pct <= 55:
                fp_score = 65
            elif feed_pct <= 70:
                fp_score = 45
            else:
                fp_score = 20
            components["farm_feed_pressure"] = {
                "score": fp_score,
                "label": _component_label(
                    fp_score,
                    ((80, "Balanced"), (60, "Manageable"), (40, "High"), (0, "Critical")),
                ),
                "explanation": (
                    f"Feed is {feed_pct:.0f}% of total farm expenses (MWK {feed_cost:,.0f}). "
                    + ("Feed costs are under control." if fp_score >= 65
                       else "Feed is consuming too much of the budget. Review bulk buying options.")
                ),
            }

        # ── Marketplace readiness ─────────────────────────────────────
        try:
            from inventory.models_marketplace import MarketplaceListing, ListingStatus
            live_count = MarketplaceListing.objects.filter(
                business=business, vertical="farm", status=ListingStatus.LIVE
            ).count()
            publishable = batches.filter(count_current__gt=0).count()
            if publishable > 0:
                pub_ratio = live_count / publishable
                if pub_ratio >= 0.5:
                    mr_score = 90
                elif pub_ratio >= 0.2:
                    mr_score = 65
                elif pub_ratio > 0:
                    mr_score = 40
                else:
                    mr_score = 20
                components["farm_marketplace_readiness"] = {
                    "score": mr_score,
                    "label": _component_label(
                        mr_score,
                        ((80, "Well Published"), (55, "Some Live"), (30, "Mostly Unlisted"), (0, "Not Listed")),
                    ),
                    "explanation": (
                        f"{live_count} of {publishable} publishable batches are live on the marketplace. "
                        + ("Great marketplace presence." if mr_score >= 65
                           else "Publish more batches to reach buyers and improve cash flow.")
                    ),
                }
        except Exception:
            pass

        # ── Crop yield intelligence ────────────────────────────────────
        try:
            from inventory.models_farm import FarmCropSeason, FarmSeasonStatus
            active_seasons = FarmCropSeason.objects.filter(
                business=business, status=FarmSeasonStatus.ACTIVE
            )
            seasons_with_yield = active_seasons.filter(projected_yield__isnull=False).count()
            total_seasons = active_seasons.count()
            if total_seasons > 0:
                completeness = seasons_with_yield / total_seasons * 100
                cy_score = 90 if completeness >= 80 else (65 if completeness >= 50 else 35)
                components["farm_crop_intelligence"] = {
                    "score": cy_score,
                    "label": _component_label(
                        cy_score,
                        ((80, "Well Tracked"), (55, "Partial"), (0, "Missing Data")),
                    ),
                    "explanation": (
                        f"{seasons_with_yield}/{total_seasons} active crop seasons have yield projections. "
                        + ("Crop records are complete." if cy_score >= 65
                           else "Add projected yields to unlock crop forecasts and profit planning.")
                    ),
                }
        except Exception:
            pass

    except Exception as exc:
        logger.debug("farm health components failed: %s", exc)
    return components


# ---------------------------------------------------------------------------
# Clothing Health Components  (Phase 9 — Clothing vertical)
# ---------------------------------------------------------------------------

def _clothing_health_components(business, start: date, end: date) -> dict:
    """Health components specific to the Clothing vertical."""
    components: dict = {}
    try:
        from inventory.models import MerchProduct
        from inventory.models_clothing_barcode import ClothingBarcodeUnit
        from inventory.models_verticals import ClothingSale
        _DEC2 = DecimalField(max_digits=14, decimal_places=2)

        # ── Margin health ─────────────────────────────────────────────
        products = MerchProduct.objects.filter(
            business=business, kind="clothing", is_active=True, is_archived=False
        )
        total = products.count()
        if total > 0:
            from django.db.models import F as _F
            low_margin = products.filter(
                cost_price__gt=0,
                selling_price__isnull=False,
            ).filter(
                selling_price__lt=_F("cost_price") * Decimal("1.1")
            ).count()
            margin_pct = (total - low_margin) / total * 100
            mh_score = 90 if margin_pct >= 90 else (70 if margin_pct >= 70 else 45 if margin_pct >= 50 else 20)
            components["clothing_margin_health"] = {
                "score": mh_score,
                "label": _component_label(
                    mh_score, ((80, "Healthy"), (60, "Fair"), (0, "At Risk"))
                ),
                "explanation": (
                    f"{low_margin} of {total} products ({100 - margin_pct:.0f}%) have thin or negative margins. "
                    + ("Margins look good." if mh_score >= 70
                       else "Review pricing on low-margin items to protect profitability.")
                ),
            }

        # ── Inventory accuracy ─────────────────────────────────────────
        total_in_stock = (
            products.filter(quantity_in_stock__gt=0)
            .aggregate(total=Coalesce(Sum("quantity_in_stock"), Value(0), output_field=_DEC2))["total"]
        ) or 0
        tracked_units = ClothingBarcodeUnit.objects.filter(
            business=business, is_active=True, status="IN_STOCK"
        ).count()
        combined_units = int(total_in_stock) + tracked_units

        if combined_units > 0:
            # Score based on recent sale activity vs stock on hand ratio
            recent_sales = ClothingSale.objects.filter(
                business=business,
                sold_at__date__gte=start,
                sold_at__date__lte=end,
            ).count()
            if recent_sales > 0:
                # Turnover ratio: >10% is healthy
                turnover_pct = min(100, recent_sales / combined_units * 100)
                ia_score = 90 if turnover_pct >= 20 else (70 if turnover_pct >= 10 else 50 if turnover_pct >= 5 else 30)
            else:
                ia_score = 25
            components["clothing_stock_turnover"] = {
                "score": ia_score,
                "label": _component_label(
                    ia_score, ((80, "Turning Fast"), (60, "Good"), (40, "Slow"), (0, "Stagnant"))
                ),
                "explanation": (
                    f"{recent_sales} units sold against {combined_units} units in stock this period. "
                    + ("Stock is moving well." if ia_score >= 70
                       else "Stock is not turning fast enough. Consider promotions or clearance pricing.")
                ),
            }

    except Exception as exc:
        logger.debug("clothing health components failed: %s", exc)
    return components


# ---------------------------------------------------------------------------
# Badges computation  (Phase 9 — used by view layer)
# ---------------------------------------------------------------------------

HEALTH_BADGES = {
    "books_balanced":  {"label": "Books Balanced",  "icon": "bi-journal-check",        "variant": "success"},
    "cash_strong":     {"label": "Cash Strong",     "icon": "bi-cash-stack",            "variant": "success"},
    "stock_healthy":   {"label": "Stock Healthy",   "icon": "bi-box-seam",              "variant": "info"},
    "profitable":      {"label": "Profitable",      "icon": "bi-graph-up-arrow",        "variant": "success"},
    "records_clean":   {"label": "Records Clean",   "icon": "bi-clipboard-check",       "variant": "info"},
    "sales_active":    {"label": "Sales Active",    "icon": "bi-lightning-charge-fill", "variant": "success"},
    "low_risk":        {"label": "Low Risk",        "icon": "bi-shield-check",          "variant": "success"},
    "high_mortality":  {"label": "High Mortality",  "icon": "bi-exclamation-triangle",  "variant": "danger"},
    "margins_at_risk": {"label": "Margins At Risk", "icon": "bi-exclamation-triangle",  "variant": "warning"},
    "missing_data":    {"label": "Missing Data",    "icon": "bi-database-x",            "variant": "secondary"},
}


def get_health_badges(health_result: dict) -> list[dict]:
    """
    Derive a list of earned badges from a calculate_business_health_score result.
    Returns list of {'key', 'label', 'icon', 'variant'} dicts.
    """
    badges = []
    score = health_result.get("score") or 0
    components = health_result.get("components") or {}

    def _score_ok(key, threshold=65):
        c = components.get(key)
        return c and c.get("score") is not None and c["score"] >= threshold

    null_count = sum(
        1 for c in components.values()
        if c.get("score") is None
    )

    # Profitable
    profit_comp = components.get("profit_trend")
    if profit_comp and profit_comp.get("score") is not None and profit_comp["score"] >= 60:
        badges.append({**HEALTH_BADGES["profitable"], "key": "profitable"})

    # Cash strong
    if _score_ok("cash_flow", 70):
        badges.append({**HEALTH_BADGES["cash_strong"], "key": "cash_strong"})

    # Stock healthy
    if _score_ok("stock_risk", 70):
        badges.append({**HEALTH_BADGES["stock_healthy"], "key": "stock_healthy"})

    # Sales active
    if _score_ok("sales_consistency", 65):
        badges.append({**HEALTH_BADGES["sales_active"], "key": "sales_active"})

    # Low risk (overall)
    if score >= 70:
        badges.append({**HEALTH_BADGES["low_risk"], "key": "low_risk"})

    # Records clean (low null components)
    if null_count == 0:
        badges.append({**HEALTH_BADGES["records_clean"], "key": "records_clean"})
    elif null_count >= 3:
        badges.append({**HEALTH_BADGES["missing_data"], "key": "missing_data"})

    # Farm-specific
    farm_mort = components.get("farm_mortality")
    if farm_mort and farm_mort.get("score") is not None:
        if farm_mort["score"] >= 80:
            badges.append({**HEALTH_BADGES["books_balanced"], "key": "books_balanced"})
        elif farm_mort["score"] < 40:
            badges.append({**HEALTH_BADGES["high_mortality"], "key": "high_mortality"})

    # Clothing-specific
    margin_comp = components.get("clothing_margin_health")
    if margin_comp and margin_comp.get("score") is not None and margin_comp["score"] < 50:
        badges.append({**HEALTH_BADGES["margins_at_risk"], "key": "margins_at_risk"})

    return badges
