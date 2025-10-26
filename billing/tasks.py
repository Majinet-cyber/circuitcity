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
    start = now + timedelta(hours=12)   # pick a window ~tomorrow
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


