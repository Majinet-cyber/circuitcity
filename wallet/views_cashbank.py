from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import CashBankTransaction
from .money import q2

try:
    from tenants.utils import get_active_business
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None


CASH_IN_CATEGORIES = [
    "Phone sale payment",
    "Deposit received",
    "Balance payment",
    "Owner capital injection",
    "Loan received",
    "Other income",
]
CASH_OUT_CATEGORIES = [
    "Stock purchase",
    "Rent",
    "Salary",
    "Transport",
    "Food/allowance",
    "Airtime/bundles",
    "Loan repayment",
    "Withdrawal by owner",
    "Business expense",
    "Other expense",
]


def _staff(user) -> bool:
    try:
        return bool(user.is_authenticated and (user.is_staff or user.is_superuser or user.profile.is_manager))
    except Exception:
        return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _money(value: Any) -> Decimal:
    try:
        return q2(Decimal(str(value or "0")))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _period(request: HttpRequest):
    today = timezone.localdate()
    preset = (request.GET.get("range") or "month").lower()
    start = _date(request.GET.get("start"))
    end = _date(request.GET.get("end"))
    if preset == "today":
        start = end = today
    elif preset == "week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif preset == "custom" and start and end:
        pass
    else:
        preset = "month"
        start = today.replace(day=1)
        end = today
    return preset, start, end


def _scoped_rows(request: HttpRequest):
    business = get_active_business(request)
    if not business:
        return business, CashBankTransaction.objects.none()
    return business, CashBankTransaction.objects.filter(business=business)


def _apply_filters(qs, request: HttpRequest, start, end):
    qs = qs.filter(date__gte=start, date__lte=end)
    method = request.GET.get("payment_method") or ""
    direction = request.GET.get("direction") or ""
    category = request.GET.get("category") or ""
    user_id = request.GET.get("created_by") or ""
    if method:
        qs = qs.filter(payment_method=method)
    if direction:
        qs = qs.filter(direction=direction)
    if category:
        qs = qs.filter(category=category)
    if user_id:
        qs = qs.filter(created_by_id=user_id)
    return qs


def _sum_signed(qs) -> Decimal:
    ins = qs.filter(direction=CashBankTransaction.Direction.CASH_IN).aggregate(s=Sum("amount"))["s"] or 0
    outs = qs.filter(direction=CashBankTransaction.Direction.CASH_OUT).aggregate(s=Sum("amount"))["s"] or 0
    return q2(Decimal(ins) - Decimal(outs))


def _receivables_for_business(business) -> Decimal:
    total = Decimal("0.00")
    for model_path in ("sales.models.Sale", "sales.models.Order", "inventory.models.Sale"):
        try:
            mod_name, cls_name = model_path.rsplit(".", 1)
            module = __import__(mod_name, fromlist=[cls_name])
            model = getattr(module, cls_name)
        except Exception:
            continue
        fields = {getattr(f, "name", "") for f in model._meta.get_fields()}
        if "business" not in fields and "business_id" not in fields:
            continue
        qs = model.objects.filter(business=business)
        for field in ("balance_due", "amount_due", "outstanding_balance", "remaining_balance"):
            if field in fields:
                try:
                    total += Decimal(qs.aggregate(s=Sum(field))["s"] or 0)
                    break
                except Exception:
                    continue
    return q2(total)


def _summary(request: HttpRequest):
    business, base = _scoped_rows(request)
    preset, start, end = _period(request)
    filtered = _apply_filters(base, request, start, end)
    opening = _sum_signed(base.filter(date__lt=start))
    cash_in = filtered.filter(direction=CashBankTransaction.Direction.CASH_IN).aggregate(s=Sum("amount"))["s"] or 0
    cash_out = filtered.filter(direction=CashBankTransaction.Direction.CASH_OUT).aggregate(s=Sum("amount"))["s"] or 0
    closing = q2(opening + Decimal(cash_in) - Decimal(cash_out))
    bank = q2(_sum_signed(base.filter(payment_method=CashBankTransaction.PaymentMethod.BANK)))
    mobile = q2(
        _sum_signed(
            base.filter(
                payment_method__in=[
                    CashBankTransaction.PaymentMethod.AIRTEL,
                    CashBankTransaction.PaymentMethod.MPAMBA,
                ]
            )
        )
    )
    cash_on_hand = q2(_sum_signed(base.filter(payment_method=CashBankTransaction.PaymentMethod.CASH)))
    expected = _receivables_for_business(business) if business else Decimal("0.00")
    return {
        "business": business,
        "preset": preset,
        "period_start": start,
        "period_end": end,
        "rows": filtered.select_related("created_by").order_by("-date", "-id"),
        "summary": {
            "opening_balance": q2(opening),
            "total_cash_in": q2(cash_in),
            "total_cash_out": q2(cash_out),
            "closing_balance": closing,
            "cash_on_hand": cash_on_hand,
            "bank_balance": bank,
            "mobile_money_balance": mobile,
            "total_available_cash": q2(cash_on_hand + bank + mobile),
            "expected_receivables": expected,
            "expected_vs_actual": q2(expected - closing),
        },
    }


@login_required
@require_http_methods(["GET", "POST"])
def cash_statement(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        business, _ = _scoped_rows(request)
        if not business:
            messages.error(request, "Select an active business before recording cash transactions.")
            return redirect("wallet:cash_statement")
        if not _staff(request.user):
            return HttpResponse("Not allowed", status=403)

        direction = request.POST.get("direction") or CashBankTransaction.Direction.CASH_IN
        if direction not in CashBankTransaction.Direction.values:
            messages.error(request, "Choose Cash In or Cash Out.")
            return redirect("wallet:cash_statement")
        category = (request.POST.get("category") or "Other income").strip()
        amount = _money(request.POST.get("amount"))
        if amount <= 0:
            messages.error(request, "Enter an amount greater than zero.")
            return redirect("wallet:cash_statement")
        tx_date = _date(request.POST.get("date")) or timezone.localdate()
        CashBankTransaction.objects.create(
            business=business,
            date=tx_date,
            direction=direction,
            category=category,
            payment_method=request.POST.get("payment_method") or CashBankTransaction.PaymentMethod.CASH,
            amount=amount,
            description=(request.POST.get("description") or request.POST.get("note") or "").strip(),
            related_sale_reference=(request.POST.get("related_sale_reference") or "").strip(),
            created_by=request.user,
        )
        messages.success(request, "Cash statement updated.")
        return redirect("wallet:cash_statement")

    ctx = _summary(request)
    ctx.update(
        {
            "cash_in_categories": CASH_IN_CATEGORIES,
            "cash_out_categories": CASH_OUT_CATEGORIES,
            "payment_methods": CashBankTransaction.PaymentMethod.choices,
            "directions": CashBankTransaction.Direction.choices,
            "can_manage_cash": _staff(request.user),
        }
    )
    return render(request, "wallet/cash_statement.html", ctx)


@login_required
@require_http_methods(["GET"])
def cash_statement_csv(request: HttpRequest) -> HttpResponse:
    ctx = _summary(request)
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="cash_bank_statement.csv"'
    writer = csv.writer(resp)
    writer.writerow(["date", "type", "category", "method", "amount", "balance_after", "description", "created_by"])
    for row in ctx["rows"]:
        writer.writerow([
            row.date.isoformat(),
            row.get_direction_display(),
            row.category,
            row.get_payment_method_display(),
            f"{row.amount:.2f}",
            f"{row.balance_after:.2f}",
            row.description,
            getattr(row.created_by, "username", "") if row.created_by_id else "",
        ])
    return resp


@login_required
@require_http_methods(["GET"])
def cash_statement_pdf(request: HttpRequest) -> HttpResponse:
    ctx = _summary(request)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return cash_statement_csv(request)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=28)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], textColor=colors.HexColor("#065f46"), fontSize=17)
    elements = [
        Paragraph("Emajinet Cash & Bank Statement", title_style),
        Paragraph(
            f"{getattr(ctx['business'], 'name', 'Business')} | {ctx['period_start']} to {ctx['period_end']}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]
    summary = ctx["summary"]
    elements.append(
        Table(
            [
                ["Opening", "Cash In", "Cash Out", "Closing", "Available Cash"],
                [
                    f"MWK {summary['opening_balance']:,.2f}",
                    f"MWK {summary['total_cash_in']:,.2f}",
                    f"MWK {summary['total_cash_out']:,.2f}",
                    f"MWK {summary['closing_balance']:,.2f}",
                    f"MWK {summary['total_available_cash']:,.2f}",
                ],
            ],
            style=[
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#064e3b")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbf7d0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ],
        )
    )
    elements.append(Spacer(1, 12))
    table_rows = [["Date", "Type", "Category", "Method", "Amount", "Balance", "Note"]]
    for row in ctx["rows"][:80]:
        table_rows.append([
            row.date.isoformat(),
            row.get_direction_display(),
            row.category,
            row.get_payment_method_display(),
            f"MWK {row.amount:,.2f}",
            f"MWK {row.balance_after:,.2f}",
            (row.description or "")[:48],
        ])
    elements.append(
        Table(
            table_rows,
            repeatRows=1,
            style=[
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("PADDING", (0, 0), (-1, -1), 5),
            ],
        )
    )
    doc.build(elements)
    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="cash_bank_statement.pdf"'
    return resp
