# wallet/services.py
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    WalletTransaction,
    TxnType,
    Ledger,
    SalesTarget,
    AttendanceLog,
)

# Optional models (guarded so the app still loads if they’re not migrated yet)
try:
    from .models import Payslip, PayoutSchedule  # type: ignore
except Exception:  # pragma: no cover
    Payslip = None  # type: ignore
    PayoutSchedule = None  # type: ignore

# Existing dependency
from sales.models import Sale  # you already have this


# ---------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------
LATE_BLOCK_MINUTES = 30
LATE_BLOCK_FINE = Decimal("3000.00")
WEEKEND_BONUS = Decimal("5000.00")


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


def prev_month(today: date | None = None) -> tuple[int, int]:
    today = today or timezone.localdate()
    y, m = today.year, today.month
    return (y - 1, 12) if m == 1 else (y, m - 1)


def fmt_mk(x: Decimal | int | float) -> str:
    # Simple number format for emails (MK 12,345)
    from django.contrib.humanize.templatetags.humanize import intcomma

    d = Decimal(x or 0)
    whole = int(d.quantize(Decimal("1")))
    return f"MK {intcomma(whole)}"


# ---------------------------------------------------------------------
# Core wallet helpers (kept intact)
# ---------------------------------------------------------------------
def add_txn(
    *,
    agent,
    amount,
    type,
    note: str = "",
    reference: str = "",
    effective_date: date | None = None,
    created_by=None,
    meta=None,
    ledger=Ledger.AGENT,
):
    return WalletTransaction.objects.create(
        ledger=ledger,
        agent=agent,
        amount=amount,
        type=type,
        note=note,
        reference=reference,
        effective_date=effective_date or timezone.localdate(),
        created_by=created_by,
        meta=meta or {},
    )


# --- Sales → Commission (call from a post_save of Sale or wherever you finalize a sale)
def record_sale_commission(sale: Sale, *, created: bool, created_by=None):
    # example: 3% commission of sale.amount  (adjust to your real rule)
    if not created:
        return
    rate = sale.commission_rate or Decimal("0.03")
    commission = (sale.amount or Decimal("0")) * rate
    if commission:
        eff = sale.date.date() if hasattr(sale.date, "date") else sale.date
        add_txn(
            agent=sale.agent,
            amount=commission,
            type=TxnType.COMMISSION,
            note=f"Commission for Sale #{sale.id}",
            reference=f"SALE-{sale.id}",
            effective_date=eff,
            created_by=created_by,
            meta={"sale_id": sale.id, "rate": str(rate)},
        )


# --- Attendance penalties/bonuses (run daily at 18:00 with Celery/cron)
def apply_attendance_dispositions(for_date: date | None = None, *, created_by=None):
    d = for_date or timezone.localdate()
    logs = AttendanceLog.objects.filter(date=d).select_related("agent")
    for log in logs:
        if log.check_in:
            # Late? official start 08:00
            late_minutes = max(0, (log.check_in.hour * 60 + log.check_in.minute) - (8 * 60))
            blocks = late_minutes // LATE_BLOCK_MINUTES
            if blocks:
                fine = LATE_BLOCK_FINE * blocks
                add_txn(
                    agent=log.agent,
                    amount=-fine,
                    type=TxnType.PENALTY,
                    note=f"Late arrival ({late_minutes} min → {blocks}×{LATE_BLOCK_FINE:,})",
                    reference=f"ATT-{d.isoformat()}",
                    effective_date=d,
                    created_by=created_by,
                    meta={"late_minutes": int(late_minutes), "blocks": int(blocks)},
                )
            # Weekend bonus
            if log.weekend:
                add_txn(
                    agent=log.agent,
                    amount=WEEKEND_BONUS,
                    type=TxnType.BONUS,
                    note="Weekend attendance bonus",
                    reference=f"WKND-{d.isoformat()}",
                    effective_date=d,
                    created_by=created_by,
                )
        else:
            # optional: absence penalty
            pass


# --- Monthly sales target bonus (run on month end OR nightly incremental)
def apply_monthly_target_bonus(agent, year: int, month: int, *, created_by=None):
    try:
        t = SalesTarget.objects.get(agent=agent, year=year, month=month)
    except SalesTarget.DoesNotExist:
        return

    first_day, last_day = month_bounds(year, month)
    count = Sale.objects.filter(agent=agent, date__date__gte=first_day, date__date__lte=last_day).count()

    extra = max(0, count - t.target_count)
    if extra:
        bonus = t.bonus_per_extra * extra
        add_txn(
            agent=agent,
            amount=bonus,
            type=TxnType.BONUS,
            note=f"Target exceeded by {extra} sale(s)",
            reference=f"TARGET-{year}-{month}",
            effective_date=last_day,
            created_by=created_by,
            meta={"count": count, "target": t.target_count},
        )


# --- Aggregations for the UI ---
def agent_wallet_summary(agent, *, today=None):
    today = today or timezone.localdate()
    start_month = today.replace(day=1)

    qs_all = WalletTransaction.objects.filter(ledger=Ledger.AGENT, agent=agent)
    qs_month = qs_all.filter(effective_date__gte=start_month, effective_date__lte=today)
    qs_today = qs_all.filter(effective_date=today)

    def total(qs):
        return qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")

    return {
        "today_earnings": total(qs_today.filter(amount__gt=0)),
        "today_deductions": -total(qs_today.filter(amount__lt=0)),
        "month_total": total(qs_month),
        "month_deductions": -total(qs_month.filter(amount__lt=0)),
        "all_time_total": total(qs_all),
        "all_time_deductions": -total(qs_all.filter(amount__lt=0)),
        "balance": total(qs_all),  # current wallet
    }


def ranking(period: str = "month"):
    today = timezone.localdate()
    if period == "all":
        filt = Q()
    else:
        start = today.replace(day=1)
        filt = Q(effective_date__gte=start, effective_date__lte=today)
    rows = (
        WalletTransaction.objects.filter(ledger=Ledger.AGENT)
        .filter(filt)
        .values("agent__id", "agent__first_name", "agent__last_name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:20]
    )
    return list(rows)


# ---------------------------------------------------------------------
# Payslip helpers (compute → post → create record → email)
# ---------------------------------------------------------------------
@dataclass
class PayslipBreakdown:
    gross: Decimal
    deductions: Decimal
    net: Decimal
    by_type: dict[str, Decimal]


def compute_monthly_payslip(agent, year: int, month: int) -> PayslipBreakdown:
    """
    Calculate gross/deductions/net from all wallet txns for the month.
    Positive amounts contribute to gross; negatives to deductions.
    """
    first, last = month_bounds(year, month)
    qs = WalletTransaction.objects.filter(
        ledger=Ledger.AGENT,
        agent=agent,
        effective_date__gte=first,
        effective_date__lte=last,
    )

    pos = qs.filter(amount__gt=0).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    neg = qs.filter(amount__lt=0).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    by_type = {row["type"]: row["s"] or Decimal("0") for row in qs.values("type").annotate(s=Sum("amount"))}

    gross = pos
    deductions = -neg
    net = gross - deductions
    return PayslipBreakdown(gross=gross, deductions=deductions, net=net, by_type=by_type)


def render_payslip_html(agent, year: int, month: int, b: PayslipBreakdown, company_name: str | None = None) -> str:
    """
    Renders HTML for the email. Falls back to inline HTML if the template is missing.
    """
    ctx = {
        "agent": agent,
        "year": year,
        "month": month,
        "gross": b.gross,
        "deductions": b.deductions,
        "net": b.net,
        "by_type": b.by_type,
        "fmt_mk": fmt_mk,
        "company_name": company_name or getattr(settings, "APP_NAME", "Circuit City"),
    }
    try:
        return render_to_string("wallet/payslip_email.html", ctx)
    except Exception:
        # Minimal inline fallback
        items = "".join(
            f"<li>{k.title()}: {fmt_mk(v)}</li>"
            for k, v in sorted(b.by_type.items(), key=lambda x: x[0])
        )
        return f"""
        <div>
          <h3>Payslip — {ctx['company_name']}</h3>
          <p><b>{getattr(agent, "get_full_name", lambda: agent.username)()}</b> — {year}-{month:02d}</p>
          <ul>{items}</ul>
          <p><b>Gross:</b> {fmt_mk(b.gross)}<br/>
             <b>Deductions:</b> {fmt_mk(b.deductions)}<br/>
             <b>Net:</b> {fmt_mk(b.net)}</p>
        </div>
        """


def send_payslip_email(agent, year: int, month: int, b: PayslipBreakdown, *, subject: str | None = None) -> bool:
    """
    Sends an HTML payslip email to the agent, returns True/False for success.
    """
    to = getattr(agent, "email", "") or ""
    if not to:
        return False

    company = getattr(settings, "APP_NAME", "Circuit City")
    html = render_payslip_html(agent, year, month, b, company_name=company)

    subject = subject or f"{company} • Payslip for {year}-{month:02d}"
    msg = EmailMultiAlternatives(subject=subject, body=" ", to=[to])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=True)
    return True


@transaction.atomic
def create_and_post_payslip(agent, year: int, month: int, *, created_by=None, post_wallet_payout: bool = True):
    """
    1) Compute breakdown
    2) (optional) Post the payout: agent -net, company +net
    3) Create/update Payslip record
    Returns (payslip, breakdown)
    """
    if Payslip is None:
        raise RuntimeError("Payslip model not available. Run migrations.")

    b = compute_monthly_payslip(agent, year, month)

    # Post payout to ledgers
    if post_wallet_payout and b.net and b.net > 0:
        last_day = month_bounds(year, month)[1]
        add_txn(
            agent=agent,
            amount=-b.net,
            type=TxnType.PAYSLIP,
            note=f"Payslip {year}-{month:02d}",
            created_by=created_by,
            effective_date=last_day,
            meta={"gross": str(b.gross), "deductions": str(b.deductions)},
        )
        WalletTransaction.objects.create(
            ledger=Ledger.COMPANY,
            agent=agent,
            amount=b.net,
            type=TxnType.PAYSLIP,
            note=f"[Agent {agent.id}] Payslip {year}-{month:02d}",
            created_by=created_by,
            effective_date=last_day,
            meta={"gross": str(b.gross), "deductions": str(b.deductions)},
        )

    # Upsert payslip
    p, _ = Payslip.objects.get_or_create(
        agent=agent,
        year=year,
        month=month,
        defaults={"gross": b.gross, "deductions": b.deductions, "net": b.net},
    )
    p.gross, p.deductions, p.net = b.gross, b.deductions, b.net
    p.save()

    return p, b


def bulk_issue_payslips(
    agents: Iterable,
    year: int,
    month: int,
    *,
    created_by=None,
    email: bool = True,
    post_wallet_payout: bool = True,
) -> dict:
    """
    Issues payslips for a set of agents. Returns a summary dict.
    """
    results: list[dict] = []
    ok = 0
    for agent in agents:
        try:
            p, b = create_and_post_payslip(
                agent, year, month, created_by=created_by, post_wallet_payout=post_wallet_payout
            )
            emailed = False
            if email:
                emailed = send_payslip_email(agent, year, month, b)
                # Best-effort flag for convenience in UI
                try:
                    type(p).objects.filter(id=p.id).update(sent_to_email=bool(emailed))
                except Exception:
                    pass
            results.append({"agent_id": agent.id, "net": b.net, "emailed": bool(emailed), "ok": True})
            ok += 1
        except Exception as e:  # keep going on errors
            results.append({"agent_id": getattr(agent, "id", None), "error": str(e), "ok": False})
    return {"count": len(results), "ok": ok, "results": results}


# ---------------------------------------------------------------------
# Payout schedules (runner using the M2M `users`)
# ---------------------------------------------------------------------
def run_monthly_schedule(schedule, *, when: date | None = None, created_by=None) -> dict:
    """
    Executes a PayoutSchedule for (year, month). If `when` is omitted, uses previous month.
    Uses the schedule.users M2M as the recipient list.
    """
    if PayoutSchedule is None:
        raise RuntimeError("PayoutSchedule model not available. Run migrations.")

    when = when or timezone.localdate()
    year, month = prev_month(when)

    agents = list(schedule.users.filter(is_active=True))
    res = bulk_issue_payslips(
        agents,
        year,
        month,
        created_by=created_by,
        email=True,
        post_wallet_payout=True,
    )

    schedule.last_run_at = timezone.now()
    schedule.save(update_fields=["last_run_at"])
    return {"schedule_id": schedule.id, "year": year, "month": month, **res}
