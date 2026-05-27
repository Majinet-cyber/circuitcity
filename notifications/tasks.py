# notifications/tasks.py
"""
Celery tasks for email notifications.
"""
from __future__ import annotations

import logging

from cc.celery import app as celery_app
from notifications.services import dispatch_event as _dispatch_event

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,),
                 retry_backoff=True, retry_backoff_max=600)
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


@celery_app.task(bind=True, max_retries=5, autoretry_for=(Exception,),
                 retry_backoff=True, retry_backoff_max=600)
def notify_sale_completed(self, sale_id: int):
    """
    Celery task: send email notification after a sale is committed.

    Called via transaction.on_commit() to guarantee atomicity.
    Retries up to 5 times with exponential backoff.

    Args:
        sale_id: PK of the Sale (or PharmacySale) that was completed.
    """
    try:
        from notifications.services import notify_sale_completion
        # Try generic Sale first, then PharmacySale
        sale = None
        try:
            from sales.models import Sale
            sale = Sale.objects.get(pk=sale_id)
        except Exception:
            pass

        if sale is None:
            try:
                from inventory.models_pharmacy import PharmacySale
                sale = PharmacySale.objects.get(pk=sale_id)
            except Exception:
                pass

        if sale is None:
            logger.warning(f"notify_sale_completed: sale_id={sale_id} not found in Sale or PharmacySale")
            return

        notify_sale_completion(sale)
    except Exception as exc:
        logger.error(f"notify_sale_completed failed for sale_id={sale_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=5, autoretry_for=(Exception,),
                 retry_backoff=True, retry_backoff_max=600)
def notify_payment_recorded(self, sale_id: int, sale_type: str = "pharmacy"):
    """
    Celery task: send email notification when a payment is recorded.

    For pharmacy/other verticals where payment is captured at point of sale.
    Uses the same SALE_INSTANT email flow but with payment-specific context.

    Args:
        sale_id: PK of the PharmacySale (or Sale).
        sale_type: 'pharmacy' | 'phones' — determines which model to load.
    """
    try:
        from notifications.services import notify_sale_completion
        sale = None
        if sale_type == "pharmacy":
            try:
                from inventory.models_pharmacy import PharmacySale
                sale = PharmacySale.objects.get(pk=sale_id)
            except Exception:
                pass
        else:
            try:
                from sales.models import Sale
                sale = Sale.objects.get(pk=sale_id)
            except Exception:
                pass

        if sale is None:
            logger.warning(f"notify_payment_recorded: sale_id={sale_id} (type={sale_type}) not found")
            return

        notify_sale_completion(sale)
    except Exception as exc:
        logger.error(f"notify_payment_recorded failed for sale_id={sale_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=5, autoretry_for=(Exception,),
                 retry_backoff=True, retry_backoff_max=600)
def notify_restock_alert(self, product_id: int, business_id: int, alert_type: str = "low_stock"):
    """
    Celery task: send email when a restock alert is triggered.

    alert_type options: 'low_stock' | 'out_of_stock'

    Args:
        product_id: PK of the MerchProduct (or PharmacyBatch).
        business_id: PK of the Business.
        alert_type: Type of restock alert.
    """
    try:
        from notifications.services import notify_restock_alert_email
        notify_restock_alert_email(product_id=product_id, business_id=business_id, alert_type=alert_type)
    except Exception as exc:
        logger.error(
            f"notify_restock_alert failed for product_id={product_id} business_id={business_id}: {exc}",
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


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
