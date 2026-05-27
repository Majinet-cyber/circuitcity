# billing/management/commands/process_subscriptions.py
"""
Django management command to process subscription renewals and status transitions.

Usage:
    python manage.py process_subscriptions
    python manage.py process_subscriptions --dry-run

This should be run daily via cron or Celery beat.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import domain


class Command(BaseCommand):
    help = "Process subscription renewals and status transitions (run daily)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate processing without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE — No changes will be made"))

        self.stdout.write(self.style.SUCCESS(f"Starting subscription processing at {timezone.now()}"))

        if dry_run:
            # In dry run, just count what would happen
            from billing.models import BusinessSubscription

            now = timezone.now()

            trial_expired = BusinessSubscription.objects.filter(
                status__in=[
                    BusinessSubscription.Status.TRIAL,
                    BusinessSubscription.Status.TRIALING,
                ],
                trial_end__lt=now,
            ).count()

            period_expired = BusinessSubscription.objects.filter(
                status=BusinessSubscription.Status.ACTIVE,
                current_period_end__lt=now,
            ).count()

            # For past_due → suspended, we need to check grace period
            from datetime import timedelta

            from django.conf import settings

            grace_days = getattr(settings, "BILLING_GRACE_DAYS", 7)

            past_due_subs = BusinessSubscription.objects.filter(status=BusinessSubscription.Status.PAST_DUE)

            grace_expired_count = 0
            for sub in past_due_subs:
                grace_anchor = sub.next_billing_date or sub.current_period_end or sub.trial_end
                if grace_anchor:
                    grace_deadline = grace_anchor + timedelta(days=grace_days)
                    if now >= grace_deadline:
                        grace_expired_count += 1

            self.stdout.write(
                self.style.WARNING(
                    f"Would process:\n"
                    f"  - {trial_expired} trial expiries\n"
                    f"  - {period_expired} period expiries\n"
                    f"  - {grace_expired_count} grace period expiries (suspend)\n"
                )
            )

            return

        # Real processing
        stats = domain.process_subscription_renewals()

        self.stdout.write(
            self.style.SUCCESS(
                f"Subscription processing complete:\n"
                f"  - {stats['total_checked']} subscriptions checked\n"
                f"  - {stats['expired_trials']} trials expired\n"
                f"  - {stats['expired_periods']} periods expired\n"
                f"  - {stats['suspended']} subscriptions suspended\n"
                f"  - {stats['errors']} errors\n"
            )
        )

        if stats["errors"] > 0:
            self.stdout.write(self.style.ERROR(f"⚠️  {stats['errors']} errors occurred. Check logs for details."))
