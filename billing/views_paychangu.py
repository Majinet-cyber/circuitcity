# billing/views_paychangu.py
"""
PayChangu payment provider views.
Handles checkout initiation, webhooks, and return/callback URLs.
"""
from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal

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
    Payment,
    PaymentTransaction,
    WebhookEvent,
    Invoice,
)
from . import paychangu_service

logger = logging.getLogger(__name__)


# ==============================================================================
# PAYCHANGU CHECKOUT INITIATION
# ==============================================================================

@login_required
@require_business
@require_POST
def paychangu_initiate(request: HttpRequest) -> HttpResponse:
    """
    Initiate a PayChangu checkout session.
    
    POST params:
        - plan_code: slug of the SubscriptionPlan
        - amount: payment amount (optional, defaults to plan amount)
    
    Returns:
        JSON response with checkout_url or error
    """
    business: Business = request.business
    location = getattr(request, "location", None) or getattr(business, "locations", None).first() if hasattr(business, "locations") else None
    
    plan_code = request.POST.get("plan_code", "").strip()
    amount_str = request.POST.get("amount", "").strip()
    
    if not plan_code:
        return JsonResponse({
            "status": "error",
            "message": "No plan selected."
        }, status=400)
    
    # Load plan
    try:
        plan = SubscriptionPlan.objects.get(code=plan_code, is_active=True)
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({
            "status": "error",
            "message": f"Plan '{plan_code}' not found."
        }, status=404)
    
    # Determine amount
    if amount_str:
        try:
            amount = Decimal(amount_str)
        except Exception:
            return JsonResponse({
                "status": "error",
                "message": "Invalid amount format."
            }, status=400)
    else:
        amount = plan.amount
    
    # Check if PayChangu is configured
    if not paychangu_service.is_paychangu_configured():
        return JsonResponse({
            "status": "error",
            "message": "PayChangu is not configured. Please use another payment method or contact support."
        }, status=503)
    
    # Generate unique transaction reference
    tx_ref = f"pc-{business.id}-{uuid.uuid4().hex[:12]}-{int(timezone.now().timestamp())}"
    
    # Build return and callback URLs
    return_url = request.build_absolute_uri(reverse("billing:paychangu_return"))
    callback_url = request.build_absolute_uri(reverse("billing:paychangu_webhook"))
    
    # Metadata
    meta = {
        "plan_code": plan_code,
        "user_id": str(request.user.id),
        "user_email": request.user.email,
    }
    
    # Create PaymentTransaction record (pending)
    try:
        transaction = PaymentTransaction.objects.create(
            business=business,
            location=location,
            created_by=request.user,
            provider="paychangu",
            tx_ref=tx_ref,
            amount=amount,
            currency=plan.currency,
            status=PaymentTransaction.Status.PENDING,
        )
    except Exception as e:
        logger.error(f"Failed to create PaymentTransaction: {e}")
        return JsonResponse({
            "status": "error",
            "message": "Failed to create transaction record."
        }, status=500)
    
    # Call PayChangu API to create checkout
    result = paychangu_service.create_checkout(
        business=business,
        location=location,
        amount=amount,
        currency=plan.currency,
        tx_ref=tx_ref,
        return_url=return_url,
        callback_url=callback_url,
        meta=meta,
        user_email=request.user.email,
        user_phone=getattr(request.user, "phone", None),
        description=f"{plan.name} subscription",
    )
    
    if result.get("status") != "success":
        logger.error(f"PayChangu checkout failed for business {business.id}: {result.get('message')}")
        transaction.mark_failed()
        return JsonResponse({
            "status": "error",
            "message": result.get("message", "Failed to create checkout.")
        }, status=500)
    
    # Update transaction with checkout URL and raw payload
    transaction.checkout_url = result.get("checkout_url", "")
    transaction.raw_init_payload = result.get("raw_response", {})
    transaction.save(update_fields=["checkout_url", "raw_init_payload", "updated_at"])
    
    logger.info(
        f"PayChangu checkout initiated: business={business.id}, "
        f"tx_ref={tx_ref}, amount={amount}"
    )
    
    return JsonResponse({
        "status": "success",
        "checkout_url": result.get("checkout_url"),
        "tx_ref": tx_ref,
        "message": "Checkout created successfully."
    })


# ==============================================================================
# PAYCHANGU WEBHOOK (IPN)
# ==============================================================================

@csrf_exempt
@require_POST
def paychangu_webhook(request: HttpRequest) -> HttpResponse:
    """
    Handle PayChangu webhook notifications.
    
    Verifies signature, extracts tx_ref, calls verify API, updates transaction.
    Must return 200 quickly to acknowledge receipt.
    """
    # Get raw request body BEFORE any parsing
    payload = request.body
    
    # Read signature from header (try multiple names)
    # Prefer request.headers.get() first, then fall back to META
    signature = (
        request.headers.get("Signature", "")
        or request.META.get("HTTP_SIGNATURE", "")
        or request.headers.get("X-Signature", "")
        or request.META.get("HTTP_X_SIGNATURE", "")
        or request.headers.get("X-PayChangu-Signature", "")
        or request.META.get("HTTP_X_PAYCHANGU_SIGNATURE", "")
    ).strip()
    
    if not signature:
        logger.warning("PayChangu webhook missing signature header")
        return HttpResponse("Missing signature", status=401)
    
    # Verify signature using raw bytes (BEFORE any JSON parsing)
    is_valid = paychangu_service.verify_webhook_signature(payload, signature)
    if not is_valid:
        logger.warning("PayChangu webhook signature verification failed")
        return HttpResponse("Invalid signature", status=401)
    
    # Parse payload
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as e:
        logger.error(f"PayChangu webhook: failed to parse JSON: {e}")
        return HttpResponseBadRequest("Invalid JSON")
    
    # Log webhook event
    try:
        WebhookEvent.objects.create(
            provider="paychangu",
            event_type=data.get("event", "webhook"),
            external_id=data.get("tx_ref", ""),
            payload=data,
        )
    except Exception as e:
        logger.error(f"Failed to log PayChangu webhook: {e}")
    
    # Extract transaction reference - try various field names
    tx_ref = (
        data.get("tx_ref") 
        or data.get("reference")
        or data.get("transaction_id")
        or data.get("payment_reference")
        or data.get("transaction_reference")
    )
    
    if not tx_ref:
        logger.warning(f"PayChangu webhook missing tx_ref in payload: {list(data.keys())}")
        return HttpResponse("OK", status=200)  # Return 200 to avoid retries
    
    logger.info(f"PayChangu webhook received for tx_ref={tx_ref}")
    
    # Find transaction
    try:
        transaction = PaymentTransaction.objects.get(tx_ref=tx_ref, provider="paychangu")
    except PaymentTransaction.DoesNotExist:
        logger.warning(f"PayChangu webhook: transaction not found for tx_ref {tx_ref}")
        return HttpResponse("OK", status=200)  # Return 200 to avoid retries
    
    # Idempotency: skip if already SUCCESS
    if transaction.status == PaymentTransaction.Status.SUCCESS:
        logger.info(f"PayChangu webhook: transaction {tx_ref} already SUCCESS, skipping")
        return HttpResponse("OK", status=200)
    
    # Store webhook payload
    transaction.raw_webhook_payload = data
    transaction.save(update_fields=["raw_webhook_payload", "updated_at"])
    
    # Verify transaction with PayChangu API
    verify_result = paychangu_service.verify_payment(tx_ref)
    
    if verify_result.get("status") == "ERROR":
        logger.error(f"PayChangu verify API failed for {tx_ref}: {verify_result.get('message')}")
        return HttpResponse("OK", status=200)  # Return 200 to avoid retries
    
    # Update transaction based on verification result
    # Accept various success status strings
    verified_status = verify_result.get("status")
    
    # Also check webhook payload status for immediate feedback
    webhook_status = (
        data.get("status", "").lower()
        or data.get("payment_status", "").lower()
        or data.get("transaction_status", "").lower()
    )
    
    # Map common success indicators
    success_indicators = ["success", "successful", "completed", "complete"]
    if webhook_status in success_indicators and verified_status == "SUCCESS":
        logger.info(f"Webhook status '{webhook_status}' confirmed by verify API")
    elif webhook_status in success_indicators:
        logger.info(f"Webhook indicates success ('{webhook_status}'), but verify API returned: {verified_status}")
    
    if verified_status == "SUCCESS":
        # Mark transaction as successful (idempotent)
        transaction.mark_success(verify_result.get("raw_response", {}))
        logger.info(f"PayChangu transaction {tx_ref} marked SUCCESS")
        
        # Find and process associated invoice
        try:
            # Look for invoice in transaction metadata or find by business
            from .models import Invoice
            
            # Try to find invoice from session data or business context
            invoice = None
            if transaction.business:
                # Find the most recent unpaid invoice for this business
                invoice = Invoice.objects.filter(
                    business=transaction.business,
                    status__in=[Invoice.Status.DRAFT, Invoice.Status.SENT],
                    total=transaction.amount,
                    currency=transaction.currency,
                ).order_by('-created_at').first()
            
            if invoice:
                # Mark invoice as paid (idempotent)
                if invoice.status != Invoice.Status.PAID:
                    invoice.mark_paid()
                    logger.info(f"Invoice {invoice.number} marked PAID for tx_ref {tx_ref}")
                
                # Activate subscription
                try:
                    sub = getattr(transaction.business, "subscription", None)
                    if sub and sub.status != BusinessSubscription.Status.ACTIVE:
                        sub.status = BusinessSubscription.Status.ACTIVE
                        sub.last_payment_at = timezone.now()
                        sub.payment_method = BusinessSubscription.Method.AIRTEL  # Default
                        
                        # Set payment method based on transaction metadata
                        meta = transaction.raw_init_payload.get("meta", {})
                        payment_method = meta.get("payment_method", "")
                        if payment_method == "AIRTEL_MONEY":
                            sub.payment_method = BusinessSubscription.Method.AIRTEL
                        elif payment_method == "BANK":
                            sub.payment_method = BusinessSubscription.Method.STANDARD_BANK
                        elif payment_method == "CARD":
                            sub.payment_method = BusinessSubscription.Method.CARD
                        
                        # Advance billing period
                        sub.advance_period()
                        sub.save(update_fields=[
                            "status", "last_payment_at", "payment_method", 
                            "current_period_start", "current_period_end", 
                            "next_billing_date", "updated_at"
                        ])
                        logger.info(
                            f"Subscription activated for business {transaction.business.id}, "
                            f"tx_ref {tx_ref}"
                        )
                    elif sub and sub.status == BusinessSubscription.Status.ACTIVE:
                        logger.info(
                            f"Subscription already ACTIVE for business {transaction.business.id}, "
                            f"tx_ref {tx_ref} - skipping activation (idempotent)"
                        )
                except Exception as e:
                    logger.error(f"Failed to activate subscription for tx_ref {tx_ref}: {e}", exc_info=True)
            else:
                logger.warning(
                    f"No matching invoice found for tx_ref {tx_ref}, "
                    f"business={transaction.business.id}, amount={transaction.amount}"
                )
        
        except Exception as e:
            logger.error(f"Failed to process invoice/subscription for tx_ref {tx_ref}: {e}", exc_info=True)
        
        logger.info(f"Webhook confirmed: tx_ref={tx_ref}, status=SUCCESS, invoice marked PAID")
    
    elif verified_status == "FAILED":
        transaction.mark_failed(verify_result.get("raw_response", {}))
        logger.info(f"PayChangu transaction {tx_ref} marked FAILED")
    
    else:
        # PENDING or other status - keep as pending
        logger.info(f"PayChangu transaction {tx_ref} still {verified_status}")
    
    return HttpResponse("OK", status=200)


# ==============================================================================
# PAYCHANGU RETURN (Browser Redirect)
# ==============================================================================

@login_required
def paychangu_return(request: HttpRequest) -> HttpResponse:
    """
    Browser return page after PayChangu payment.
    Shows "Payment processing..." page with auto-polling.
    
    Query params from PayChangu:
        - tx_ref, reference, or transaction_id: transaction reference
        - status: optional status hint
    """
    # Extract tx_ref from various possible field names
    tx_ref = (
        request.GET.get("tx_ref") 
        or request.GET.get("reference")
        or request.GET.get("transaction_id")
        or request.GET.get("payment_reference")
        or ""
    )
    
    if not tx_ref:
        logger.warning("PayChangu return: no tx_ref in query params")
        return render(
            request,
            "billing/paychangu_return.html",
            {
                "tx_ref": "",
                "status": "error",
                "message": "No payment reference found. Please contact support if you completed a payment.",
            },
        )
    
    # Store tx_ref in session for easy retrieval
    request.session["paychangu_return_tx_ref"] = tx_ref
    request.session.save()
    
    logger.info(f"PayChangu return: tx_ref={tx_ref}")
    
    # Render processing page (will poll via JavaScript)
    return render(
        request,
        "billing/paychangu_return.html",
        {
            "tx_ref": tx_ref,
            "status": "processing",
            "message": "Payment is being processed. Please wait...",
        },
    )


# ==============================================================================
# PAYCHANGU PAYMENT STATUS API (for polling)
# ==============================================================================

@login_required
@require_business
def paychangu_payment_status(request: HttpRequest) -> JsonResponse:
    """
    JSON API endpoint to check payment status.
    Used by return page to poll for payment confirmation.
    
    Query params:
        - tx_ref: transaction reference
    
    Returns:
        {
            "status": "pending" | "success" | "failed",
            "transaction_status": "...",
            "invoice_status": "...",
            "subscription_status": "...",
            "next_url": "/dashboard/..." (when success),
            "message": "..."
        }
    """
    business = request.business
    tx_ref = request.GET.get("tx_ref", "").strip()
    
    if not tx_ref:
        return JsonResponse({
            "status": "error",
            "message": "Missing tx_ref parameter"
        }, status=400)
    
    # Find transaction - scoped to current business (multi-tenant safe)
    try:
        transaction = PaymentTransaction.objects.get(
            tx_ref=tx_ref,
            business=business,
            provider="PAYCHANGU"
        )
    except PaymentTransaction.DoesNotExist:
        logger.warning(f"Payment status check: tx_ref {tx_ref} not found for business {business.id}")
        return JsonResponse({
            "status": "error",
            "message": "Payment not found"
        }, status=404)
    
    # Get related invoice and subscription
    invoice = None
    subscription = None
    
    try:
        invoice = Invoice.objects.filter(
            business=business,
            total=transaction.amount,
            currency=transaction.currency,
        ).order_by('-created_at').first()
    except Exception:
        pass
    
    try:
        subscription = getattr(business, "subscription", None)
    except Exception:
        pass
    
    # Build response based on transaction status
    if transaction.status == PaymentTransaction.Status.SUCCESS:
        return JsonResponse({
            "status": "success",
            "transaction_status": transaction.status,
            "invoice_status": invoice.status if invoice else None,
            "subscription_status": subscription.status if subscription else None,
            "next_url": "/inventory/dashboard/",  # or wherever you want to redirect
            "message": "Payment confirmed! Your subscription is now active."
        })
    
    elif transaction.status == PaymentTransaction.Status.FAILED:
        return JsonResponse({
            "status": "failed",
            "transaction_status": transaction.status,
            "invoice_status": invoice.status if invoice else None,
            "subscription_status": subscription.status if subscription else None,
            "message": "Payment failed. Please try again or contact support."
        })
    
    else:
        # Still pending - check with PayChangu API for latest status
        verify_result = paychangu_service.verify_payment(tx_ref)
        
        if verify_result.get("status") == "SUCCESS":
            # Update transaction immediately
            transaction.mark_success(verify_result.get("raw_response", {}))
            
            # Activate invoice and subscription (same logic as webhook)
            if invoice and invoice.status != Invoice.Status.PAID:
                invoice.mark_paid()
            
            if subscription and subscription.status != BusinessSubscription.Status.ACTIVE:
                subscription.status = BusinessSubscription.Status.ACTIVE
                subscription.last_payment_at = timezone.now()
                subscription.advance_period()
                subscription.save()
            
            return JsonResponse({
                "status": "success",
                "transaction_status": "success",
                "invoice_status": invoice.status if invoice else None,
                "subscription_status": subscription.status if subscription else None,
                "next_url": "/inventory/dashboard/",
                "message": "Payment confirmed! Your subscription is now active."
            })
        
        elif verify_result.get("status") == "FAILED":
            transaction.mark_failed(verify_result.get("raw_response", {}))
            return JsonResponse({
                "status": "failed",
                "transaction_status": "failed",
                "message": "Payment failed. Please try again."
            })
        
        else:
            # Still pending
            return JsonResponse({
                "status": "pending",
                "transaction_status": "pending",
                "message": "Payment is being processed..."
            })


# ==============================================================================
# PAYCHANGU CALLBACK (Optional Alternative to Webhook)
# ==============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def paychangu_callback(request: HttpRequest) -> HttpResponse:
    """
    Optional callback endpoint for PayChangu backend notifications.
    Similar to webhook but might be called differently by PayChangu.
    
    If PayChangu uses this instead of webhook, implement same logic as webhook.
    For now, redirect to webhook handler.
    """
    # If POST, treat as webhook
    if request.method == "POST":
        return paychangu_webhook(request)
    
    # If GET, extract params and show status
    tx_ref = request.GET.get("tx_ref", "")
    return redirect(f"{reverse('billing:paychangu_return')}?tx_ref={tx_ref}")

