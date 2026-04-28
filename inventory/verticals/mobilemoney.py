# inventory/verticals/mobilemoney.py
"""
Mobile Money vertical — agent float management, transactions, credits,
commissions, reconciliation, and inter-agent settlements.

Real operational tool for Airtel Money and TNM Mpamba agents in Malawi.
"""
from __future__ import annotations

from datetime import date as dt_date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import DecimalField, Q, Sum, Value, Count
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.helpers import get_active_business
from inventory.models_mobilemoney import (
    AgentSettlement,
    AgentSettlementType,
    CommissionRule,
    CommissionRuleType,
    CreditType,
    MobileMoneyCredit,
    MobileMoneyNetwork,
    MobileMoneyReconciliation,
    MobileMoneyTransaction,
    MobileMoneyTxType,
    TX_MOVEMENTS,
)
from tenants.utils import require_business

# ── Shared helpers ────────────────────────────────────────────────────────────

_DEC = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Decimal("0.00")


def _coalesce_sum(qs, field: str, filter_q=None) -> Decimal:
    kw = {f"total": Coalesce(Sum(field, filter=filter_q) if filter_q else Sum(field), Value(0), output_field=_DEC)}
    return Decimal(str(qs.aggregate(**kw)["total"] or 0))


def _compute_movements(tx_type: str, amount: Decimal) -> tuple[Decimal, Decimal]:
    """Return (cash_movement, float_movement) for a transaction type."""
    signs = TX_MOVEMENTS.get(tx_type, (0, 0))
    return Decimal(str(signs[0])) * amount, Decimal(str(signs[1])) * amount


def _auto_commission(business, network: str, tx_type: str, amount: Decimal) -> Decimal:
    """
    Calculate commission using active CommissionRule for this business/network/tx_type.
    Returns 0 if no rule found.
    """
    rules = CommissionRule.objects.filter(
        business=business, network=network, tx_type=tx_type, is_active=True,
        min_amount__lte=amount,
    ).filter(Q(max_amount__isnull=True) | Q(max_amount__gte=amount)).order_by("min_amount")
    for rule in rules:
        calc = rule.calculate(amount)
        if calc > 0:
            return calc
    return _ZERO


def _get_float_balance(business) -> Decimal:
    """Current e-float position = sum of all float_movement records."""
    return _coalesce_sum(
        MobileMoneyTransaction.objects.filter(business=business),
        "float_movement",
    )


def _get_cash_balance(business, since: dt_date | None = None) -> Decimal:
    """Current cash position from last reconciliation onward, or all time."""
    qs = MobileMoneyTransaction.objects.filter(business=business)
    if since:
        qs = qs.filter(created_at__date__gte=since)
    return _coalesce_sum(qs, "cash_movement")


def _generate_insights(ctx: dict) -> list[str]:
    """Generate smart operational insights based on dashboard context."""
    insights = []
    diff = ctx.get("recon_difference", _ZERO)
    if diff < -Decimal("5000"):
        insights.append(f"You are short by MWK {abs(diff):,.0f} — check your reconciliation")
    elif diff > Decimal("5000"):
        insights.append(f"You have an overage of MWK {diff:,.0f} — verify your cash count")

    overdue = ctx.get("overdue_count", 0)
    if overdue:
        insights.append(f"{overdue} overdue credit{'s' if overdue != 1 else ''} need follow-up")

    float_bal = ctx.get("float_balance", _ZERO)
    if _ZERO < float_bal < Decimal("20000"):
        insights.append("Float is low — consider topping up before evening traffic")

    airtel_comm = ctx.get("airtel_commission_today", _ZERO)
    tnm_comm = ctx.get("tnm_commission_today", _ZERO)
    if airtel_comm > tnm_comm and tnm_comm > 0:
        insights.append("Airtel Money generated more commission today")
    elif tnm_comm > airtel_comm and airtel_comm > 0:
        insights.append("TNM Mpamba generated more commission today")

    total_debts = ctx.get("total_agent_debts", _ZERO)
    if total_debts > Decimal("50000"):
        insights.append(f"Agent debts total MWK {total_debts:,.0f} — plan repayment soon")

    return insights


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@login_required
@require_business
def dashboard(request):
    business = get_active_business(request)
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    today_qs = MobileMoneyTransaction.objects.filter(business=business, created_at__date=today)

    # ── Today's aggregates ──────────────────────────────────────────────────
    today_agg = today_qs.aggregate(
        cash_in=Coalesce(Sum("amount", filter=Q(tx_type__in=[MobileMoneyTxType.CASH_IN, MobileMoneyTxType.SEND_MONEY])), Value(0), output_field=_DEC),
        cash_out=Coalesce(Sum("amount", filter=Q(tx_type__in=[MobileMoneyTxType.CASH_OUT, MobileMoneyTxType.RECEIVE_MONEY])), Value(0), output_field=_DEC),
        commission_total=Coalesce(Sum("commission"), Value(0), output_field=_DEC),
        airtel_commission=Coalesce(Sum("commission", filter=Q(network=MobileMoneyNetwork.AIRTEL)), Value(0), output_field=_DEC),
        tnm_commission=Coalesce(Sum("commission", filter=Q(network=MobileMoneyNetwork.TNM)), Value(0), output_field=_DEC),
        tx_count=Count("id"),
    )
    today_cash_in = Decimal(str(today_agg["cash_in"] or 0))
    today_cash_out = Decimal(str(today_agg["cash_out"] or 0))
    today_commission = Decimal(str(today_agg["commission_total"] or 0))
    today_tx_count = today_agg["tx_count"] or 0
    airtel_commission_today = Decimal(str(today_agg["airtel_commission"] or 0))
    tnm_commission_today = Decimal(str(today_agg["tnm_commission"] or 0))

    # ── Balances ────────────────────────────────────────────────────────────
    float_balance = _get_float_balance(business)

    # Cash balance since last reconciliation
    latest_recon = MobileMoneyReconciliation.objects.filter(business=business).first()
    cash_since = latest_recon.date + timedelta(days=1) if latest_recon else None
    cash_movement_since_recon = _get_cash_balance(business, since=cash_since)
    base_cash = latest_recon.actual_closing_cash if latest_recon else _ZERO
    cash_in_hand = base_cash + cash_movement_since_recon

    recon_difference = latest_recon.difference if latest_recon else _ZERO

    # ── Credits & debts ─────────────────────────────────────────────────────
    open_statuses = [MobileMoneyCredit.STATUS_PENDING, MobileMoneyCredit.STATUS_PARTIAL, MobileMoneyCredit.STATUS_OVERDUE]
    credits_qs = MobileMoneyCredit.objects.filter(
        business=business, credit_type=CreditType.CUSTOMER_CREDIT, status__in=open_statuses,
    )
    debts_qs = MobileMoneyCredit.objects.filter(
        business=business, credit_type=CreditType.AGENT_DEBT, status__in=open_statuses,
    )
    credits_agg = credits_qs.aggregate(
        total=Coalesce(Sum("amount_credited") - Sum("amount_repaid"), Value(0), output_field=_DEC)
    )
    debts_agg = debts_qs.aggregate(
        total=Coalesce(Sum("amount_credited") - Sum("amount_repaid"), Value(0), output_field=_DEC)
    )
    credits_outstanding = Decimal(str(credits_agg["total"] or 0))
    total_agent_debts = Decimal(str(debts_agg["total"] or 0))
    overdue_count = MobileMoneyCredit.objects.filter(
        business=business,
        status=MobileMoneyCredit.STATUS_OVERDUE,
    ).count()

    # ── Weekly / Monthly commissions ────────────────────────────────────────
    all_txns = MobileMoneyTransaction.objects.filter(business=business)
    week_commission = Decimal(str(
        all_txns.filter(created_at__date__gte=week_start).aggregate(
            total=Coalesce(Sum("commission"), Value(0), output_field=_DEC)
        )["total"] or 0
    ))
    month_commission = Decimal(str(
        all_txns.filter(created_at__date__gte=month_start).aggregate(
            total=Coalesce(Sum("commission"), Value(0), output_field=_DEC)
        )["total"] or 0
    ))

    # ── Net balance position ─────────────────────────────────────────────────
    net_balance = cash_in_hand + float_balance - total_agent_debts

    # ── Recent transactions ──────────────────────────────────────────────────
    recent_transactions = MobileMoneyTransaction.objects.filter(
        business=business
    ).order_by("-created_at")[:10]

    # ── Agent settlements summary ────────────────────────────────────────────
    pending_settlements = AgentSettlement.objects.filter(business=business, is_settled=False).count()

    # ── Demo mode ───────────────────────────────────────────────────────────
    is_demo = today_tx_count == 0 and not latest_recon
    if is_demo:
        today_cash_in = Decimal("245000")
        today_cash_out = Decimal("178000")
        today_commission = Decimal("3200")
        today_tx_count = 18
        credits_outstanding = Decimal("45000")
        total_agent_debts = Decimal("20000")
        float_balance = Decimal("85000")
        cash_in_hand = Decimal("120000")
        net_balance = Decimal("185000")
        week_commission = Decimal("18500")
        month_commission = Decimal("67000")
        airtel_commission_today = Decimal("2100")
        tnm_commission_today = Decimal("1100")
        overdue_count = 2
        recon_difference = _ZERO
        pending_settlements = 1

    ctx = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        # Balances
        "cash_in_hand": cash_in_hand,
        "float_balance": float_balance,
        "net_balance": net_balance,
        # Today
        "today_cash_in": today_cash_in,
        "today_cash_out": today_cash_out,
        "today_commission": today_commission,
        "today_tx_count": today_tx_count,
        # Commission breakdown
        "airtel_commission_today": airtel_commission_today,
        "tnm_commission_today": tnm_commission_today,
        "week_commission": week_commission,
        "month_commission": month_commission,
        # Credits / debts
        "credits_outstanding": credits_outstanding,
        "total_agent_debts": total_agent_debts,
        "overdue_count": overdue_count,
        # Reconciliation
        "latest_recon": latest_recon,
        "recon_difference": recon_difference,
        # Settlements
        "pending_settlements": pending_settlements,
        # Recent activity
        "recent_transactions": recent_transactions,
        "is_demo": is_demo,
        # Insights
        "insights": _generate_insights({
            "recon_difference": recon_difference,
            "overdue_count": overdue_count,
            "float_balance": float_balance,
            "airtel_commission_today": airtel_commission_today,
            "tnm_commission_today": tnm_commission_today,
            "total_agent_debts": total_agent_debts,
        }),
    }
    return render(request, "verticals/mobilemoney/dashboard.html", ctx)


# ── TRANSACTIONS ─────────────────────────────────────────────────────────────

@login_required
@require_business
def transactions(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            tx_type = request.POST.get("tx_type", "cash_in")
            network = request.POST.get("network", "airtel")
            amount_raw = request.POST.get("amount", "0").replace(",", "")
            amount = Decimal(amount_raw)
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()
            reference_number = request.POST.get("reference_number", "").strip()
            notes = request.POST.get("notes", "").strip()
            charges_raw = request.POST.get("charges", "0").replace(",", "")
            charges = Decimal(charges_raw or "0")

            if amount <= 0:
                messages.error(request, "Amount must be greater than 0.")
                return redirect("mobilemoney:transactions")

            # Commission: use submitted value, or auto-calculate if blank/zero
            commission_raw = request.POST.get("commission", "").strip().replace(",", "")
            if commission_raw:
                commission = Decimal(commission_raw)
            else:
                commission = _auto_commission(business, network, tx_type, amount)

            # Movements
            cash_movement, float_movement = _compute_movements(tx_type, amount)

            # Prevent impossible negative float (soft guard — show warning)
            current_float = _get_float_balance(business)
            if float_movement < 0 and (current_float + float_movement) < -Decimal("500000"):
                messages.error(
                    request,
                    f"This transaction would make float go below -MWK 500,000. "
                    f"Current float: MWK {current_float:,.0f}. Check your entries."
                )
                return redirect("mobilemoney:transactions")

            with db_transaction.atomic():
                MobileMoneyTransaction.objects.create(
                    business=business,
                    tx_type=tx_type,
                    network=network,
                    amount=amount,
                    commission=commission,
                    charges=charges,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    reference_number=reference_number,
                    cash_movement=cash_movement,
                    float_movement=float_movement,
                    notes=notes,
                    created_by=request.user,
                )

            net_effect = ""
            if cash_movement > 0:
                net_effect = f" | Cash +MWK {cash_movement:,.0f}"
            elif cash_movement < 0:
                net_effect = f" | Cash -MWK {abs(cash_movement):,.0f}"
            if float_movement > 0:
                net_effect += f" | Float +MWK {float_movement:,.0f}"
            elif float_movement < 0:
                net_effect += f" | Float -MWK {abs(float_movement):,.0f}"

            messages.success(
                request,
                f"{dict(MobileMoneyTxType.choices).get(tx_type, tx_type)} recorded: "
                f"MWK {amount:,.0f}{net_effect}"
            )
            return redirect("mobilemoney:transactions")
        except (ValueError, TypeError) as exc:
            messages.error(request, f"Invalid input: {exc}")
        except Exception as exc:
            messages.error(request, f"Error recording transaction: {exc}")

    tx_list = MobileMoneyTransaction.objects.filter(business=business).order_by("-created_at")[:60]
    float_balance = _get_float_balance(business)

    ctx = {
        "business": business,
        "active_tab": "transactions",
        "transactions": tx_list,
        "networks": MobileMoneyNetwork.choices,
        "tx_types": MobileMoneyTxType.choices,
        "float_balance": float_balance,
        "tx_movements_info": {
            MobileMoneyTxType.SEND_MONEY: "Cash IN, Float OUT",
            MobileMoneyTxType.RECEIVE_MONEY: "Cash OUT, Float IN",
            MobileMoneyTxType.CASH_IN: "Cash IN, Float OUT",
            MobileMoneyTxType.CASH_OUT: "Cash OUT, Float IN",
            MobileMoneyTxType.FLOAT_PURCHASE: "Cash OUT, Float IN",
            MobileMoneyTxType.AIRTIME: "Float OUT only",
            MobileMoneyTxType.BILL_PAYMENT: "Float OUT only",
            MobileMoneyTxType.REVERSAL: "No automatic movement",
            MobileMoneyTxType.FAILED: "No movement",
            MobileMoneyTxType.CORRECTION: "No automatic movement",
            MobileMoneyTxType.ADJUSTMENT: "No automatic movement",
        },
    }
    return render(request, "verticals/mobilemoney/transactions.html", ctx)


# ── CREDITS / DEBTS ───────────────────────────────────────────────────────────

@login_required
@require_business
def credits(request):
    business = get_active_business(request)
    today = timezone.now().date()

    if request.method == "POST":
        action = request.POST.get("action", "create")

        if action == "create":
            try:
                credit_type = request.POST.get("credit_type", CreditType.CUSTOMER_CREDIT)
                customer_name = request.POST.get("customer_name", "").strip()
                customer_phone = request.POST.get("customer_phone", "").strip()
                amount_str = request.POST.get("amount_credited", "0").replace(",", "")
                amount_credited = Decimal(amount_str)
                due_date_str = request.POST.get("due_date", "").strip()
                reason = request.POST.get("reason", "").strip()
                notes = request.POST.get("notes", "").strip()

                if not customer_name:
                    messages.error(request, "Name is required.")
                    return redirect("mobilemoney:credits")
                if amount_credited <= 0:
                    messages.error(request, "Amount must be greater than 0.")
                    return redirect("mobilemoney:credits")

                due_date = None
                if due_date_str:
                    try:
                        due_date = dt_date.fromisoformat(due_date_str)
                    except ValueError:
                        pass

                MobileMoneyCredit.objects.create(
                    business=business,
                    credit_type=credit_type,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    amount_credited=amount_credited,
                    due_date=due_date,
                    reason=reason,
                    notes=notes,
                    created_by=request.user,
                )
                type_label = "Credit" if credit_type == CreditType.CUSTOMER_CREDIT else "Debt"
                messages.success(
                    request,
                    f"{type_label} recorded for {customer_name}: MWK {amount_credited:,.0f}"
                )
            except (ValueError, TypeError) as exc:
                messages.error(request, f"Invalid input: {exc}")
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        return redirect("mobilemoney:credits")

    open_statuses = [MobileMoneyCredit.STATUS_PENDING, MobileMoneyCredit.STATUS_PARTIAL, MobileMoneyCredit.STATUS_OVERDUE]
    customer_credits = MobileMoneyCredit.objects.filter(
        business=business, credit_type=CreditType.CUSTOMER_CREDIT
    ).order_by("-created_at")
    agent_debts = MobileMoneyCredit.objects.filter(
        business=business, credit_type=CreditType.AGENT_DEBT
    ).order_by("-created_at")

    credits_summary = customer_credits.filter(status__in=open_statuses).aggregate(
        total=Coalesce(Sum("amount_credited") - Sum("amount_repaid"), Value(0), output_field=_DEC)
    )
    debts_summary = agent_debts.filter(status__in=open_statuses).aggregate(
        total=Coalesce(Sum("amount_credited") - Sum("amount_repaid"), Value(0), output_field=_DEC)
    )
    overdue_credits = customer_credits.filter(status=MobileMoneyCredit.STATUS_OVERDUE)
    overdue_debts = agent_debts.filter(status=MobileMoneyCredit.STATUS_OVERDUE)

    ctx = {
        "business": business,
        "active_tab": "credits",
        "today": today,
        "customer_credits": customer_credits,
        "agent_debts": agent_debts,
        "credits_outstanding": Decimal(str(credits_summary["total"] or 0)),
        "debts_outstanding": Decimal(str(debts_summary["total"] or 0)),
        "overdue_credits": overdue_credits,
        "overdue_debts": overdue_debts,
        "credit_type_choices": CreditType.choices,
    }
    return render(request, "verticals/mobilemoney/credits.html", ctx)


@login_required
@require_business
def credit_repayment(request, credit_id):
    """Record a repayment against an existing credit/debt."""
    business = get_active_business(request)
    credit = get_object_or_404(MobileMoneyCredit, pk=credit_id, business=business)

    if request.method == "POST":
        try:
            amount_raw = request.POST.get("amount", "0").replace(",", "")
            amount = Decimal(amount_raw)
            if amount <= 0:
                messages.error(request, "Repayment amount must be greater than 0.")
                return redirect("mobilemoney:credits")
            credit.amount_repaid += amount
            credit.update_status()
            credit.save()
            messages.success(
                request,
                f"Repayment of MWK {amount:,.0f} recorded for {credit.customer_name}. "
                f"Balance remaining: MWK {credit.balance:,.0f}"
            )
        except Exception as exc:
            messages.error(request, f"Error: {exc}")
    return redirect("mobilemoney:credits")


# ── COMMISSIONS ───────────────────────────────────────────────────────────────

@login_required
@require_business
def commissions(request):
    business = get_active_business(request)
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "add_rule":
            try:
                network = request.POST.get("network", "airtel")
                tx_type = request.POST.get("tx_type", "cash_in")
                rule_type = request.POST.get("rule_type", "percentage")
                fixed_amount = Decimal(request.POST.get("fixed_amount", "0") or "0")
                pct_raw = request.POST.get("percentage_rate", "0") or "0"
                percentage_rate = Decimal(pct_raw)
                min_amount = Decimal(request.POST.get("min_amount", "0") or "0")
                max_amount_raw = request.POST.get("max_amount", "").strip()
                max_amount = Decimal(max_amount_raw) if max_amount_raw else None

                CommissionRule.objects.create(
                    business=business,
                    network=network,
                    tx_type=tx_type,
                    rule_type=rule_type,
                    fixed_amount=fixed_amount,
                    percentage_rate=percentage_rate,
                    min_amount=min_amount,
                    max_amount=max_amount,
                )
                messages.success(request, "Commission rule added.")
            except Exception as exc:
                messages.error(request, f"Error adding rule: {exc}")
        elif action == "deactivate_rule":
            rule_id = request.POST.get("rule_id")
            try:
                rule = CommissionRule.objects.get(pk=rule_id, business=business)
                rule.is_active = False
                rule.save(update_fields=["is_active"])
                messages.success(request, "Commission rule deactivated.")
            except CommissionRule.DoesNotExist:
                messages.error(request, "Rule not found.")
        return redirect("mobilemoney:commissions")

    all_txns = MobileMoneyTransaction.objects.filter(business=business)

    # Period summaries
    def _period_commission(qs):
        return Decimal(str(qs.aggregate(t=Coalesce(Sum("commission"), Value(0), output_field=_DEC))["t"] or 0))

    today_comm = _period_commission(all_txns.filter(created_at__date=today))
    week_comm = _period_commission(all_txns.filter(created_at__date__gte=week_start))
    month_comm = _period_commission(all_txns.filter(created_at__date__gte=month_start))
    all_time_comm = _period_commission(all_txns)

    # Provider breakdown (month)
    month_qs = all_txns.filter(created_at__date__gte=month_start)
    airtel_month = _period_commission(month_qs.filter(network=MobileMoneyNetwork.AIRTEL))
    tnm_month = _period_commission(month_qs.filter(network=MobileMoneyNetwork.TNM))

    # TX type breakdown (month)
    tx_breakdown = (
        month_qs.values("tx_type")
        .annotate(total_comm=Coalesce(Sum("commission"), Value(0), output_field=_DEC), count=Count("id"))
        .order_by("-total_comm")
    )
    tx_label_map = dict(MobileMoneyTxType.choices)
    for row in tx_breakdown:
        row["tx_label"] = tx_label_map.get(row["tx_type"], row["tx_type"])

    # Active commission rules
    rules = CommissionRule.objects.filter(business=business).order_by("network", "tx_type", "min_amount")

    ctx = {
        "business": business,
        "active_tab": "commissions",
        "today": today,
        "today_commission": today_comm,
        "week_commission": week_comm,
        "month_commission": month_comm,
        "all_time_commission": all_time_comm,
        "airtel_month_commission": airtel_month,
        "tnm_month_commission": tnm_month,
        "tx_breakdown": list(tx_breakdown),
        "commission_rules": rules,
        "networks": MobileMoneyNetwork.choices,
        "tx_types": MobileMoneyTxType.choices,
        "rule_types": CommissionRuleType.choices,
    }
    return render(request, "verticals/mobilemoney/commissions.html", ctx)


# ── RECONCILIATION ────────────────────────────────────────────────────────────

@login_required
@require_business
def reconciliation(request):
    business = get_active_business(request)
    today = timezone.now().date()

    if request.method == "POST":
        try:
            recon_date_str = request.POST.get("date", str(today))
            recon_date = dt_date.fromisoformat(recon_date_str)

            opening_cash = Decimal(request.POST.get("opening_cash", "0").replace(",", "") or "0")
            opening_float = Decimal(request.POST.get("opening_float", "0").replace(",", "") or "0")
            actual_closing_cash = Decimal(request.POST.get("actual_closing_cash", "0").replace(",", "") or "0")
            notes = request.POST.get("notes", "").strip()

            # Auto-aggregate from transactions on this date
            day_qs = MobileMoneyTransaction.objects.filter(business=business, created_at__date=recon_date)
            day_agg = day_qs.aggregate(
                cash_in=Coalesce(Sum("cash_movement", filter=Q(cash_movement__gt=0)), Value(0), output_field=_DEC),
                cash_out_neg=Coalesce(Sum("cash_movement", filter=Q(cash_movement__lt=0)), Value(0), output_field=_DEC),
                float_in=Coalesce(Sum("float_movement", filter=Q(float_movement__gt=0)), Value(0), output_field=_DEC),
                float_out_neg=Coalesce(Sum("float_movement", filter=Q(float_movement__lt=0)), Value(0), output_field=_DEC),
                commissions=Coalesce(Sum("commission"), Value(0), output_field=_DEC),
            )

            recon, _ = MobileMoneyReconciliation.objects.update_or_create(
                business=business,
                date=recon_date,
                defaults=dict(
                    opening_cash=opening_cash,
                    opening_float=opening_float,
                    total_cash_in=Decimal(str(abs(day_agg["cash_in"] or 0))),
                    total_cash_out=Decimal(str(abs(day_agg["cash_out_neg"] or 0))),
                    total_float_in=Decimal(str(abs(day_agg["float_in"] or 0))),
                    total_float_out=Decimal(str(abs(day_agg["float_out_neg"] or 0))),
                    total_commissions=Decimal(str(day_agg["commissions"] or 0)),
                    actual_closing_cash=actual_closing_cash,
                    notes=notes,
                    created_by=request.user,
                ),
            )

            diff = recon.difference
            if diff == 0:
                status_msg = "Balanced"
            elif diff < 0:
                status_msg = f"Shortage of MWK {abs(diff):,.0f}"
            else:
                status_msg = f"Overage of MWK {diff:,.0f}"

            messages.success(request, f"Reconciliation for {recon_date} saved. {status_msg}.")
            return redirect("mobilemoney:reconciliation")
        except Exception as exc:
            messages.error(request, f"Error saving reconciliation: {exc}")

    recons = MobileMoneyReconciliation.objects.filter(business=business).order_by("-date")[:30]
    # Pre-fill today's aggregates for the form
    today_day_agg = MobileMoneyTransaction.objects.filter(
        business=business, created_at__date=today
    ).aggregate(
        cash_in=Coalesce(Sum("cash_movement", filter=Q(cash_movement__gt=0)), Value(0), output_field=_DEC),
        cash_out=Coalesce(Sum("cash_movement", filter=Q(cash_movement__lt=0)), Value(0), output_field=_DEC),
        commission=Coalesce(Sum("commission"), Value(0), output_field=_DEC),
        tx_count=Count("id"),
    )
    latest_recon = recons.first()

    ctx = {
        "business": business,
        "active_tab": "reconciliation",
        "today": today,
        "reconciliations": recons,
        "latest_recon": latest_recon,
        "today_cash_in": Decimal(str(abs(today_day_agg["cash_in"] or 0))),
        "today_cash_out": Decimal(str(abs(today_day_agg["cash_out"] or 0))),
        "today_commission": Decimal(str(today_day_agg["commission"] or 0)),
        "today_tx_count": today_day_agg["tx_count"] or 0,
        "opening_cash_suggestion": latest_recon.actual_closing_cash if latest_recon else _ZERO,
        "opening_float_suggestion": latest_recon.opening_float if latest_recon else _ZERO,
    }
    return render(request, "verticals/mobilemoney/reconciliation.html", ctx)


# ── AGENT SETTLEMENTS ─────────────────────────────────────────────────────────

@login_required
@require_business
def settlements(request):
    business = get_active_business(request)

    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "create":
            try:
                settlement_type = request.POST.get("settlement_type", AgentSettlementType.BORROWED_FLOAT)
                agent_name = request.POST.get("agent_name", "").strip()
                agent_phone = request.POST.get("agent_phone", "").strip()
                amount_raw = request.POST.get("amount", "0").replace(",", "")
                amount = Decimal(amount_raw)
                direction = request.POST.get("direction", AgentSettlement.DIRECTION_RECEIVED)
                notes = request.POST.get("notes", "").strip()

                if not agent_name:
                    messages.error(request, "Agent name is required.")
                    return redirect("mobilemoney:settlements")
                if amount <= 0:
                    messages.error(request, "Amount must be greater than 0.")
                    return redirect("mobilemoney:settlements")

                AgentSettlement.objects.create(
                    business=business,
                    settlement_type=settlement_type,
                    agent_name=agent_name,
                    agent_phone=agent_phone,
                    amount=amount,
                    direction=direction,
                    notes=notes,
                    created_by=request.user,
                )
                type_label = dict(AgentSettlementType.choices).get(settlement_type, settlement_type)
                messages.success(request, f"{type_label} with {agent_name}: MWK {amount:,.0f} recorded.")
            except Exception as exc:
                messages.error(request, f"Error: {exc}")

        elif action == "mark_settled":
            settlement_id = request.POST.get("settlement_id")
            try:
                s = AgentSettlement.objects.get(pk=settlement_id, business=business)
                s.is_settled = True
                s.settled_at = timezone.now()
                s.save(update_fields=["is_settled", "settled_at"])
                messages.success(request, f"Settlement with {s.agent_name} marked as settled.")
            except AgentSettlement.DoesNotExist:
                messages.error(request, "Settlement not found.")
        return redirect("mobilemoney:settlements")

    all_settlements = AgentSettlement.objects.filter(business=business).order_by("-created_at")
    pending = all_settlements.filter(is_settled=False)
    settled = all_settlements.filter(is_settled=True)[:20]

    # How much do we owe vs how much are we owed
    pending_we_owe = _ZERO
    pending_owed_us = _ZERO
    for s in pending:
        impact = s.balance_impact
        if impact < 0:
            pending_we_owe += abs(impact)
        else:
            pending_owed_us += impact

    ctx = {
        "business": business,
        "active_tab": "settlements",
        "pending_settlements": pending,
        "settled_settlements": settled,
        "pending_we_owe": pending_we_owe,
        "pending_owed_us": pending_owed_us,
        "settlement_types": AgentSettlementType.choices,
        "direction_choices": AgentSettlement.DIRECTION_CHOICES,
    }
    return render(request, "verticals/mobilemoney/settlements.html", ctx)
