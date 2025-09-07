# wallet/tasks.py
from __future__ import annotations
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from decimal import Decimal

from .models import Payslip, PayoutSchedule
from .services import compute_payslip_numbers, month_range_for_previous_month

@shared_task
def send_payslip_email(payslip_id: int) -> str:
    ps = Payslip.objects.select_related("user").get(id=payslip_id)
    ctx = {"ps": ps, "user": ps.user}
    subject = f"Payslip • {ps.period_start:%b %Y} • {ps.user.get_username()}"
    html = render_to_string("wallet/emails/payslip_email.html", ctx)
    text = render_to_string("wallet/emails/payslip_email.txt", ctx)
    msg = EmailMultiAlternatives(subject, text, to=[ps.email_to] if ps.email_to else [])
    msg.attach_alternative(html, "text/html")
    msg.send()
    ps.status = "SENT"
    ps.sent_at = timezone.now()
    ps.save(update_fields=["status", "sent_at", "updated_at"])
    return ps.reference

@shared_task
def run_payout_schedules() -> int:
    """
    Executes active schedules for due date/time.
    Sends payslips for the previous calendar month.
    """
    now = timezone.localtime()
    ran = 0
    for sched in PayoutSchedule.objects.filter(active=True):
        # Is it the scheduled hour?
        if now.hour != sched.at_hour:
            continue
        # Is today the scheduled day (or last day if day_of_month overflow)?
        # Compute last day of current month
        next_month = (now.date().replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
        last_day = (next_month - timezone.timedelta(days=1)).day
        due_day = min(sched.day_of_month, last_day)
        if now.day != due_day:
            continue

        start, end = month_range_for_previous_month(now.date())
        for u in sched.users.all():
            base = Decimal(getattr(u, "base_salary", None) or getattr(ps := Payslip(), "base_salary", "40000"))
            nums = compute_payslip_numbers(u, start, end, base)
            ps = Payslip.objects.create(
                user=u, period_start=start, period_end=end,
                base_salary=base, **nums, created_by=None, email_to=getattr(u, "email", "")
            )
            send_payslip_email.delay(ps.id)
            ran += 1
        sched.last_run_at = now
        sched.save(update_fields=["last_run_at"])
    return ran
