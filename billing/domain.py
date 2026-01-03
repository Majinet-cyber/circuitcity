# billing/domain.py
"""
Domain services for billing operations.
Centralized business logic for subscription lifecycle, payment processing, and invoice management.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BusinessSubscription, Invoice, InvoiceItem, Payment, PaymentEvent, PaymentTransaction

logger = logging.getLogger(__name__)

# ======================================================================
# Idempotency Key Generation
# ======================================================================


def compute_idempotency_key(
    provider: str,
    tx_ref: str,
    event_type: str = "",
    amount: str = "",
    currency: str = "",
) -> str:
    """
    Compute deterministic idempotency key for payment events.

    Args:
        provider: Payment provider name (paychangu, stripe, etc.)
        tx_ref: Transaction reference
        event_type: Event type (payment.success, payment.failed, etc.)
        amount: Payment amount (string)
        currency: Currency code

    Returns:
        SHA256 hash of concatenated inputs
    """
    key_input = f"{provider}:{tx_ref}:{event_type}:{amount}:{currency}"
    return hashlib.sha256(key_input.encode()).hexdigest()


# ======================================================================
# Subscription Lifecycle State Transitions
# ======================================================================


def activate_subscription(
    subscription: BusinessSubscription,
    *,
    payment_method: str = "",
    period_days: Optional[int] = None,
) -> BusinessSubscription:
    """
    Activate subscription and start paid period.

    Args:
        subscription: BusinessSubscription instance
        payment_method: Payment method used (airtel, card, etc.)
        period_days: Billing period length (defaults to plan interval)

    Returns:
        Updated subscription
    """
    now = timezone.now()
    subscription.status = BusinessSubscription.Status.ACTIVE
    subscription.current_period_start = now
    subscription.last_payment_at = now

    if period_days is None:
        from .models import SubscriptionPlan

        period_days = 30 if subscription.plan.interval == SubscriptionPlan.Interval.MONTH else 365

    subscription.current_period_end = now + timedelta(days=period_days)
    subscription.next_billing_date = subscription.current_period_end

    if payment_method:
        # Map payment method to subscription method enum
        method_map = {
            "airtel": BusinessSubscription.Method.AIRTEL,
            "tnm": BusinessSubscription.Method.AIRTEL,  # Use same enum
            "card": BusinessSubscription.Method.CARD,
            "standard_bank": BusinessSubscription.Method.STANDARD_BANK,
            "stripe": BusinessSubscription.Method.STRIPE,
            "pesapal": BusinessSubscription.Method.PESAPAL,
        }
        subscription.payment_method = method_map.get(payment_method.lower(), BusinessSubscription.Method.NONE)

    subscription.save(
        update_fields=[
            "status",
            "current_period_start",
            "current_period_end",
            "next_billing_date",
            "last_payment_at",
            "payment_method",
            "updated_at",
        ]
    )

    logger.info(
        f"Subscription activated: business={subscription.business.id}, "
        f"plan={subscription.plan.code}, period_days={period_days}"
    )

    return subscription


def mark_past_due(subscription: BusinessSubscription) -> BusinessSubscription:
    """
    Mark subscription as past due (payment failed or period expired without payment).

    Args:
        subscription: BusinessSubscription instance

    Returns:
        Updated subscription
    """
    subscription.status = BusinessSubscription.Status.PAST_DUE
    subscription.save(update_fields=["status", "updated_at"])

    logger.info(f"Subscription marked PAST_DUE: business={subscription.business.id}")

    return subscription


def suspend_subscription(subscription: BusinessSubscription, reason: str = "") -> BusinessSubscription:
    """
    Suspend subscription (block access, preserve data).

    Args:
        subscription: BusinessSubscription instance
        reason: Reason for suspension

    Returns:
        Updated subscription
    """
    subscription.status = BusinessSubscription.Status.SUSPENDED
    if reason:
        subscription.meta["suspended_reason"] = reason
        subscription.meta["suspended_at"] = timezone.now().isoformat()
    subscription.save(update_fields=["status", "meta", "updated_at"])

    logger.warning(f"Subscription SUSPENDED: business={subscription.business.id}, reason={reason}")

    return subscription


def refresh_subscription_status(subscription: BusinessSubscription) -> BusinessSubscription:
    """
    Refresh subscription status based on current time and dates.
    This is the canonical status normalization function.

    Transitions:
    - TRIAL → PAST_DUE (if trial_end passed)
    - ACTIVE → PAST_DUE (if current_period_end passed)
    - PAST_DUE → SUSPENDED (if grace period expired)

    Args:
        subscription: BusinessSubscription instance

    Returns:
        Updated subscription
    """
    now = timezone.now()
    changed = False
    original_status = subscription.status
    grace_days = getattr(settings, "BILLING_GRACE_DAYS", 7)

    # Skip if already in terminal state
    if subscription.status in (
        BusinessSubscription.Status.SUSPENDED,
        BusinessSubscription.Status.CANCELED,
        BusinessSubscription.Status.EXPIRED,
    ):
        return subscription

    # TRIAL → PAST_DUE (trial expired)
    if subscription.status in (BusinessSubscription.Status.TRIAL, BusinessSubscription.Status.TRIALING):
        if subscription.trial_end and now >= subscription.trial_end:
            subscription.status = BusinessSubscription.Status.PAST_DUE
            changed = True
            logger.info(
                f"Subscription trial expired: business={subscription.business.id}, "
                f"trial_end={subscription.trial_end}"
            )

    # ACTIVE → PAST_DUE (period expired)
    elif subscription.status == BusinessSubscription.Status.ACTIVE:
        if subscription.current_period_end and now > subscription.current_period_end:
            subscription.status = BusinessSubscription.Status.PAST_DUE
            changed = True
            logger.info(
                f"Subscription period expired: business={subscription.business.id}, "
                f"current_period_end={subscription.current_period_end}"
            )

    # PAST_DUE → SUSPENDED (grace expired)
    if subscription.status == BusinessSubscription.Status.PAST_DUE:
        # Determine grace anchor
        grace_anchor = subscription.next_billing_date or subscription.current_period_end or subscription.trial_end

        if grace_anchor:
            grace_deadline = grace_anchor + timedelta(days=grace_days)
            if now >= grace_deadline:
                suspend_subscription(
                    subscription, reason=f"Grace period expired ({grace_days} days after {grace_anchor.date()})"
                )
                changed = True
                logger.warning(
                    f"Subscription suspended after grace: business={subscription.business.id}, "
                    f"grace_deadline={grace_deadline}"
                )

    if changed and subscription.status != original_status:
        subscription.save(update_fields=["status", "updated_at"])
        logger.info(
            f"Subscription status changed: business={subscription.business.id}, "
            f"{original_status} → {subscription.status}"
        )

    return subscription


def process_subscription_renewals() -> Dict[str, Any]:
    """
    Process all subscription renewals and status transitions.
    Should be called daily via scheduled task.

    Returns:
        Dict with processing statistics
    """
    from .models import BusinessSubscription

    stats = {
        "total_checked": 0,
        "expired_trials": 0,
        "expired_periods": 0,
        "suspended": 0,
        "errors": 0,
    }

    # Get all non-terminal subscriptions
    subscriptions = BusinessSubscription.objects.filter(
        status__in=[
            BusinessSubscription.Status.TRIAL,
            BusinessSubscription.Status.TRIALING,
            BusinessSubscription.Status.ACTIVE,
            BusinessSubscription.Status.PAST_DUE,
        ]
    ).select_related("business", "plan")

    logger.info(f"Processing {subscriptions.count()} subscriptions for status refresh")

    for sub in subscriptions:
        stats["total_checked"] += 1
        original_status = sub.status

        try:
            refresh_subscription_status(sub)

            # Track transitions
            if original_status in (BusinessSubscription.Status.TRIAL, BusinessSubscription.Status.TRIALING):
                if sub.status == BusinessSubscription.Status.PAST_DUE:
                    stats["expired_trials"] += 1
            elif original_status == BusinessSubscription.Status.ACTIVE:
                if sub.status == BusinessSubscription.Status.PAST_DUE:
                    stats["expired_periods"] += 1
            elif original_status == BusinessSubscription.Status.PAST_DUE:
                if sub.status == BusinessSubscription.Status.SUSPENDED:
                    stats["suspended"] += 1

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error processing subscription {sub.id} for business {sub.business.id}: {e}", exc_info=True)

    logger.info(
        f"Subscription renewal processing complete: {stats['total_checked']} checked, "
        f"{stats['expired_trials']} trials expired, {stats['expired_periods']} periods expired, "
        f"{stats['suspended']} suspended, {stats['errors']} errors"
    )

    return stats


# ======================================================================
# Invoice Operations
# ======================================================================


def apply_payment_to_invoice(
    invoice: Invoice,
    payment_transaction: PaymentTransaction,
) -> Invoice:
    """
    Apply payment to invoice and mark as paid.
    Also generates PDF for download.

    Args:
        invoice: Invoice instance
        payment_transaction: PaymentTransaction instance

    Returns:
        Updated invoice
    """
    if invoice.status == Invoice.Status.PAID:
        logger.info(f"Invoice {invoice.number} already PAID, skipping (idempotent)")
        return invoice

    invoice.status = Invoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.provider_reference = payment_transaction.tx_ref
    invoice.save(update_fields=["status", "paid_at", "provider_reference", "updated_at"])

    logger.info(f"Invoice {invoice.number} marked PAID, " f"provider_reference={payment_transaction.tx_ref}")

    # Generate PDF asynchronously (non-blocking)
    try:
        from . import pdf_generator

        pdf_generator.generate_and_save_invoice_pdf(invoice)
        logger.info(f"Invoice {invoice.number} PDF generated successfully")
    except Exception as e:
        logger.error(f"Failed to generate PDF for invoice {invoice.number}: {e}", exc_info=True)
        # Don't fail the payment if PDF generation fails

    return invoice


def create_subscription_invoice(
    business,
    subscription: BusinessSubscription,
    *,
    period_start=None,
    period_end=None,
    provider_reference: str = "",
) -> Invoice:
    """
    Create invoice for subscription billing period.

    Args:
        business: Business instance
        subscription: BusinessSubscription instance
        period_start: Billing period start date
        period_end: Billing period end date
        provider_reference: Payment provider reference

    Returns:
        Created invoice
    """
    if period_start is None:
        period_start = timezone.localdate()
    if period_end is None:
        period_end = period_start + timedelta(days=30)

    invoice = Invoice.objects.create(
        business=business,
        subscription=subscription,
        currency=subscription.plan.currency,
        billing_period_start=period_start,
        billing_period_end=period_end,
        provider_reference=provider_reference,
        status=Invoice.Status.ISSUED,
        issued_at=timezone.now(),
    )

    # Add line item for subscription
    InvoiceItem.objects.create(
        invoice=invoice,
        description=f"{subscription.plan.name} — {subscription.plan.get_interval_display()}",
        qty=Decimal("1"),
        unit="period",
        unit_price=subscription.plan.amount,
    )

    invoice.recalc_totals(save=True)

    logger.info(
        f"Invoice {invoice.number} created for subscription, " f"business={business.id}, amount={invoice.total}"
    )

    return invoice


# ======================================================================
# Webhook Event Processing (Idempotent + Atomic)
# ======================================================================


@transaction.atomic
def process_payment_webhook(
    *,
    provider: str,
    tx_ref: str,
    event_type: str,
    amount: Decimal,
    currency: str,
    payload: Dict[str, Any],
    signature_valid: bool,
    event_id: str = "",
) -> Dict[str, Any]:
    """
    Process payment webhook event with full idempotency and atomicity.

    This is the single source of truth for webhook processing.
    All webhook handlers should call this function.

    Args:
        provider: Payment provider (paychangu, stripe, etc.)
        tx_ref: Transaction reference
        event_type: Event type (payment.success, etc.)
        amount: Payment amount
        currency: Currency code
        payload: Raw webhook payload
        signature_valid: Whether signature was verified
        event_id: Provider's event ID (if available)

    Returns:
        Dict with:
            - status: "processed" | "ignored" | "failed"
            - message: Description
            - event: PaymentEvent instance
    """
    # Compute idempotency key
    idempotency_key = compute_idempotency_key(
        provider=provider,
        tx_ref=tx_ref,
        event_type=event_type,
        amount=str(amount),
        currency=currency,
    )

    # Get or create PaymentEvent (idempotent)
    event, created = PaymentEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "provider": provider,
            "event_id": event_id,
            "reference": tx_ref,
            "event_type": event_type,
            "payload_json": payload,
            "signature_valid": signature_valid,
            "status": PaymentEvent.Status.RECEIVED,
        },
    )

    if not created:
        # Event already exists
        if event.status == PaymentEvent.Status.PROCESSED:
            logger.info(f"Event {idempotency_key[:16]}... already PROCESSED, skipping (idempotent)")
            return {
                "status": "ignored",
                "message": "Event already processed",
                "event": event,
            }
        elif event.status == PaymentEvent.Status.IGNORED:
            logger.info(f"Event {idempotency_key[:16]}... already IGNORED, skipping")
            return {
                "status": "ignored",
                "message": "Event already ignored",
                "event": event,
            }

    # Signature validation check
    if not signature_valid:
        error_msg = "Webhook signature verification failed"
        event.mark_failed(error_msg)
        logger.error(f"Event {idempotency_key[:16]}... signature invalid")
        return {
            "status": "failed",
            "message": error_msg,
            "event": event,
        }

    # Find payment transaction (with row lock)
    try:
        payment_txn = PaymentTransaction.objects.select_for_update().get(
            tx_ref=tx_ref,
            provider=provider,
        )
    except PaymentTransaction.DoesNotExist:
        error_msg = f"PaymentTransaction not found for tx_ref={tx_ref}"
        event.mark_ignored(error_msg)
        logger.warning(f"Event {idempotency_key[:16]}... {error_msg}")
        return {
            "status": "ignored",
            "message": error_msg,
            "event": event,
        }

    # Check if transaction already processed
    if payment_txn.status == PaymentTransaction.Status.SUCCESS:
        event.mark_ignored("Transaction already SUCCESS")
        logger.info(f"Event {idempotency_key[:16]}... transaction already SUCCESS, skipping")
        return {
            "status": "ignored",
            "message": "Transaction already successful",
            "event": event,
        }

    # Process based on event type
    try:
        if event_type in ("payment.success", "payment.completed", "charge.succeeded"):
            # Mark transaction successful
            payment_txn.mark_success(payload)

            # Find or create invoice
            invoice = _find_or_create_invoice_for_transaction(payment_txn)

            if invoice:
                # Mark invoice paid
                apply_payment_to_invoice(invoice, payment_txn)

                # Activate subscription
                subscription = getattr(payment_txn.business, "subscription", None)
                if subscription and subscription.status != BusinessSubscription.Status.ACTIVE:
                    activate_subscription(
                        subscription,
                        payment_method=payment_txn.payment_method,
                    )

            event.mark_processed()

            logger.info(
                f"Event {idempotency_key[:16]}... PROCESSED successfully, "
                f"tx_ref={tx_ref}, invoice={invoice.number if invoice else 'N/A'}"
            )

            return {
                "status": "processed",
                "message": "Payment processed successfully",
                "event": event,
                "transaction": payment_txn,
                "invoice": invoice,
            }

        elif event_type in ("payment.failed", "payment.cancelled", "charge.failed"):
            payment_txn.mark_failed(payload)
            event.mark_processed()

            logger.info(f"Event {idempotency_key[:16]}... payment FAILED, tx_ref={tx_ref}")

            return {
                "status": "processed",
                "message": "Payment failed",
                "event": event,
                "transaction": payment_txn,
            }

        else:
            # Unknown event type
            event.mark_ignored(f"Unknown event type: {event_type}")
            logger.warning(f"Event {idempotency_key[:16]}... unknown event_type={event_type}")
            return {
                "status": "ignored",
                "message": f"Unknown event type: {event_type}",
                "event": event,
            }

    except Exception as e:
        error_msg = f"Error processing event: {str(e)}"
        event.mark_failed(error_msg)
        logger.error(f"Event {idempotency_key[:16]}... processing failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "message": error_msg,
            "event": event,
        }


def _find_or_create_invoice_for_transaction(payment_txn: PaymentTransaction) -> Optional[Invoice]:
    """
    Find or create invoice for payment transaction.

    Args:
        payment_txn: PaymentTransaction instance

    Returns:
        Invoice instance or None
    """
    # Try to find existing invoice by provider_reference
    invoice = Invoice.objects.filter(
        provider_reference=payment_txn.tx_ref,
        business=payment_txn.business,
    ).first()

    if invoice:
        return invoice

    # Try to find by amount + currency + business (heuristic match)
    invoice = (
        Invoice.objects.filter(
            business=payment_txn.business,
            total=payment_txn.amount,
            currency=payment_txn.currency,
            status__in=[Invoice.Status.DRAFT, Invoice.Status.ISSUED, Invoice.Status.SENT],
        )
        .order_by("-created_at")
        .first()
    )

    if invoice:
        # Link invoice to transaction
        invoice.provider_reference = payment_txn.tx_ref
        invoice.save(update_fields=["provider_reference", "updated_at"])
        return invoice

    # Create new invoice for subscription payment
    subscription = getattr(payment_txn.business, "subscription", None)
    if subscription:
        invoice = create_subscription_invoice(
            business=payment_txn.business,
            subscription=subscription,
            provider_reference=payment_txn.tx_ref,
        )
        return invoice

    logger.warning(
        f"No invoice found or created for tx_ref={payment_txn.tx_ref}, " f"business={payment_txn.business.id}"
    )
    return None
