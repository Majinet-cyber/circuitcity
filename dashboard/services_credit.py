"""
Credit Score Engine — calculate_customer_credit_score
Evaluates customer creditworthiness from layby/credit history.
No new models needed: uses LaybyOrder + LaybyPayment.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)


# ── Weights (must sum to 100) ──────────────────────────────────────────────
_WEIGHTS = {
    "default_behavior":     40,
    "repayment_speed":      20,
    "debt_size":            20,
    "purchase_consistency": 10,
    "relationship_duration": 10,
}


def _label_and_color(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Low Risk", "green"
    elif score >= 65:
        return "Moderate Risk", "amber"
    elif score >= 50:
        return "Caution", "orange"
    else:
        return "High Risk", "red"


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, val)))


def _no_data_component(reason: str = "Not enough data") -> dict:
    return {"score": None, "label": reason, "explanation": reason}


# ── Component scorers ──────────────────────────────────────────────────────

def _score_default_behavior(orders) -> dict:
    """
    40% weight. Ratio of completed vs total. Cancelled/overdue penalised.
    """
    total = len(orders)
    if total == 0:
        return _no_data_component()

    completed = sum(1 for o in orders if o.status == "completed")
    cancelled = sum(1 for o in orders if o.status == "cancelled")
    # active orders with balance > 0 that are old (>90 days) count as overdue
    today = date.today()
    overdue = 0
    for o in orders:
        if o.status == "active":
            age = (today - o.created_at.date()).days
            if age > 90 and o.balance > 0:
                overdue += 1

    completion_rate = completed / total
    # Start from completion rate, deduct for overdue
    raw = completion_rate * 100 - (overdue * 15)
    score = _clamp(raw)

    if score >= 80:
        label, explanation = "Excellent", f"{completed}/{total} orders completed — very reliable borrower."
    elif score >= 65:
        label, explanation = "Good", f"{completed}/{total} completed. Some gaps but generally reliable."
    elif score >= 50:
        label, explanation = "Fair", f"Only {completed}/{total} completed. {overdue} overdue order(s) noted."
    else:
        label, explanation = "Poor", f"Low completion ({completed}/{total}). {cancelled} cancelled, {overdue} overdue."

    return {"score": score, "label": label, "explanation": explanation}


def _score_repayment_speed(orders) -> dict:
    """
    20% weight. Average days taken to complete installment plans.
    Faster = higher score.
    """
    completed = [o for o in orders if o.status == "completed"]
    if not completed:
        return _no_data_component("No completed orders yet")

    durations = []
    for o in completed:
        last_payment = o.payments.order_by("-received_at").first()
        if last_payment and o.created_at:
            days = (last_payment.received_at.date() - o.created_at.date()).days
            if days >= 0:
                durations.append(days)

    if not durations:
        return _no_data_component("Cannot calculate repayment duration")

    avg_days = sum(durations) / len(durations)
    # Expected: term_months * 30 days is baseline
    avg_term = sum((o.term_months or 3) * 30 for o in completed) / len(completed)

    ratio = avg_days / avg_term if avg_term > 0 else 1.0
    # ratio < 1 = paid early, ratio > 1 = paid late
    if ratio <= 0.75:
        score, label, explanation = 100, "Excellent", f"Paid on average {avg_days:.0f} days — well ahead of schedule."
    elif ratio <= 1.0:
        score, label, explanation = 80, "Good", f"Paid on average {avg_days:.0f} days — on time."
    elif ratio <= 1.3:
        score, label, explanation = 60, "Fair", f"Paid on average {avg_days:.0f} days — slightly behind schedule."
    else:
        score, label, explanation = 35, "Slow Payer", f"Paid on average {avg_days:.0f} days — significantly behind schedule."

    return {"score": _clamp(score), "label": label, "explanation": explanation}


def _score_debt_size(orders) -> dict:
    """
    20% weight. Total outstanding balance vs total purchase value.
    Lower outstanding = higher score.
    """
    active = [o for o in orders if o.status == "active"]
    if not active:
        return {"score": 90, "label": "No Outstanding Debt", "explanation": "No active layby orders — clean slate."}

    total_value = sum((o.total_price or Decimal("0")) for o in active)
    total_outstanding = sum((o.balance or Decimal("0")) for o in active)

    if total_value == 0:
        return _no_data_component()

    outstanding_ratio = float(total_outstanding / total_value)

    if outstanding_ratio <= 0.25:
        score, label = 90, "Low Debt"
    elif outstanding_ratio <= 0.5:
        score, label = 70, "Moderate Debt"
    elif outstanding_ratio <= 0.75:
        score, label = 50, "High Debt"
    else:
        score, label = 25, "Very High Debt"

    explanation = (
        f"MWK {total_outstanding:,.0f} outstanding of MWK {total_value:,.0f} total "
        f"({outstanding_ratio*100:.0f}% unpaid across {len(active)} active order(s))."
    )
    return {"score": _clamp(score), "label": label, "explanation": explanation}


def _score_purchase_consistency(orders) -> dict:
    """
    10% weight. Frequency and recency of orders.
    """
    if not orders:
        return _no_data_component()

    total = len(orders)
    today = date.today()
    recent = sum(1 for o in orders if (today - o.created_at.date()).days <= 180)

    if total >= 5 and recent >= 2:
        score, label = 90, "Highly Consistent"
        explanation = f"{total} orders total, {recent} in last 6 months — loyal customer."
    elif total >= 3 or recent >= 1:
        score, label = 65, "Regular Customer"
        explanation = f"{total} orders total, {recent} in last 6 months."
    elif total >= 1:
        score, label = 45, "Occasional"
        explanation = f"Only {total} order(s), {recent} in last 6 months — limited history."
    else:
        score, label = 20, "Rare"
        explanation = "Very few orders on record."

    return {"score": _clamp(score), "label": label, "explanation": explanation}


def _score_relationship_duration(orders) -> dict:
    """
    10% weight. How long the customer has been ordering.
    """
    if not orders:
        return _no_data_component()

    earliest = min(o.created_at.date() for o in orders)
    months = max(1, (date.today() - earliest).days // 30)

    if months >= 24:
        score, label = 100, "Long-term Customer"
        explanation = f"{months} months as a customer — very established relationship."
    elif months >= 12:
        score, label = 80, "Established Customer"
        explanation = f"{months} months as a customer."
    elif months >= 6:
        score, label = 60, "Growing Relationship"
        explanation = f"{months} months — relationship is building."
    else:
        score, label = 40, "New Customer"
        explanation = f"Only {months} month(s) — insufficient history to judge long-term reliability."

    return {"score": _clamp(score), "label": label, "explanation": explanation}


# ── Main entry point ───────────────────────────────────────────────────────

def calculate_customer_credit_score(
    business,
    customer_phone: str,
    customer_name: Optional[str] = None,
) -> dict:
    """
    Returns:
    {
      "score": 78,
      "label": "Low Risk",
      "status_color": "green",
      "lending_guidance": "...",
      "components": { "default_behavior": {...}, ... },
      "recommendations": [...],
      "data_summary": { "total_orders": N, "completed": N, "active": N, "cancelled": N }
    }
    """
    try:
        from layby.models import LaybyOrder, LaybyPayment  # noqa: F401
    except ImportError:
        log.warning("Layby app not available for credit scoring.")
        return _empty_score("Layby module not available.")

    try:
        # Scope orders to this business via membership
        Membership = None
        try:
            from tenants.models import Membership as M
            Membership = M
        except ImportError:
            pass

        qs = LaybyOrder.objects.filter(
            customer_phone=customer_phone
        ).prefetch_related("payments").order_by("-created_at")

        if Membership is not None:
            biz_user_ids = Membership.objects.filter(
                business=business, status="ACTIVE"
            ).values_list("user_id", flat=True)
            qs = qs.filter(created_by_id__in=list(biz_user_ids))
        else:
            qs = qs.filter(created_by__isnull=False)

        orders = list(qs.select_related("created_by"))

        if not orders and customer_name:
            # Fallback: search by name if phone yields nothing
            qs2 = LaybyOrder.objects.filter(
                customer_name__icontains=customer_name
            ).prefetch_related("payments").order_by("-created_at")
            if Membership is not None:
                biz_user_ids = Membership.objects.filter(
                    business=business, status="ACTIVE"
                ).values_list("user_id", flat=True)
                qs2 = qs2.filter(created_by_id__in=list(biz_user_ids))
            orders = list(qs2.select_related("created_by"))

    except Exception as e:
        log.exception("Error fetching layby orders for credit score: %s", e)
        return _empty_score(f"Data error: {e}")

    if not orders:
        return _empty_score("No credit history found for this customer.")

    # ── Compute components ─────────────────────────────────────────────────
    components = {
        "default_behavior":      _score_default_behavior(orders),
        "repayment_speed":       _score_repayment_speed(orders),
        "debt_size":             _score_debt_size(orders),
        "purchase_consistency":  _score_purchase_consistency(orders),
        "relationship_duration": _score_relationship_duration(orders),
    }

    # ── Weighted average (skip None scores) ───────────────────────────────
    total_weight = 0
    weighted_sum = 0.0
    for key, comp in components.items():
        if comp["score"] is not None:
            w = _WEIGHTS.get(key, 0)
            weighted_sum += comp["score"] * w
            total_weight += w

    if total_weight == 0:
        overall = 50
    else:
        overall = _clamp(weighted_sum / total_weight)

    label, status_color = _label_and_color(overall)

    # ── Recommendations ───────────────────────────────────────────────────
    recs = []
    db = components["default_behavior"]
    rs = components["repayment_speed"]
    ds = components["debt_size"]
    pc = components["purchase_consistency"]

    if db.get("score") is not None and db["score"] < 65:
        recs.append("Follow up on incomplete or overdue layby orders before extending new credit.")
    if rs.get("score") is not None and rs["score"] < 65:
        recs.append("Customer tends to pay late — consider shorter terms or higher deposit requirements.")
    if ds.get("score") is not None and ds["score"] < 65:
        recs.append("Outstanding balance is high — avoid extending additional credit until existing balance is reduced.")
    if pc.get("score") is not None and pc["score"] < 50:
        recs.append("Customer history is limited. Start with a small credit limit and build trust.")
    if overall >= 80:
        recs.append("Excellent track record — this customer is a strong candidate for premium credit terms.")
    elif overall >= 65:
        recs.append("Generally reliable — standard credit terms are appropriate.")

    if not recs:
        recs.append("Continue monitoring payment behaviour on current orders.")

    # ── Lending guidance ──────────────────────────────────────────────────
    if overall >= 80:
        lending_guidance = "✅ Approved for standard layby terms up to 12 months. Low default risk."
    elif overall >= 65:
        lending_guidance = "🟡 Approved with caution. Use standard terms. Monitor payments closely."
    elif overall >= 50:
        lending_guidance = "🟠 Conditional approval. Require higher deposit (≥40%). Maximum 6-month term."
    else:
        lending_guidance = "🔴 High risk. Do not extend new credit until outstanding balances are cleared."

    # ── Data summary ──────────────────────────────────────────────────────
    data_summary = {
        "total_orders":   len(orders),
        "completed":      sum(1 for o in orders if o.status == "completed"),
        "active":         sum(1 for o in orders if o.status == "active"),
        "cancelled":      sum(1 for o in orders if o.status == "cancelled"),
        "total_value":    float(sum((o.total_price or Decimal("0")) for o in orders)),
        "total_paid":     float(sum((o.amount_paid or Decimal("0")) for o in orders)),
        "total_outstanding": float(sum((o.balance or Decimal("0")) for o in orders)),
        "customer_name":  orders[0].customer_name if orders else customer_name or "",
        "customer_phone": customer_phone,
    }

    return {
        "score":           overall,
        "label":           label,
        "status_color":    status_color,
        "lending_guidance": lending_guidance,
        "components":      components,
        "recommendations": recs,
        "data_summary":    data_summary,
    }


def _empty_score(reason: str) -> dict:
    return {
        "score":           None,
        "label":           "No Data",
        "status_color":    "gray",
        "lending_guidance": reason,
        "components":      {},
        "recommendations": [reason],
        "data_summary":    {},
    }


def get_all_customers_credit_summary(business) -> list[dict]:
    """
    Return a list of all unique customers (by phone) with their credit score summary.
    Used for the credit scores list view.
    """
    try:
        from layby.models import LaybyOrder
        Membership = None
        try:
            from tenants.models import Membership as M
            Membership = M
        except ImportError:
            pass

        qs = LaybyOrder.objects.all()
        if Membership is not None:
            biz_user_ids = Membership.objects.filter(
                business=business, status="ACTIVE"
            ).values_list("user_id", flat=True)
            qs = qs.filter(created_by_id__in=list(biz_user_ids))

        # Get unique customers
        seen = set()
        customers = []
        for order in qs.order_by("-created_at"):
            key = order.customer_phone or order.customer_name
            if key and key not in seen:
                seen.add(key)
                customers.append({
                    "name": order.customer_name,
                    "phone": order.customer_phone,
                })
            if len(customers) >= 200:
                break

        results = []
        for c in customers:
            try:
                score_data = calculate_customer_credit_score(
                    business,
                    customer_phone=c["phone"],
                    customer_name=c["name"],
                )
                results.append({
                    "name":   c["name"],
                    "phone":  c["phone"],
                    "score":  score_data["score"],
                    "label":  score_data["label"],
                    "color":  score_data["status_color"],
                    "orders": score_data["data_summary"].get("total_orders", 0),
                    "outstanding": score_data["data_summary"].get("total_outstanding", 0),
                })
            except Exception as e:
                log.debug("Skip customer %s: %s", c["phone"], e)

        results.sort(key=lambda x: (x["score"] or 0), reverse=True)
        return results

    except Exception as e:
        log.exception("Error building credit summary list: %s", e)
        return []
