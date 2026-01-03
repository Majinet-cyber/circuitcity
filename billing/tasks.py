# billing/tasks.py
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

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
    except Exception as e:
        logger.error(f"Failed to send invoice paid email for {invoice.number}: {e}", exc_info=True)
        raise  # Re-raise so Celery can retry if configured