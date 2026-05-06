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

from django.db.models import Sum
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
        "used_extended_period": not _allow_extended_period,
        "summary_cards": _summary_cards(business, start_date, end_date),
    }
