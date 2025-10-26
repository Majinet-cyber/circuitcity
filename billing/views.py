# billing/views.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tenants.models import Business
from tenants.utils import require_business

from .models import (
    SubscriptionPlan,
    BusinessSubscription,
    Invoice,
    InvoiceItem,
    Payment,
)

# Optional (guarded) import to avoid hard dependency during bootstrap
try:
    from .models import WebhookEvent  # type: ignore
except Exception:
    WebhookEvent = None  # type: ignore

# Forms (UI tabs: Airtel / Standard Bank / Card)
try:
    from .forms import ChoosePlanForm, AirtelForm, BankProofForm, CardForm
except Exception:
    # Safe fallbacks if forms aren't wired yet
    from django import forms  # type: ignore

    class ChoosePlanForm(forms.Form):  # type: ignore
        plan = forms.ModelChoiceField(queryset=SubscriptionPlan.objects.filter(is_active=True))

    class AirtelForm(forms.Form):  # type: ignore
        msisdn = forms.CharField()

    class BankProofForm(forms.Form):  # type: ignore
        reference = forms.CharField()

    class CardForm(forms.Form):  # type: ignore
        number = forms.CharField()
        exp_month = forms.IntegerField()
        exp_year = forms.IntegerField()
        cvv = forms.CharField()


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _first_of_next_month(dt: date) -> date:
    """Return the first day of the next month for a given date."""
    if dt.month == 12:
        return date(dt.year + 1, 1, 1)
    return date(dt.year, dt.month + 1, 1)


def _compute_period_end(plan: SubscriptionPlan, start_dt: timezone.datetime) -> timezone.datetime:
    """
    Compute the period end aligned to monthly/yearly cycles.
    Yearly = +365d. Monthly aligns to first-of-next-month midnight.
    """
    if plan.interval == SubscriptionPlan.Interval.YEAR:
        return start_dt + timedelta(days=365)
    next_month = _first_of_next_month(start_dt.date())
    return timezone.make_aware(
        timezone.datetime.combine(next_month, timezone.datetime.min.time())
    )


def _ensure_trial_subscription(biz: Business) -> BusinessSubscription:
    """Ensure the business has a subscription object (seed a trial if missing)."""
    sub = getattr(biz, "subscription", None)
    if sub:
        return sub
    # pick the cheapest active plan as default when seeding a trial
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
    if not plan:
        # create a placeholder plan so UI keeps working
        plan = SubscriptionPlan.objects.create(code="starter", name="Starter", amount=Decimal("0.00"))
    return BusinessSubscription.start_trial(
        business=biz,
        plan=plan,
        days=getattr(settings, "BILLING_TRIAL_DAYS", 30),
    )


def _sub_badge(sub: BusinessSubscription) -> str:
    if sub.status == BusinessSubscription.Status.TRIAL:
        return f"Trial â€” {sub.days_left_in_trial()} days left"
    if sub.status == BusinessSubscription.Status.ACTIVE:
        return "Active"
    if sub.status == BusinessSubscription.Status.GRACE:
        return "Grace period"
    return sub.get_status_display()


def _plan_slug(plan: SubscriptionPlan) -> str:
    """Stable slug for plan pages (code preferred, else slugified name)."""
    code = (getattr(plan, "code", None) or "").strip()
    return code.lower() if code else slugify(plan.name or "plan")


def _create_draft_invoice_for_plan(biz: Business, plan: SubscriptionPlan, *, created_by) -> Invoice:
    """Centralized draft invoice creation so 'subscribe' and 'select_plan' stay consistent."""
    now = timezone.now()
    period_end = _compute_period_end(plan, now)

    inv = Invoice.objects.create(
        business=biz,
        created_by=created_by,
        to_name=getattr(biz, "name", "") or "",
        to_email=getattr(biz, "manager_email", "") or getattr(biz, "email", ""),
        to_phone=getattr(biz, "whatsapp_number", "") or getattr(biz, "phone", ""),
        period_start=now.date(),
        period_end=period_end.date(),
        notes=f"{plan.name} subscription ({plan.get_interval_display().lower()})",
        currency=plan.currency,
        status=Invoice.Status.DRAFT,
    )
    InvoiceItem.objects.create(
        invoice=inv,
        description=f"{plan.name} â€” {plan.get_interval_display()} plan",
        qty=Decimal("1"),
        unit="mo" if plan.interval == SubscriptionPlan.Interval.MONTH else "yr",
        unit_price=Decimal(plan.amount),
    )
    inv.recalc_totals(save=True)
    return inv


# --------- outbound notifications (email / WhatsApp) -------------------
def _send_invoice_email(inv: Invoice) -> None:
    """
    Lightweight email fanout using existing notifications plumbing.
    Falls back to console backend in DEBUG.
    """
    try:
        from billing.notifications import send_invoice_email  # our convenience wrapper
        send_invoice_email(inv)
    except Exception:
        # best-effort: no crash if email layer isn't ready
        pass


def _send_invoice_whatsapp(inv: Invoice) -> None:
    try:
        from billing.notifications import send_invoice_whatsapp
        send_invoice_whatsapp(inv)
    except Exception:
        pass


# ------------------------------------------------------------------------------
# Public/tenant views
# ------------------------------------------------------------------------------
@login_required
@require_business
def subscribe(request: HttpRequest) -> HttpResponse:
    """
    Pick a plan (or show current); seed trial if missing; create the first invoice draft.
    This page now primarily serves GET (the one-click flow posts to select_plan).
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("amount", "name")

    # Backward compatibility: still accept POST if old template submits here.
    if request.method == "POST":
        form = ChoosePlanForm(request.POST)
        if form.is_valid():
            plan = form.cleaned_data["plan"]
            sub.plan = plan
            sub.save(update_fields=["plan", "updated_at"])

            inv = _create_draft_invoice_for_plan(biz, plan, created_by=request.user)
            request.session["billing_invoice_id"] = str(inv.id)
            return redirect("billing:checkout")
        else:
            messages.error(request, "Please choose a valid plan.")
    else:
        form = ChoosePlanForm(initial={"plan": sub.plan_id} if sub.plan_id else None)

    return render(
        request,
        "billing/subscribe.html",
        {
            "plans": plans,
            "form": form,
            "sub": sub,
            "days_left": sub.days_left_in_trial(),
            "sub_badge": _sub_badge(sub),
        },
    )


# -------- One-click plan selection -> plan page (then checkout) ----------
@login_required
@require_business
@require_POST
def select_plan(request: HttpRequest) -> HttpResponse:
    """
    Receives POST from a plan card. Sets plan, creates draft invoice, and routes
    to the plan-specific page. That page may immediately link/redirect to checkout.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)

    plan_id = request.POST.get("plan")
    if not plan_id:
        return HttpResponseBadRequest("Missing plan id")

    try:
        plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        messages.error(request, "Unknown or inactive plan.")
        return redirect("billing:subscribe")

    # Update subscription plan
    sub.plan = plan
    sub.save(update_fields=["plan", "updated_at"])

    # Create a fresh draft invoice
    inv = _create_draft_invoice_for_plan(biz, plan, created_by=request.user)
    request.session["billing_invoice_id"] = str(inv.id)

    # Head to the plan-specific landing (with graceful fallback inside).
    return redirect("billing:plan_detail", slug=_plan_slug(plan))


@login_required
@require_business
def plan_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Shows a per-plan page if a dedicated template exists:
      - billing/plan_<slug>.html  (e.g., plan_starter.html, plan_growth.html)
    If missing, falls back to checkout immediately.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)

    # If no invoice in session (e.g., user refreshed), ensure there's one for current plan
    inv_id = request.session.get("billing_invoice_id")
    if not inv_id and sub.plan_id:
        inv = _create_draft_invoice_for_plan(biz, sub.plan, created_by=request.user)
        request.session["billing_invoice_id"] = str(inv.id)

    template_name = f"billing/plan_{slug}.html"
    try:
        return render(
            request,
            template_name,
            {
                "plan_slug": slug,
                "sub": sub,
                "sub_badge": _sub_badge(sub),
            },
        )
    except TemplateDoesNotExist:
        # No bespoke page yet â€” go straight to checkout.
        return redirect("billing:checkout")


@login_required
@require_business
def checkout(request: HttpRequest) -> HttpResponse:
    """
    Interactive checkout with tabs:
    - Airtel Money (prompt)
    - Standard Bank (proof/reference)
    - Card (number/exp/cvv) â€” stubbed tokenization for now
    Shows invoice preview on the side.
    """
    biz: Business = request.business
    inv_id = request.session.get("billing_invoice_id")
    if not inv_id:
        messages.info(request, "No pending invoice. Pick a plan first.")
        return redirect("billing:subscribe")

    invoice = get_object_or_404(Invoice, id=inv_id, business=biz)

    airtel_form = AirtelForm(prefix="airtel")
    bank_form = BankProofForm(prefix="bank")
    card_form = CardForm(prefix="card")

    if request.method == "POST":
        method = (request.POST.get("method") or "").lower()

        # ---------------- Airtel Money ----------------
        if method == "airtel":
            airtel_form = AirtelForm(request.POST, prefix="airtel")
            if airtel_form.is_valid():
                msisdn = airtel_form.cleaned_data["msisdn"]
                Payment.objects.create(
                    business=biz,
                    invoice=invoice,
                    provider=Payment.Provider.AIRTEL,
                    amount=invoice.total,
                    currency=invoice.currency,
                    status=Payment.Status.PENDING,
                    raw_payload={"msisdn": msisdn},
                )
                messages.success(
                    request,
                    "Airtel Money prompt initiated (stub). Please approve on your phone. Weâ€™ll activate once confirmed.",
                )
                return redirect("billing:success")

        # ---------------- Standard Bank (manual) -----
        elif method == "standard_bank":
            bank_form = BankProofForm(request.POST, prefix="bank")
            if bank_form.is_valid():
                ref = bank_form.cleaned_data["reference"]
                Payment.objects.create(
                    business=biz,
                    invoice=invoice,
                    provider=Payment.Provider.STANDARD_BANK,
                    amount=invoice.total,
                    currency=invoice.currency,
                    status=Payment.Status.PENDING,
                    reference=ref,
                )
                messages.info(request, "Proof submitted. Weâ€™ll verify and activate shortly.")
                return redirect("billing:success")

        # ---------------- Card (stub success) --------
        elif method == "card":
            card_form = CardForm(request.POST, prefix="card")
            if card_form.is_valid():
                # In real flow: tokenize cardâ†’chargeâ†’webhook. For now, mark success.
                Payment.objects.create(
                    business=biz,
                    invoice=invoice,
                    provider=Payment.Provider.CARD,
                    amount=invoice.total,
                    currency=invoice.currency,
                    status=Payment.Status.SUCCEEDED,
                    external_id="TEST-OK",
                )
                invoice.mark_paid()

                sub = _ensure_trial_subscription(biz)
                if not sub.plan_id:
                    sub.plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
                sub.status = BusinessSubscription.Status.ACTIVE
                sub.last_payment_at = timezone.now()
                sub.advance_period()
                sub.save(update_fields=["plan", "status", "last_payment_at", "updated_at"])

                # Notify & mark sent
                _send_invoice_email(invoice)
                _send_invoice_whatsapp(invoice)
                invoice.mark_sent()

                messages.success(request, "Payment successful and subscription activated.")
                return redirect("billing:success")

        messages.error(request, "Please check your payment details and try again.")

    # Sidebar badge
    sub = _ensure_trial_subscription(biz)
    return render(
        request,
        "billing/checkout.html",
        {
            "invoice": invoice,
            "airtel_form": airtel_form,
            "bank_form": bank_form,
            "card_form": card_form,
            "sub_badge": _sub_badge(sub),
        },
    )


@login_required
@require_business
def success(request: HttpRequest) -> HttpResponse:
    return render(request, "billing/success.html")


# ---------------- Invoice send/download endpoints ----------------------
@login_required
@require_business
def invoice_send(request: HttpRequest, pk: str) -> HttpResponse:
    """
    Sends invoice via email/WhatsApp and marks it sent.
    Works with either UUID or INT pk based on your URL conf.
    """
    biz: Business = request.business
    inv = get_object_or_404(Invoice, id=pk, business=biz)
    _send_invoice_email(inv)
    _send_invoice_whatsapp(inv)
    inv.mark_sent()
    messages.success(request, f"Invoice {inv.number} sent.")
    # bounce back to checkout or subscribe
    return redirect(request.META.get("HTTP_REFERER") or reverse("billing:checkout"))


@login_required
@require_business
def invoice_download(request: HttpRequest, pk: str) -> FileResponse:
    """
    Minimal PDF placeholder (so UI has a real download). Replace with a proper
    generator (WeasyPrint/ReportLab) later.
    """
    biz: Business = request.business
    inv = get_object_or_404(Invoice, id=pk, business=biz)

    content = f"""
    Invoice: {inv.number}
    Business: {getattr(biz, "name", "")}
    Period: {inv.period_start} â€“ {inv.period_end}
    Amount: {inv.currency} {inv.total}
    Status: {inv.get_status_display()}
    """.strip()

    pdf_bytes = _plain_text_to_minimal_pdf(content)
    return FileResponse(BytesIO(pdf_bytes), as_attachment=True, filename=f"{inv.number}.pdf")


def _plain_text_to_minimal_pdf(text: str) -> bytes:
    # Extremely small valid PDF (monospace text at fixed coords)
    # Pragmatic placeholder; swap with a real PDF lib for production.
    text = text.replace("(", r"\(").replace(")", r"\)").replace("\\", r"\\")
    lines = text.splitlines()
    y = 750
    content_ops = []
    for i, line in enumerate(lines):
        content_ops.append(f"BT /F1 12 Tf 50 {y - i * 16} Td ({line}) Tj ET")
    content_body = "\n".join(content_ops).encode("latin-1", "ignore")

    xref = []
    out = BytesIO()
    def w(s): out.write(s if isinstance(s, bytes) else s.encode("latin-1"))
    w("%PDF-1.4\n")
    xref.append(out.tell()); w("1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n")
    xref.append(out.tell()); w("2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n")
    xref.append(out.tell()); w("3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj\n")
    xref.append(out.tell()); w(f"4 0 obj <</Length {len(content_body)}>> stream\n"); out.write(content_body); w("\nendstream endobj\n")
    xref.append(out.tell()); w("5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Courier>> endobj\n")
    xref_pos = out.tell()
    w("xref\n0 6\n0000000000 65535 f \n")
    for pos in xref:
        w(f"{pos:010} 00000 n \n")
    w(f"trailer <</Size 6 /Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF")
    return out.getvalue()


# ---------------- Minimal webhook endpoint ------------------------------
@csrf_exempt
def webhook(request: HttpRequest) -> JsonResponse:
    """
    Minimal idempotent webhook collector.
    Stores raw payload + headers into WebhookEvent.payload (if model is available).
    """
    raw = request.body.decode("utf-8", errors="ignore")
    if WebhookEvent:
        try:
            provider = request.GET.get("provider", "unknown")
            event_type = request.GET.get("event", "unknown")
            external_id = request.GET.get("id", "")

            # Store headers inside payload for auditing; model has no separate headers field
            payload = {
                "raw": raw,
                "headers": {k: v for k, v in request.headers.items() },
                "query": dict(request.GET),
            }

            WebhookEvent.objects.create(
                provider=provider,
                event_type=event_type,
                external_id=external_id,
                payload=payload,
            )
        except Exception:
            # Never crash a webhook
            pass
    return JsonResponse({"ok": True})


# ------------------------------------------------------------------------------
# Paywall / Manage pages (tenant-facing)
# ------------------------------------------------------------------------------
@login_required
@require_business
def paywall(request: HttpRequest) -> HttpResponse:
    """
    Shown when trial/subscription is not active.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("amount")
    return render(request, "billing/paywall.html", {"sub": sub, "plans": plans, "sub_badge": _sub_badge(sub)})


@login_required
@require_business
def manage(request: HttpRequest) -> HttpResponse:
    """
    Basic â€œmanage subscriptionâ€ page (stub). You can add upgrade/downgrade actions here later.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("amount")
    return render(request, "billing/manage.html", {"sub": sub, "plans": plans, "sub_badge": _sub_badge(sub)})


# ------------------------------------------------------------------------------
# HQ / Admin views (legacy â€“ prefer hq app views)
# ------------------------------------------------------------------------------
@staff_member_required
def hq_subscriptions(request: HttpRequest) -> HttpResponse:
    """
    Admin list to view/enforce. Reachable at /hq/subscriptions (see urls.py).
    """
    items = (
        BusinessSubscription.objects.select_related("business", "plan")
        .order_by("-started_at")
    )
    return render(request, "billing/hq_subscriptions.html", {"items": items})


@staff_member_required
@require_POST
def force_status(request: HttpRequest, sub_id: str) -> HttpResponse:
    """
    Force a subscription status from the HQ list (quick admin tool).
    """
    new_status = request.POST.get("status")
    sub = get_object_or_404(BusinessSubscription, id=sub_id)
    choices = dict(BusinessSubscription.Status.choices)
    if new_status in choices:
        sub.status = new_status
        if new_status == BusinessSubscription.Status.ACTIVE:
            # give 30 days by default; tune if needed
            now = timezone.now()
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=30)
            sub.next_billing_date = sub.current_period_end
        sub.save()
        messages.success(request, f"Subscription updated to {choices[new_status]}.")
    else:
        messages.error(request, "Invalid status.")
    return redirect("billing:hq")


