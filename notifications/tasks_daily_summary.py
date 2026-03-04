# notifications/tasks_daily_summary.py
"""
Celery task: send the vertical-aware daily summary email for every business
whose DailySummarySettings has is_enabled=True and whose configured send_hour
matches the current hour in the business's timezone.

Safeguards
----------
1. Skip if no active recipients configured.
2. Skip if already sent today (last_sent_date == today, per-business timezone).
3. Only fire during the configured send_hour (±0 minutes tolerance; the Beat
   schedule runs every hour, so we fire once in the correct hour).
4. Each business is processed independently; one failure does not block others.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pytz
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

logger = logging.getLogger(__name__)

# Imported at module level so tests can patch them cleanly.
# We defer the actual DB/ORM access to runtime (inside task functions).
from notifications.models import BusinessEmailRecipient, DailySummarySettings  # noqa: E402
from notifications.daily_summary.registry import get_provider  # noqa: E402


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_daily_summaries(self):
    """
    Master task: iterate every enabled business and fire per-business subtasks.
    Scheduled hourly via Celery Beat; each business decides for itself whether
    its configured send_hour has arrived.
    """
    now_utc = timezone.now()

    settings_qs = DailySummarySettings.objects.filter(  # type: ignore[attr-defined]
        is_enabled=True,
    ).select_related("business")

    dispatched = 0
    skipped = 0

    for ds in settings_qs:
        try:
            _maybe_send_for_business(ds, now_utc)
            dispatched += 1
        except Exception as exc:
            logger.error(
                "[DailySummary] Unhandled error for business %s: %s",
                ds.business_id,
                exc,
                exc_info=True,
            )
            skipped += 1

    logger.info(
        "[DailySummary] Cycle complete: %d dispatched, %d skipped/errored.",
        dispatched,
        skipped,
    )
    return {"dispatched": dispatched, "skipped": skipped}


def _maybe_send_for_business(ds: Any, now_utc: Any) -> None:
    """
    Decide whether to send for this business right now.

    Steps:
    1. Convert now_utc to the business timezone.
    2. Check current hour == ds.send_hour.
    3. Check last_sent_date != today (in business tz).
    4. Get active recipients — skip if none.
    5. Compute metrics via provider.
    6. Send email to all recipients.
    7. Update last_sent_date.
    """
    business = ds.business

    # 1. Local time for this business
    try:
        biz_tz = pytz.timezone(ds.timezone)
    except Exception:
        biz_tz = pytz.timezone("Africa/Blantyre")

    now_local = now_utc.astimezone(biz_tz)
    today_local: date = now_local.date()

    # 2. Hour gate — only run in the configured send_hour
    if now_local.hour != ds.send_hour:
        return

    # 3. Idempotency gate — already sent today?
    if ds.last_sent_date == today_local:
        logger.debug(
            "[DailySummary] %s already sent for %s, skipping.",
            business.name,
            today_local,
        )
        return

    # 4. Recipients gate
    recipients_qs = BusinessEmailRecipient.objects.filter(
        business=business,
        is_active=True,
    ).values_list("email", "name")

    recipient_list = [(email, name) for email, name in recipients_qs]
    if not recipient_list:
        logger.info(
            "[DailySummary] %s has no active recipients, skipping.", business.name
        )
        return

    # 5. Compute metrics
    provider = get_provider(business)
    report_date = today_local  # report on today's data
    metrics = provider.get_metrics(business, report_date)

    # 6. Render & send
    html_body, text_body = provider.render_email(business, metrics, report_date)
    subject = f"[{business.name}] Daily Summary — {report_date.strftime('%Y-%m-%d')}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")

    email_addresses = [email for email, _ in recipient_list]

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=email_addresses,
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        msg.send(fail_silently=False)
        logger.info(
            "[DailySummary] Sent '%s' to %d recipient(s) for %s.",
            subject,
            len(email_addresses),
            business.name,
        )
    except Exception as exc:
        logger.error(
            "[DailySummary] Failed to send email for %s: %s",
            business.name,
            exc,
            exc_info=True,
        )
        raise

    # 7. Record last_sent_date to prevent duplicates
    ds.last_sent_date = today_local
    ds.save(update_fields=["last_sent_date"])
