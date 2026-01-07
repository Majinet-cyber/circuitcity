# notifications/tasks.py
"""
Celery tasks for email notifications.
"""
from __future__ import annotations

from cc.celery import app as celery_app
from notifications.services import dispatch_event as _dispatch_event


@celery_app.task(bind=True, max_retries=3)
def dispatch_email_event(self, event_id: int):
    """
    Celery task to dispatch an email notification event.

    Args:
        event_id: ID of NotificationEvent to process
    """
    try:
        _dispatch_event(event_id)
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task
def send_daily_sales_summary():
    """
    Celery task to send yesterday's sales summary emails.
    Should be scheduled daily at 01:00 Africa/Blantyre via Celery Beat.
    """
    from notifications.management.commands.send_yesterday_sales_summary import Command

    command = Command()
    command.handle()


@celery_app.task
def send_weekly_sales_digest():
    """
    Celery task to send weekly sales digest emails to managers.
    Should be scheduled every Friday at 17:00 Africa/Blantyre (15:00 UTC) via Celery Beat.

    Note: Malawi is UTC+2, so 17:00 Malawi = 15:00 UTC
    """
    from notifications.services import send_weekly_sales_digest as send_digest

    return send_digest()
