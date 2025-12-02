# billing/views_providers.py
"""
Provider-specific checkout views for Stripe and Pesapal.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from tenants.models import Business
from tenants.utils import require_business, get_active_business

from .models import (
    SubscriptionPlan,
    BusinessSubscription,
    Invoice,
    Payment,
    WebhookEvent,
)
from . import stripe_service, pesapal_service

logger = logging.getLogger(__name__)


# ==============================================================================
# STRIPE CHECKOUT
# ==============================================================================

@login_required
@require_business
@require_POST
def stripe_checkout(request: HttpRequest) -> HttpResponse:
    """
    Create a Stripe Checkout Session and redirect user to Stripe.
    
    POST params:
        - plan_code: slug of the SubscriptionPlan
    """
    business: Business = request.business
    plan_code = request.POST.get("plan_code", "").strip()
    
    if not plan_code:
        messages.error(request, "No plan selected.")
        return redirect("billing:subscribe")
    
    # Load plan
    try:
        plan = SubscriptionPlan.objects.get(code=plan_code, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        messages.error(request, f"Plan '{plan_code}' not found.")
        return redirect("billing:subscribe")
    
    # Check if Stripe is configured
    if not stripe_service.is_stripe_configured():
        messages.error(
            request,
            "Stripe is not configured. Please use another payment method or contact support."
        )
        return redirect("billing:subscribe")
    
    # Build success/cancel URLs
    success_url = request.build_absolute_uri(reverse("billing:stripe_success"))
    cancel_url = request.build_absolute_uri(reverse("billing:subscribe"))
    
    # Create Stripe Checkout Session
    result = stripe_service.create_checkout_session(
        business=business,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
        user_email=request.user.email,
    )
    
    if result.get("error"):
        messages.error(request, f"Stripe checkout failed: {result['error']}")
        logger.error(f"Stripe checkout error for business {business.id}: {result['error']}")
        return redirect("billing:subscribe")
    
    # Redirect to Stripe
    redirect_url = result.get("url")
    if not redirect_url:
        messages.error(request, "Failed to create Stripe checkout session.")
        return redirect("billing:subscribe")
    
    # Store session ID in user session for tracking (optional)
    request.session["stripe_session_id"] = result.get("id")
    
    logger.info(
        f"Redirecting business {business.id} to Stripe checkout for plan {plan_code}"
    )
    return redirect(redirect_url)


@login_required
@require_business
def stripe_success(request: HttpRequest) -> HttpResponse:
    """
    Success page after Stripe Checkout.
    The actual activation happens via webhook.
    """
    business: Business = request.business
    
    return render(
        request,
        "billing/stripe_success.html",
        {
            "business": business,
            "message": "Payment processing... Your subscription will be activated shortly.",
        },
    )


@csrf_exempt
@require_POST
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle Stripe webhooks.
    
    Events handled:
        - checkout.session.completed: Activate subscription
        - invoice.payment_succeeded: Renew subscription
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    
    if not sig_header:
        logger.warning("Stripe webhook missing signature header")
        return HttpResponseBadRequest("Missing signature")
    
    # Construct and verify event
    event = stripe_service.construct_webhook_event(payload, sig_header)
    if not event:
        logger.warning("Stripe webhook verification failed")
        return HttpResponseBadRequest("Invalid signature")
    
    # Log webhook event
    if WebhookEvent:
        try:
            WebhookEvent.objects.create(
                provider="stripe",
                event_type=event.get("type", ""),
                external_id=event.get("id", ""),
                payload=event,
            )
        except Exception as e:
            logger.error(f"Failed to log Stripe webhook: {e}")
    
    event_type = event.get("type")
    logger.info(f"Stripe webhook received: {event_type}")
    
    # Handle checkout.session.completed
    if event_type == "checkout.session.completed":
        _handle_stripe_checkout_completed(event)
    
    # Handle invoice.payment_succeeded (recurring payments)
    elif event_type == "invoice.payment_succeeded":
        _handle_stripe_invoice_paid(event)
    
    return HttpResponse(status=200)


def _handle_stripe_checkout_completed(event: dict) -> None:
    """Process checkout.session.completed event."""
    result = stripe_service.handle_checkout_completed(event.get("data", {}))
    
    if result.get("status") != "success":
        logger.error(f"Stripe checkout processing failed: {result.get('message')}")
        return
    
    business_id = result.get("business_id")
    plan_code = result.get("plan_code")
    stripe_subscription_id = result.get("stripe_subscription_id")
    stripe_customer_id = result.get("stripe_customer_id")
    
    try:
        business = Business.objects.get(id=business_id)
        plan = SubscriptionPlan.objects.get(code=plan_code)
    except (Business.DoesNotExist, SubscriptionPlan.DoesNotExist) as e:
        logger.error(f"Stripe webhook: Business or Plan not found: {e}")
        return
    
    # Get or create subscription
    sub, created = BusinessSubscription.objects.get_or_create(
        business=business,
        defaults={"plan": plan},
    )
    
    if not created:
        sub.plan = plan
    
    # Update subscription
    sub.status = BusinessSubscription.Status.ACTIVE
    sub.payment_method = BusinessSubscription.Method.STRIPE
    sub.stripe_subscription_id = stripe_subscription_id or ""
    sub.stripe_customer_id = stripe_customer_id or ""
    sub.last_payment_at = timezone.now()
    
    # Set period dates
    now = timezone.now()
    sub.current_period_start = now
    if plan.interval == SubscriptionPlan.Interval.MONTH:
        sub.current_period_end = now + timezone.timedelta(days=30)
    else:
        sub.current_period_end = now + timezone.timedelta(days=365)
    sub.next_billing_date = sub.current_period_end
    
    sub.save()
    
    logger.info(
        f"Stripe subscription activated for business {business.id}, "
        f"plan {plan.code}, stripe_sub_id {stripe_subscription_id}"
    )


def _handle_stripe_invoice_paid(event: dict) -> None:
    """Process invoice.payment_succeeded event (recurring)."""
    result = stripe_service.handle_invoice_payment_succeeded(event.get("data", {}))
    
    if result.get("status") != "success":
        logger.error(f"Stripe invoice processing failed: {result.get('message')}")
        return
    
    stripe_subscription_id = result.get("stripe_subscription_id")
    if not stripe_subscription_id:
        logger.error("Stripe invoice event missing subscription_id")
        return
    
    try:
        sub = BusinessSubscription.objects.get(stripe_subscription_id=stripe_subscription_id)
    except BusinessSubscription.DoesNotExist:
        logger.warning(f"Stripe subscription not found: {stripe_subscription_id}")
        return
    
    # Renew subscription
    sub.status = BusinessSubscription.Status.ACTIVE
    sub.last_payment_at = timezone.now()
    sub.advance_period()
    sub.save()
    
    logger.info(f"Stripe subscription renewed: {stripe_subscription_id}")


# ==============================================================================
# PESAPAL CHECKOUT
# ==============================================================================

@login_required
@require_business
@require_POST
def pesapal_checkout(request: HttpRequest) -> HttpResponse:
    """
    Submit order to Pesapal and redirect user to payment page.
    
    POST params:
        - plan_code: slug of the SubscriptionPlan
    """
    business: Business = request.business
    plan_code = request.POST.get("plan_code", "").strip()
    
    if not plan_code:
        messages.error(request, "No plan selected.")
        return redirect("billing:subscribe")
    
    # Load plan
    try:
        plan = SubscriptionPlan.objects.get(code=plan_code, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        messages.error(request, f"Plan '{plan_code}' not found.")
        return redirect("billing:subscribe")
    
    # Check if Pesapal is configured
    if not pesapal_service.is_pesapal_configured():
        messages.error(
            request,
            "Pesapal is not configured. Please use another payment method or contact support."
        )
        return redirect("billing:subscribe")
    
    # Build callback URL (browser redirect after payment)
    callback_url = request.build_absolute_uri(reverse("billing:pesapal_callback"))
    
    # Submit order to Pesapal
    result = pesapal_service.submit_order_request(
        business=business,
        plan=plan,
        callback_url=callback_url,
        user_email=request.user.email,
        user_phone=getattr(request.user, "phone", None),
    )
    
    if result.get("status") != "success":
        messages.error(request, f"Pesapal order failed: {result.get('message')}")
        logger.error(f"Pesapal order error for business {business.id}: {result}")
        return redirect("billing:subscribe")
    
    # Create or update subscription record (pending status)
    sub, created = BusinessSubscription.objects.get_or_create(
        business=business,
        defaults={"plan": plan},
    )
    
    if not created:
        sub.plan = plan
    
    sub.status = BusinessSubscription.Status.TRIAL  # Keep in trial until payment confirmed
    sub.payment_method = BusinessSubscription.Method.PESAPAL
    sub.pesapal_order_tracking_id = result.get("order_tracking_id", "")
    sub.pesapal_merchant_reference = result.get("merchant_reference", "")
    
    # Set provisional period dates
    now = timezone.now()
    sub.current_period_start = now
    if plan.interval == SubscriptionPlan.Interval.MONTH:
        sub.current_period_end = now + timezone.timedelta(days=30)
    else:
        sub.current_period_end = now + timezone.timedelta(days=365)
    
    sub.save()
    
    # Redirect to Pesapal
    redirect_url = result.get("redirect_url")
    logger.info(
        f"Redirecting business {business.id} to Pesapal for plan {plan_code}, "
        f"tracking_id={result.get('order_tracking_id')}"
    )
    
    return redirect(redirect_url)


@login_required
def pesapal_callback(request: HttpRequest) -> HttpResponse:
    """
    Browser callback after Pesapal payment.
    Show a confirmation page while IPN processes the payment.
    """
    # Extract query params (Pesapal sends OrderTrackingId, OrderMerchantReference)
    tracking_id = request.GET.get("OrderTrackingId", "")
    merchant_ref = request.GET.get("OrderMerchantReference", "")
    
    # Optional: check status immediately for user feedback
    status_msg = "We are confirming your payment. Please wait..."
    
    if tracking_id:
        status_result = pesapal_service.get_transaction_status(tracking_id, merchant_ref)
        status = status_result.get("status", "PENDING")
        
        if status == "COMPLETED":
            status_msg = "Payment successful! Your subscription will be activated shortly."
        elif status == "FAILED":
            status_msg = "Payment failed. Please try again or contact support."
        elif status == "PENDING":
            status_msg = "Payment is being processed. We'll notify you once confirmed."
    
    return render(
        request,
        "billing/pesapal_callback.html",
        {
            "tracking_id": tracking_id,
            "merchant_ref": merchant_ref,
            "status_msg": status_msg,
        },
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def pesapal_ipn(request: HttpRequest) -> HttpResponse:
    """
    IPN (Instant Payment Notification) from Pesapal.
    
    Pesapal sends GET or POST with:
        - OrderTrackingId
        - OrderMerchantReference
        - OrderNotificationType (e.g. 'COMPLETED')
    
    We query the transaction status and update the subscription.
    """
    # Parse notification
    if request.method == "POST":
        params = request.POST.dict()
    else:
        params = request.GET.dict()
    
    parsed = pesapal_service.parse_ipn_notification(params)
    tracking_id = parsed.get("order_tracking_id")
    merchant_ref = parsed.get("merchant_reference")
    notification_type = parsed.get("notification_type")
    
    logger.info(
        f"Pesapal IPN received: tracking_id={tracking_id}, "
        f"merchant_ref={merchant_ref}, type={notification_type}"
    )
    
    if not tracking_id:
        logger.warning("Pesapal IPN missing OrderTrackingId")
        return HttpResponseBadRequest("Missing OrderTrackingId")
    
    # Log webhook event
    if WebhookEvent:
        try:
            WebhookEvent.objects.create(
                provider="pesapal",
                event_type=notification_type or "IPN",
                external_id=tracking_id,
                payload=params,
            )
        except Exception as e:
            logger.error(f"Failed to log Pesapal IPN: {e}")
    
    # Get transaction status from Pesapal
    status_result = pesapal_service.get_transaction_status(tracking_id, merchant_ref)
    status = status_result.get("status", "UNKNOWN")
    
    logger.info(f"Pesapal transaction status for {tracking_id}: {status}")
    
    # Find subscription
    try:
        sub = BusinessSubscription.objects.get(pesapal_order_tracking_id=tracking_id)
    except BusinessSubscription.DoesNotExist:
        logger.warning(f"Pesapal IPN: subscription not found for tracking_id {tracking_id}")
        return HttpResponse("OK", status=200)  # Return 200 to avoid retries
    
    # Update subscription based on status
    if status == "COMPLETED":
        sub.status = BusinessSubscription.Status.ACTIVE
        sub.last_payment_at = timezone.now()
        sub.save()
        logger.info(f"Pesapal payment completed for business {sub.business_id}")
    
    elif status in ("FAILED", "CANCELLED"):
        # Don't cancel subscription, just log
        logger.warning(f"Pesapal payment {status} for business {sub.business_id}")
    
    # Always return 200 to acknowledge receipt
    return HttpResponse("OK", status=200)

