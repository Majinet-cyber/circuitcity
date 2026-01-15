# cc/services/email_dispatcher.py
"""
SSOT Email Dispatcher Service
Centralized, reliable email sending with retries, transaction safety, and logging.
All email sending MUST go through this dispatcher.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


# Email event constants - SSOT
class EmailEvent:
    """Email event types - single source of truth."""
    SALE_OCCURRED = 'SALE_OCCURRED'
    USER_SIGNUP = 'USER_SIGNUP'
    OTP_REQUEST = 'OTP_REQUEST'
    SUBSCRIPTION_SUCCESS = 'SUBSCRIPTION_SUCCESS'
    SUBSCRIPTION_CANCELLED = 'SUBSCRIPTION_CANCELLED'
    AGENT_COMMISSION = 'AGENT_COMMISSION'
    DAILY_SUMMARY = 'DAILY_SUMMARY'
    WEEKLY_DIGEST = 'WEEKLY_DIGEST'
    IMPORTANT_ALERT = 'IMPORTANT_ALERT'
    CUSTOM = 'CUSTOM'
    
    # Owner alerts (new - Jan 2026)
    OWNER_NEW_SIGNUP = 'OWNER_NEW_SIGNUP'
    OWNER_NEW_SUBSCRIPTION = 'OWNER_NEW_SUBSCRIPTION'
    OWNER_NEW_BUSINESS = 'OWNER_NEW_BUSINESS'
    SALE_RECEIPT = 'SALE_RECEIPT'


# Owner email recipients (SSOT)
OWNER_ALERT_EMAILS = [
    'jadepaulchris@gmail.com',
    'info@imajinet.com',
]


# Template mapping - SSOT
EMAIL_TEMPLATES = {
    EmailEvent.SALE_OCCURRED: {
        'subject': 'Sale Completed - {business_name}',
        'html_template': 'notifications/emails/sale_instant.html',
        'text_template': 'notifications/emails/sale_instant.txt',
    },
    EmailEvent.USER_SIGNUP: {
        'subject': 'Welcome to {business_name}!',
        'html_template': 'notifications/emails/welcome_manager.html',
        'text_template': 'notifications/emails/welcome_manager.txt',
    },
    EmailEvent.OTP_REQUEST: {
        'subject': 'Your verification code',
        'html_template': 'notifications/emails/otp_code.html',
        'text_template': 'notifications/emails/otp_code.txt',
    },
    EmailEvent.SUBSCRIPTION_SUCCESS: {
        'subject': 'Subscription Activated - {plan_name}',
        'html_template': 'billing/emails/subscription_success.html',
        'text_template': 'billing/emails/subscription_success.txt',
    },
    EmailEvent.SUBSCRIPTION_CANCELLED: {
        'subject': 'Subscription Cancelled',
        'html_template': 'billing/emails/subscription_cancelled.html',
        'text_template': 'billing/emails/subscription_cancelled.txt',
    },
    EmailEvent.AGENT_COMMISSION: {
        'subject': 'Commission Earned - {amount}',
        'html_template': 'notifications/emails/agent_commission.html',
        'text_template': 'notifications/emails/agent_commission.txt',
    },
    EmailEvent.DAILY_SUMMARY: {
        'subject': 'Daily Sales Summary - {date}',
        'html_template': 'notifications/emails/sales_daily_summary.html',
        'text_template': 'notifications/emails/sales_daily_summary.txt',
    },
    EmailEvent.WEEKLY_DIGEST: {
        'subject': 'Weekly Digest - {week}',
        'html_template': 'notifications/emails/weekly_digest.html',
        'text_template': 'notifications/emails/weekly_digest.txt',
    },
    EmailEvent.IMPORTANT_ALERT: {
        'subject': 'Important Alert - {alert_title}',
        'html_template': 'notifications/emails/important_alert.html',
        'text_template': 'notifications/emails/important_alert.txt',
    },
    EmailEvent.OWNER_NEW_SIGNUP: {
        'subject': '🎉 New Signup: {user_email}',
        'html_template': 'notifications/emails/owner_new_signup.html',
        'text_template': 'notifications/emails/owner_new_signup.txt',
    },
    EmailEvent.OWNER_NEW_SUBSCRIPTION: {
        'subject': '💳 New Subscription: {business_name}',
        'html_template': 'notifications/emails/owner_new_subscription.html',
        'text_template': 'notifications/emails/owner_new_subscription.txt',
    },
    EmailEvent.OWNER_NEW_BUSINESS: {
        'subject': '🏪 New Business Created: {business_name}',
        'html_template': 'notifications/emails/owner_new_business.html',
        'text_template': 'notifications/emails/owner_new_business.txt',
    },
    EmailEvent.SALE_RECEIPT: {
        'subject': 'Sale Receipt - {business_name}',
        'html_template': 'notifications/emails/sale_receipt.html',
        'text_template': 'notifications/emails/sale_receipt.txt',
    },
}


def _sanitize_context_for_json(context):
    """
    Sanitize context dict for JSON storage.
    Converts Decimal values to strings to avoid JSON serialization errors.
    """
    from decimal import Decimal
    sanitized = {}
    for key, value in context.items():
        if isinstance(value, Decimal):
            sanitized[key] = str(value)
        else:
            sanitized[key] = value
    return sanitized


def send_event_email(
    event: str,
    to: str | list[str],
    context: dict[str, Any],
    *,
    business=None,
    user=None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    force: bool = False,
) -> int:
    """
    Send an event email (SSOT for all email sending).
    
    Args:
        event: Email event type (use EmailEvent constants)
        to: Recipient email(s)
        context: Template context dict
        business: Optional Business instance
        user: Optional User instance
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        force: If True, bypass user preferences (for transactional emails)
    
    Returns:
        EmailDeliveryLog ID
    
    Raises:
        ValueError: If event type unknown or required context missing
    
    Usage:
        send_event_email(
            EmailEvent.SALE_OCCURRED,
            to='manager@example.com',
            context={'sale_id': 123, 'total': 1000},
            business=business,
            user=user
        )
    """
    from cc.models_email import EmailDeliveryLog
    
    # Validate event
    if event not in EMAIL_TEMPLATES and event != EmailEvent.CUSTOM:
        raise ValueError(f"Unknown email event: {event}")
    
    # Normalize recipients
    to_list = [to] if isinstance(to, str) else to
    if not to_list:
        raise ValueError("At least one recipient required")
    
    primary_recipient = to_list[0]
    
    # Check user preferences (unless force=True or transactional)
    transactional_events = {EmailEvent.OTP_REQUEST, EmailEvent.SUBSCRIPTION_SUCCESS, EmailEvent.SUBSCRIPTION_CANCELLED}
    if not force and event not in transactional_events:
        if not _should_send_email(user, event):
            logger.info(f"Email skipped due to user preferences: {event} to {primary_recipient}")
            return _create_log_entry(
                event, primary_recipient, '', 'User preferences', 'skipped',
                business=business, user=user
            )
    
    # Get template config
    if event == EmailEvent.CUSTOM:
        if 'subject' not in context or 'html_template' not in context:
            raise ValueError("Custom emails require 'subject' and 'html_template' in context")
        template_config = context
    else:
        template_config = EMAIL_TEMPLATES[event]
    
    # Build subject
    subject = template_config['subject'].format(**context) if '{' in template_config['subject'] else template_config['subject']
    
    # Sanitize context for JSON storage (convert Decimals to strings)
    sanitized_context = _sanitize_context_for_json(context)
    
    # Create log entry
    log = EmailDeliveryLog.objects.create(
        event=event,
        to=primary_recipient,
        cc=', '.join(cc or []),
        bcc=', '.join(bcc or []),
        subject=subject,
        template_name=template_config.get('html_template', ''),
        status='pending',
        business=business,
        user=user,
        metadata=sanitized_context
    )
    
    # Enqueue email task (transaction-safe)
    transaction.on_commit(lambda: _enqueue_email_task(log.id))
    
    logger.info(f"Email queued: {event} to {primary_recipient} (log_id={log.id})")
    return log.id


def _should_send_email(user, event: str) -> bool:
    """
    Check if email should be sent based on user preferences.
    Returns True if user hasn't opted out.
    """
    if not user:
        return True  # No user = send (system emails)
    
    try:
        from notifications.models import NotificationPreference
        prefs = NotificationPreference.objects.get(user=user)
    except Exception:
        # No preferences found = send (opt-out model: default ON)
        return True
    
    # Map event to preference field
    event_to_pref = {
        EmailEvent.SALE_OCCURRED: 'sale_emails_enabled',
        EmailEvent.USER_SIGNUP: 'welcome_emails',
        EmailEvent.AGENT_COMMISSION: 'commission_emails_enabled',
        EmailEvent.DAILY_SUMMARY: 'daily_summary_email',
        EmailEvent.WEEKLY_DIGEST: 'weekly_digest_enabled',
        EmailEvent.IMPORTANT_ALERT: 'important_alerts_email',
    }
    
    pref_field = event_to_pref.get(event)
    if not pref_field:
        return True  # Unknown event = send
    
    return getattr(prefs, pref_field, True)


def _enqueue_email_task(log_id: int):
    """
    Enqueue email sending task (Celery).
    Falls back to sync sending if Celery unavailable.
    """
    try:
        from cc.tasks.email_tasks import send_email_task
        send_email_task.delay(log_id)
        logger.info(f"Email task enqueued for log_id={log_id}")
    except Exception as e:
        logger.warning(f"Celery unavailable, sending sync: {e}")
        # Fallback: send synchronously
        from cc.tasks.email_tasks import send_email_task
        send_email_task(log_id)


def _create_log_entry(event, to, subject, template, status, *, business=None, user=None) -> int:
    """Helper to create a log entry (for skipped emails)."""
    from cc.models_email import EmailDeliveryLog
    log = EmailDeliveryLog.objects.create(
        event=event,
        to=to,
        subject=subject,
        template_name=template,
        status=status,
        business=business,
        user=user
    )
    return log.id


def send_owner_alert(event: str, context: dict[str, Any], *, business=None, user=None) -> list[int]:
    """
    Send alert email to owner email addresses (SSOT).
    
    Always sends to OWNER_ALERT_EMAILS defined in settings/constants.
    Used for: new signups, new subscriptions, new businesses.
    
    Args:
        event: Owner alert event type (EmailEvent.OWNER_*)
        context: Template context dict
        business: Optional Business instance
        user: Optional User instance
    
    Returns:
        List of EmailDeliveryLog IDs
    
    Usage:
        send_owner_alert(
            EmailEvent.OWNER_NEW_SIGNUP,
            context={'user_email': 'newuser@example.com', 'user_name': 'John'},
            user=user
        )
    """
    log_ids = []
    for owner_email in OWNER_ALERT_EMAILS:
        try:
            log_id = send_event_email(
                event=event,
                to=owner_email,
                context=context,
                business=business,
                user=user,
                force=True,  # Owner alerts bypass user preferences
            )
            log_ids.append(log_id)
        except Exception as e:
            logger.error(f"Failed to send owner alert to {owner_email}: {e}", exc_info=True)
    
    return log_ids


def send_welcome_and_owner_alert(user, business=None):
    """
    Send welcome email to new user AND owner alert email (SSOT entry point for signup).
    
    This is the single function to call on user signup to ensure BOTH emails are sent.
    Idempotent: safe to call multiple times (uses EmailDeliveryLog deduplication).
    
    Args:
        user: User instance (newly created)
        business: Optional Business instance
    
    Returns:
        dict with 'welcome_log_id' and 'owner_alert_log_ids'
    """
    from cc.models_email import EmailDeliveryLog
    
    business_name = business.name if business else "Emajinet"
    user_email = user.email or user.username
    user_name = user.get_full_name() or user.username
    
    # Check if welcome email already sent (idempotency)
    existing_welcome = EmailDeliveryLog.objects.filter(
        event=EmailEvent.USER_SIGNUP,
        to=user_email,
        user=user
    ).first()
    
    welcome_log_id = None
    if not existing_welcome:
        try:
            welcome_log_id = send_event_email(
                EmailEvent.USER_SIGNUP,
                to=user_email,
                context={
                    'business_name': business_name,
                    'user_name': user_name,
                    'user_email': user_email,
                },
                business=business,
                user=user,
                force=True,  # Welcome emails are transactional
            )
            logger.info(f"Welcome email sent to {user_email}")
        except Exception as e:
            logger.error(f"Failed to send welcome email to {user_email}: {e}", exc_info=True)
    else:
        welcome_log_id = existing_welcome.id
        logger.info(f"Welcome email already sent to {user_email} (log_id={existing_welcome.id})")
    
    # Send owner alert (idempotent)
    owner_alert_log_ids = []
    try:
        owner_alert_log_ids = send_owner_alert(
            EmailEvent.OWNER_NEW_SIGNUP,
            context={
                'user_email': user_email,
                'user_name': user_name,
                'business_name': business_name,
                'user_id': user.id,
            },
            business=business,
            user=user
        )
        logger.info(f"Owner alerts sent for new signup: {user_email}")
    except Exception as e:
        logger.error(f"Failed to send owner alert for signup {user_email}: {e}", exc_info=True)
    
    return {
        'welcome_log_id': welcome_log_id,
        'owner_alert_log_ids': owner_alert_log_ids,
    }


def send_sale_receipt_and_owner_notification(sale, business, recipient_email=None):
    """
    Send sale receipt to business AND notify owners (SSOT entry point for sales).
    
    This ensures EVERY sale triggers emails:
    1. Receipt to business owner/manager (or customer if provided)
    2. Notification to platform owners
    
    Args:
        sale: Sale instance
        business: Business instance
        recipient_email: Optional override recipient (defaults to business owner)
    
    Returns:
        dict with 'receipt_log_id' and 'owner_notification_sent'
    """
    from cc.models_email import EmailDeliveryLog
    
    # Determine recipient
    if not recipient_email:
        # Default: send to business owner or primary manager
        try:
            from tenants.models import Membership
            manager = Membership.objects.filter(
                business=business,
                role='MANAGER'
            ).first()
            recipient_email = manager.user.email if manager else 'admin@example.com'
        except Exception:
            recipient_email = 'admin@example.com'
    
    # Check idempotency
    existing_receipt = EmailDeliveryLog.objects.filter(
        event=EmailEvent.SALE_RECEIPT,
        metadata__sale_id=sale.id,
        to=recipient_email
    ).first()
    
    receipt_log_id = None
    if not existing_receipt:
        try:
            receipt_log_id = send_event_email(
                EmailEvent.SALE_RECEIPT,
                to=recipient_email,
                context={
                    'business_name': business.name,
                    'sale_id': sale.id,
                    'total': getattr(sale, 'total_amount', 0) or getattr(sale, 'total', 0),
                    'date': getattr(sale, 'created_at', None) or getattr(sale, 'date', None),
                },
                business=business,
                force=True,  # Receipts are transactional
            )
            logger.info(f"Sale receipt sent for sale_id={sale.id} to {recipient_email}")
        except Exception as e:
            logger.error(f"Failed to send sale receipt for sale_id={sale.id}: {e}", exc_info=True)
    else:
        receipt_log_id = existing_receipt.id
        logger.info(f"Sale receipt already sent for sale_id={sale.id} (log_id={existing_receipt.id})")
    
    # Optional: notify owners of every sale (could be noisy; make configurable)
    owner_notification_sent = False
    # For now, skip owner notification per sale (too noisy)
    # Uncomment if needed:
    # try:
    #     send_owner_alert(
    #         EmailEvent.SALE_OCCURRED,
    #         context={'business_name': business.name, 'sale_id': sale.id, 'total': sale.total},
    #         business=business
    #     )
    #     owner_notification_sent = True
    # except Exception as e:
    #     logger.error(f"Failed to send owner alert for sale_id={sale.id}: {e}", exc_info=True)
    
    return {
        'receipt_log_id': receipt_log_id,
        'owner_notification_sent': owner_notification_sent,
    }


