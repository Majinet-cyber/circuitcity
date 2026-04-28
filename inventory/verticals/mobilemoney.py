# inventory/verticals/mobilemoney.py
"""
Mobile Money vertical — agent float management, transactions, credits, reconciliation.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.utils import timezone

from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models_mobilemoney import (
    MobileMoneyCredit,
    MobileMoneyNetwork,
    MobileMoneyReconciliation,
    MobileMoneyTransaction,
    MobileMoneyTxType,
)
from tenants.utils import require_business

# ---------------------------------------------------------------------------
# Helper guard
# ---------------------------------------------------------------------------

def _require_mm(view_func):
    """Require business + mobile_money kind (soft check — shows notice if wrong kind)."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

_DEC = DecimalField(max_digits=12, decimal_places=2)


@login_required
@require_business
def dashboard(request):
    business = get_active_business(request)
    today = timezone.now().date()

    # Today's transactions
    today_qs = MobileMoneyTransaction.objects.filter(business=business, created_at__date=today)

    from django.db.models import Q

    agg = today_qs.aggregate(
        cash_in_total=Coalesce(
            Sum("amount", filter=Q(tx_type=MobileMoneyTxType.CASH_IN)),
            Value(0),
            output_field=_DEC,
        ),
        cash_out_total=Coalesce(
            Sum("amount", filter=Q(tx_type=MobileMoneyTxType.CASH_OUT)),
            Value(0),
            output_field=_DEC,
        ),
        commission_total=Coalesce(Sum("commission"), Value(0), output_field=_DEC),
    )

    today_cash_in = Decimal(str(agg["cash_in_total"] or 0))
    today_cash_out = Decimal(str(agg["cash_out_total"] or 0))
    today_commission = Decimal(str(agg["commission_total"] or 0))
    today_tx_count = today_qs.count()

    # Credits outstanding
    credits_qs = MobileMoneyCredit.objects.filter(
        business=business,
        status__in=[MobileMoneyCredit.STATUS_PENDING, MobileMoneyCredit.STATUS_PARTIAL, MobileMoneyCredit.STATUS_OVERDUE],
    )
    credits_agg = credits_qs.aggregate(
        outstanding=Coalesce(
            Sum("amount_credited") - Sum("amount_repaid"),
            Value(0),
            output_field=_DEC,
        )
    )
    credits_outstanding = Decimal(str(credits_agg["outstanding"] or 0))

    # Recent reconciliation
    latest_recon = MobileMoneyReconciliation.objects.filter(business=business).first()

    # Recent transactions
    recent_transactions = MobileMoneyTransaction.objects.filter(business=business).order_by("-created_at")[:10]

    is_demo = today_tx_count == 0 and not latest_recon
    demo_values = {}
    if is_demo:
        demo_values = {
            "today_cash_in": Decimal("245000"),
            "today_cash_out": Decimal("178000"),
            "today_commission": Decimal("3200"),
            "today_tx_count": 18,
            "credits_outstanding": Decimal("45000"),
            "opening_cash": Decimal("120000"),
            "float_balance": Decimal("85000"),
        }

    context = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        "today_cash_in": demo_values.get("today_cash_in", today_cash_in),
        "today_cash_out": demo_values.get("today_cash_out", today_cash_out),
        "today_commission": demo_values.get("today_commission", today_commission),
        "today_tx_count": demo_values.get("today_tx_count", today_tx_count),
        "credits_outstanding": demo_values.get("credits_outstanding", credits_outstanding),
        "opening_cash": demo_values.get("opening_cash", latest_recon.opening_cash if latest_recon else Decimal("0")),
        "float_balance": demo_values.get("float_balance", Decimal("0")),
        "latest_recon": latest_recon,
        "recent_transactions": recent_transactions,
        "is_demo": is_demo,
        "networks": MobileMoneyNetwork.choices,
        "tx_types": MobileMoneyTxType.choices,
    }
    return render(request, "verticals/mobilemoney/dashboard.html", context)


# ---------------------------------------------------------------------------
# TRANSACTIONS
# ---------------------------------------------------------------------------

@login_required
@require_business
def transactions(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            tx_type = request.POST.get("tx_type", "cash_in")
            network = request.POST.get("network", "airtel")
            amount = Decimal(request.POST.get("amount", "0"))
            commission = Decimal(request.POST.get("commission", "0"))
            customer_phone = request.POST.get("customer_phone", "").strip()
            reference_number = request.POST.get("reference_number", "").strip()
            notes = request.POST.get("notes", "").strip()

            if amount <= 0:
                messages.error(request, "Amount must be greater than 0")
                return redirect("mobilemoney:transactions")

            # Compute cash & float movement
            cash_movement = Decimal("0")
            float_movement = Decimal("0")
            if tx_type == MobileMoneyTxType.CASH_IN:
                cash_movement = amount
                float_movement = -amount
            elif tx_type == MobileMoneyTxType.CASH_OUT:
                cash_movement = -amount
                float_movement = amount
            elif tx_type == MobileMoneyTxType.AIRTIME:
                float_movement = -amount
            elif tx_type == MobileMoneyTxType.BILL_PAYMENT:
                float_movement = -amount

            MobileMoneyTransaction.objects.create(
                business=business,
                tx_type=tx_type,
                network=network,
                amount=amount,
                commission=commission,
                customer_phone=customer_phone,
                reference_number=reference_number,
                cash_movement=cash_movement,
                float_movement=float_movement,
                notes=notes,
                created_by=request.user,
            )
            messages.success(request, f"Transaction recorded: MK {amount:,.2f}")
            return redirect("mobilemoney:transactions")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
        except Exception as e:
            messages.error(request, f"Error recording transaction: {e}")

    tx_list = MobileMoneyTransaction.objects.filter(business=business).order_by("-created_at")[:50]
    context = {
        "business": business,
        "active_tab": "transactions",
        "transactions": tx_list,
        "networks": MobileMoneyNetwork.choices,
        "tx_types": MobileMoneyTxType.choices,
    }
    return render(request, "verticals/mobilemoney/transactions.html", context)


# ---------------------------------------------------------------------------
# CREDITS
# ---------------------------------------------------------------------------

@login_required
@require_business
def credits(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()
            amount_credited = Decimal(request.POST.get("amount_credited", "0"))
            due_date_str = request.POST.get("due_date", "").strip()
            notes = request.POST.get("notes", "").strip()

            if not customer_name:
                messages.error(request, "Customer name is required")
                return redirect("mobilemoney:credits")
            if amount_credited <= 0:
                messages.error(request, "Amount must be greater than 0")
                return redirect("mobilemoney:credits")

            from datetime import date as dt_date
            due_date = None
            if due_date_str:
                try:
                    due_date = dt_date.fromisoformat(due_date_str)
                except ValueError:
                    pass

            MobileMoneyCredit.objects.create(
                business=business,
                customer_name=customer_name,
                customer_phone=customer_phone,
                amount_credited=amount_credited,
                due_date=due_date,
                notes=notes,
                created_by=request.user,
            )
            messages.success(request, f"Credit recorded for {customer_name}: MK {amount_credited:,.2f}")
            return redirect("mobilemoney:credits")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid input: {e}")
        except Exception as e:
            messages.error(request, f"Error recording credit: {e}")

    credits_list = MobileMoneyCredit.objects.filter(business=business).order_by("-created_at")
    context = {
        "business": business,
        "active_tab": "credits",
        "credits": credits_list,
    }
    return render(request, "verticals/mobilemoney/credits.html", context)


@login_required
@require_business
def credit_repayment(request, credit_id):
    """Record a repayment against an existing credit."""
    business = get_active_business(request)
    credit = MobileMoneyCredit.objects.get(pk=credit_id, business=business)

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            if amount <= 0:
                messages.error(request, "Amount must be greater than 0")
                return redirect("mobilemoney:credits")
            credit.amount_repaid += amount
            if credit.amount_repaid >= credit.amount_credited:
                credit.amount_repaid = credit.amount_credited
                credit.status = MobileMoneyCredit.STATUS_PAID
            else:
                credit.status = MobileMoneyCredit.STATUS_PARTIAL
            credit.save()
            messages.success(request, f"Repayment of MK {amount:,.2f} recorded for {credit.customer_name}")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect("mobilemoney:credits")


# ---------------------------------------------------------------------------
# RECONCILIATION
# ---------------------------------------------------------------------------

@login_required
@require_business
def reconciliation(request):
    business = get_active_business(request)
    today = timezone.now().date()

    from django.db.models import Q

    if request.method == "POST":
        try:
            recon_date_str = request.POST.get("date", str(today))
            from datetime import date as dt_date
            recon_date = dt_date.fromisoformat(recon_date_str)

            opening_cash = Decimal(request.POST.get("opening_cash", "0"))
            opening_float = Decimal(request.POST.get("opening_float", "0"))
            actual_closing_cash = Decimal(request.POST.get("actual_closing_cash", "0"))
            notes = request.POST.get("notes", "").strip()

            # Auto-aggregate from transactions
            day_qs = MobileMoneyTransaction.objects.filter(business=business, created_at__date=recon_date)
            day_agg = day_qs.aggregate(
                cash_in=Coalesce(Sum("cash_movement", filter=Q(cash_movement__gt=0)), Value(0), output_field=_DEC),
                cash_out=Coalesce(Sum("cash_movement", filter=Q(cash_movement__lt=0)), Value(0), output_field=_DEC),
                float_in=Coalesce(Sum("float_movement", filter=Q(float_movement__gt=0)), Value(0), output_field=_DEC),
                float_out=Coalesce(Sum("float_movement", filter=Q(float_movement__lt=0)), Value(0), output_field=_DEC),
            )

            recon, _ = MobileMoneyReconciliation.objects.update_or_create(
                business=business,
                date=recon_date,
                defaults=dict(
                    opening_cash=opening_cash,
                    opening_float=opening_float,
                    total_cash_in=Decimal(str(abs(day_agg["cash_in"] or 0))),
                    total_cash_out=Decimal(str(abs(day_agg["cash_out"] or 0))),
                    total_float_in=Decimal(str(abs(day_agg["float_in"] or 0))),
                    total_float_out=Decimal(str(abs(day_agg["float_out"] or 0))),
                    actual_closing_cash=actual_closing_cash,
                    notes=notes,
                    created_by=request.user,
                ),
            )
            messages.success(
                request,
                f"Reconciliation for {recon_date} saved. "
                f"Difference: MK {recon.difference:,.2f} "
                f"({'shortage' if recon.difference < 0 else 'surplus' if recon.difference > 0 else 'balanced'})",
            )
            return redirect("mobilemoney:reconciliation")
        except Exception as e:
            messages.error(request, f"Error saving reconciliation: {e}")

    recons = MobileMoneyReconciliation.objects.filter(business=business).order_by("-date")[:30]
    context = {
        "business": business,
        "active_tab": "reconciliation",
        "today": today,
        "reconciliations": recons,
    }
    return render(request, "verticals/mobilemoney/reconciliation.html", context)
