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
}


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
        metadata=context
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

