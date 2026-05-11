from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from dashboard.models import BusinessHealthCheck
from wallet.money import q2

logger = logging.getLogger(__name__)


def _money(value: Any = None) -> Decimal:
    return q2(value)


def _setting_decimal(name: str, default: str) -> Decimal:
    return _money(getattr(settings, name, default))


def _safe_reverse(name: str, default: str = "#") -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return default
    except Exception:
        return default


def _sum_signed(qs) -> Decimal:
    try:
        from wallet.models import CashBankTransaction

        ins = qs.filter(direction=CashBankTransaction.Direction.CASH_IN).aggregate(s=Sum("amount")).get("s") or 0
        outs = qs.filter(direction=CashBankTransaction.Direction.CASH_OUT).aggregate(s=Sum("amount")).get("s") or 0
        return _money(Decimal(ins) - Decimal(outs))
    except Exception:
        return Decimal("0.00")


def _cash_rows(business):
    try:
        from wallet.models import CashBankTransaction

        return CashBankTransaction.objects.filter(business=business)
    except Exception:
        return None


def _category_sum(qs, direction: str, words: tuple[str, ...]) -> Decimal:
    if qs is None:
        return Decimal("0.00")
    total = Decimal("0.00")
    try:
        direction_qs = qs.filter(direction=direction)
        for row in direction_qs.only("amount", "category"):
            category = (row.category or "").lower()
            if any(word in category for word in words):
                total += _money(row.amount)
    except Exception:
        return Decimal("0.00")
    return _money(total)


def _expense_total(day_rows) -> Decimal:
    if day_rows is None:
        return Decimal("0.00")
    try:
        from wallet.models import CashBankTransaction

        excluded = ("stock", "withdrawal", "loan repayment", "loan")
        total = Decimal("0.00")
        for row in day_rows.filter(direction=CashBankTransaction.Direction.CASH_OUT).only("amount", "category"):
            category = (row.category or "").lower()
            if any(word in category for word in excluded):
                continue
            total += _money(row.amount)
        return _money(total)
    except Exception:
        return Decimal("0.00")


def _sales_totals(business, day: date) -> dict[str, Decimal | int]:
    try:
        from dashboard.services_health import _sales_totals as health_sales_totals

        totals = health_sales_totals(business, day, day) or {}
        return {
            "revenue": _money(totals.get("revenue")),
            "cost": _money(totals.get("cost")),
            "count": int(totals.get("count") or 0),
        }
    except Exception as exc:
        logger.warning("books balance sales totals failed: %s", exc)
        return {"revenue": Decimal("0.00"), "cost": Decimal("0.00"), "count": 0}


def _current_stock_value(business) -> Decimal:
    try:
        from dashboard.services_health import _business_kind, _clothing_metrics

        today = timezone.localdate()
        if _business_kind(business) == "clothing":
            return _money((_clothing_metrics(business, today, today) or {}).get("stock_value"))
    except Exception:
        pass

    total = Decimal("0.00")
    try:
        from inventory.models import InventoryItem

        stock = InventoryItem.objects.filter(business=business, is_active=True, status="IN_STOCK").only("order_price")
        total += sum((_money(item.order_price) for item in stock), Decimal("0.00"))
    except Exception:
        pass

    try:
        from inventory.models import MerchProduct

        products = MerchProduct.objects.filter(business=business, is_active=True, is_archived=False)
        product_fields = {field.name for field in MerchProduct._meta.get_fields()}
        only_fields = ["quantity_in_stock"] + [
            field for field in ("cost_price", "buying_price", "unit_cost") if field in product_fields
        ]
        for product in products.only(*only_fields):
            qty = _money(getattr(product, "quantity_in_stock", 0))
            cost = (
                getattr(product, "cost_price", None)
                or getattr(product, "buying_price", None)
                or getattr(product, "unit_cost", None)
                or Decimal("0.00")
            )
            total += qty * _money(cost)
    except Exception:
        pass

    return _money(total)


def _receivables_for_business(business) -> tuple[Decimal, bool]:
    total = Decimal("0.00")
    found_source = False
    for model_path in (
        "sales.models.Sale",
        "sales.models.Order",
        "inventory.models.Sale",
        "inventory.models.LiquorCreditSale",
        "inventory.models_welding.WeldingJob",
        "inventory.models_car_hire.CarHireTrip",
    ):
        try:
            mod_name, cls_name = model_path.rsplit(".", 1)
            module = __import__(mod_name, fromlist=[cls_name])
            model = getattr(module, cls_name)
            fields = {getattr(f, "name", "") for f in model._meta.get_fields()}
        except Exception:
            continue

        qs = None
        try:
            if "business" in fields:
                qs = model.objects.filter(business=business)
            elif "seller_business" in fields:
                qs = model.objects.filter(seller_business=business)
            elif "location" in fields:
                qs = model.objects.filter(location__business=business)
        except Exception:
            qs = None
        if qs is None:
            continue

        found_source = True
        for field in ("balance_due", "amount_due", "outstanding_balance", "remaining_balance"):
            if field in fields:
                try:
                    total += _money(qs.aggregate(s=Sum(field)).get("s"))
                    break
                except Exception:
                    continue
    return _money(total), found_source


def _health_actions() -> list[dict[str, str]]:
    return [
        {"label": "Record missing cost", "url": _safe_reverse("wallet:admin_costs_create", "/wallet/admin/costs/new/"), "icon": "bi-receipt"},
        {"label": "Record owner withdrawal", "url": _safe_reverse("wallet:cash_statement", "/wallet/cash-bank/"), "icon": "bi-cash-stack"},
        {"label": "Record capital injection", "url": _safe_reverse("wallet:cash_statement", "/wallet/cash-bank/"), "icon": "bi-bank"},
        {"label": "Adjust stock", "url": _safe_reverse("inventory:stock_list", "/inventory/list/"), "icon": "bi-box-seam"},
        {"label": "View receivables", "url": _safe_reverse("dashboard:credit_scores", "/dashboard/credit-scores/"), "icon": "bi-people"},
        {"label": "View cash statement", "url": _safe_reverse("wallet:cash_statement", "/wallet/cash-bank/"), "icon": "bi-wallet2"},
        {"label": "View stock movement", "url": _safe_reverse("inventory:stock_list", "/inventory/list/"), "icon": "bi-arrow-left-right"},
    ]


def _classify(
    *,
    sales_revenue: Decimal,
    cost_of_goods_sold: Decimal,
    recorded_expenses: Decimal,
    current_cash: Decimal,
    current_stock_value: Decimal,
    current_receivables: Decimal,
    expected_value: Decimal,
    actual_value: Decimal,
    variance: Decimal,
    tolerance: Decimal,
    has_cash_rows: bool,
    has_receivable_source: bool,
    sales_count: int,
) -> dict[str, Any]:
    useful_dimensions = sum(
        1
        for present in (
            has_cash_rows or current_cash != 0,
            current_stock_value > 0 or cost_of_goods_sold > 0,
            sales_revenue > 0 or sales_count > 0,
            recorded_expenses > 0,
            current_receivables > 0,
        )
        if present
    )

    if useful_dimensions == 0:
        return {
            "status": BusinessHealthCheck.Status.NOT_ENOUGH_DATA,
            "score": 0,
            "recommendation": "Not enough data to reconcile yet. Record sales, cash movement, stock, or costs to unlock the daily books check.",
            "badges": ["Getting Started"],
        }

    badges: list[str] = []
    if current_cash > 0:
        badges.append("Cash Strong")
    if current_stock_value > 0:
        badges.append("Stock Healthy")
    if sales_revenue - cost_of_goods_sold - recorded_expenses > 0:
        badges.append("Profit Positive")

    if sales_revenue > 0 and not has_cash_rows:
        badges.extend(["Watch Cash", "Record Cash"])
        return {
            "status": BusinessHealthCheck.Status.WARNING_MISSING_MONEY,
            "score": 52,
            "recommendation": "Cash is missing from the story. Record cash, bank, or mobile money collections for today's sales before calling the books balanced.",
            "badges": badges,
        }

    if sales_revenue > 0 and cost_of_goods_sold <= 0 and recorded_expenses <= 0:
        badges.extend(["Record Costs", "Costs Missing"])
        return {
            "status": BusinessHealthCheck.Status.WARNING_COSTS,
            "score": 56,
            "recommendation": "Sales are recorded, but costs are not in the story yet. Add cost of goods, overheads, or missing expenses before trusting the profit.",
            "badges": badges,
        }

    if sales_revenue > 0 and recorded_expenses <= 0:
        badges.append("Record Costs")

    if sales_revenue > 0 and current_receivables > (sales_revenue * Decimal("0.50")):
        badges.append("Collect Debts")
        return {
            "status": BusinessHealthCheck.Status.WARNING_RECEIVABLES,
            "score": 62,
            "recommendation": "Receivables are swallowing your cash. Sales are moving, but customer balances are growing too fast.",
            "badges": badges,
        }

    if current_stock_value > 0 and current_cash >= 0 and current_stock_value > max(current_cash * Decimal("3"), Decimal("1.00")):
        badges.append("Stock Heavy")

    if useful_dimensions < 2 or (sales_revenue > 0 and not has_receivable_source):
        badges.append("Needs More Data")
        return {
            "status": BusinessHealthCheck.Status.NOT_ENOUGH_DATA,
            "score": 35 if useful_dimensions else 0,
            "recommendation": "Not enough data to reconcile yet. Cash, stock, receivable, and cost records are needed before the system can verify the books.",
            "badges": badges,
        }

    abs_variance = abs(variance)
    if abs_variance <= tolerance:
        badges.insert(0, "Balanced")
        status = BusinessHealthCheck.Status.WINNING if sales_revenue > 0 and (sales_revenue - cost_of_goods_sold - recorded_expenses) > 0 else BusinessHealthCheck.Status.BALANCED
        return {
            "status": status,
            "score": 95 if status == BusinessHealthCheck.Status.WINNING else 90,
            "recommendation": "Books balanced. You are winning." if status == BusinessHealthCheck.Status.WINNING else "Books balanced. Your records look clean.",
            "badges": badges,
        }

    ratio = abs_variance / max(abs(expected_value), abs(actual_value), Decimal("1.00"))
    danger = abs_variance > (tolerance * Decimal("5")) or ratio > Decimal("0.15")
    status = BusinessHealthCheck.Status.DANGER if danger else BusinessHealthCheck.Status.WARNING_MISSING_MONEY
    score = 30 if danger else 58

    if variance > 0:
        recommendation = f"MWK {variance:,.0f} appears unaccounted for. Check missing costs, withdrawals, stock purchases, or unpaid balances."
        badges.append("Missing Money")
    else:
        recommendation = f"You have MWK {abs_variance:,.0f} more value than expected. Check unrecorded capital injection, unpaid sales, or inventory corrections."
        badges.append("Investigate Value")
    return {"status": status, "score": score, "recommendation": recommendation, "badges": badges}


def run_daily_books_balance(business, day: date | None = None, *, force: bool = False) -> BusinessHealthCheck:
    day = day or timezone.localdate()

    cash_qs = _cash_rows(business)
    day_rows = cash_qs.filter(date=day) if cash_qs is not None else None
    opening_cash = _sum_signed(cash_qs.filter(date__lt=day)) if cash_qs is not None else Decimal("0.00")
    current_cash = _sum_signed(cash_qs.filter(date__lte=day)) if cash_qs is not None else Decimal("0.00")
    has_cash_rows = bool(cash_qs is not None and cash_qs.exists())

    sales = _sales_totals(business, day)
    sales_revenue = _money(sales["revenue"])
    cost_of_goods_sold = _money(sales["cost"])
    sales_count = int(sales["count"] or 0)

    current_stock_value = _current_stock_value(business)
    stock_purchases = _category_sum(day_rows, "cash_out", ("stock", "purchase", "inventory"))
    opening_stock_value = _money(current_stock_value + cost_of_goods_sold - stock_purchases)
    if opening_stock_value < 0:
        opening_stock_value = Decimal("0.00")

    current_receivables, has_receivable_source = _receivables_for_business(business)
    opening_receivables = current_receivables

    recorded_expenses = _expense_total(day_rows)
    try:
        from dashboard.services_health import _cfo_expense_total

        recorded_expenses += _money(_cfo_expense_total(business, day, day))
    except Exception:
        pass
    recorded_expenses = _money(recorded_expenses)

    capital_injection = _category_sum(day_rows, "cash_in", ("capital", "owner injection"))
    owner_withdrawals = _category_sum(day_rows, "cash_out", ("withdrawal", "owner"))
    loans_received = _category_sum(day_rows, "cash_in", ("loan",))
    loan_repayments = _category_sum(day_rows, "cash_out", ("loan", "repayment"))

    profit = _money(sales_revenue - cost_of_goods_sold - recorded_expenses)
    opening_position = _money(opening_cash + opening_stock_value + opening_receivables)
    actual_value = _money(current_cash + current_stock_value + current_receivables)
    expected_value = _money(opening_position + profit + capital_injection + loans_received - owner_withdrawals - loan_repayments)
    variance = _money(expected_value - actual_value)
    tolerance = max(_setting_decimal("BOOKS_BALANCE_VARIANCE_TOLERANCE_MWK", "1000.00"), _money(sales_revenue * Decimal("0.01")))

    classification = _classify(
        sales_revenue=sales_revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        recorded_expenses=recorded_expenses,
        current_cash=current_cash,
        current_stock_value=current_stock_value,
        current_receivables=current_receivables,
        expected_value=expected_value,
        actual_value=actual_value,
        variance=variance,
        tolerance=tolerance,
        has_cash_rows=has_cash_rows,
        has_receivable_source=has_receivable_source,
        sales_count=sales_count,
    )

    defaults = {
        "opening_cash": opening_cash,
        "opening_stock_value": opening_stock_value,
        "opening_receivables": opening_receivables,
        "current_cash": current_cash,
        "current_stock_value": current_stock_value,
        "current_receivables": current_receivables,
        "sales_revenue": sales_revenue,
        "cost_of_goods_sold": cost_of_goods_sold,
        "recorded_expenses": recorded_expenses,
        "capital_injection": capital_injection,
        "owner_withdrawals": owner_withdrawals,
        "loans_received": loans_received,
        "loan_repayments": loan_repayments,
        "expected_value": expected_value,
        "actual_value": actual_value,
        "variance": variance,
        "tolerance": tolerance,
        "score": classification["score"],
        "status": classification["status"],
        "recommendation": classification["recommendation"],
        "badges": classification["badges"],
        "actions": _health_actions(),
        "meta": {
            "opening_position": str(opening_position),
            "profit": str(profit),
            "stock_purchases": str(stock_purchases),
            "sales_count": sales_count,
            "has_cash_rows": has_cash_rows,
            "has_receivable_source": has_receivable_source,
            "calculated_at": timezone.now().isoformat(),
        },
    }
    check, _created = BusinessHealthCheck.objects.update_or_create(
        business=business,
        date=day,
        defaults=defaults,
    )
    return check


def books_balance_history(business) -> dict[str, Any]:
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    checks = BusinessHealthCheck.objects.filter(business=business)
    return {
        "today": checks.filter(date=today).first(),
        "week": checks.filter(date__gte=week_start, date__lte=today).order_by("-date"),
        "month": checks.filter(date__gte=month_start, date__lte=today).order_by("-date"),
    }
