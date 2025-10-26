# billing/migrations/0002_backfill_trials.py
from __future__ import annotations
from decimal import Decimal

from django.db import migrations

def backfill_trials(apps, schema_editor):
    SubscriptionPlan = apps.get_model("billing", "SubscriptionPlan")
    BusinessSubscription = apps.get_model("billing", "BusinessSubscription")
    Business = apps.get_model("tenants", "Business")

    # Get a plan (cheapest active; or create a free starter if none)
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
    if not plan:
        plan = SubscriptionPlan.objects.create(
            code="starter", name="Starter", amount=Decimal("0.00"), is_active=True
        )

    # For each Business, ensure a subscription exists (trial)
    for biz in Business.objects.all():
        if not BusinessSubscription.objects.filter(business=biz).exists():
            # Use the model method from current code path (works in migration with apps model)
            sub = BusinessSubscription.objects.create(
                business=biz,
                plan=plan,
                status="trial",
            )
            # Minimal anchors – the post_save signal will fill trial periods if needed
            # If signals aren’t connected in migration, set sane defaults:
            from datetime import timedelta
            from django.utils import timezone
            now = timezone.now()
            trial_end = now + timedelta(days=30)
            sub.started_at = now
            sub.trial_end = trial_end
            sub.current_period_start = now
            sub.current_period_end = trial_end
            sub.next_billing_date = trial_end
            sub.save()

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),   # <— update if your last billing migration has a different number
        ("tenants", "0001_initial"),   # <— update if needed
    ]

    operations = [
        migrations.RunPython(backfill_trials, reverse_code=noop),
    ]
