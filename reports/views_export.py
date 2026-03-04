from __future__ import annotations
import csv
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.db.models import Sum, Count, F, Q, DecimalField
from django.db.models.functions import Coalesce, TruncDate

from .views import ReportFilters, _is_staff_or_auditor, _get_active_business, _get_period_dates
from sales.models import Sale
from inventory.models import InventoryItem
from wallet.models import WalletTransaction, TxnType, Ledger


def _apply_filters(qs, f: ReportFilters):
    from .views_api import _apply_filters as _af

    return _af(qs, f)


def _csv_response(filename: str):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_sales_csv(request):
    f = ReportFilters.from_request(request)
    qs = _apply_filters(Sale.objects.select_related("agent"), f).order_by("-created_at")

    resp = _csv_response("sales_report.csv")
    w = csv.writer(resp)
    w.writerow(["Date", "Agent", "Model", "Channel", "Amount_MWK", "Profit_MWK", "Ad_Source"])
    for s in qs:
        w.writerow(
            [
                s.created_at.date(),
                getattr(s.agent, "name", None),
                s.model,
                s.channel,
                s.amount,
                s.profit,
                getattr(s, "ad_source", ""),
            ]
        )
    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_expenses_csv(request):
    # If you have an Expense model, replace with real fields. Placeholder columns:
    resp = _csv_response("monthly_expenses.csv")
    w = csv.writer(resp)
    w.writerow(["Month", "Category", "Amount_MWK", "Notes"])
    # TODO: plug in real Expense aggregations
    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_inventory_csv(request):
    # Sold vs time vs model vs agent
    f = ReportFilters.from_request(request)
    sales = _apply_filters(Sale.objects.all(), f)
    by_model = (
        sales.values("model")
        .annotate(sold=Count("id"), revenue=Coalesce(Sum("amount"), 0), profit=Coalesce(Sum("profit"), 0))
        .order_by("-sold")
    )

    resp = _csv_response("inventory_sold_by_model.csv")
    w = csv.writer(resp)
    w.writerow(["Model", "Units_Sold", "Revenue_MWK", "Profit_MWK"])
    for r in by_model:
        w.writerow([r["model"], r["sold"], r["revenue"], r["profit"]])
    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_management_report_csv(request):
    # A compact management snapshot (KPI pack)
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.all(), f)
    kpis = base.aggregate(amount=Coalesce(Sum("amount"), 0), profit=Coalesce(Sum("profit"), 0), orders=Count("id"))

    resp = _csv_response("management_snapshot.csv")
    w = csv.writer(resp)
    w.writerow(["Metric", "Value"])
    for k, v in kpis.items():
        w.writerow([k, v])
    return resp


# -------------------------------
# New Monthly Export Endpoints
# -------------------------------
@login_required
@user_passes_test(_is_staff_or_auditor)
def export_monthly_sales(request):
    """
    Export monthly sales with complete details.
    Columns: date, time, location, product, brand, variant, quantity, unit_price,
    total_price, payment_method, agent, customer_name, profit, business_id, business_name
    """
    business = _get_active_business(request)
    start_date, end_date = _get_period_dates(request)

    # Get sales for the period
    sales_qs = (
        Sale.objects.filter(sold_at__gte=start_date, sold_at__lte=end_date)
        .select_related("item__product", "agent", "location", "item__business")
        .order_by("sold_at")
    )

    if business:
        sales_qs = sales_qs.filter(item__business=business)

    resp = _csv_response(f"monthly_sales_{start_date}_{end_date}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "date",
            "time",
            "location",
            "product",
            "brand",
            "variant",
            "quantity",
            "unit_price",
            "total_price",
            "payment_method",
            "agent",
            "customer_name",
            "profit",
            "business_id",
            "business_name",
        ]
    )

    for sale in sales_qs:
        product = sale.item.product if hasattr(sale.item, "product") else None
        profit = sale.price - (product.cost_price if product and hasattr(product, "cost_price") else Decimal("0.00"))

        w.writerow(
            [
                sale.sold_at,
                sale.created_at.strftime("%H:%M:%S") if hasattr(sale, "created_at") else "",
                sale.location.name if hasattr(sale, "location") and sale.location else "",
                product.name if product else "",
                product.brand if product and hasattr(product, "brand") else "",
                product.variant if product and hasattr(product, "variant") else "",
                1,  # quantity is always 1 for phone sales
                float(sale.price),
                float(sale.price),
                sale.payment_method if hasattr(sale, "payment_method") else "CASH",
                sale.agent.username if sale.agent else "",
                "",  # customer_name (not tracked in phone sales)
                float(profit),
                sale.item.business.id if sale.item.business else "",
                sale.item.business.name if sale.item.business else "",
            ]
        )

    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_monthly_costs(request):
    """
    Export monthly admin costs.
    Columns: date, type (fixed/variable), recurring_flag, category, amount, note, business_id
    """
    business = _get_active_business(request)
    start_date, end_date = _get_period_dates(request)

    # Get costs for the period
    costs_qs = WalletTransaction.objects.filter(
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    ).order_by("effective_date")

    if business:
        costs_qs = costs_qs.filter(business=business)

    resp = _csv_response(f"monthly_costs_{start_date}_{end_date}.csv")
    w = csv.writer(resp)
    w.writerow(["date", "type", "recurring_flag", "category", "amount", "note", "business_id"])

    for cost in costs_qs:
        cost_type = "recurring" if cost.type == TxnType.COST_RECURRING else "once_off"
        w.writerow(
            [
                cost.effective_date,
                cost_type,
                "Yes" if cost.is_recurring else "No",
                cost.type,
                float(abs(cost.amount)),  # Convert negative to positive for display
                cost.note,
                cost.business.id if cost.business else "",
            ]
        )

    return resp


@login_required
@user_passes_test(_is_staff_or_auditor)
def export_monthly_summary(request):
    """
    Export monthly summary with daily aggregates.
    Columns: date, total_revenue, total_costs, total_commissions, gross_profit,
    net_profit, cash_amount, bank_amount, mobile_amount
    """
    business = _get_active_business(request)
    start_date, end_date = _get_period_dates(request)

    if not business:
        # Return empty CSV if no business
        resp = _csv_response(f"monthly_summary_{start_date}_{end_date}.csv")
        w = csv.writer(resp)
        w.writerow(
            [
                "date",
                "total_revenue",
                "total_costs",
                "total_commissions",
                "gross_profit",
                "net_profit",
                "cash_amount",
                "bank_amount",
                "mobile_amount",
            ]
        )
        return resp

    # Get daily sales aggregates
    daily_sales = {}
    sales_qs = Sale.objects.filter(item__business=business, sold_at__gte=start_date, sold_at__lte=end_date)

    for sale in (
        sales_qs.annotate(date=TruncDate("sold_at"))
        .values("date")
        .annotate(
            revenue=Coalesce(Sum("price"), Decimal("0.00")),
            commissions=Coalesce(
                Sum(F("price") * F("commission_pct") / 100, output_field=DecimalField()), Decimal("0.00")
            ),
            cash=Coalesce(Sum("price", filter=Q(payment_method="CASH")), Decimal("0.00")),
            bank=Coalesce(Sum("price", filter=Q(payment_method="BANK")), Decimal("0.00")),
            mobile=Coalesce(Sum("price", filter=Q(payment_method="MOBILE_MONEY")), Decimal("0.00")),
        )
        .order_by("date")
    ):
        daily_sales[sale["date"]] = sale

    # Get daily costs
    daily_costs = {}
    costs_qs = WalletTransaction.objects.filter(
        business=business,
        ledger=Ledger.COMPANY,
        type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING],
        effective_date__gte=start_date,
        effective_date__lte=end_date,
    )

    for cost in costs_qs.values("effective_date").annotate(total=Coalesce(Sum("amount"), Decimal("0.00"))):
        daily_costs[cost["effective_date"]] = abs(cost["total"])

    # Generate CSV
    resp = _csv_response(f"monthly_summary_{start_date}_{end_date}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "date",
            "total_revenue",
            "total_costs",
            "total_commissions",
            "gross_profit",
            "net_profit",
            "cash_amount",
            "bank_amount",
            "mobile_amount",
        ]
    )

    # Iterate through all days in the period
    current_date = start_date
    while current_date <= end_date:
        sales = daily_sales.get(current_date, {})
        revenue = sales.get("revenue", Decimal("0.00"))
        commissions = sales.get("commissions", Decimal("0.00"))
        cash = sales.get("cash", Decimal("0.00"))
        bank = sales.get("bank", Decimal("0.00"))
        mobile = sales.get("mobile", Decimal("0.00"))
        costs = daily_costs.get(current_date, Decimal("0.00"))

        gross_profit = revenue  # Would subtract COGS if tracked
        net_profit = gross_profit - costs - commissions

        w.writerow(
            [
                current_date,
                float(revenue),
                float(costs),
                float(commissions),
                float(gross_profit),
                float(net_profit),
                float(cash),
                float(bank),
                float(mobile),
            ]
        )

        current_date += timedelta(days=1)

    return resp
