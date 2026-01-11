# billing/tasks.py
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import paychangu_service
from .models import BusinessSubscription
from .notify import fanout


@shared_task
def remind_trials_ending_soon():
    """
    Send a reminder when a business trial ends in ~1 day.
    Runs daily via Celery Beat.
    """
    now = timezone.now()
    start = now + timedelta(hours=12)  # pick a window ~tomorrow
    end = now + timedelta(hours=36)

    qs = BusinessSubscription.objects.select_related("business").filter(
        status=BusinessSubscription.Status.TRIAL,
        trial_end__gte=start,
        trial_end__lt=end,
    )

    count = 0
    for sub in qs:
        biz = sub.business
        if not biz:
            continue
        ends = sub.trial_end.astimezone(timezone.get_current_timezone())
        title = "Your trial ends tomorrow"
        body = (
            f"Hi! A quick reminder that your Circuit City trial for "
            f"{getattr(biz, 'name', 'your business')} ends on {ends:%b %d, %Y %H:%M}.\n\n"
            f"To keep agents and managers active, please subscribe from the app.\n"
            f"Payment options: Airtel Money, Standard Bank, Card."
        )
        fanout(business=biz, title=title, body=body, ntype="trial_notice")
        count += 1
    return {"reminded": count}


@shared_task
def process_subscription_renewals():
    """
    Process all subscription renewals and status transitions.
    Should be run daily via Celery Beat.

    Transitions:
    - TRIAL → PAST_DUE (trial expired)
    - ACTIVE → PAST_DUE (period expired)
    - PAST_DUE → SUSPENDED (grace expired)

    Returns:
        Dict with processing statistics
    """
    from . import domain

    stats = domain.process_subscription_renewals()

    return {
        "total_checked": stats["total_checked"],
        "expired_trials": stats["expired_trials"],
        "expired_periods": stats["expired_periods"],
        "suspended": stats["suspended"],
        "errors": stats["errors"],
    }


@shared_task
def send_invoice_paid_email(invoice_id):
    """
    Celery task to send invoice paid confirmation email.

    Args:
        invoice_id: UUID or int ID of the Invoice

    Sends HTML + plain text email with optional PDF attachment.
    Non-blocking: failures are logged but don't break webhook processing.
    """
    import logging

    from django.conf import settings
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.urls import reverse

    from .models import Invoice

    logger = logging.getLogger(__name__)

    logger.info(f"Sending invoice paid email for invoice_id={invoice_id}")

    try:
        invoice = Invoice.objects.select_related("business", "subscription").get(pk=invoice_id)
    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_id} not found for email send")
        return

    if invoice.status != Invoice.Status.PAID:
        logger.warning(f"Invoice {invoice_id} is not PAID (status={invoice.status}), skipping email")
        return

    # Idempotency check: only send email once per invoice
    # Use meta field to track if email was sent
    if invoice.meta.get("email_sent"):
        logger.info(f"Email already sent for invoice {invoice.number} (idempotent), skipping")
        return

    # Get recipient email
    business = invoice.business
    recipient_email = None

    if business:
        # Try business email first
        recipient_email = getattr(business, "email", None)

        # Fallback to manager email
        if not recipient_email:
            try:
                manager_membership = (
                    business.memberships.filter(role__in=["OWNER", "MANAGER"]).order_by("-created_at").first()
                )
                if manager_membership and manager_membership.user:
                    recipient_email = manager_membership.user.email
            except Exception:
                pass

    # Fallback to invoice creator
    if not recipient_email and invoice.created_by:
        recipient_email = invoice.created_by.email

    if not recipient_email:
        logger.error(f"No recipient email found for invoice {invoice.number}")
        return

    # Build context for template
    subscription = invoice.subscription
    next_billing_date = None
    if subscription:
        next_billing_date = subscription.current_period_end

    # Build download URL (full URL)
    download_url = None
    try:
        from django.contrib.sites.models import Site

        domain = Site.objects.get_current().domain
        download_path = reverse("billing:invoice_download", args=[invoice.pk])
        download_url = f"https://{domain}{download_path}"
    except Exception:
        # Fallback if Sites framework not configured
        download_url = f"https://emajinet.com/billing/invoice/{invoice.pk}/download/"

    context = {
        "invoice": invoice,
        "business": business,
        "subscription": subscription,
        "next_billing_date": next_billing_date,
        "payment_method": getattr(subscription, "payment_method", "Mobile Money") if subscription else "Mobile Money",
        "provider_reference": invoice.provider_reference or "",
        "download_url": download_url,
        "dashboard_url": "https://emajinet.com/app/",
        "support_url": "mailto:support@emajinet.com",
    }

    # Render templates
    subject = f"Payment Confirmed - Invoice {invoice.number}"
    text_content = render_to_string("billing/emails/invoice_paid.txt", context)
    html_content = render_to_string("billing/emails/invoice_paid.html", context)

    # Create email
    email = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient_email]
    )
    email.attach_alternative(html_content, "text/html")

    # Optionally attach PDF (if generated and not too large)
    if invoice.pdf_file and invoice.pdf_file.name:
        try:
            # Only attach if file size < 5MB
            file_size = invoice.pdf_file.size
            if file_size < 5 * 1024 * 1024:  # 5MB limit
                email.attach_file(invoice.pdf_file.path)
                logger.info(f"Attached PDF to email: {invoice.pdf_file.name} ({file_size} bytes)")
            else:
                logger.warning(f"PDF too large to attach ({file_size} bytes), using download link only")
        except Exception as e:
            logger.warning(f"Could not attach PDF to email: {e}")

    # Send email
    try:
        email.send(fail_silently=False)
        logger.info(f"Invoice paid email sent successfully to {recipient_email} for invoice {invoice.number}")

        # Mark email as sent (idempotency)
        invoice.meta["email_sent"] = True
        invoice.meta["email_sent_at"] = timezone.now().isoformat()
        invoice.meta["email_sent_to"] = recipient_email
        invoice.save(update_fields=["meta", "updated_at"])
    except Exception as e:
        logger.error(f"Failed to send invoice paid email for {invoice.number}: {e}", exc_info=True)
        raise  # Re-raise so Celery can retry if configured


# ======================================================================
# Dunning & Auto-billing Tasks
# ======================================================================
@shared_task
def create_renewal_invoices():
    """
    Job 1: Create renewal invoices at period end.
    Runs hourly (safe) to find subscriptions that need renewal.

    - Find subscriptions where now >= current_period_end and cancel_at_period_end == False
    - Create renewal invoice if one doesn't exist
    - Set subscription to past_due with grace period
    """
    import logging
    from decimal import Decimal

    from .models import BusinessSubscription, Invoice, InvoiceItem

    logger = logging.getLogger(__name__)
    now = timezone.now()

    # Find subscriptions due for renewal
    subscriptions_due = BusinessSubscription.objects.filter(
        status__in=[
            BusinessSubscription.Status.ACTIVE,
            BusinessSubscription.Status.TRIALING,
            BusinessSubscription.Status.TRIAL,
        ],
        current_period_end__lte=now,
        cancel_at_period_end=False,
    ).select_related("business", "plan")

    stats = {"checked": 0, "invoices_created": 0, "errors": 0}

    for sub in subscriptions_due:
        stats["checked"] += 1

        try:
            # Check if renewal invoice already exists for this period
            existing_invoice = Invoice.objects.filter(
                subscription=sub,
                status__in=[Invoice.Status.DRAFT, Invoice.Status.ISSUED],
                billing_period_start=sub.current_period_end.date(),
            ).first()

            if existing_invoice:
                logger.info(f"Renewal invoice already exists for subscription {sub.id}")
                continue

            # Create renewal invoice
            next_period_start = sub.current_period_end
            if sub.plan.interval == sub.plan.Interval.MONTH:
                next_period_end = next_period_start + timedelta(days=30)
            else:
                next_period_end = next_period_start + timedelta(days=365)

            invoice = Invoice.objects.create(
                business=sub.business,
                subscription=sub,
                status=Invoice.Status.DRAFT,
                due_date=(now + timedelta(days=2)).date(),  # 2-day grace
                billing_period_start=next_period_start.date(),
                billing_period_end=next_period_end.date(),
                currency=sub.plan.currency,
                subtotal=sub.plan.amount,
                total=sub.plan.amount,
                next_attempt_at=now,  # Attempt immediately
            )

            # Add invoice item
            InvoiceItem.objects.create(
                invoice=invoice,
                description=f"{sub.plan.name} subscription renewal",
                qty=Decimal("1"),
                unit="month" if sub.plan.interval == sub.plan.Interval.MONTH else "year",
                unit_price=sub.plan.amount,
            )

            # Update subscription to past_due with grace period
            grace_until = now + timedelta(days=2)
            sub.status = BusinessSubscription.Status.PAST_DUE
            sub.past_due_since = now
            sub.grace_until = grace_until
            sub.save(update_fields=["status", "past_due_since", "grace_until", "updated_at"])

            stats["invoices_created"] += 1
            logger.info(
                f"Created renewal invoice {invoice.number} for subscription {sub.id}, set to past_due with grace until {grace_until}"
            )

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error creating renewal invoice for subscription {sub.id}: {e}", exc_info=True)

    logger.info(f"Renewal invoice creation complete: {stats}")
    return stats


@shared_task
def process_dunning_attempts():
    """
    Job 2: Process dunning attempts (3x/day for 2 days = 6 total attempts).
    Runs hourly but enforces spacing (8 hours between attempts).

    - Select unpaid invoices with attempt_count < 6 and next_attempt_at <= now
    - Attempt billing (create PayChangu checkout or push if available)
    - Record BillingAttempt
    - On success: mark paid, extend subscription period
    - On failure: increment attempt_count, set next_attempt_at = now + 8 hours
    """
    import logging
    from decimal import Decimal

    from . import paychangu_service
    from .models import BillingAttempt, BusinessSubscription, Invoice, PaymentTransaction

    logger = logging.getLogger(__name__)
    now = timezone.now()

    # Find invoices ready for dunning retry
    invoices_to_retry = Invoice.objects.filter(
        status__in=[Invoice.Status.DRAFT, Invoice.Status.ISSUED],
        attempt_count__lt=6,
        next_attempt_at__lte=now,
        subscription__isnull=False,
        subscription__status=BusinessSubscription.Status.PAST_DUE,
        subscription__grace_until__gte=now,  # Still within grace
        locked_for_dunning=False,
    ).select_related("business", "subscription", "subscription__plan")

    stats = {"checked": 0, "succeeded": 0, "failed": 0, "skipped": 0, "errors": 0}

    for invoice in invoices_to_retry:
        stats["checked"] += 1

        try:
            # Lock invoice to prevent concurrent processing
            Invoice.objects.filter(pk=invoice.pk, locked_for_dunning=False).update(locked_for_dunning=True)

            # Re-fetch to ensure we have the lock
            invoice.refresh_from_db()
            if not invoice.locked_for_dunning:
                stats["skipped"] += 1
                continue

            sub = invoice.subscription
            attempt_no = invoice.attempt_count + 1

            # Create BillingAttempt record
            billing_attempt = BillingAttempt.objects.create(
                invoice=invoice,
                subscription=sub,
                attempt_no=attempt_no,
                status=BillingAttempt.Status.INITIATED,
                meta={
                    "amount": str(invoice.total),
                    "currency": invoice.currency,
                    "billing_phone": sub.billing_phone or "",
                },
            )

            # Check if PayChangu is configured
            if not paychangu_service.is_paychangu_configured():
                logger.warning(f"PayChangu not configured, skipping dunning attempt for invoice {invoice.number}")
                billing_attempt.mark_failed("PayChangu not configured", save=True)
                invoice.attempt_count = attempt_no
                invoice.next_attempt_at = now + timedelta(hours=8)
                invoice.locked_for_dunning = False
                invoice.save(update_fields=["attempt_count", "next_attempt_at", "locked_for_dunning", "updated_at"])
                stats["skipped"] += 1
                continue

            # Generate transaction reference
            tx_ref = f"renewal-{invoice.id}-{attempt_no}-{now.timestamp():.0f}"

            # Attempt to create PayChangu checkout session
            # (In production, if PayChangu supports push/collect API, use that instead)
            try:
                from django.conf import settings
                from django.urls import reverse

                # Get domain from settings, fallback to a sensible default
                domain = getattr(settings, "SITE_DOMAIN", None)
                if not domain:
                    # Try to get from django.contrib.sites if installed
                    try:
                        if "django.contrib.sites" in getattr(settings, "INSTALLED_APPS", []):
                            from django.contrib.sites.models import Site
                            domain = Site.objects.get_current().domain
                    except Exception:
                        pass
                if not domain:
                    domain = "localhost"
                
                callback_url = f"https://{domain}{reverse('billing:paychangu_webhook')}"
                return_url = f"https://{domain}/billing/manage/"

                result = paychangu_service.create_checkout(
                    business=sub.business,
                    location=None,
                    amount=invoice.total,
                    currency=invoice.currency,
                    tx_ref=tx_ref,
                    return_url=return_url,
                    callback_url=callback_url,
                    meta={
                        "invoice_id": str(invoice.id),
                        "subscription_id": str(sub.id),
                        "attempt_no": attempt_no,
                    },
                    user_email=sub.business.email if hasattr(sub.business, "email") else "",
                    user_phone=sub.billing_phone or "",
                    description=f"Subscription renewal - {sub.plan.name}",
                )

                if result.get("status") == "success":
                    checkout_url = result.get("checkout_url", "")
                    billing_attempt.payment_session_id = checkout_url
                    billing_attempt.provider_ref = tx_ref
                    billing_attempt.save(update_fields=["payment_session_id", "provider_ref", "updated_at"])

                    # Create PaymentTransaction record
                    PaymentTransaction.objects.create(
                        business=sub.business,
                        provider="paychangu",
                        tx_ref=tx_ref,
                        amount=invoice.total,
                        currency=invoice.currency,
                        status=PaymentTransaction.Status.PENDING,
                        meta={
                            "invoice_id": str(invoice.id),
                            "subscription_id": str(sub.id),
                            "dunning_attempt": attempt_no,
                        },
                    )

                    # Send email notification with payment link
                    # (In production, use your email service)
                    logger.info(f"Dunning attempt #{attempt_no} initiated for invoice {invoice.number}: {checkout_url}")

                    # TODO: Send email with checkout_url to sub.billing_phone or business email

                    # Mark attempt as initiated (will be marked succeeded when webhook arrives)
                    invoice.attempt_count = attempt_no
                    invoice.next_attempt_at = now + timedelta(hours=8)  # Next retry in 8 hours
                    invoice.locked_for_dunning = False
                    invoice.save(update_fields=["attempt_count", "next_attempt_at", "locked_for_dunning", "updated_at"])

                    stats["succeeded"] += 1
                else:
                    # PayChangu API failed
                    error_msg = result.get("message", "Unknown error")
                    billing_attempt.mark_failed(error_msg, save=True)

                    invoice.attempt_count = attempt_no
                    invoice.next_attempt_at = now + timedelta(hours=8)
                    invoice.locked_for_dunning = False
                    invoice.save(update_fields=["attempt_count", "next_attempt_at", "locked_for_dunning", "updated_at"])

                    stats["failed"] += 1
                    logger.error(f"Dunning attempt #{attempt_no} failed for invoice {invoice.number}: {error_msg}")

            except Exception as e:
                billing_attempt.mark_failed(str(e), save=True)
                invoice.attempt_count = attempt_no
                invoice.next_attempt_at = now + timedelta(hours=8)
                invoice.locked_for_dunning = False
                invoice.save(update_fields=["attempt_count", "next_attempt_at", "locked_for_dunning", "updated_at"])
                stats["errors"] += 1
                logger.error(f"Error during dunning attempt for invoice {invoice.number}: {e}", exc_info=True)

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error processing dunning for invoice {invoice.id}: {e}", exc_info=True)

    logger.info(f"Dunning processing complete: {stats}")
    return stats


@shared_task
def suspend_expired_grace_periods():
    """
    Job 3: Suspend subscriptions after grace period expires.
    Runs hourly to find subscriptions with status=past_due and now > grace_until.
    """
    import logging

    from .models import BusinessSubscription
    from .services import notify_hq

    logger = logging.getLogger(__name__)
    now = timezone.now()

    # Find subscriptions with expired grace periods
    subscriptions_to_suspend = BusinessSubscription.objects.filter(
        status=BusinessSubscription.Status.PAST_DUE,
        grace_until__lt=now,
    ).select_related("business")

    stats = {"checked": 0, "suspended": 0, "errors": 0}

    for sub in subscriptions_to_suspend:
        stats["checked"] += 1

        try:
            sub.status = BusinessSubscription.Status.SUSPENDED
            sub.suspended_at = now
            sub.save(update_fields=["status", "suspended_at", "updated_at"])

            stats["suspended"] += 1
            logger.warning(
                f"Subscription {sub.id} (business={sub.business.id}) suspended after grace period expired (was due since {sub.past_due_since})"
            )

            # Notify HQ of suspension (idempotent)
            try:
                notify_hq.notify_subscription_suspended(sub)
            except Exception as e:
                logger.error(f"Failed to send HQ suspension notification for {sub.id}: {e}")

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error suspending subscription {sub.id}: {e}", exc_info=True)

    logger.info(f"Grace period suspension complete: {stats}")
    return stats


@shared_task
def process_cancellations():
    """
    Job 4: Process cancellations at period end.
    Runs hourly to find subscriptions with cancel_at_period_end=True and now >= current_period_end.
    """
    import logging

    from .models import BusinessSubscription
    from .services import notify_hq

    logger = logging.getLogger(__name__)
    now = timezone.now()

    # Find subscriptions ready to be canceled
    subscriptions_to_cancel = BusinessSubscription.objects.filter(
        cancel_at_period_end=True,
        current_period_end__lte=now,
        status__in=[
            BusinessSubscription.Status.ACTIVE,
            BusinessSubscription.Status.TRIALING,
            BusinessSubscription.Status.TRIAL,
            BusinessSubscription.Status.PAST_DUE,
        ],
    ).select_related("business")

    stats = {"checked": 0, "canceled": 0, "errors": 0}

    for sub in subscriptions_to_cancel:
        stats["checked"] += 1

        try:
            sub.status = BusinessSubscription.Status.CANCELED
            if not sub.canceled_at:
                sub.canceled_at = now
            sub.save(update_fields=["status", "canceled_at", "updated_at"])

            stats["canceled"] += 1
            logger.info(
                f"Subscription {sub.id} (business={sub.business.id}) canceled at period end (period ended {sub.current_period_end})"
            )

            # Notify HQ of effective cancellation (idempotent)
            try:
                notify_hq.notify_cancellation_effective(sub)
            except Exception as e:
                logger.error(f"Failed to send HQ cancellation notification for {sub.id}: {e}")

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error canceling subscription {sub.id}: {e}", exc_info=True)

    logger.info(f"Cancellation processing complete: {stats}")
    return stats
