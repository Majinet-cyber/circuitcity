# wallet/views.py
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.db.models import Sum
from django.http import HttpRequest, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, TemplateView

# ---- OTP alias: requires OTP when ENABLE_2FA=1; otherwise behaves like login_required
try:
    if getattr(settings, "ENABLE_2FA", False):
        from django_otp.decorators import otp_required  # type: ignore
    else:
        raise ImportError
except Exception:  # pragma: no cover
    from django.contrib.auth.decorators import login_required as otp_required  # type: ignore

# Optional tenant helper (don’t hard-fail if tenants app is unavailable)
try:
    from tenants.utils import get_active_business  # type: ignore
except Exception:  # pragma: no cover
    def get_active_business(_request):  # type: ignore
        return None

from .models import (
    AdminPurchaseOrder,
    AdminPurchaseOrderItem,
    BudgetRequest,
    Ledger,
    Payment,
    PaymentMethod,
    Payslip,
    PayoutSchedule,
    PurchaseOrderStatus,
    TxnType,
    WalletTransaction,
)
from .services import add_txn, agent_wallet_summary, ranking

# Optional: PO forms come from inventory.forms if available
try:
    from inventory.forms import PurchaseOrderHeaderForm, PurchaseOrderItemForm
except Exception:  # pragma: no cover
    PurchaseOrderHeaderForm = None
    PurchaseOrderItemForm = None


# ---------------------------------------------------------------------
# Helpers / guards
# ---------------------------------------------------------------------
def _staff(user) -> bool:
    """
    Manager-like users can access admin views:
    - Admins: user.is_staff
    - Managers: user.profile.is_manager  (if profile exists)
    """
    try:
        return bool(user.is_authenticated and (user.is_staff or user.profile.is_manager))
    except Exception:
        return bool(user.is_authenticated and user.is_staff)


def _month_bounds(year: int, month: int) -> Tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


def _sum(qs, **filters) -> Decimal:
    return qs.filter(**filters).aggregate(s=Sum("amount"))["s"] or Decimal("0")


def _maybe_scope_to_business(qs, business):
    """
    If model has a 'business' field, add business filter;
    otherwise return qs unchanged. This avoids crashes when some
    models aren’t tenant-scoped.
    """
    if not business:
        return qs
    try:
        if "business" in [f.name for f in qs.model._meta.get_fields()]:
            return qs.filter(business=business)
    except Exception:
        pass
    return qs


def _compute_breakdown(agent, first: date, last: date) -> dict:
    """
    Returns a dict with positive/negative totals and simple type splits
    for the agent's ledger within [first, last].
    """
    qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        effective_date__gte=first,
        effective_date__lte=last,
    )

    pos_total = _sum(qs, amount__gt=0)
    neg_total = _sum(qs, amount__lt=0)  # negative number or 0

    # Split out common types (only counting positives where it makes sense)
    commission = _sum(qs, type=TxnType.COMMISSION, amount__gt=0)
    bonus = _sum(qs, type=TxnType.BONUS, amount__gt=0)
    advances = -_sum(qs, type=TxnType.ADVANCE, amount__lt=0)  # to positive
    penalties = -_sum(qs, type=TxnType.PENALTY, amount__lt=0)

    return {
        "pos_total": pos_total,
        "neg_total": neg_total,
        "commission": commission,
        "bonus": bonus,
        "advances": advances,
        "penalties": penalties,
    }


def _send_payslip_email(p: Payslip) -> bool:
    """
    Minimal email sender; attach numbers in body.
    Returns True if we think it went out successfully.
    """
    if not getattr(p, "email_to", ""):
        return False

    subject = f"Payslip · {p.year}-{p.month:02d} · {getattr(settings, 'APP_NAME', 'Circuit City')}"
    body = (
        f"Hello,\n\n"
        f"Here is your payslip for {p.year}-{p.month:02d}.\n\n"
        f"Base salary: MWK {p.base_salary:,.0f}\n"
        f"Commission:  MWK {p.commission:,.0f}\n"
        f"Bonuses/Fee: MWK {p.bonuses_fees:,.0f}\n"
        f"Deductions:  MWK {p.deductions:,.0f}\n"
        f"----------------------------------\n"
        f"Gross:       MWK {p.gross:,.0f}\n"
        f"Net:         MWK {p.net:,.0f}\n\n"
        f"Ref: {p.reference}\n"
        f"— {getattr(settings, 'APP_NAME', 'Circuit City')}"
    )
    sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [p.email_to], fail_silently=True)
    return bool(sent)


def _json_requested(request: HttpRequest) -> bool:
    """
    True if the client clearly asked for JSON.
    """
    accept = (request.headers.get("Accept") or "").lower()
    return accept.startswith("application/json") or request.GET.get("format") == "json"


# =====================================================================
# JSON APIs used by the wallet page
# =====================================================================

@login_required
@require_GET
def api_txn_types(request: HttpRequest):
    """Return available transaction types for the Reason dropdown."""
    return JsonResponse({
        "ok": True,
        "types": [{"value": v, "label": lbl} for v, lbl in TxnType.choices],
    })


@login_required
@require_GET
def api_summary(request: HttpRequest):
    """Return the current user's wallet summary (balance, etc.)."""
    s = agent_wallet_summary(request.user)

    def ser(val):
        return float(val) if isinstance(val, Decimal) else val

    if isinstance(s, dict):
        s = {k: ser(v) for k, v in s.items()}

    return JsonResponse({"ok": True, "summary": s})


@login_required
@require_POST
def api_add_txn(request: HttpRequest):
    """
    Add a transaction to the current user's agent wallet.
    Accepts JSON or form-encoded data.
    """
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            data = json.loads(request.body.decode() or "{}")
        except Exception:
            data = {}
    else:
        data = request.POST

    # Parse fields
    try:
        amount = Decimal(str(data.get("amount", "0") or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid amount."}, status=400)

    ttype = (data.get("type") or data.get("reason") or "").strip()
    note = (data.get("note") or data.get("memo") or "").strip()

    if ttype not in TxnType.values:
        return JsonResponse({"ok": False, "error": "Invalid reason/type."}, status=400)

    # Post to the AGENT ledger (services.add_txn handles sign/validation)
    add_txn(
        agent=request.user,
        amount=amount,
        type=ttype,
        note=note,
        created_by=request.user,
        ledger=Ledger.AGENT,
    )
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------
# Payslip builder (helper)
# ---------------------------------------------------------------------
def _create_or_update_payslip_and_txn(
    *,
    agent,
    year: int,
    month: int,
    created_by,
    send_now: bool = False,
    payment_method: str | None = None,
) -> Payslip:
    """
    Compute totals -> create/update Payslip -> post wallet/company mirror txns (for net)
    -> optionally send email now. Returns the Payslip.
    """
    first, last = _month_bounds(year, month)
    breakdown = _compute_breakdown(agent, first, last)

    # Components — base salary default can be configured via settings
    base_salary = Decimal(getattr(settings, "WALLET_BASE_SALARY", "40000") or "0")
    commission = breakdown["commission"]
    bonuses_fees = breakdown["bonus"]
    deductions = -(breakdown["neg_total"])  # convert to positive

    gross = base_salary + commission + bonuses_fees
    net = gross - deductions

    # Create / update payslip record
    p, created = Payslip.objects.get_or_create(
        agent=agent,
        year=year,
        month=month,
        defaults=dict(
            base_salary=base_salary,
            commission=commission,
            bonuses_fees=bonuses_fees,
            deductions=deductions,
            gross=gross,
            net=net,
            created_by=created_by,
            email_to=getattr(agent, "email", "") or "",
            meta={
                "calc": {
                    "pos_total": str(breakdown["pos_total"]),
                    "neg_total": str(breakdown["neg_total"]),
                    "advances": str(breakdown["advances"]),
                    "penalties": str(breakdown["penalties"]),
                }
            },
        ),
    )
    if not created:
        p.base_salary = base_salary
        p.commission = commission
        p.bonuses_fees = bonuses_fees
        p.deductions = deductions
        p.gross = gross
        p.net = net
        if not getattr(p, "email_to", ""):
            p.email_to = getattr(agent, "email", "") or ""
        if not getattr(p, "created_by", None):
            p.created_by = created_by
        p.save()

    # Post wallet/company transactions only when net != 0 (avoid noise)
    if net != 0:
        # Agent wallet reduces by net (payment out)
        add_txn(
            agent=agent,
            amount=-net,
            type=TxnType.PAYSLIP,
            note=f"Payslip {year}-{month:02d}",
            created_by=created_by,
            meta={"gross": str(gross), "deductions": str(deductions)},
        )
        # Company mirror increases by net (payout made)
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=net,
            type=TxnType.PAYSLIP,
            note=f"[Agent {agent.id}] Payslip {year}-{month:02d}",
            created_by=created_by,
        )

    # Optional: record a Payment row (future integrations)
    if payment_method:
        Payment.objects.create(
            payslip=p,
            method=payment_method if payment_method in PaymentMethod.values else PaymentMethod.MANUAL,
            amount=p.net,
            status="PENDING",
            processed_by=created_by,
            meta={"auto_created": True},
        )

    # Optional: send email now
    if send_now:
        ok = _send_payslip_email(p)
        if ok:
            p.sent_to_email = True
            p.sent_at = timezone.now()
            p.status = "SENT"
            p.save(update_fields=["sent_to_email", "sent_at", "status"])

    return p


# ---------------------------------------------------------------------
# Agent wallet views (login-only; read/own-wallet)
# ---------------------------------------------------------------------
@method_decorator(ensure_csrf_cookie, name="dispatch")
class AgentWalletView(LoginRequiredMixin, TemplateView):
    """
    Agent self wallet page.

    ensure_csrf_cookie -> guarantees a CSRF cookie on first GET so that any
    subsequent fetch/POST from the page has a token (prevents 403 HTML pages
    that used to surface as “Unexpected token '<'” in the UI).
    """
    template_name = "wallet/agent_wallet.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        biz = get_active_business(self.request)

        # Summary is already per-user; txns also per-user
        txns = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=u)
        ctx["agent_summary"] = agent_wallet_summary(u)
        ctx["txns"] = txns.order_by("-effective_date", "-id")[:50]

        # Scope tenant-aware lists where possible
        bqs = BudgetRequest.objects.filter(agent=u).order_by("-created_at")
        pqs = Payslip.objects.filter(agent=u).order_by("-year", "-month")
        ctx["budgets"] = bqs[:5]
        ctx["payslips"] = pqs[:5]

        # For ranking chart on the wallet page, prefer tenant scope if supported by service
        try:
            ctx["ranking_period"] = "month"
            ctx["ranking_rows"] = ranking("month", business=biz)  # type: ignore[arg-type]
        except TypeError:
            # If your ranking(service) doesn't accept business, fall back gracefully
            ctx["ranking_period"] = "month"
            ctx["ranking_rows"] = ranking("month")
        return ctx


class AgentTxnListView(LoginRequiredMixin, ListView):
    template_name = "wallet/agent_txns.html"
    paginate_by = 50

    def get_queryset(self):
        return (
            WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=self.request.user)
            .order_by("-effective_date", "-id")
        )


@login_required
def api_ranking(request: HttpRequest):
    period = request.GET.get("period", "month")
    biz = get_active_business(request)
    try:
        rows = ranking(period, business=biz)  # type: ignore[arg-type]
    except TypeError:
        rows = ranking(period)
    return JsonResponse({"rows": rows})


# ---------------------------------------------------------------------
# Admin wallet views (OTP-required)
# ---------------------------------------------------------------------
@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminWalletHome(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_home.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        biz = get_active_business(self.request)
        qs = WalletTransaction.objects.filter(ledger=Ledger.COMPANY)
        qs = _maybe_scope_to_business(qs, biz)
        ctx["company_spend"] = qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        ctx["recent"] = qs.select_related("agent").order_by("-created_at")[:30]
        pending = BudgetRequest.objects.all()
        pending = _maybe_scope_to_business(pending, biz)
        ctx["budgets_pending"] = pending.filter(status=BudgetRequest.Status.PENDING).count()
        return ctx


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminAgentWallet(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_agent.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, agent_id, **kwargs):
        U = get_user_model()
        agent = get_object_or_404(U, id=agent_id)
        ctx = super().get_context_data(**kwargs)
        biz = get_active_business(self.request)

        ctx["agent"] = agent
        ctx["summary"] = agent_wallet_summary(agent)

        tx = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=agent)
        ctx["txns"] = tx.order_by("-effective_date", "-id")[:100]

        bqs = BudgetRequest.objects.filter(agent=agent)
        pqs = Payslip.objects.filter(agent=agent)
        bqs = _maybe_scope_to_business(bqs, biz)
        pqs = _maybe_scope_to_business(pqs, biz)

        ctx["budgets"] = bqs.order_by("-created_at")
        ctx["payslips"] = pqs.order_by("-year", "-month")
        return ctx


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminIssueTxnView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_issue.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        U = get_user_model()
        agent = get_object_or_404(U, id=request.POST.get("agent_id"))
        amount = Decimal(request.POST.get("amount", "0"))
        ttype = request.POST.get("type")
        note = request.POST.get("note", "")

        # Agent wallet (signed amount)
        add_txn(
            agent=agent,
            amount=amount,
            type=ttype,
            note=note,
            created_by=request.user,
            ledger=Ledger.AGENT,
        )

        # Mirror to company ledger for a full business trail
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=-amount,
            type=ttype,
            note=f"[Agent {agent.id}] {note}",
            created_by=request.user,
        )
        return redirect("wallet:admin_agent", agent_id=agent.id)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminBudgetsView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/admin_budgets.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        biz = get_active_business(self.request)

        pending = BudgetRequest.objects.all()
        approved = BudgetRequest.objects.all()
        paid = BudgetRequest.objects.all()

        pending = _maybe_scope_to_business(pending, biz).filter(status=BudgetRequest.Status.PENDING).select_related("agent")
        approved = _maybe_scope_to_business(approved, biz).filter(status=BudgetRequest.Status.APPROVED).select_related("agent")
        paid = _maybe_scope_to_business(paid, biz).filter(status=BudgetRequest.Status.PAID).select_related("agent")

        ctx["pending"] = pending
        ctx["approved"] = approved
        ctx["paid"] = paid
        return ctx

    def post(self, request):
        bid = int(request.POST["budget_id"])
        action = request.POST["action"]  # approve / reject / pay
        b = get_object_or_404(BudgetRequest, id=bid)

        if action == "approve":
            b.status = BudgetRequest.Status.APPROVED
        elif action == "reject":
            b.status = BudgetRequest.Status.REJECTED
        elif action == "pay":
            b.status = BudgetRequest.Status.PAID
            add_txn(
                agent=b.agent,
                amount=Decimal(b.amount),
                type=TxnType.BUDGET,
                note=f"Budget: {getattr(b, 'title', 'Approved budget')}",
                created_by=request.user,
            )
            WalletTransaction.objects.create(
                ledger=Ledger.COMPANY,
                agent=b.agent,
                amount=-Decimal(b.amount),
                type=TxnType.BUDGET,
                note=f"[Agent {b.agent_id}] {getattr(b, 'title', 'Approved budget')}",
                created_by=request.user,
            )

        b.decided_by = request.user
        b.decided_at = timezone.now()
        b.save()
        return redirect("wallet:admin_budgets")


# ---------------------------------------------------------------------
# Payslips (single + bulk + schedules) — OTP-required
# ---------------------------------------------------------------------
@otp_required
def issue_payslip(request, agent_id: int, year: int, month: int):
    """
    Legacy single-agent endpoint. Now delegates to the bulk-capable helper.
    Returns JSON if explicitly requested.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    U = get_user_model()
    agent = get_object_or_404(U, id=agent_id)

    p = _create_or_update_payslip_and_txn(
        agent=agent,
        year=year,
        month=month,
        created_by=request.user,
        send_now=bool(request.GET.get("send") == "1" or request.POST.get("send_now")),
        payment_method=request.POST.get("method") if request.method == "POST" else None,
    )
    if _json_requested(request):
        return JsonResponse(
            {"ok": True, "agent": agent.id, "reference": p.reference, "net": float(p.net)}
        )
    return redirect("wallet:admin_agent", agent_id=agent.id)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminIssuePayslipView(LoginRequiredMixin, TemplateView):
    """
    Issue a SINGLE payslip via form (agent, year, month, send_now, method).
    """
    template_name = "wallet/admin_issue_payslip.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        U = get_user_model()
        ctx["agents"] = U.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        today = timezone.localdate()
        ctx["year"] = int(self.request.GET.get("year", today.year))
        ctx["month"] = int(self.request.GET.get("month", today.month))
        return ctx

    def post(self, request: HttpRequest):
        U = get_user_model()
        agent = get_object_or_404(U, id=request.POST.get("agent_id"))
        year = int(request.POST.get("year"))
        month = int(request.POST.get("month"))
        send_now = request.POST.get("send_now") in ("1", "true", "on", "yes")
        method = request.POST.get("method")  # optional

        p = _create_or_update_payslip_and_txn(
            agent=agent,
            year=year,
            month=month,
            created_by=request.user,
            send_now=send_now,
            payment_method=method,
        )
        if _json_requested(request):
            return JsonResponse(
                {"ok": True, "agent": agent.id, "reference": p.reference, "net": float(p.net)}
            )
        return redirect("wallet:admin_agent", agent_id=agent.id)


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPayslipBulkView(LoginRequiredMixin, TemplateView):
    """
    GET  -> form to pick agents + period + send_now flag
    POST -> issue payslips for selected agents (and optionally email)
    """
    template_name = "wallet/admin_payslips.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        U = get_user_model()
        ctx["agents"] = U.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        today = timezone.localdate()
        ctx["year"] = int(self.request.GET.get("year", today.year))
        ctx["month"] = int(self.request.GET.get("month", today.month))
        return ctx

    def post(self, request: HttpRequest):
        U = get_user_model()
        # Accept multiple forms: agent_ids=1&agent_ids=2 or comma string
        raw = request.POST.getlist("agent_ids") or request.POST.get("agent_ids", "")
        if isinstance(raw, str):
            agent_ids = [x for x in (y.strip() for y in raw.split(",")) if x]
        else:
            agent_ids = raw

        if not agent_ids and _json_requested(request):
            return JsonResponse({"ok": False, "error": "No agents selected."}, status=400)

        year = int(request.POST.get("year"))
        month = int(request.POST.get("month"))
        send_now = request.POST.get("send_now") in ("1", "true", "on", "yes")
        method = request.POST.get("method")  # optional

        agents = list(U.objects.filter(id__in=agent_ids, is_active=True))
        results = []
        for a in agents:
            p = _create_or_update_payslip_and_txn(
                agent=a,
                year=year,
                month=month,
                created_by=request.user,
                send_now=send_now,
                payment_method=method,
            )
            results.append({"agent": a.id, "net": float(p.net), "reference": p.reference, "sent": p.sent_to_email})

        # JSON if requested; otherwise go home
        if _json_requested(request):
            return JsonResponse({"ok": True, "count": len(results), "results": results})
        return redirect("wallet:admin_home")


@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPayoutSchedulesView(LoginRequiredMixin, TemplateView):
    """
    Minimal view to create/update monthly auto-send schedules.
    You will still need a Celery beat job to call the runner daily/hourly.
    """
    template_name = "wallet/admin_schedules.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        U = get_user_model()
        ctx["schedules"] = PayoutSchedule.objects.all().prefetch_related("users")
        ctx["agents"] = U.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        return ctx

    def post(self, request: HttpRequest):
        name = request.POST.get("name") or "Monthly Payouts"
        day = int(request.POST.get("day_of_month", 28))
        hour = int(request.POST.get("at_hour", 9))
        active = request.POST.get("active") in ("1", "true", "on", "yes")
        user_ids = request.POST.getlist("user_ids")

        sch = PayoutSchedule.objects.create(
            name=name,
            day_of_month=day,
            at_hour=hour,
            active=active,
            created_by=request.user,
        )
        if user_ids:
            sch.users.add(*user_ids)

        if _json_requested(request):
            return JsonResponse({"ok": True, "id": sch.id})
        return redirect("wallet:admin_schedules")


@otp_required
def run_payout_schedule(request: HttpRequest, schedule_id: int):
    """
    Manual trigger: issues payslips for all users on the schedule for
    the previous month. Useful for testing before wiring Celery.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    sch = get_object_or_404(PayoutSchedule, id=schedule_id, active=True)
    today = timezone.localdate()
    prev_year = today.year if today.month > 1 else (today.year - 1)
    prev_month = today.month - 1 if today.month > 1 else 12

    results = []
    for u in sch.users.all():
        p = _create_or_update_payslip_and_txn(
            agent=u,
            year=prev_year,
            month=prev_month,
            created_by=request.user,
            send_now=True,  # schedules send email
        )
        results.append({"agent": u.id, "reference": p.reference, "net": float(p.net)})

    sch.last_run_at = timezone.now()
    sch.save(update_fields=["last_run_at"])

    return JsonResponse({"ok": True, "schedule": sch.id, "count": len(results), "results": results})


# ---------------------------------------------------------------------
# Admin Purchase Orders (simple views) — OTP-required
# ---------------------------------------------------------------------
@method_decorator([otp_required, ensure_csrf_cookie], name="dispatch")
class AdminPOListView(LoginRequiredMixin, TemplateView):
    """
    Lists Admin Purchase Orders with simple filters. (Wire in wallet/urls.py)
    """
    template_name = "wallet/admin_pos.html"

    def dispatch(self, request, *args, **kwargs):
        if not _staff(request.user):
            return redirect("wallet:agent_wallet")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status = self.request.GET.get("status")
        qs = AdminPurchaseOrder.objects.all().order_by("-created_at")
        if status in (
            PurchaseOrderStatus.DRAFT,
            PurchaseOrderStatus.SENT,
            PurchaseOrderStatus.COMPLETED,
            PurchaseOrderStatus.CANCELLED,
        ):
            qs = qs.filter(status=status)
        ctx["orders"] = qs
        ctx["status"] = status or "all"
        return ctx


@otp_required
def admin_po_new(request: HttpRequest):
    """
    Create a new PO header then redirect to detail page to add items.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    if PurchaseOrderHeaderForm is None:
        return HttpResponseBadRequest("PurchaseOrderHeaderForm not available.")

    if request.method == "POST":
        form = PurchaseOrderHeaderForm(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.status = PurchaseOrderStatus.DRAFT
            po.save()
            return redirect("wallet:admin_po_detail", po_id=po.id)
    else:
        form = PurchaseOrderHeaderForm()

    return render(request, "wallet/admin_po_new.html", {"form": form})


@otp_required
def admin_po_detail(request: HttpRequest, po_id: int):
    """
    View/edit a PO: add items, recompute totals, and move simple statuses.
    """
    if not _staff(request.user):
        return redirect("wallet:agent_wallet")

    po = get_object_or_404(AdminPurchaseOrder, id=po_id)

    ItemForm = PurchaseOrderItemForm  # alias
    if ItemForm is None:
        return HttpResponseBadRequest("PurchaseOrderItemForm not available.")

    if request.method == "POST":
        action = request.POST.get("action") or "add_item"

        if action == "add_item":
            form = ItemForm(request.POST)
            if form.is_valid():
                AdminPurchaseOrderItem.objects.create(po=po, **form.to_model_kwargs())
                po.recompute_totals(save=True)
                return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "delete_item":
            item_id = request.POST.get("item_id")
            if item_id:
                it = get_object_or_404(AdminPurchaseOrderItem, id=item_id, po=po)
                it.delete()
                po.recompute_totals(save=True)
                return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "recompute":
            po.recompute_totals(save=True)
            return redirect("wallet:admin_po_detail", po_id=po.id)
        elif action == "set_status":
            new_status = request.POST.get("status")
            if new_status in PurchaseOrderStatus.values:
                po.status = new_status
                po.save(update_fields=["status"])
            return redirect("wallet:admin_po_detail", po_id=po.id)

    # GET or invalid POST -> render page
    form = ItemForm()
    items = po.items.select_related("product").all().order_by("id")
    return render(
        request,
        "wallet/admin_po_detail.html",
        {"po": po, "form": form, "items": items, "status_choices": PurchaseOrderStatus.choices},
    )


# ---------------------------------------------------------------------
# URL-callable views (expose .as_view() for urls.py)
# ---------------------------------------------------------------------
# Agent area
agent_wallet = AgentWalletView.as_view()
agent_txns = AgentTxnListView.as_view()

# Admin area
admin_home = AdminWalletHome.as_view()
admin_agent = AdminAgentWallet.as_view()
admin_issue = AdminIssueTxnView.as_view()
admin_budgets = AdminBudgetsView.as_view()
admin_issue_payslip = AdminIssuePayslipView.as_view()
admin_payslips = AdminPayslipBulkView.as_view()
admin_schedules = AdminPayoutSchedulesView.as_view()
admin_po_list = AdminPOListView.as_view()
