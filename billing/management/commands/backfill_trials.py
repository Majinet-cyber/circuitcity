from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import BusinessSubscription, SubscriptionPlan, TRIAL_DAYS_DEFAULT
from tenants.models import Business


class Command(BaseCommand):
    help = "Ensure every Business has a subscription. Missing ones get a trial on the cheapest active plan."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=TRIAL_DAYS_DEFAULT,
            help=f"Trial length for new subs (default: {TRIAL_DAYS_DEFAULT})",
        )
        parser.add_argument(
            "--reset-existing",
            action="store_true",
            help="If set, re-seed trial anchors for Businesses that already have a subscription in TRIAL without anchors.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        days = int(opts["days"])
        reset_existing = bool(opts["reset_existing"])

        plan = (
            SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
            or SubscriptionPlan.objects.create(code="starter", name="Starter", amount="0.00")
        )

        created = 0
        fixed = 0

        for biz in Business.objects.all().select_related("subscription"):
            if not hasattr(biz, "subscription") or biz.subscription is None:
                BusinessSubscription.ensure_trial_for_business(biz)
                created += 1
                self.stdout.write(self.style.SUCCESS(f"+ trial -> {biz}"))
            elif reset_existing:
                sub = biz.subscription
                if sub.status == BusinessSubscription.Status.TRIAL and (not sub.trial_end or not sub.current_period_end):
                    now = timezone.now()
                    sub.started_at = sub.started_at or now
                    sub.current_period_start = now
                    sub.trial_end = now + timezone.timedelta(days=days)
                    sub.current_period_end = sub.trial_end
                    sub.next_billing_date = sub.trial_end
                    sub.save(update_fields=[
                        "started_at", "current_period_start", "trial_end",
                        "current_period_end", "next_billing_date", "updated_at"
                    ])
                    fixed += 1
                    self.stdout.write(self.style.WARNING(f"* fixed anchors -> {biz}"))

        self.stdout.write(self.style.MIGRATE_HEADING(f"Done. New trials: {created}, fixed: {fixed}"))


