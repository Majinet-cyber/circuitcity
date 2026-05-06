"""
Business Credit Score service.

This score represents the business's creditworthiness for lender, supplier,
bank, investor, and partner review. It is business-scoped and never uses
customer-level credit as the primary subject.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

log = logging.getLogger(__name__)

WEIGHTS = {
    "revenue_consistency": 14,
    "profit_trend": 12,
    "cash_flow_stability": 12,
    "expense_control": 10,
    "stock_turnover": 10,
    "payment_discipline": 10,
    "recurring_obligations": 8,
    "debt_exposure": 8,
    "business_history": 6,
    "operational_activity": 6,
    "reporting_completeness": 4,
}


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def _empty_component(label: str, explanation: str) -> dict:
    return {"score": None, "label": label, "explanation": explanation}


def _label(score: int) -> tuple[str, str]:
    if score >= 85:
        return "Excellent", "green"
    if score >= 72:
        return "Good", "green"
    if score >= 58:
        return "Moderate", "amber"
    if score >= 42:
        return "Watchlist", "orange"
    return "High Risk", "red"


def _business_user_ids(business) -> list[int]:
    try:
        from tenants.models import Membership

        return list(
            Membership.objects.filter(business=business, status="ACTIVE")
            .values_list("user_id", flat=True)
        )
    except Exception:
        return []


def _sales_queryset(business, start: date, end: date):
    """Prefer canonical Sale rows; fall back to sold inventory rows."""
    try:
        from sales.models import Sale

        qs = Sale.objects.filter(
            location__business=business,
            sold_at__gte=start,
            sold_at__lte=end,
            is_rolled_back=False,
        ).select_related("item")
        if qs.exists():
            return "sale", qs
    except Exception as exc:
        log.debug("Sale queryset unavailable for credit score: %s", exc)

    try:
        from inventory.models import InventoryItem

        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
            selling_price__isnull=False,
        )
        return "inventory", qs
    except Exception as exc:
        log.debug("Inventory sales queryset unavailable for credit score: %s", exc)
        return "none", []


def _sales_totals(business, start: date, end: date) -> dict:
    source, qs = _sales_queryset(business, start, end)
    if source == "none":
        return {"source": source, "count": 0, "revenue": Decimal("0"), "cost": Decimal("0"), "days": 0}

    if source == "sale":
        rows = list(qs)
        revenue = sum((row.price or Decimal("0")) for row in rows)
        cost = sum((getattr(row.item, "order_price", None) or Decimal("0")) for row in rows)
        days = len({row.sold_at for row in rows if row.sold_at})
        return {"source": source, "count": len(rows), "revenue": revenue, "cost": cost, "days": days}

    agg = qs.aggregate(revenue=Sum("selling_price"), cost=Sum("order_price"), count=Count("id"))
    days = (
        qs.annotate(day=TruncDate("sold_at"))
        .values("day")
        .distinct()
        .count()
    )
    return {
        "source": source,
        "count": agg.get("count") or 0,
        "revenue": agg.get("revenue") or Decimal("0"),
        "cost": agg.get("cost") or Decimal("0"),
        "days": days,
    }


def _monthly_revenue_series(business, months: int = 6) -> list[float]:
    today = timezone.localdate()
    series = []
    for i in range(months - 1, -1, -1):
        month_anchor = (today.replace(day=1) - timedelta(days=i * 31)).replace(day=1)
        next_month = (month_anchor.replace(day=28) + timedelta(days=4)).replace(day=1)
        totals = _sales_totals(business, month_anchor, next_month - timedelta(days=1))
        series.append(float(totals["revenue"] or 0))
    return series


def _monthly_recurring_total(business) -> Decimal:
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


def _layby_orders(business, start: Optional[date] = None, end: Optional[date] = None):
    try:
        from layby.models import LaybyOrder

        qs = LaybyOrder.objects.all()
        user_ids = _business_user_ids(business)
        if user_ids:
            qs = qs.filter(created_by_id__in=user_ids)
        else:
            qs = qs.none()
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)
        return qs
    except Exception:
        return []


def _score_revenue_consistency(business) -> dict:
    series = _monthly_revenue_series(business)
    active = [v for v in series if v > 0]
    if len(active) < 2:
        return _empty_component("Limited history", "Need at least two revenue months to measure consistency.")

    avg = statistics.mean(active)
    if avg <= 0:
        return _empty_component("Limited history", "Revenue history is not yet usable.")
    cv = statistics.pstdev(active) / avg if len(active) > 1 else 0
    months_active = len(active)
    base = 95 if cv <= 0.2 else 82 if cv <= 0.4 else 68 if cv <= 0.65 else 50 if cv <= 1 else 35
    coverage_bonus = min(8, months_active)
    score = _clamp(base + coverage_bonus - 6)
    return {
        "score": score,
        "label": "Stable" if score >= 72 else "Variable" if score >= 50 else "Irregular",
        "explanation": f"Revenue appears in {months_active} of 6 months; variation index is {cv:.2f}.",
    }


def _score_profit_trend(business, start: date, end: date) -> dict:
    current = _sales_totals(business, start, end)
    if current["revenue"] <= 0:
        return _empty_component("No recent revenue", "No sales revenue found in the scoring period.")
    margin = float((current["revenue"] - current["cost"]) / current["revenue"] * 100)
    days = max((end - start).days, 1)
    prior = _sales_totals(business, start - timedelta(days=days), start - timedelta(days=1))
    prior_margin = (
        float((prior["revenue"] - prior["cost"]) / prior["revenue"] * 100)
        if prior["revenue"] > 0
        else None
    )
    base = 92 if margin >= 30 else 78 if margin >= 20 else 64 if margin >= 12 else 48 if margin > 0 else 25
    if prior_margin is not None:
        base += max(-10, min(10, (margin - prior_margin) * 0.4))
    score = _clamp(base)
    return {
        "score": score,
        "label": "Profitable" if margin > 12 else "Thin margin" if margin > 0 else "Loss making",
        "explanation": f"Gross margin is {margin:.1f}% over the scoring period.",
    }


def _score_cash_flow(business, start: date, end: date) -> dict:
    totals = _sales_totals(business, start, end)
    if totals["count"] == 0:
        return _empty_component("No inflow data", "No sales were found for cash-flow scoring.")
    period_days = max((end - start).days + 1, 1)
    coverage = totals["days"] / period_days
    score = 92 if coverage >= 0.65 else 78 if coverage >= 0.4 else 62 if coverage >= 0.22 else 45 if coverage >= 0.1 else 30
    return {
        "score": score,
        "label": "Stable inflow" if score >= 72 else "Uneven inflow" if score >= 50 else "Sparse inflow",
        "explanation": f"Recorded sales on {totals['days']} of {period_days} days.",
    }


def _score_expense_control(business, start: date, end: date) -> dict:
    revenue = _sales_totals(business, start, end)["revenue"]
    monthly_obligations = _monthly_recurring_total(business)
    if revenue <= 0 and monthly_obligations <= 0:
        return _empty_component("No expense baseline", "No revenue or recurring obligation records found.")
    if revenue <= 0:
        return {
            "score": 40,
            "label": "Unproven",
            "explanation": f"Recurring obligations are about MWK {monthly_obligations:,.0f}/month, but no recent revenue was found.",
        }
    period_months = Decimal(max((end - start).days + 1, 1)) / Decimal("30")
    obligations_for_period = monthly_obligations * period_months
    ratio = float(obligations_for_period / revenue) if revenue else 1
    score = 92 if ratio <= 0.15 else 78 if ratio <= 0.28 else 62 if ratio <= 0.45 else 45 if ratio <= 0.7 else 25
    return {
        "score": score,
        "label": "Controlled" if score >= 72 else "Manageable" if score >= 50 else "Heavy expenses",
        "explanation": f"Recurring obligations equal about {ratio:.0%} of period revenue.",
    }


def _score_stock_turnover(business, start: date, end: date) -> dict:
    try:
        from inventory.models import InventoryItem

        sold = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__date__gte=start,
            sold_at__date__lte=end,
        ).count()
        in_stock = InventoryItem.objects.filter(business=business, is_active=True, status="IN_STOCK").count()
    except Exception:
        sold = in_stock = 0
    total = sold + in_stock
    if total == 0:
        return _empty_component("No stock data", "No inventory records found for stock turnover.")
    turnover = sold / total
    score = 90 if turnover >= 0.55 else 76 if turnover >= 0.35 else 62 if turnover >= 0.2 else 45 if sold else 35
    return {
        "score": score,
        "label": "Healthy turnover" if score >= 72 else "Slow turnover" if score >= 50 else "Low movement",
        "explanation": f"{sold} items sold against {in_stock} currently in stock.",
    }


def _score_payment_discipline(business, start: date, end: date) -> dict:
    orders = list(_layby_orders(business, start, end))
    if not orders:
        return _empty_component("No repayment data", "No layby or repayment records found for this period.")
    completed = sum(1 for order in orders if order.status == "completed")
    cancelled = sum(1 for order in orders if order.status == "cancelled")
    overdue = 0
    today = timezone.localdate()
    for order in orders:
        if order.status == "active" and (today - order.created_at.date()).days > ((order.term_months or 3) * 35):
            if order.balance > 0:
                overdue += 1
    raw = completed / len(orders) * 100 - cancelled * 8 - overdue * 10
    score = _clamp(raw)
    return {
        "score": score,
        "label": "Disciplined" if score >= 72 else "Mixed" if score >= 50 else "Needs attention",
        "explanation": f"{completed}/{len(orders)} layby orders completed; {overdue} overdue active orders.",
    }


def _score_recurring_obligations(business) -> dict:
    monthly_revenue = Decimal(str(sum(_monthly_revenue_series(business, 3)) / 3))
    monthly_obligations = _monthly_recurring_total(business)
    if monthly_revenue <= 0 and monthly_obligations <= 0:
        return _empty_component("No obligations data", "No recurring obligations have been recorded.")
    if monthly_revenue <= 0:
        return {"score": 42, "label": "Unproven", "explanation": f"Monthly obligations are MWK {monthly_obligations:,.0f}; revenue baseline is missing."}
    ratio = float(monthly_obligations / monthly_revenue)
    score = 92 if ratio <= 0.12 else 78 if ratio <= 0.25 else 62 if ratio <= 0.4 else 45 if ratio <= 0.65 else 25
    return {
        "score": score,
        "label": "Light obligations" if score >= 72 else "Moderate obligations" if score >= 50 else "Heavy obligations",
        "explanation": f"Recurring obligations are about {ratio:.0%} of average monthly revenue.",
    }


def _score_debt_exposure(business) -> dict:
    orders = list(_layby_orders(business))
    if not orders:
        return {"score": 78, "label": "No recorded debt exposure", "explanation": "No open layby balances are recorded for this business."}
    outstanding = sum((order.balance or Decimal("0")) for order in orders if order.status == "active")
    monthly_revenue = Decimal(str(sum(_monthly_revenue_series(business, 3)) / 3))
    if outstanding <= 0:
        return {"score": 90, "label": "Clean exposure", "explanation": "No outstanding active layby balances were found."}
    if monthly_revenue <= 0:
        return {"score": 42, "label": "Exposure unbenchmarked", "explanation": f"Outstanding exposure is MWK {outstanding:,.0f}, but revenue baseline is missing."}
    ratio = float(outstanding / monthly_revenue)
    score = 90 if ratio <= 0.1 else 76 if ratio <= 0.25 else 60 if ratio <= 0.5 else 42 if ratio <= 0.9 else 25
    return {
        "score": score,
        "label": "Low exposure" if score >= 72 else "Moderate exposure" if score >= 50 else "High exposure",
        "explanation": f"Open customer balance exposure is {ratio:.0%} of average monthly revenue.",
    }


def _score_business_history(business) -> dict:
    created = getattr(business, "created_at", None)
    if not created:
        return _empty_component("Unknown age", "Business creation date is unavailable.")
    months = max(1, (timezone.now() - created).days // 30)
    score = 95 if months >= 24 else 82 if months >= 12 else 66 if months >= 6 else 48 if months >= 3 else 35
    return {
        "score": score,
        "label": "Established" if score >= 72 else "Developing" if score >= 50 else "New",
        "explanation": f"Business history in Emajinet is approximately {months} month(s).",
    }


def _score_operational_activity(business, start: date, end: date) -> dict:
    sales = _sales_totals(business, start, end)
    try:
        from inventory.models import InventoryItem
        stock_count = InventoryItem.objects.filter(business=business, is_active=True).count()
    except Exception:
        stock_count = 0
    activity = sales["count"] + min(stock_count, 50)
    if activity <= 0:
        return _empty_component("No activity", "No sales or stock activity found.")
    score = 90 if activity >= 80 else 76 if activity >= 40 else 62 if activity >= 18 else 48 if activity >= 5 else 35
    return {
        "score": score,
        "label": "Active operations" if score >= 72 else "Moderate activity" if score >= 50 else "Light activity",
        "explanation": f"{sales['count']} sales and {stock_count} active stock records contribute to this score.",
    }


def _score_reporting_completeness(business, start: date, end: date) -> dict:
    sources = 0
    labels = []
    totals = _sales_totals(business, start, end)
    if totals["count"]:
        sources += 1
        labels.append("sales")
    try:
        from inventory.models import InventoryItem
        if InventoryItem.objects.filter(business=business, is_active=True).exists():
            sources += 1
            labels.append("inventory")
    except Exception:
        pass
    if _monthly_recurring_total(business) > 0:
        sources += 1
        labels.append("recurring costs")
    if list(_layby_orders(business, start, end)[:1]):
        sources += 1
        labels.append("layby")
    score = _clamp(sources / 4 * 100)
    if score == 0:
        return _empty_component("Incomplete", "No reporting sources were found.")
    return {
        "score": score,
        "label": "Complete" if score >= 75 else "Partial",
        "explanation": "Available reporting sources: " + ", ".join(labels) + ".",
    }


def _financing_summary(score: Optional[int], revenue: Decimal) -> tuple[str, str]:
    if score is None:
        return "Not ready yet", "No lender-ready score is available until business activity is recorded."
    if score >= 85:
        return "Strong lender-ready profile", "The business shows strong creditworthiness for supplier finance, bank review, or investor diligence."
    if score >= 72:
        return "Finance-ready with standard checks", "The business is a good candidate for financing, subject to normal affordability and document checks."
    if score >= 58:
        return "Potentially financeable", "The business may qualify for smaller facilities while improving consistency and reporting."
    if score >= 42:
        return "Watchlist", "The business should improve cash flow, expense control, and reporting before taking on larger obligations."
    return "High risk", "The business is not ready for new credit without operational improvements."


def _limit_range(score: Optional[int], avg_monthly_revenue: Decimal) -> Optional[dict]:
    if score is None or avg_monthly_revenue <= 0:
        return None
    if score >= 85:
        low, high = Decimal("0.35"), Decimal("0.60")
    elif score >= 72:
        low, high = Decimal("0.20"), Decimal("0.40")
    elif score >= 58:
        low, high = Decimal("0.10"), Decimal("0.22")
    elif score >= 42:
        low, high = Decimal("0.04"), Decimal("0.10")
    else:
        return None
    return {
        "low": int(avg_monthly_revenue * low),
        "high": int(avg_monthly_revenue * high),
        "basis": "Based on average monthly recorded revenue and current score band.",
    }


def calculate_business_credit_score(
    business,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    today = timezone.localdate()
    end = end_date or today
    start = start_date or (today - timedelta(days=180))

    components = {
        "revenue_consistency": _score_revenue_consistency(business),
        "profit_trend": _score_profit_trend(business, start, end),
        "cash_flow_stability": _score_cash_flow(business, start, end),
        "expense_control": _score_expense_control(business, start, end),
        "stock_turnover": _score_stock_turnover(business, start, end),
        "payment_discipline": _score_payment_discipline(business, start, end),
        "recurring_obligations": _score_recurring_obligations(business),
        "debt_exposure": _score_debt_exposure(business),
        "business_history": _score_business_history(business),
        "operational_activity": _score_operational_activity(business, start, end),
        "reporting_completeness": _score_reporting_completeness(business, start, end),
    }

    weighted = 0.0
    available = 0
    for key, weight in WEIGHTS.items():
        score = components[key].get("score")
        if score is not None:
            weighted += score * weight
            available += weight

    if available <= 12:
        overall = None
        label, color = "No data yet", "gray"
    else:
        overall = _clamp(weighted / available)
        label, color = _label(overall)

    monthly_revenue = Decimal(str(sum(_monthly_revenue_series(business, 3)) / 3))
    readiness_title, readiness = _financing_summary(overall, monthly_revenue)
    limit = _limit_range(overall, monthly_revenue)

    reasons = []
    recommendations = []
    for key, comp in components.items():
        score = comp.get("score")
        title = key.replace("_", " ").title()
        if score is not None and score >= 72:
            reasons.append(f"{title}: {comp['label']}.")
        elif score is not None and score < 58:
            recommendations.append(f"Improve {title.lower()}: {comp['explanation']}")

    if not reasons and overall is not None:
        reasons.append("The score is based on partial but usable operating data.")
    if not recommendations:
        recommendations.append("Keep recording sales, stock, costs, and repayment activity consistently.")
    if overall is None:
        recommendations = [
            "Record sales and stock activity to establish a business credit profile.",
            "Add recurring costs so affordability can be assessed.",
            "Keep repayment and payment records current.",
        ]

    return {
        "score": overall,
        "label": label,
        "status_color": color,
        "components": components,
        "reasons": reasons[:6],
        "recommendations": recommendations[:6],
        "financing_readiness_title": readiness_title,
        "financing_readiness": readiness,
        "recommended_credit_limit_range": limit,
        "summary": {
            "avg_monthly_revenue": int(monthly_revenue),
            "monthly_recurring_obligations": int(_monthly_recurring_total(business)),
            "sales_count": _sales_totals(business, start, end)["count"],
            "period_start": start,
            "period_end": end,
        },
        "period": {"start": start, "end": end},
        "is_onboarding": overall is None,
    }


def calculate_customer_credit_score(business, customer_phone: str = "", customer_name: Optional[str] = None) -> dict:
    """Backward-compatible wrapper. The product now scores the business."""
    score = calculate_business_credit_score(business)
    score["legacy_customer_lookup"] = {
        "customer_phone": customer_phone,
        "customer_name": customer_name or "",
        "note": "Customer-level credit scoring has been replaced by business creditworthiness scoring.",
    }
    return score


def get_all_customers_credit_summary(business) -> list[dict]:
    """Backward-compatible API shape; returns a single business-level row."""
    score = calculate_business_credit_score(business)
    return [
        {
            "name": getattr(business, "name", "Business"),
            "phone": "",
            "score": score.get("score"),
            "label": score.get("label"),
            "color": score.get("status_color"),
            "orders": score.get("summary", {}).get("sales_count", 0),
            "outstanding": score.get("summary", {}).get("monthly_recurring_obligations", 0),
        }
    ]
