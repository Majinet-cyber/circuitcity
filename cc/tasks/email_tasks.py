# cc/tasks/email_tasks.py
"""
Celery tasks for reliable email sending with retries and error handling.
All email tasks use exponential backoff and logging.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes between retries
    retry_jitter=True,
    name='cc.tasks.send_email_task'
)
def send_email_task(self, log_id: int):
    """
    Send email from EmailDeliveryLog with retries.
    
    Args:
        log_id: EmailDeliveryLog ID
        
    Retries:
        - Max 5 retries
        - Exponential backoff: 2^retry * base (with jitter)
        - Base delay: ~60s, max delay: 10 minutes
    """
    from cc.models_email import EmailDeliveryLog
    
    try:
        log = EmailDeliveryLog.objects.get(id=log_id)
    except EmailDeliveryLog.DoesNotExist:
        logger.error(f"EmailDeliveryLog {log_id} not found, cannot send")
        return
    
    # Increment attempts
    log.increment_attempts()
    
    try:
        # Get template paths from metadata or template_name
        html_template = log.metadata.get('html_template', log.template_name)
        text_template = log.metadata.get('text_template', '')
        
        # Render email content
        context = log.metadata.copy()
        context.update({
            'business': log.business,
            'user': log.user,
            'SITE_URL': getattr(settings, 'SITE_URL', 'https://emajinet.africa'),
        })
        
        html_content = None
        if html_template:
            try:
                html_content = render_to_string(html_template, context)
            except Exception as e:
                logger.warning(f"Failed to render HTML template {html_template}: {e}")
        
        # Text fallback
        if text_template:
            try:
                text_content = render_to_string(text_template, context)
            except Exception:
                text_content = strip_tags(html_content) if html_content else log.subject
        else:
            text_content = strip_tags(html_content) if html_content else log.subject
        
        # Build recipient lists
        to_list = [log.to]
        cc_list = [e.strip() for e in log.cc.split(',') if e.strip()] if log.cc else []
        bcc_list = [e.strip() for e in log.bcc.split(',') if e.strip()] if log.bcc else []
        
        # Send email
        email = EmailMultiAlternatives(
            subject=log.subject,
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@emajinet.africa'),
            to=to_list,
            cc=cc_list,
            bcc=bcc_list,
        )
        
        if html_content:
            email.attach_alternative(html_content, "text/html")
        
        email.send(fail_silently=False)
        
        # Mark as sent
        log.mark_sent()
        logger.info(
            f"✅ Email sent successfully: {log.event} to {log.to} "
            f"(log_id={log_id}, attempts={log.attempts})"
        )
        
    except Exception as exc:
        error_msg = str(exc)
        log.mark_failed(error_msg)
        
        logger.error(
            f"❌ Email send failed: {log.event} to {log.to} "
            f"(log_id={log_id}, attempt={log.attempts}/{self.max_retries + 1}): {error_msg}",
            exc_info=True
        )
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        else:
            logger.critical(
                f"🚨 Email delivery EXHAUSTED retries: {log.event} to {log.to} "
                f"(log_id={log_id}, attempts={log.attempts}). Manual intervention required."
            )
            # Final failure - mark as failed (already done above)


@shared_task(name='cc.tasks.cleanup_old_email_logs')
def cleanup_old_email_logs(days: int = 90):
    """
    Cleanup old email delivery logs (keep last 90 days by default).
    Run via Celery Beat schedule.
    """
    from datetime import timedelta
    from django.utils import timezone
    from cc.models_email import EmailDeliveryLog
    
    cutoff_date = timezone.now() - timedelta(days=days)
    deleted_count, _ = EmailDeliveryLog.objects.filter(
        created_at__lt=cutoff_date,
        status='sent'  # Only delete successfully sent emails
    ).delete()
    
    logger.info(f"Cleaned up {deleted_count} old email delivery logs (older than {days} days)")
    return deleted_count


@shared_task(name='cc.tasks.retry_failed_emails')
def retry_failed_emails(max_age_hours: int = 24):
    """
    Retry recently failed emails (last 24 hours by default).
    Run via Celery Beat schedule.
    """
    from datetime import timedelta
    from django.utils import timezone
    from cc.models_email import EmailDeliveryLog
    
    cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
    failed_logs = EmailDeliveryLog.objects.filter(
        status='failed',
        created_at__gte=cutoff_time,
        attempts__lt=5  # Don't retry if already hit max attempts
    )
    
    retry_count = 0
    for log in failed_logs:
        # Reset status to pending and re-enqueue
        log.status = 'pending'
        log.save(update_fields=['status'])
        send_email_task.delay(log.id)
        retry_count += 1
    
    logger.info(f"Re-queued {retry_count} failed emails for retry")
    return retry_count

