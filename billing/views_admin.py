from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.db.models import Q, Count
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .models import BusinessSubscription, SubscriptionPlan, Invoice, Payment

# Optional Webhook model (guarded import in case you haven't added it yet)
try:
    from .models import WebhookEvent  # type: ignore
except Exception:
    WebhookEvent = None  # type: ignore


def _superuser_only(request: HttpRequest) -> bool:
    return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


def _html_page(title: str, body: str) -> HttpResponse:
    html = f"""
    <main style="max-width:1080px;margin:2rem auto;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
      <header style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
        <h1 style="margin:0">{escape(title)}</h1>
        <nav style="font-size:.95rem">
          <a href="{reverse('billing:admin_dashboard')}">Dashboard</a>
          {' | <a href="'+reverse('billing:admin_webhook_logs')+'">Webhook logs</a>' if WebhookEvent else ''}
        </nav>
      </header>
      {body}
    </main>
    """.strip()
    return HttpResponse(html)


@staff_member_required
def super_dashboard(request: HttpRequest) -> HttpResponse:
    if not _superuser_only(request):
        return HttpResponseForbidden("Superuser only")

    now = timezone.now()
    tomorrow = (now + timedelta(days=1)).date()
    soon = now + timedelta(days=3)

    subs = BusinessSubscription.objects.select_related("business", "plan")

    # Quick metrics
    totals = {
        "total": subs.count(),
        "trial": subs.filter(status=BusinessSubscription.Status.TRIAL).count(),
        "active": subs.filter(status=BusinessSubscription.Status.ACTIVE).count(),
        "grace": subs.filter(status=BusinessSubscription.Status.GRACE).count(),
        "past_due": subs.filter(status=BusinessSubscription.Status.PAST_DUE).count(),
        "expired": subs.filter(status=BusinessSubscription.Status.EXPIRED).count(),
    }

    trials_ending_tomorrow = subs.filter(
        status=BusinessSubscription.Status.TRIAL,
        trial_end__date=tomorrow,
    ).order_by("trial_end")[:50]

    in_grace = subs.filter(status=BusinessSubscription.Status.GRACE).order_by("next_billing_date")[:50]

    invoices_recent = Invoice.objects.select_related("business").order_by("-created_at")[:50]

    # Render minimal HTML (keeps you moving fast without templates)
    def _sub_row(s: BusinessSubscription) -> str:
        biz = escape(getattr(s.business, "name", "—"))
        plan = escape(getattr(s.plan, "name", "—"))
        status = escape(s.get_status_display())
        trial_end = escape(s.trial_end.strftime("%Y-%m-%d %H:%M") if s.trial_end else "—")
        next_bill = escape(s.next_billing_date.strftime("%Y-%m-%d %H:%M") if s.next_billing_date else "—")
        ex = escape(str(s.id))
        extend_url = reverse("billing:admin_extend_trial", args=[s.id])
        renew_url = reverse("billing:admin_force_renew", args=[s.id])
        return f"""
        <tr>
          <td>{biz}</td><td>{plan}</td><td>{status}</td>
          <td>{trial_end}</td><td>{next_bill}</td>
          <td style="white-space:nowrap">
            <form action="{extend_url}" method="post" style="display:inline">{_csrf(request)}
              <input type="number" name="days" value="7" min="1" max="365" style="width:70px">
              <button type="submit">Extend</button>
            </form>
            <form action="{renew_url}" method="post" style="display:inline;margin-left:.5rem">{_csrf(request)}
              <button type="submit">Force renew</button>
            </form>
          </td>
        </tr>
        """

    def _inv_row(inv: Invoice) -> str:
        resend_url = reverse("billing:admin_resend_invoice", args=[inv.id])
        return f"""
        <tr>
          <td>{escape(inv.number)}</td>
          <td>{escape(getattr(inv.business, 'name', '—'))}</td>
          <td>{escape(inv.get_status_display())}</td>
          <td style="text-align:right">{escape(str(inv.total))} {escape(inv.currency)}</td>
          <td>{escape(inv.issue_date.strftime('%Y-%m-%d'))}</td>
          <td style="white-space:nowrap">
            <form action="{resend_url}" method="post" style="display:inline">{_csrf(request)}
              <button type="submit">Resend</button>
            </form>
          </td>
        </tr>
        """

    body = f"""
    <section style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.75rem;margin-bottom:1rem">
      {_stat("Total", totals["total"])}
      {_stat("Trial", totals["trial"])}
      {_stat("Active", totals["active"])}
      {_stat("Grace", totals["grace"])}
      {_stat("Past due", totals["past_due"])}
    </section>

    <details open>
      <summary style="font-weight:600">Trials ending tomorrow ({trials_ending_tomorrow.count()})</summary>
      <table border="1" cellpadding="6" cellspacing="0" style="width:100%;margin:.5rem 0">
        <thead><tr><th>Business</th><th>Plan</th><th>Status</th><th>Trial end</th><th>Next bill</th><th>Actions</th></tr></thead>
        <tbody>
          {''.join(_sub_row(s) for s in trials_ending_tomorrow)}
        </tbody>
      </table>
    </details>

    <details>
      <summary style="font-weight:600">In grace period ({in_grace.count()})</summary>
      <table border="1" cellpadding="6" cellspacing="0" style="width:100%;margin:.5rem 0">
        <thead><tr><th>Business</th><th>Plan</th><th>Status</th><th>Trial end</th><th>Next bill</th><th>Actions</th></tr></thead>
        <tbody>
          {''.join(_sub_row(s) for s in in_grace)}
        </tbody>
      </table>
    </details>

    <details open>
      <summary style="font-weight:600">Recent invoices</summary>
      <table border="1" cellpadding="6" cellspacing="0" style="width:100%;margin:.5rem 0">
        <thead><tr><th>#</th><th>Business</th><th>Status</th><th>Total</th><th>Issued</th><th>Actions</th></tr></thead>
        <tbody>
          {''.join(_inv_row(i) for i in invoices_recent)}
        </tbody>
      </table>
    </details>
    """
    return _html_page("Billing • Super Admin", body)


@staff_member_required
def extend_trial(request: HttpRequest, sub_id) -> HttpResponse:
    if not _superuser_only(request):
        return HttpResponseForbidden("Superuser only")
    if request.method != "POST":
        return HttpResponseForbidden("POST required")
    sub = get_object_or_404(BusinessSubscription, id=sub_id)
    days = int(request.POST.get("days", "7"))
    now = timezone.now()
    # Extend from current trial_end if present and in the future, else from now
    start = sub.trial_end if sub.trial_end and sub.trial_end > now else now
    sub.trial_end = start + timedelta(days=max(days, 1))
    sub.status = BusinessSubscription.Status.TRIAL
    sub.next_billing_date = sub.trial_end
    sub.save(update_fields=["trial_end", "status", "next_billing_date", "updated_at"])
    return HttpResponseRedirect(reverse("billing:admin_dashboard"))


@staff_member_required
def force_renew(request: HttpRequest, sub_id) -> HttpResponse:
    if not _superuser_only(request):
        return HttpResponseForbidden("Superuser only")
    if request.method != "POST":
        return HttpResponseForbidden("POST required")
    sub = get_object_or_404(BusinessSubscription, id=sub_id)
    sub.status = BusinessSubscription.Status.ACTIVE
    sub.last_payment_at = timezone.now()
    sub.advance_period()
    sub.save(update_fields=["status", "last_payment_at", "updated_at"])
    return HttpResponseRedirect(reverse("billing:admin_dashboard"))


@staff_member_required
def resend_invoice(request: HttpRequest, invoice_id) -> HttpResponse:
    if not _superuser_only(request):
        return HttpResponseForbidden("Superuser only")
    if request.method != "POST":
        return HttpResponseForbidden("POST required")
    inv = get_object_or_404(Invoice, id=invoice_id)
    _send_invoice_email(inv)
    _send_invoice_whatsapp(inv)
    inv.mark_sent()
    return HttpResponseRedirect(reverse("billing:admin_dashboard"))


@staff_member_required
def webhook_logs(request: HttpRequest) -> HttpResponse:
    if not _superuser_only(request):
        return HttpResponseForbidden("Superuser only")
    if not WebhookEvent:
        return _html_page("Webhook logs", "<p>No WebhookEvent model is available.</p>")
    events = WebhookEvent.objects.order_by("-received_at")[:200]
    rows = "".join(
        f"<tr><td>{escape(e.received_at.strftime('%Y-%m-%d %H:%M'))}</td>"
        f"<td>{escape(e.source)}</td><td>{escape(e.event_type)}</td>"
        f"<td>{escape(e.external_id or '—')}</td></tr>"
        for e in events
    )
    body = f"""
    <table border="1" cellpadding="6" cellspacing="0" style="width:100%">
      <thead><tr><th>Received</th><th>Source</th><th>Type</th><th>External ID</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    """
    return _html_page("Webhook logs", body)


# ---------- helpers ----------------------------------------------------

def _csrf(request: HttpRequest) -> str:
    from django.middleware.csrf import get_token
    return f'<input type="hidden" name="csrfmiddlewaretoken" value="{escape(get_token(request))}">'


def _stat(label: str, value) -> str:
    return f"""
    <div style="padding:.75rem;border:1px solid #e5e7eb;border-radius:.75rem;background:#fafafa">
      <div style="font-size:.85rem;color:#6b7280">{escape(label)}</div>
      <div style="font-size:1.25rem;font-weight:700">{escape(str(value))}</div>
    </div>
    """

def _send_invoice_email(inv: Invoice) -> None:
    subject = f"Invoice {inv.number} — {getattr(inv.business, 'name', '')}"
    to_email = inv.manager_email or settings.DEFAULT_FROM_EMAIL
    body = (
        f"Hello,\n\n"
        f"Please find your invoice {inv.number} for {inv.currency} {inv.total}.\n"
        f"Issued: {inv.issue_date}  Due: {inv.due_date or '—'}\n\n"
        f"Thank you."
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=True)
    except Exception:
        pass


def _send_invoice_whatsapp(inv: Invoice) -> None:
    """
    Very simple WhatsApp dispatcher honoring WHATSAPP_BACKEND.
    - 'console': no-op (acts like success)
    - 'twilio' / 'meta': you can wire actual SDK/API here later.
    """
    backend = (getattr(settings, "WHATSAPP_BACKEND", "console") or "console").lower()
    to_phone = inv.manager_whatsapp
    if not to_phone:
        return
    msg = f"Invoice {inv.number}: {inv.currency} {inv.total}. Issued {inv.issue_date}."
    try:
        if backend == "console":
            # Dev mode: just log to stdout
            print(f"[WA] to={to_phone} :: {msg}")
        else:
            # Placeholder: integrate Twilio/Meta API as needed
            print(f"[WA:{backend}] SEND to={to_phone} :: {msg}")
    except Exception:
        pass
