# cc/services/email_integration.py
"""
Email Integration Layer - Bridges existing notification system with new EmailDeliveryLog
This provides visibility and audit trail without disrupting existing reliable email system.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction

logger = logging.getLogger(__name__)


def log_email_event(
    event: str,
    to: str,
    subject: str,
    template: str = '',
    *,
    business=None,
    user=None,
    metadata: dict = None,
    status: str = 'sent'
):
    """
    Log email event to EmailDeliveryLog for audit trail.
    Called by existing email system for visibility.
    
    Args:
        event: Email event type
        to: Recipient email
        subject: Email subject
        template: Template name used
        business: Optional Business instance
        user: Optional User instance
        metadata: Optional metadata dict
        status: Email status ('sent', 'failed', etc.)
    """
    try:
        from cc.models_email import EmailDeliveryLog
        
        log = EmailDeliveryLog.objects.create(
            event=_map_legacy_event(event),
            to=to,
            subject=subject,
            template_name=template,
            status=status,
            attempts=1,
            business=business,
            user=user,
            metadata=metadata or {}
        )
        
        if status == 'sent':
            log.mark_sent()
        
        logger.debug(f"Logged email event: {event} to {to} (log_id={log.id})")
        return log.id
        
    except Exception as e:
        logger.warning(f"Failed to log email event: {e}")
        # Never block email sending due to logging failure
        return None


def _map_legacy_event(event_type: str) -> str:
    """Map existing event types to new EmailEvent constants."""
    event_map = {
        'SALE_INSTANT': 'SALE_OCCURRED',
        'SALE_BATCH': 'SALE_OCCURRED',
        'WELCOME_MANAGER': 'USER_SIGNUP',
        'WELCOME_AGENT': 'USER_SIGNUP',
        'OTP_CODE': 'OTP_REQUEST',
        'OTP_RESET': 'OTP_REQUEST',
        'OTP_VERIFY': 'OTP_REQUEST',
        'SUBSCRIPTION_SUCCESS': 'SUBSCRIPTION_SUCCESS',
        'SUBSCRIPTION_CANCELLED': 'SUBSCRIPTION_CANCELLED',
        'AGENT_COMMISSION': 'AGENT_COMMISSION',
        'DAILY_SUMMARY': 'DAILY_SUMMARY',
        'WEEKLY_DIGEST': 'WEEKLY_DIGEST',
        'IMPORTANT_ALERT': 'IMPORTANT_ALERT',
    }
    return event_map.get(event_type, 'CUSTOM')


# Patch notifications/services.py dispatch_event to log emails
def patch_notification_dispatcher():
    """
    Monkey-patch existing dispatch_event to add EmailDeliveryLog tracking.
    Called at Django startup via AppConfig.ready().
    """
    try:
        from notifications import services as notif_services
        
        original_dispatch = notif_services.dispatch_event
        
        def wrapped_dispatch_event(event_id: int):
            """Wrapped dispatcher that logs to EmailDeliveryLog."""
            try:
                from notifications.models import NotificationEvent
                event = NotificationEvent.objects.get(id=event_id)
                
                # Log email BEFORE sending
                log_email_event(
                    event=event.event_type,
                    to=event.recipient_email,
                    subject=event.payload.get('subject', ''),
                    template=str(event.payload.get('html_template', '')),
                    business=event.business,
                    user=event.user,
                    metadata=event.payload,
                    status='pending'
                )
            except Exception as e:
                logger.warning(f"Failed to pre-log email event {event_id}: {e}")
            
            # Call original dispatcher
            result = original_dispatch(event_id)
            
            # Update log status to 'sent' on success
            try:
                from notifications.models import NotificationEvent
                event = NotificationEvent.objects.get(id=event_id)
                if event.status == 'sent':
                    log_email_event(
                        event=event.event_type,
                        to=event.recipient_email,
                        subject=event.payload.get('subject', ''),
                        template=str(event.payload.get('html_template', '')),
                        business=event.business,
                        user=event.user,
                        metadata=event.payload,
                        status='sent'
                    )
            except Exception as e:
                logger.warning(f"Failed to post-log email event {event_id}: {e}")
            
            return result
        
        # Apply patch
        notif_services.dispatch_event = wrapped_dispatch_event
        logger.info("✅ Email dispatcher patched for EmailDeliveryLog tracking")
        
    except Exception as e:
        logger.warning(f"Failed to patch email dispatcher: {e}")

