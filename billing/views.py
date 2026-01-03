# billing/views.py
from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tenants.models import Business
from tenants.utils import require_business

from . import paychangu_service
from .models import (
    BusinessSubscription,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentTransaction,
    SubscriptionChangeIntent,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)

# Optional (guarded) import to avoid hard dependency during bootstrap
try:
    from .models import WebhookEvent  # type: ignore
except Exception:
    WebhookEvent = None  # type: ignore

# Forms (UI tabs: Airtel / Standard Bank / Card)
try:
    from .forms import AirtelForm, BankProofForm, CardForm, ChoosePlanForm
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
    return timezone.make_aware(timezone.datetime.combine(next_month, timezone.datetime.min.time()))


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
        return f"Trial – {sub.days_left_in_trial()} days left"
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
        description=f"{plan.name} – {plan.get_interval_display()} plan",
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

    NO payment provider errors are shown here - only on checkout page.
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

    # Go directly to checkout (production behavior)
    return redirect("billing:checkout")


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
        # No bespoke page yet – go straight to checkout.
        return redirect("billing:checkout")


@login_required
@require_business
def checkout(request: HttpRequest) -> HttpResponse:
    """
    Interactive checkout with tabs:
    - Airtel Money (PayChangu Mobile Money Direct Charge - push to phone)
    - TNM Mpamba (PayChangu Mobile Money Direct Charge - push to phone)
    - Card (PayChangu Hosted Checkout)

    Mobile Money uses direct charge API (push prompt to phone).
    Card uses hosted checkout (redirect to PayChangu).
    Shows invoice preview on the side.
    """
    biz: Business = request.business
    inv_id = request.session.get("billing_invoice_id")
    if not inv_id:
        messages.info(request, "No pending invoice. Please pick a plan first.")
        return redirect("billing:subscribe")

    invoice = get_object_or_404(Invoice, id=inv_id, business=biz)

    # Pass PayChangu mode to template for test mode hints
    paychangu_mode = getattr(settings, "PAYCHANGU_MODE", "test")

    if request.method == "POST":
        method = (request.POST.get("method") or "").lower()
        phone = (request.POST.get("phone") or "").strip()

        # Check if PayChangu is configured
        if not paychangu_service.is_paychangu_configured():
            logger.error("PayChangu not configured, cannot process payment")
            messages.error(request, "Payment system is not configured. Please contact support.")
            return render(
                request,
                "billing/checkout.html",
                {
                    "invoice": invoice,
                    "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                    "PAYCHANGU_MODE": paychangu_mode,
                },
            )

        # Validate phone number for mobile money methods
        if method in ("airtel", "tnm"):
            if not phone:
                messages.error(request, "Please provide a valid phone number.")
                return render(
                    request,
                    "billing/checkout.html",
                    {
                        "invoice": invoice,
                        "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                        "PAYCHANGU_MODE": paychangu_mode,
                    },
                )

            # Normalize phone number
            try:
                normalized_phone = paychangu_service.normalize_malawi_phone(phone)
            except ValueError as e:
                messages.error(request, f"Invalid phone number: {e}")
                return render(
                    request,
                    "billing/checkout.html",
                    {
                        "invoice": invoice,
                        "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                        "PAYCHANGU_MODE": paychangu_mode,
                    },
                )

            # Test mode validation: only allow sandbox numbers
            if paychangu_mode == "test":
                validation_result = paychangu_service.validate_test_mode_phone(phone, method)
                if not validation_result.get("valid"):
                    messages.warning(request, validation_result.get("message"))
                    return render(
                        request,
                        "billing/checkout.html",
                        {
                            "invoice": invoice,
                            "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                            "PAYCHANGU_MODE": paychangu_mode,
                        },
                    )

        try:
            # Generate unique transaction reference and charge ID
            tx_ref = f"billing-{biz.id}-{uuid.uuid4().hex[:12]}"
            charge_id = f"charge-{uuid.uuid4().hex[:16]}"

            # Get location (first location if available, otherwise None)
            location = None
            if hasattr(biz, "locations"):
                location = biz.locations.first()

            # Get subscription plan for metadata
            sub = _ensure_trial_subscription(biz)
            plan_code = sub.plan.code if sub.plan else "unknown"

            logger.info(
                f"Initiating PayChangu payment: business={biz.id}, "
                f"invoice={invoice.id}, tx_ref={tx_ref}, method={method}, "
                f"amount={invoice.total}"
            )

            # Create PaymentTransaction record (PENDING)
            transaction = PaymentTransaction.objects.create(
                business=biz,
                location=location,
                created_by=request.user,
                provider="paychangu",
                tx_ref=tx_ref,
                charge_id=charge_id if method in ("airtel", "tnm") else "",
                payment_method=method,
                amount=invoice.total,
                currency=invoice.currency,
                status=PaymentTransaction.Status.PENDING,
            )

            # Store invoice reference in session for webhook processing
            request.session[f"paychangu_tx_{tx_ref}"] = {
                "invoice_id": str(invoice.id),
                "method": method,
            }

            # Build callback URLs
            callback_url = request.build_absolute_uri(reverse("billing:paychangu_webhook"))

            # Prepare metadata
            meta = {
                "plan_code": plan_code,
                "invoice_id": str(invoice.id),
                "payment_method": method,
                "user_id": str(request.user.id),
                "user_email": request.user.email,
            }

            # MOBILE MONEY: Direct Charge (push to phone)
            if method in ("airtel", "tnm"):
                # Resolve operator ref_id dynamically (with caching + env override support)
                operator_result = paychangu_service.get_operator_ref_id(method)

                if operator_result.get("status") != "success":
                    error_msg = operator_result.get("message", "Failed to resolve mobile money operator")
                    logger.error(f"Operator resolution failed: business={biz.id}, method={method}, error={error_msg}")
                    transaction.mark_failed({"error": error_msg})
                    messages.error(request, f"Payment setup error: {error_msg}. Please contact support.")
                    return render(
                        request,
                        "billing/checkout.html",
                        {
                            "invoice": invoice,
                            "sub_badge": _sub_badge(sub),
                            "PAYCHANGU_MODE": paychangu_mode,
                        },
                    )

                operator_ref_id = operator_result.get("ref_id")
                operator_name = operator_result.get("operator_name", method.upper())

                logger.info(
                    f"Resolved operator: method={method}, name={operator_name}, ref_id={operator_ref_id[:8]}..."
                )

                result = paychangu_service.momo_initialize_payment(
                    operator_ref_id=operator_ref_id,
                    mobile=phone,
                    amount=invoice.total,
                    currency=invoice.currency,
                    tx_ref=tx_ref,
                    charge_id=charge_id,
                    callback_url=callback_url,
                    meta=meta,
                    description=f"{invoice.number} - {sub.plan.name if sub.plan else 'Subscription'}",
                )

                if result.get("status") != "success":
                    error_msg = result.get("message", "Failed to initiate payment")
                    logger.error(f"PayChangu MoMo init failed: business={biz.id}, tx_ref={tx_ref}, error={error_msg}")
                    transaction.mark_failed(result.get("raw_response", {}))
                    messages.error(request, f"Payment initiation failed: {error_msg}. Please try again.")
                    return render(
                        request,
                        "billing/checkout.html",
                        {
                            "invoice": invoice,
                            "sub_badge": _sub_badge(sub),
                            "PAYCHANGU_MODE": paychangu_mode,
                        },
                    )

                # Update transaction with init payload
                transaction.raw_init_payload = result.get("raw_response", {})
                transaction.save(update_fields=["raw_init_payload", "updated_at"])

                logger.info(f"PayChangu MoMo initialized: tx_ref={tx_ref}, charge_id={charge_id}")

                # Store tx_ref in session for polling
                request.session["billing_tx_ref"] = tx_ref
                request.session["billing_charge_id"] = charge_id

                # Render waiting page with polling
                return render(
                    request,
                    "billing/payment_waiting.html",
                    {
                        "tx_ref": tx_ref,
                        "charge_id": charge_id,
                        "method": method.upper(),
                        "phone_masked": phone[:3] + "***" + phone[-2:] if len(phone) > 5 else "***",
                        "amount": invoice.total,
                        "currency": invoice.currency,
                    },
                )

            # CARD: Hosted Checkout (redirect to PayChangu)
            elif method == "card":
                return_url = request.build_absolute_uri(reverse("billing:paychangu_return"))

                result = paychangu_service.create_checkout(
                    business=biz,
                    location=location,
                    amount=invoice.total,
                    currency=invoice.currency,
                    tx_ref=tx_ref,
                    return_url=return_url,
                    callback_url=callback_url,
                    meta=meta,
                    user_email=request.user.email,
                    user_phone=getattr(request.user, "phone", None),
                    description=f"{invoice.number} - {sub.plan.name if sub.plan else 'Subscription'}",
                )

                if result.get("status") != "success":
                    error_msg = result.get("message", "Failed to initiate payment")
                    logger.error(f"PayChangu checkout failed: business={biz.id}, tx_ref={tx_ref}, error={error_msg}")
                    transaction.mark_failed(result.get("raw_response", {}))
                    messages.error(request, f"Payment initiation failed: {error_msg}. Please try again.")
                    return render(
                        request,
                        "billing/checkout.html",
                        {
                            "invoice": invoice,
                            "sub_badge": _sub_badge(sub),
                            "PAYCHANGU_MODE": paychangu_mode,
                        },
                    )

                # Update transaction with checkout details
                transaction.checkout_url = result.get("checkout_url", "")
                transaction.raw_init_payload = result.get("raw_response", {})
                transaction.save(update_fields=["checkout_url", "raw_init_payload", "updated_at"])

                logger.info(f"PayChangu checkout created: tx_ref={tx_ref}, checkout_url={transaction.checkout_url}")

                # Store tx_ref in session for return page
                request.session["billing_tx_ref"] = tx_ref

                # Redirect to PayChangu checkout page
                checkout_url = result.get("checkout_url")
                if checkout_url:
                    return redirect(checkout_url)
                else:
                    messages.error(request, "Failed to get checkout URL. Please try again.")
                    return render(
                        request,
                        "billing/checkout.html",
                        {
                            "invoice": invoice,
                            "sub_badge": _sub_badge(sub),
                            "PAYCHANGU_MODE": paychangu_mode,
                        },
                    )

            else:
                messages.error(request, "Invalid payment method selected.")
                return render(
                    request,
                    "billing/checkout.html",
                    {
                        "invoice": invoice,
                        "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                        "PAYCHANGU_MODE": paychangu_mode,
                    },
                )

        except Exception as e:
            logger.error(f"Checkout error: business={biz.id}, error={e}", exc_info=True)
            messages.error(request, f"An error occurred: {str(e)}. Please try again.")
            return render(
                request,
                "billing/checkout.html",
                {
                    "invoice": invoice,
                    "sub_badge": _sub_badge(_ensure_trial_subscription(biz)),
                    "PAYCHANGU_MODE": paychangu_mode,
                },
            )

    # GET request: show checkout form
    sub = _ensure_trial_subscription(biz)
    return render(
        request,
        "billing/checkout.html",
        {
            "invoice": invoice,
            "sub_badge": _sub_badge(sub),
            "PAYCHANGU_MODE": paychangu_mode,
        },
    )


@login_required
@require_business
def payment_status_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint to check payment status (for polling from payment_waiting.html).

    Query params:
        - charge_id: PayChangu charge ID (for mobile money)
        - tx_ref: Transaction reference (fallback)

    Returns:
        {
            "status": "pending" | "success" | "failed",
            "message": "...",
            "redirect_url": "/billing/success/" (when success)
        }
    """
    biz = request.business
    charge_id = request.GET.get("charge_id", "").strip()
    tx_ref = request.GET.get("tx_ref", "").strip()

    if not charge_id and not tx_ref:
        return JsonResponse({"status": "error", "message": "Missing charge_id or tx_ref"}, status=400)

    # Find transaction - scoped to current business (multi-tenant safe)
    try:
        if charge_id:
            transaction = PaymentTransaction.objects.get(charge_id=charge_id, business=biz, provider="paychangu")
        else:
            transaction = PaymentTransaction.objects.get(tx_ref=tx_ref, business=biz, provider="paychangu")
    except PaymentTransaction.DoesNotExist:
        logger.warning(f"Payment status check: charge_id={charge_id} tx_ref={tx_ref} not found for business {biz.id}")
        return JsonResponse({"status": "error", "message": "Payment not found"}, status=404)

    # If already SUCCESS or FAILED, return immediately
    if transaction.status == PaymentTransaction.Status.SUCCESS:
        return JsonResponse(
            {
                "status": "success",
                "message": "Payment confirmed! Your subscription is now active.",
                "redirect_url": reverse("billing:success"),
            }
        )

    if transaction.status == PaymentTransaction.Status.FAILED:
        return JsonResponse(
            {
                "status": "failed",
                "message": "Payment failed. Please try again.",
            }
        )

    # Still PENDING - verify with PayChangu API
    if transaction.charge_id:
        # Mobile Money: use momo_verify_payment
        verify_result = paychangu_service.momo_verify_payment(transaction.charge_id)
    else:
        # Hosted checkout: use verify_payment
        verify_result = paychangu_service.verify_payment(transaction.tx_ref)

    if verify_result.get("status") == "ERROR":
        logger.error(f"PayChangu verify API failed for {transaction.tx_ref}: {verify_result.get('message')}")
        return JsonResponse(
            {
                "status": "pending",
                "message": "Checking payment status...",
            }
        )

    verified_status = verify_result.get("status")

    if verified_status == "SUCCESS":
        # Mark transaction as successful
        transaction.mark_success(verify_result.get("raw_response", {}))

        # Find and mark invoice as paid
        try:
            invoice = (
                Invoice.objects.filter(
                    business=biz,
                    total=transaction.amount,
                    currency=transaction.currency,
                    status__in=[Invoice.Status.DRAFT, Invoice.Status.SENT],
                )
                .order_by("-created_at")
                .first()
            )

            if invoice and invoice.status != Invoice.Status.PAID:
                invoice.status = Invoice.Status.PAID
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["status", "paid_at", "updated_at"])
                logger.info(f"Invoice {invoice.number} marked PAID for charge_id {transaction.charge_id}")
        except Exception as e:
            logger.error(f"Failed to mark invoice paid: {e}", exc_info=True)

        # Activate subscription
        try:
            sub = getattr(biz, "subscription", None)
            if sub and sub.status != BusinessSubscription.Status.ACTIVE:
                sub.status = BusinessSubscription.Status.ACTIVE
                sub.last_payment_at = timezone.now()

                # Set payment method
                if transaction.payment_method == "airtel":
                    sub.payment_method = BusinessSubscription.Method.AIRTEL
                elif transaction.payment_method == "tnm":
                    sub.payment_method = BusinessSubscription.Method.AIRTEL  # Use same enum for now
                elif transaction.payment_method == "card":
                    sub.payment_method = BusinessSubscription.Method.CARD

                sub.advance_period()
                sub.save()
                logger.info(f"Subscription activated for business {biz.id}, charge_id {transaction.charge_id}")
        except Exception as e:
            logger.error(f"Failed to activate subscription: {e}", exc_info=True)

        return JsonResponse(
            {
                "status": "success",
                "message": "Payment confirmed! Your subscription is now active.",
                "redirect_url": reverse("billing:success"),
            }
        )

    elif verified_status == "FAILED":
        transaction.mark_failed(verify_result.get("raw_response", {}))
        return JsonResponse(
            {
                "status": "failed",
                "message": "Payment failed. Please try again.",
            }
        )

    else:
        # Still PENDING
        return JsonResponse(
            {
                "status": "pending",
                "message": "Payment is being processed...",
            }
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
    Period: {inv.period_start} – {inv.period_end}
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

    def w(s):
        out.write(s if isinstance(s, bytes) else s.encode("latin-1"))

    w("%PDF-1.4\n")
    xref.append(out.tell())
    w("1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n")
    xref.append(out.tell())
    w("2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n")
    xref.append(out.tell())
    w(
        "3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj\n"
    )
    xref.append(out.tell())
    w(f"4 0 obj <</Length {len(content_body)}>> stream\n")
    out.write(content_body)
    w("\nendstream endobj\n")
    xref.append(out.tell())
    w("5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Courier>> endobj\n")
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
                "headers": {k: v for k, v in request.headers.items()},
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
# Trial Expired / Paywall pages (tenant-facing)
# ------------------------------------------------------------------------------
@login_required
def trial_expired(request: HttpRequest) -> HttpResponse:
    """
    Shown when a manager's trial has expired and they have no active subscription.
    This page provides a clear message and CTA to subscribe or contact support.
    """
    biz = getattr(request, "business", None)
    sub = None

    if biz:
        sub = getattr(biz, "subscription", None)

    reason = request.GET.get("reason", "expired")

    return render(
        request,
        "billing/trial_expired.html",
        {
            "business": biz,
            "subscription": sub,
            "reason": reason,
        },
    )


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
def invoice_list(request: HttpRequest) -> HttpResponse:
    """
    List invoices for the current business.
    Minimal placeholder view that returns 200.
    """
    biz: Business = request.business
    invoices = Invoice.objects.filter(business=biz).order_by("-created_at")[:50]
    return render(
        request,
        "billing/invoices_list.html",
        {
            "invoices": invoices,
            "business": biz,
        },
    )


@login_required
@require_business
def manage(request: HttpRequest) -> HttpResponse:
    """
    Manage subscription page with current plan details, available plans, and invoice history.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("amount")
    
    # Get recent invoices (last 3)
    invoices = Invoice.objects.filter(business=biz).order_by("-created_at")[:3]
    
    return render(
        request,
        "billing/manage.html",
        {
            "sub": sub,
            "plans": plans,
            "invoices": invoices,
            "sub_badge": _sub_badge(sub),
        },
    )


# ------------------------------------------------------------------------------
# Subscription Upgrade Flow
# ------------------------------------------------------------------------------
@login_required
@require_business
@require_POST
def upgrade_start(request: HttpRequest, to_plan_code: str) -> HttpResponse:
    """
    Start subscription upgrade flow.
    
    1. Validate upgrade is to a higher-tier plan
    2. Calculate amount due (difference between plans)
    3. Create SubscriptionChangeIntent
    4. Initiate PayChangu checkout for the difference
    5. Redirect to PayChangu or show error
    
    Webhook will apply the upgrade after payment confirmed.
    """
    biz: Business = request.business
    sub = _ensure_trial_subscription(biz)
    
    # Validate current plan exists
    if not sub.plan:
        messages.error(request, "No current plan found. Please subscribe first.")
        return redirect("billing:subscribe")
    
    # Get target plan
    try:
        to_plan = SubscriptionPlan.objects.get(code=to_plan_code, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        messages.error(request, f"Plan '{to_plan_code}' not found.")
        return redirect("billing:manage")
    
    from_plan = sub.plan
    
    # Validate upgrade direction (must be to higher-priced plan)
    if to_plan.amount <= from_plan.amount:
        messages.error(request, "You can only upgrade to a higher-tier plan.")
        return redirect("billing:manage")
    
    # Calculate amount due (simple difference, no proration yet)
    amount_due = max(Decimal("0"), to_plan.amount - from_plan.amount)
    
    if amount_due == 0:
        messages.info(request, "No payment required for this plan change.")
        return redirect("billing:manage")
    
    # Generate idempotency key (prevents duplicate intents)
    # Format: business_id:from_plan:to_plan:period_start_timestamp
    period_start_ts = int(sub.current_period_start.timestamp()) if sub.current_period_start else 0
    idempotency_key = f"{biz.id}:{from_plan.code}:{to_plan.code}:{period_start_ts}"
    
    # Check if intent already exists (prevent duplicates)
    existing_intent = SubscriptionChangeIntent.objects.filter(
        idempotency_key=idempotency_key,
        status__in=[
            SubscriptionChangeIntent.Status.PENDING,
            SubscriptionChangeIntent.Status.PAID,
        ],
    ).first()
    
    if existing_intent:
        messages.info(request, "An upgrade is already in progress. Please complete the payment.")
        # Redirect to checkout or status page
        return redirect("billing:manage")
    
    # Create SubscriptionChangeIntent
    try:
        intent = SubscriptionChangeIntent.objects.create(
            business=biz,
            subscription=sub,
            from_plan_code=from_plan.code,
            to_plan_code=to_plan.code,
            from_plan_amount=from_plan.amount,
            to_plan_amount=to_plan.amount,
            amount_due=amount_due,
            currency=to_plan.currency,
            status=SubscriptionChangeIntent.Status.PENDING,
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        logger.error(f"Failed to create upgrade intent: business={biz.id}, error={e}", exc_info=True)
        messages.error(request, "Failed to initiate upgrade. Please try again.")
        return redirect("billing:manage")
    
    # Generate unique transaction reference
    tx_ref = f"upgrade-{biz.id}-{uuid.uuid4().hex[:12]}"
    charge_id = f"charge-{uuid.uuid4().hex[:16]}"
    
    # Store tx_ref in intent for webhook lookup
    intent.tx_ref = tx_ref
    intent.save(update_fields=["tx_ref", "updated_at"])
    
    # Get location (first location if available)
    location = None
    if hasattr(biz, "locations"):
        location = biz.locations.first()
    
    # Create PaymentTransaction record (PENDING)
    transaction = PaymentTransaction.objects.create(
        business=biz,
        location=location,
        created_by=request.user,
        provider="paychangu",
        tx_ref=tx_ref,
        charge_id=charge_id,
        payment_method="card",  # Default to card, can be changed later
        amount=amount_due,
        currency=intent.currency,
        status=PaymentTransaction.Status.PENDING,
    )
    
    # Build callback URLs
    callback_url = request.build_absolute_uri(reverse("billing:paychangu_webhook"))
    return_url = request.build_absolute_uri(reverse("billing:paychangu_return"))
    
    # Prepare metadata for PayChangu
    meta = {
        "purpose": "subscription_upgrade",
        "intent_id": str(intent.id),
        "business_id": str(biz.id),
        "from_plan": from_plan.code,
        "to_plan": to_plan.code,
        "amount_due": str(amount_due),
        "currency": intent.currency,
        "user_id": str(request.user.id),
        "user_email": request.user.email,
    }
    
    # Initiate PayChangu hosted checkout
    try:
        result = paychangu_service.create_checkout(
            business=biz,
            location=location,
            amount=amount_due,
            currency=intent.currency,
            tx_ref=tx_ref,
            return_url=return_url,
            callback_url=callback_url,
            meta=meta,
            user_email=request.user.email,
            user_phone=getattr(request.user, "phone", None),
            description=f"Upgrade: {from_plan.name} → {to_plan.name}",
        )
        
        if result.get("status") != "success":
            error_msg = result.get("message", "Failed to initiate payment")
            logger.error(f"PayChangu checkout failed: business={biz.id}, tx_ref={tx_ref}, error={error_msg}")
            transaction.mark_failed(result.get("raw_response", {}))
            intent.mark_failed()
            messages.error(request, f"Payment initiation failed: {error_msg}. Please try again.")
            return redirect("billing:manage")
        
        # Update transaction with checkout details
        transaction.checkout_url = result.get("checkout_url", "")
        transaction.raw_init_payload = result.get("raw_response", {})
        transaction.save(update_fields=["checkout_url", "raw_init_payload", "updated_at"])
        
        # Store intent reference in PayChangu metadata
        intent.paychangu_reference = result.get("checkout_id", "")
        intent.save(update_fields=["paychangu_reference", "updated_at"])
        
        logger.info(
            f"Upgrade checkout created: business={biz.id}, intent={intent.id}, "
            f"tx_ref={tx_ref}, amount_due={amount_due}"
        )
        
        # Store tx_ref in session for return page
        request.session["billing_tx_ref"] = tx_ref
        request.session["upgrade_intent_id"] = str(intent.id)
        
        # Redirect to PayChangu checkout page
        checkout_url = result.get("checkout_url")
        if checkout_url:
            return redirect(checkout_url)
        else:
            messages.error(request, "Failed to get checkout URL. Please try again.")
            return redirect("billing:manage")
            
    except Exception as e:
        logger.error(f"Upgrade checkout error: business={biz.id}, error={e}", exc_info=True)
        transaction.mark_failed({"error": str(e)})
        intent.mark_failed()
        messages.error(request, f"An error occurred: {str(e)}. Please try again.")
        return redirect("billing:manage")


# ------------------------------------------------------------------------------
# HQ / Admin views (legacy – prefer hq app views)
# ------------------------------------------------------------------------------
@staff_member_required
def hq_subscriptions(request: HttpRequest) -> HttpResponse:
    """
    Admin list to view/enforce. Reachable at /hq/subscriptions (see urls.py).
    """
    items = BusinessSubscription.objects.select_related("business", "plan").order_by("-started_at")
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


# ------------------------------------------------------------------------------
# Trial Lock Page
# ------------------------------------------------------------------------------
def trial_expired(request: HttpRequest) -> HttpResponse:
    """
    Hard lock page shown when trial has expired.
    User can only access billing pages, logout, or contact admin.
    """
    # Get business from request (set by TenantResolutionMiddleware)
    business = getattr(request, "business", None)

    # If no business, redirect to tenant chooser
    if not business:
        return redirect("/accounts/login/")

    # Check subscription status
    sub = getattr(business, "subscription", None)

    # If subscription is actually active, redirect to dashboard
    if sub and sub.is_active_now():
        return redirect("/app/home/")

    context = {
        "business": business,
        "subscription": sub,
        "reason": request.GET.get("reason", "expired"),
    }

    return render(request, "billing/trial_expired.html", context)
